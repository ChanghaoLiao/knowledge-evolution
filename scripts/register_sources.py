#!/usr/bin/env python3
"""Register approved Import/Adopt roots without scanning their contents."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from _import_common import SCHEMA_VERSION, record_event, utc_now, write_json


SOURCE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create an isolated Import/Adopt job from a reviewed JSON configuration. "
            "This command validates paths but does not scan source contents."
        )
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--job-dir", type=Path, required=True)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args()


def paths_overlap(left: Path, right: Path) -> bool:
    try:
        left.relative_to(right)
        return True
    except ValueError:
        pass
    try:
        right.relative_to(left)
        return True
    except ValueError:
        return False


def validate_config(config: dict[str, Any], job_dir: Path) -> dict[str, Any]:
    sources = config.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("config.sources must be a non-empty array")

    target_raw = config.get("target_root")
    if not isinstance(target_raw, str) or not target_raw.strip():
        raise ValueError("config.target_root must be a non-empty string")
    target = Path(target_raw).expanduser().resolve()
    job_dir = job_dir.expanduser().resolve()
    if paths_overlap(target, job_dir):
        raise ValueError("job directory must not overlap target_root")

    batch_config = config.get("batch") or {}
    retention_config = config.get("retention") or {}
    if not isinstance(batch_config, dict):
        raise ValueError("config.batch must be an object")
    if not isinstance(retention_config, dict):
        raise ValueError("config.retention must be an object")

    normalized_sources: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("every source must be a JSON object")
        source_id = str(source.get("id", ""))
        if not SOURCE_ID_PATTERN.fullmatch(source_id):
            raise ValueError(f"invalid source id: {source_id!r}")
        if source_id in seen_ids:
            raise ValueError(f"duplicate source id: {source_id}")
        seen_ids.add(source_id)

        mode = source.get("mode")
        if mode not in {"import", "adopt"}:
            raise ValueError(f"source {source_id} mode must be import or adopt")
        root = Path(str(source.get("root", ""))).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"source root is not a directory: {root}")
        if paths_overlap(root, job_dir):
            raise ValueError(f"job directory must not overlap source {source_id}: {root}")
        if mode == "adopt" and root != target:
            raise ValueError(
                f"adopt source {source_id} must equal target_root; use import for external sources"
            )
        if mode == "import" and paths_overlap(root, target):
            raise ValueError(
                f"import source {source_id} must not overlap target_root: {root}"
            )

        include = source.get("include") or ["*", "**/*"]
        exclude = source.get("exclude") or []
        if not all(isinstance(value, str) for value in include + exclude):
            raise ValueError(f"source {source_id} include/exclude entries must be strings")
        normalized_sources.append(
            {
                "id": source_id,
                "root": str(root),
                "mode": mode,
                "writable": False,
                "include": include,
                "exclude": exclude,
                "label": source.get("label") or source_id,
            }
        )

    for index, left in enumerate(normalized_sources):
        for right in normalized_sources[index + 1 :]:
            if paths_overlap(Path(left["root"]), Path(right["root"])):
                raise ValueError(
                    f"source roots must not overlap: {left['id']} and {right['id']}"
                )

    max_files = int(batch_config.get("max_files", 25))
    max_characters = int(batch_config.get("max_characters", 120_000))
    if min(max_files, max_characters) < 1:
        raise ValueError("batch limits must be positive")

    job_id = str(config.get("job_id") or f"import-{utc_now()[:10].replace('-', '')}")
    return {
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "created_at": utc_now(),
        "target_root": str(target),
        "target_exists_at_registration": target.is_dir(),
        "target_write_policy": "proposal-approved",
        "sources": normalized_sources,
        "batch": {
            "max_files": max_files,
            "max_characters": max_characters,
        },
        "retention": {
            "keep_extracted_text_after_completion": bool(
                retention_config.get("keep_extracted_text_after_completion", False)
            )
        },
    }


def main() -> int:
    args = parse_args()
    try:
        job_dir = args.job_dir.expanduser().resolve()
        if (job_dir / "job.json").exists():
            raise ValueError(f"job already exists: {job_dir}")
        if job_dir.exists() and any(job_dir.iterdir()):
            raise ValueError(f"job directory must be empty: {job_dir}")
        config = json.loads(args.config.expanduser().read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError("configuration must be a JSON object")
        job = validate_config(config, job_dir)
        job_dir.mkdir(parents=True, exist_ok=True)
        write_json(job_dir / "job.json", job)
        write_json(
            job_dir / "checkpoint.json",
            {
                "schema_version": SCHEMA_VERSION,
                "job_id": job["job_id"],
                "stage": "registered",
                "resume_stage": None,
                "created_at": utc_now(),
                "updated_at": utc_now(),
                "artifacts": {},
                "summary": {"sources": len(job["sources"])},
                "batches": {},
            },
        )
        record_event(job_dir, "sources-registered", {"source_ids": [s["id"] for s in job["sources"]]})
        result = {
            "job_dir": str(job_dir),
            "job_id": job["job_id"],
            "stage": "registered",
            "sources": [
                {"id": source["id"], "mode": source["mode"], "writable": False}
                for source in job["sources"]
            ],
            "target_root": job["target_root"],
            "target_write_policy": job["target_write_policy"],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
