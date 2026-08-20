#!/usr/bin/env python3
"""Verify source preservation, pipeline coverage, and recorded target state."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from _import_common import (
    artifact_sha256,
    iter_jsonl,
    load_checkpoint,
    load_job,
    path_within,
    resolve_source_file,
    sha256_file,
    utc_now,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify that registered source files still match inventory, extracted files are "
            "accounted for, candidate evidence resolves, and recorded targets match their hashes."
        )
    )
    parser.add_argument("--job-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-source-unchanged", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Return non-zero when warnings exist")
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args()


def verify_sources(
    job: dict[str, Any],
    manifest: list[dict[str, Any]],
    applied: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int, list[dict[str, Any]]]:
    changes: list[dict[str, Any]] = []
    approved_target_changes: list[dict[str, Any]] = []
    checked = 0
    applied_by_target = {
        str(record.get("target_path")): record
        for record in applied
        if record.get("target_path")
    }
    for record in manifest:
        path = resolve_source_file(job, record)
        if not path.is_file():
            changes.append({"file_id": record["file_id"], "change": "missing"})
            continue
        stat = path.stat()
        current_hash = None
        if record.get("sha256"):
            current_hash = sha256_file(path)
            changed = current_hash != record["sha256"]
        else:
            changed = (stat.st_size, stat.st_mtime_ns) != (record.get("size"), record.get("mtime_ns"))
        checked += 1
        if changed:
            applied_record = applied_by_target.get(str(record.get("relative_path")))
            if current_hash is None and record.get("source_mode") == "adopt" and applied_record:
                current_hash = sha256_file(path)
            if (
                record.get("source_mode") == "adopt"
                and applied_record
                and current_hash
                and current_hash == applied_record.get("after_sha256")
            ):
                approved_target_changes.append(
                    {
                        "file_id": record["file_id"],
                        "relative_path": record["relative_path"],
                        "change_id": applied_record.get("change_id"),
                    }
                )
                continue
            changes.append(
                {
                    "file_id": record["file_id"],
                    "source_id": record["source_id"],
                    "relative_path": record["relative_path"],
                    "change": "modified-since-inventory",
                    "inventory_sha256": record.get("sha256"),
                    "current_sha256": current_hash,
                }
            )
    return changes, checked, approved_target_changes


def verify_targets(job: dict[str, Any], applied_path: Path) -> tuple[list[dict[str, Any]], int]:
    errors: list[dict[str, Any]] = []
    checked = 0
    if not applied_path.exists():
        return errors, checked
    target_root = Path(job["target_root"]).resolve()
    for record in iter_jsonl(applied_path):
        target = (target_root / str(record.get("target_path", ""))).resolve()
        if not path_within(target, target_root):
            errors.append({"change_id": record.get("change_id"), "error": "target-outside-root"})
            continue
        if not target.is_file():
            errors.append({"change_id": record.get("change_id"), "error": "target-missing"})
            continue
        current_hash = sha256_file(target)
        checked += 1
        if current_hash != record.get("after_sha256"):
            errors.append(
                {
                    "change_id": record.get("change_id"),
                    "error": "target-changed-after-application-record",
                    "recorded_sha256": record.get("after_sha256"),
                    "current_sha256": current_hash,
                }
            )
    return errors, checked


def main() -> int:
    args = parse_args()
    try:
        job_dir = args.job_dir.expanduser().resolve()
        job = load_job(job_dir)
        checkpoint = load_checkpoint(job_dir)
        if args.output and not path_within(args.output.expanduser().resolve(), job_dir):
            raise ValueError("verification output must be stored inside the job directory")
        manifest_path = job_dir / "source-manifest.jsonl"
        if not manifest_path.exists():
            raise ValueError("source-manifest.jsonl is missing")
        manifest = list(iter_jsonl(manifest_path))
        manifest_ids = {record["file_id"] for record in manifest}

        applied_path = job_dir / "applied.jsonl"
        applied = list(iter_jsonl(applied_path)) if applied_path.exists() else []
        source_changes, source_checked, approved_target_changes = verify_sources(
            job, manifest, applied
        )
        errors: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        if source_changes:
            destination = errors if args.require_source_unchanged else warnings
            destination.append(
                {
                    "kind": "source-state-changed",
                    "message": "Source changes are not attributed to this pipeline; refresh before applying stale proposals.",
                    "files": source_changes,
                }
            )

        artifact_errors: list[dict[str, Any]] = []
        artifacts = checkpoint.get("artifacts", {})
        for name, relative in artifacts.items():
            if name.endswith("_sha256") or not isinstance(relative, str):
                continue
            expected = artifacts.get(f"{name}_sha256")
            if not expected:
                continue
            artifact_path = (job_dir / relative).resolve()
            if not path_within(artifact_path, job_dir) or not artifact_path.is_file():
                artifact_errors.append({"artifact": name, "error": "missing-or-outside-job"})
            elif artifact_sha256(artifact_path) != expected:
                artifact_errors.append({"artifact": name, "error": "digest-mismatch"})
        errors.extend({"kind": "artifact-verification", **value} for value in artifact_errors)

        extraction_status: Counter[str] = Counter()
        extracted_file_ids: set[str] = set()
        indexed_file_ids: set[str] = set()
        index_path = job_dir / "extraction-index.jsonl"
        if index_path.exists():
            for record in iter_jsonl(index_path):
                indexed_file_ids.add(str(record["file_id"]))
                extraction_status[str(record.get("status", "unknown"))] += 1
                if record.get("status") == "extracted":
                    extracted_file_ids.add(str(record["file_id"]))
            missing_manifest = extracted_file_ids - manifest_ids
            if missing_manifest:
                errors.append({"kind": "unknown-extracted-file-ids", "file_ids": sorted(missing_manifest)})
            missing_index = manifest_ids - indexed_file_ids
            unknown_index = indexed_file_ids - manifest_ids
            if missing_index:
                errors.append({"kind": "manifest-files-missing-from-index", "file_ids": sorted(missing_index)})
            if unknown_index:
                errors.append({"kind": "index-files-missing-from-manifest", "file_ids": sorted(unknown_index)})
            if extraction_status.get("error"):
                warnings.append({"kind": "extraction-errors", "count": extraction_status["error"]})
            if extraction_status.get("unsupported"):
                warnings.append({"kind": "unsupported-files", "count": extraction_status["unsupported"]})
            if extraction_status.get("deferred"):
                warnings.append({"kind": "deferred-files", "count": extraction_status["deferred"]})
        elif checkpoint.get("stage") not in {"registered", "inventoried"}:
            errors.append({"kind": "missing-extraction-index"})

        chunk_ids: set[str] = set()
        chunk_file_ids: set[str] = set()
        chunks_path = job_dir / "extracted-chunks.jsonl"
        if chunks_path.exists():
            for record in iter_jsonl(chunks_path):
                chunk_ids.add(str(record["chunk_id"]))
                chunk_file_ids.add(str(record["file_id"]))
            unknown_chunk_files = chunk_file_ids - manifest_ids
            if unknown_chunk_files:
                errors.append({"kind": "unknown-chunk-file-ids", "file_ids": sorted(unknown_chunk_files)})

        candidate_count = 0
        candidate_file_ids: set[str] = set()
        candidate_path_value = checkpoint.get("artifacts", {}).get("candidates")
        if candidate_path_value:
            candidate_path = job_dir / str(candidate_path_value)
            if not candidate_path.exists():
                errors.append({"kind": "missing-candidate-artifact", "path": str(candidate_path_value)})
            else:
                for candidate in iter_jsonl(candidate_path):
                    candidate_count += 1
                    for ref in candidate.get("source_refs", []):
                        file_id = str(ref.get("file_id", ""))
                        chunk_id = str(ref.get("chunk_id", ""))
                        candidate_file_ids.add(file_id)
                        if file_id not in manifest_ids:
                            errors.append({"kind": "candidate-unknown-file", "candidate_id": candidate.get("candidate_id"), "file_id": file_id})
                        if chunk_id not in chunk_ids:
                            errors.append({"kind": "candidate-unknown-chunk", "candidate_id": candidate.get("candidate_id"), "chunk_id": chunk_id})

        target_errors, target_checked = verify_targets(job, applied_path)
        errors.extend({"kind": "target-verification", **value} for value in target_errors)

        supported_manifest_ids = {
            record["file_id"] for record in manifest if record.get("extractor") != "unsupported"
        }
        report = {
            "schema_version": 1,
            "verified_at": utc_now(),
            "job_id": job["job_id"],
            "stage": checkpoint.get("stage"),
            "source_preservation": {
                "checked": source_checked,
                "changed_since_inventory": len(source_changes),
                "approved_adopt_target_changes": len(approved_target_changes),
                "pipeline_attribution": (
                    "only adopt-target changes matching recorded approved applications"
                    if approved_target_changes
                    else "none"
                ),
            },
            "coverage": {
                "manifest_files": len(manifest_ids),
                "supported_files": len(supported_manifest_ids),
                "extracted_files": len(extracted_file_ids),
                "chunked_files": len(chunk_file_ids),
                "candidate_referenced_files": len(candidate_file_ids),
                "candidates": candidate_count,
                "extraction_status": dict(extraction_status),
            },
            "targets": {"checked": target_checked, "errors": len(target_errors)},
            "artifacts": {"checked": len(artifacts), "errors": len(artifact_errors)},
            "errors": errors,
            "warnings": warnings,
            "clean": not errors and not (args.strict and warnings),
        }
        if args.output:
            write_json(args.output.expanduser().resolve(), report)
        print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
        return 0 if report["clean"] else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
