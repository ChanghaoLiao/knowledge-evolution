#!/usr/bin/env python3
"""Build a deterministic, read-only inventory for every registered source."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from _import_common import (
    artifact_sha256,
    included_by_source,
    is_ignored,
    is_sensitive,
    load_checkpoint,
    load_job,
    record_event,
    matches_patterns,
    set_stage,
    sha256_file,
    stable_id,
    utc_now,
    write_jsonl,
)


TEXT_EXTENSIONS = {
    ".adoc",
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".kts",
    ".lua",
    ".md",
    ".mdx",
    ".m",
    ".mm",
    ".org",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".rst",
    ".sh",
    ".sql",
    ".swift",
    ".tex",
    ".text",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
}
STRUCTURED_TEXT_EXTENSIONS = {".csv", ".json", ".jsonl", ".tsv"}


def extractor_for(path: Path) -> str:
    suffix = path.suffix.casefold()
    if suffix in TEXT_EXTENSIONS:
        return "text"
    if suffix in STRUCTURED_TEXT_EXTENSIONS:
        return "structured-text"
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix == ".docx":
        return "docx"
    if suffix == ".pdf":
        return "pdf"
    if suffix == ".ipynb":
        return "ipynb"
    return "unsupported"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory all registered source roots without modifying them. Sensitive, "
            "ignored, and excluded paths are omitted before content hashing."
        )
    )
    parser.add_argument("--job-dir", type=Path, required=True)
    parser.add_argument("--max-files", type=int, default=100_000)
    parser.add_argument("--max-hash-bytes", type=int, default=100 * 1024 * 1024)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Rebuild after later stages; downstream artifacts become stale by digest",
    )
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args()


def build_manifest(job: dict[str, Any], max_files: int, max_hash_bytes: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    excluded_sensitive = 0
    excluded_scope = 0
    ignored = 0
    skipped_symlinks = 0
    read_errors = 0
    truncated = False

    for source in job["sources"]:
        root = Path(source["root"])
        for current, dirs, files in os.walk(root, followlinks=False):
            current_path = Path(current)
            kept_dirs: list[str] = []
            for dirname in dirs:
                candidate = current_path / dirname
                relative = candidate.relative_to(root)
                if is_ignored(relative) or matches_patterns(relative, source.get("exclude") or []):
                    ignored += 1
                    continue
                if candidate.is_symlink():
                    skipped_symlinks += 1
                    continue
                kept_dirs.append(dirname)
            dirs[:] = sorted(kept_dirs, key=str.casefold)

            for filename in sorted(files, key=str.casefold):
                if len(records) >= max_files:
                    truncated = True
                    break
                path = current_path / filename
                relative = path.relative_to(root)
                if is_ignored(relative):
                    ignored += 1
                    continue
                if not included_by_source(relative, source):
                    excluded_scope += 1
                    continue
                if path.is_symlink():
                    skipped_symlinks += 1
                    continue
                if is_sensitive(relative):
                    excluded_sensitive += 1
                    continue
                try:
                    stat = path.stat()
                    extractor = extractor_for(path)
                    content_hash = sha256_file(path) if stat.st_size <= max_hash_bytes else None
                    record = {
                        "schema_version": 1,
                        "file_id": stable_id("file", source["id"], relative.as_posix()),
                        "source_id": source["id"],
                        "source_mode": source["mode"],
                        "relative_path": relative.as_posix(),
                        "extension": path.suffix.casefold(),
                        "media_type": mimetypes.guess_type(path.name)[0],
                        "extractor": extractor,
                        "size": stat.st_size,
                        "mtime_ns": stat.st_mtime_ns,
                        "sha256": content_hash,
                        "hash_skipped_due_to_size": content_hash is None,
                        "observed_at": utc_now(),
                    }
                    records.append(record)
                    counts[extractor] += 1
                    source_counts[source["id"]] += 1
                except OSError:
                    read_errors += 1
            if truncated:
                break
        if truncated:
            break

    records.sort(key=lambda item: (item["source_id"].casefold(), item["relative_path"].casefold()))
    summary = {
        "files": len(records),
        "by_extractor": dict(counts),
        "by_source": dict(source_counts),
        "sensitive_files_excluded": excluded_sensitive,
        "scope_excluded": excluded_scope,
        "ignored_items": ignored,
        "skipped_symlinks": skipped_symlinks,
        "read_errors": read_errors,
        "truncated": truncated,
        "max_files": max_files,
        "max_hash_bytes": max_hash_bytes,
    }
    return records, summary


def main() -> int:
    args = parse_args()
    try:
        if args.max_files < 1 or args.max_hash_bytes < 1:
            raise ValueError("limits must be positive")
        job_dir = args.job_dir.expanduser().resolve()
        job = load_job(job_dir)
        checkpoint = load_checkpoint(job_dir)
        if checkpoint.get("stage") not in {"registered", "inventoried"} and not args.refresh:
            raise ValueError(
                f"job is at stage {checkpoint.get('stage')}; pass --refresh to rebuild the manifest"
            )
        records, summary = build_manifest(job, args.max_files, args.max_hash_bytes)
        manifest_path = job_dir / "source-manifest.jsonl"
        write_jsonl(manifest_path, records)
        manifest_hash = artifact_sha256(manifest_path)
        set_stage(
            job_dir,
            "inventoried",
            artifact_updates={
                "source_manifest": "source-manifest.jsonl",
                "source_manifest_sha256": manifest_hash,
                "downstream_stale": bool(args.refresh),
            },
            summary_updates={"inventory": summary},
        )
        record_event(job_dir, "source-manifest-built", {"sha256": manifest_hash, **summary})
        result = {
            "job_id": job["job_id"],
            "stage": "inventoried",
            "manifest": str(manifest_path),
            "manifest_sha256": manifest_hash,
            "sources_modified": False,
            "summary": summary,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
