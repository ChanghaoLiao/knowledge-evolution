#!/usr/bin/env python3
"""Split extracted chunks into deterministic, resumable Agent work batches."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from _import_common import (
    artifact_sha256,
    iter_jsonl,
    load_checkpoint,
    load_job,
    record_event,
    save_checkpoint,
    set_stage,
    write_json,
    write_jsonl,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create deterministic JSONL batches for Agent semantic classification. "
            "Each record retains source, file, chunk, and locator provenance."
        )
    )
    parser.add_argument("--job-dir", type=Path, required=True)
    parser.add_argument("--max-files", type=int)
    parser.add_argument("--max-characters", type=int)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args()


def partition(
    chunks: list[dict[str, Any]], max_files: int, max_characters: int
) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_files: set[str] = set()
    current_characters = 0
    for chunk in chunks:
        file_id = str(chunk["file_id"])
        characters = int(chunk.get("character_count", len(str(chunk.get("text", "")))))
        adds_file = file_id not in current_files
        exceeds_files = adds_file and len(current_files) >= max_files
        exceeds_characters = bool(current) and current_characters + characters > max_characters
        if exceeds_files or exceeds_characters:
            batches.append(current)
            current = []
            current_files = set()
            current_characters = 0
        current.append(chunk)
        current_files.add(file_id)
        current_characters += characters
    if current:
        batches.append(current)
    return batches


def main() -> int:
    args = parse_args()
    try:
        job_dir = args.job_dir.expanduser().resolve()
        job = load_job(job_dir)
        checkpoint = load_checkpoint(job_dir)
        if checkpoint.get("stage") not in {"extracted", "batched"}:
            raise ValueError(f"job must be extracted before batching; current stage: {checkpoint.get('stage')}")
        chunks_path = job_dir / "extracted-chunks.jsonl"
        if not chunks_path.exists():
            raise ValueError("extracted-chunks.jsonl is missing")
        chunks_hash = artifact_sha256(chunks_path)
        expected_hash = checkpoint.get("artifacts", {}).get("extracted_chunks_sha256")
        if expected_hash and chunks_hash != expected_hash:
            raise ValueError("extracted chunks changed outside the pipeline")

        max_files = args.max_files or int(job["batch"]["max_files"])
        max_characters = args.max_characters or int(job["batch"]["max_characters"])
        if min(max_files, max_characters) < 1:
            raise ValueError("batch limits must be positive")

        chunks = sorted(
            iter_jsonl(chunks_path),
            key=lambda item: (
                str(item.get("source_id", "")).casefold(),
                str(item.get("relative_path", "")).casefold(),
                str(item.get("chunk_id", "")),
            ),
        )
        batch_set = chunks_hash[:16]
        batch_root = job_dir / "batches" / batch_set
        batch_root.mkdir(parents=True, exist_ok=True)
        batch_groups = partition(chunks, max_files, max_characters)
        index_records: list[dict[str, Any]] = []
        previous_status = checkpoint.get("batches", {})
        new_status: dict[str, Any] = {}
        for number, group in enumerate(batch_groups, start=1):
            batch_id = f"batch-{number:04d}"
            path = batch_root / f"{batch_id}.jsonl"
            records = [{**record, "batch_id": batch_id} for record in group]
            write_jsonl(path, records)
            file_ids = sorted({str(record["file_id"]) for record in records})
            character_count = sum(int(record.get("character_count", 0)) for record in records)
            existing = previous_status.get(batch_id, {})
            status = existing.get("status", "pending") if existing.get("batch_set") == batch_set else "pending"
            entry = {
                "batch_id": batch_id,
                "batch_set": batch_set,
                "path": path.relative_to(job_dir).as_posix(),
                "sha256": artifact_sha256(path),
                "files": len(file_ids),
                "chunks": len(records),
                "characters": character_count,
                "status": status,
            }
            index_records.append(entry)
            new_status[batch_id] = {"batch_set": batch_set, "status": status}

        index_path = batch_root / "batch-index.json"
        write_json(
            index_path,
            {
                "schema_version": 1,
                "job_id": job["job_id"],
                "batch_set": batch_set,
                "source_chunks_sha256": chunks_hash,
                "max_files": max_files,
                "max_characters": max_characters,
                "batches": index_records,
            },
        )
        checkpoint = set_stage(
            job_dir,
            "batched",
            artifact_updates={
                "batch_set": batch_set,
                "batch_index": index_path.relative_to(job_dir).as_posix(),
                "batch_index_sha256": artifact_sha256(index_path),
                "downstream_stale": False,
            },
            summary_updates={
                "batching": {
                    "batches": len(index_records),
                    "files": len({str(chunk["file_id"]) for chunk in chunks}),
                    "chunks": len(chunks),
                    "characters": sum(int(chunk.get("character_count", 0)) for chunk in chunks),
                }
            },
        )
        checkpoint["batches"] = new_status
        save_checkpoint(job_dir, checkpoint)
        record_event(job_dir, "batches-prepared", {"batch_set": batch_set, "count": len(index_records)})
        print(
            json.dumps(
                {
                    "job_id": job["job_id"],
                    "stage": "batched",
                    "batch_set": batch_set,
                    "batch_index": str(index_path),
                    "batches": len(index_records),
                },
                ensure_ascii=False,
                indent=2 if args.pretty else None,
            )
        )
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
