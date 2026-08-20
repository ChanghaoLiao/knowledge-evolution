#!/usr/bin/env python3
"""Generate exact-duplicate, near-duplicate, and conflict candidates for Agent review."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from _import_common import (
    artifact_sha256,
    iter_jsonl,
    load_checkpoint,
    load_job,
    normalize_text,
    record_event,
    set_stage,
    stable_id,
    write_jsonl,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create deterministic reconciliation candidates. Results are suggestions only; "
            "an Agent must decide whether two knowledge candidates truly duplicate or conflict."
        )
    )
    parser.add_argument("--job-dir", type=Path, required=True)
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--near-title-threshold", type=float, default=0.82)
    parser.add_argument("--near-content-threshold", type=float, default=0.62)
    parser.add_argument("--max-block-size", type=int, default=500)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args()


def similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize_text(left), normalize_text(right)).ratio()


def candidate_blocks(candidates: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    blocks: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        title = normalize_text(str(candidate.get("title", "")))
        key = (str(candidate.get("knowledge_type", "")), title[:1])
        blocks[key].append(candidate)
    return blocks


def source_duplicate_records(manifest_path: Path) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in iter_jsonl(manifest_path):
        content_hash = record.get("sha256")
        if content_hash:
            groups[str(content_hash)].append(record)
    result: list[dict[str, Any]] = []
    for content_hash, records in sorted(groups.items()):
        if len(records) < 2:
            continue
        result.append(
            {
                "relation_id": stable_id("source-duplicate", content_hash),
                "relation": "exact-source-duplicate",
                "sha256": content_hash,
                "files": [
                    {
                        "file_id": record["file_id"],
                        "source_id": record["source_id"],
                        "relative_path": record["relative_path"],
                    }
                    for record in records
                ],
                "requires_agent_review": False,
            }
        )
    return result


def knowledge_relations(
    candidates: list[dict[str, Any]],
    title_threshold: float,
    content_threshold: float,
    max_block_size: int,
) -> tuple[list[dict[str, Any]], int]:
    relations: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    skipped_large_blocks = 0
    for block in candidate_blocks(candidates).values():
        if len(block) > max_block_size:
            skipped_large_blocks += 1
            block = sorted(block, key=lambda item: str(item["candidate_id"]))[:max_block_size]
        for left_index, left in enumerate(block):
            for right in block[left_index + 1 :]:
                pair = tuple(sorted((str(left["candidate_id"]), str(right["candidate_id"]))))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                left_title = str(left.get("title", ""))
                right_title = str(right.get("title", ""))
                left_content = str(left.get("content", ""))
                right_content = str(right.get("content", ""))
                title_score = similarity(left_title, right_title)
                content_score = similarity(left_content, right_content)
                exact_content = normalize_text(left_content) == normalize_text(right_content)
                exact_title = normalize_text(left_title) == normalize_text(right_title)

                relation = None
                if exact_content:
                    relation = "exact-knowledge-duplicate"
                elif exact_title and content_score < content_threshold:
                    relation = "possible-conflict-or-version"
                elif title_score >= title_threshold and content_score >= content_threshold:
                    relation = "near-knowledge-duplicate"
                if relation is None:
                    continue
                relations.append(
                    {
                        "relation_id": stable_id("relation", *pair),
                        "left_candidate_id": pair[0],
                        "right_candidate_id": pair[1],
                        "relation": relation,
                        "title_similarity": round(title_score, 4),
                        "content_similarity": round(content_score, 4),
                        "requires_agent_review": relation != "exact-knowledge-duplicate",
                    }
                )
    relations.sort(key=lambda item: (item["relation"], item["left_candidate_id"], item["right_candidate_id"]))
    return relations, skipped_large_blocks


def main() -> int:
    args = parse_args()
    try:
        if not 0 <= args.near_title_threshold <= 1 or not 0 <= args.near_content_threshold <= 1:
            raise ValueError("similarity thresholds must be between 0 and 1")
        if args.max_block_size < 2:
            raise ValueError("--max-block-size must be at least 2")
        job_dir = args.job_dir.expanduser().resolve()
        job = load_job(job_dir)
        checkpoint = load_checkpoint(job_dir)
        if checkpoint.get("stage") not in {"classified", "reconciliation-ready"}:
            raise ValueError(f"candidate classification is required; current stage: {checkpoint.get('stage')}")
        candidate_path = (
            args.candidates.expanduser().resolve()
            if args.candidates
            else job_dir / str(checkpoint.get("artifacts", {}).get("candidates", "candidates.jsonl"))
        )
        if not candidate_path.is_file():
            raise ValueError(f"candidate file is missing: {candidate_path}")
        expected_hash = checkpoint.get("artifacts", {}).get("candidates_sha256")
        candidate_hash = artifact_sha256(candidate_path)
        if expected_hash and expected_hash != candidate_hash:
            raise ValueError("candidate file changed after validation")

        candidates = list(iter_jsonl(candidate_path))
        relations, skipped_blocks = knowledge_relations(
            candidates,
            args.near_title_threshold,
            args.near_content_threshold,
            args.max_block_size,
        )
        source_duplicates = source_duplicate_records(job_dir / "source-manifest.jsonl")
        relation_path = job_dir / "reconciliation-candidates.jsonl"
        source_path = job_dir / "source-duplicates.jsonl"
        write_jsonl(relation_path, relations)
        write_jsonl(source_path, source_duplicates)
        summary = {
            "knowledge_candidates": len(candidates),
            "knowledge_relations": len(relations),
            "source_duplicate_groups": len(source_duplicates),
            "large_blocks_truncated": skipped_blocks,
        }
        set_stage(
            job_dir,
            "reconciliation-ready",
            artifact_updates={
                "reconciliation_candidates": "reconciliation-candidates.jsonl",
                "reconciliation_candidates_sha256": artifact_sha256(relation_path),
                "source_duplicates": "source-duplicates.jsonl",
                "source_duplicates_sha256": artifact_sha256(source_path),
            },
            summary_updates={"reconciliation": summary},
        )
        record_event(job_dir, "reconciliation-candidates-built", summary)
        print(
            json.dumps(
                {"job_id": job["job_id"], "stage": "reconciliation-ready", "summary": summary},
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
