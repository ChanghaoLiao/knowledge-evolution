#!/usr/bin/env python3
"""Inspect and advance Import/Adopt state without applying knowledge edits."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from _import_common import (
    STAGES,
    artifact_sha256,
    iter_jsonl,
    load_checkpoint,
    load_job,
    path_within,
    record_event,
    require_relative_path,
    save_checkpoint,
    set_stage,
    sha256_file,
    utc_now,
    write_jsonl,
)


KNOWLEDGE_TYPES = {"concept", "project", "decision", "experience", "resource", "inbox"}
CONFIDENCE_LEVELS = {"high", "medium", "low"}
EVIDENCE_CLASSES = {"observed", "stated", "inferred"}
BATCH_STATUSES = {"pending", "classified", "reconciled", "proposed", "applied", "skipped", "failed"}
RECONCILIATION_DECISIONS = {
    "merge",
    "link",
    "version",
    "conflict",
    "keep-separate",
    "discard",
    "preserve-sources",
}
ALLOWED_TRANSITIONS = {
    "registered": {"inventoried", "paused", "failed"},
    "inventoried": {"extracted", "paused", "failed"},
    "extracted": {"batched", "paused", "failed"},
    "batched": {"classified", "paused", "failed"},
    "classified": {"reconciliation-ready", "reconciled", "paused", "failed"},
    "reconciliation-ready": {"reconciled", "paused", "failed"},
    "reconciled": {"proposed", "paused", "failed"},
    "proposed": {"partially-applied", "completed", "paused", "failed"},
    "partially-applied": {"completed", "paused", "failed"},
    "completed": set(),
    "paused": set(),
    "failed": {"paused"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Manage checkpoints, validate Agent-produced candidates, and record approved "
            "applications. This utility never edits knowledge content itself."
        )
    )
    parser.add_argument("--job-dir", type=Path, required=True)
    parser.add_argument("--pretty", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status")

    pause = subparsers.add_parser("pause")
    pause.add_argument("--reason", required=True)

    subparsers.add_parser("resume")

    stage = subparsers.add_parser("set-stage")
    stage.add_argument("--to", choices=STAGES, required=True)
    stage.add_argument("--reason", required=True)
    stage.add_argument("--artifact", type=Path)

    batch = subparsers.add_parser("record-batch")
    batch.add_argument("--batch-id", required=True)
    batch.add_argument("--status", choices=BATCH_STATUSES, required=True)
    batch.add_argument("--artifact", type=Path)

    candidates = subparsers.add_parser("validate-candidates")
    candidates.add_argument("--file", type=Path, required=True)
    candidates.add_argument("--accept", action="store_true")

    reconciliation = subparsers.add_parser("validate-reconciliation")
    reconciliation.add_argument("--file", type=Path, required=True)
    reconciliation.add_argument("--accept", action="store_true")

    application = subparsers.add_parser("record-application")
    application.add_argument("--proposal-id", required=True)
    application.add_argument("--change-id", required=True)
    application.add_argument("--target-path", required=True)
    application.add_argument("--source-file-id", action="append", default=[])
    return parser.parse_args()


def artifact_in_job(job_dir: Path, artifact: Path) -> tuple[str, str]:
    artifact = artifact.expanduser().resolve()
    if not artifact.is_file():
        raise ValueError(f"artifact does not exist: {artifact}")
    if not path_within(artifact, job_dir):
        raise ValueError("state artifacts must be stored inside the job directory")
    return artifact.relative_to(job_dir).as_posix(), artifact_sha256(artifact)


def validate_candidates(job_dir: Path, path: Path) -> dict[str, Any]:
    manifest_ids = {record["file_id"] for record in iter_jsonl(job_dir / "source-manifest.jsonl")}
    chunks = {
        record["chunk_id"]: record
        for record in iter_jsonl(job_dir / "extracted-chunks.jsonl")
    }
    seen: set[str] = set()
    errors: list[str] = []
    candidates = 0
    referenced_files: set[str] = set()
    for line_number, candidate in enumerate(iter_jsonl(path), start=1):
        candidates += 1
        candidate_id = candidate.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id:
            errors.append(f"line {line_number}: missing candidate_id")
        elif candidate_id in seen:
            errors.append(f"line {line_number}: duplicate candidate_id {candidate_id}")
        else:
            seen.add(candidate_id)
        if candidate.get("knowledge_type") not in KNOWLEDGE_TYPES:
            errors.append(f"line {line_number}: invalid knowledge_type")
        if not isinstance(candidate.get("title"), str) or not candidate["title"].strip():
            errors.append(f"line {line_number}: missing title")
        if not isinstance(candidate.get("content"), str) or not candidate["content"].strip():
            errors.append(f"line {line_number}: missing content")
        if candidate.get("confidence") not in CONFIDENCE_LEVELS:
            errors.append(f"line {line_number}: invalid confidence")
        if candidate.get("evidence_class") not in EVIDENCE_CLASSES:
            errors.append(f"line {line_number}: invalid evidence_class")
        refs = candidate.get("source_refs")
        if not isinstance(refs, list) or not refs:
            errors.append(f"line {line_number}: source_refs must be non-empty")
            continue
        for ref in refs:
            if not isinstance(ref, dict):
                errors.append(f"line {line_number}: source ref must be an object")
                continue
            file_id = ref.get("file_id")
            chunk_id = ref.get("chunk_id")
            if file_id not in manifest_ids:
                errors.append(f"line {line_number}: unknown file_id {file_id}")
            else:
                referenced_files.add(file_id)
            if chunk_id not in chunks:
                errors.append(f"line {line_number}: unknown chunk_id {chunk_id}")
                continue
            chunk = chunks[chunk_id]
            if file_id != chunk.get("file_id"):
                errors.append(f"line {line_number}: chunk_id does not belong to file_id")
            for field in ("source_id", "relative_path", "locator"):
                if not isinstance(ref.get(field), str) or not ref[field]:
                    errors.append(f"line {line_number}: source ref missing {field}")
                elif ref[field] != chunk.get(field):
                    errors.append(f"line {line_number}: source ref {field} does not match chunk")
    return {
        "valid": not errors,
        "candidates": candidates,
        "referenced_files": len(referenced_files),
        "errors": errors[:100],
        "errors_truncated": len(errors) > 100,
    }


def status_result(job_dir: Path, job: dict[str, Any], checkpoint: dict[str, Any]) -> dict[str, Any]:
    batch_counts: dict[str, int] = {}
    for entry in checkpoint.get("batches", {}).values():
        status = entry.get("status", "unknown")
        batch_counts[status] = batch_counts.get(status, 0) + 1
    return {
        "job_id": job["job_id"],
        "stage": checkpoint.get("stage"),
        "resume_stage": checkpoint.get("resume_stage"),
        "sources": [{"id": source["id"], "mode": source["mode"]} for source in job["sources"]],
        "target_root": job["target_root"],
        "artifacts": checkpoint.get("artifacts", {}),
        "summary": checkpoint.get("summary", {}),
        "batches": batch_counts,
        "updated_at": checkpoint.get("updated_at"),
    }


def validate_reconciliation(job_dir: Path, path: Path) -> dict[str, Any]:
    required_ids: set[str] = set()
    for name in ("reconciliation-candidates.jsonl", "source-duplicates.jsonl"):
        artifact = job_dir / name
        if artifact.exists():
            required_ids.update(
                str(record["relation_id"])
                for record in iter_jsonl(artifact)
                if record.get("relation_id")
            )

    seen: set[str] = set()
    errors: list[str] = []
    for line_number, decision in enumerate(iter_jsonl(path), start=1):
        relation_id = decision.get("relation_id")
        if not isinstance(relation_id, str) or not relation_id:
            errors.append(f"line {line_number}: missing relation_id")
            continue
        if relation_id in seen:
            errors.append(f"line {line_number}: duplicate relation_id {relation_id}")
        seen.add(relation_id)
        if relation_id not in required_ids:
            errors.append(f"line {line_number}: unknown relation_id {relation_id}")
        if decision.get("decision") not in RECONCILIATION_DECISIONS:
            errors.append(f"line {line_number}: invalid decision")
        if not isinstance(decision.get("reason"), str) or not decision["reason"].strip():
            errors.append(f"line {line_number}: missing reason")

    missing = sorted(required_ids - seen)
    if missing:
        errors.append(f"missing decisions for {len(missing)} relation(s): {', '.join(missing[:10])}")
    return {
        "valid": not errors,
        "required_relations": len(required_ids),
        "decisions": len(seen),
        "errors": errors[:100],
        "errors_truncated": len(errors) > 100,
    }


def transition(job_dir: Path, checkpoint: dict[str, Any], target: str, reason: str) -> dict[str, Any]:
    current = str(checkpoint.get("stage"))
    if target == current:
        return checkpoint
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(f"invalid transition: {current} -> {target}")
    result = set_stage(job_dir, target)
    record_event(job_dir, "stage-transition-authorized", {"from": current, "to": target, "reason": reason})
    return result


def main() -> int:
    args = parse_args()
    try:
        job_dir = args.job_dir.expanduser().resolve()
        job = load_job(job_dir)
        checkpoint = load_checkpoint(job_dir)

        if args.command == "status":
            result = status_result(job_dir, job, checkpoint)

        elif args.command == "pause":
            current = str(checkpoint.get("stage"))
            if current == "paused":
                result = status_result(job_dir, job, checkpoint)
            elif current in {"completed", "failed"}:
                raise ValueError(f"cannot pause a {current} job")
            else:
                checkpoint["resume_stage"] = current
                checkpoint["stage"] = "paused"
                checkpoint["pause_reason"] = args.reason
                save_checkpoint(job_dir, checkpoint)
                record_event(job_dir, "job-paused", {"from": current, "reason": args.reason})
                result = status_result(job_dir, job, checkpoint)

        elif args.command == "resume":
            if checkpoint.get("stage") != "paused" or not checkpoint.get("resume_stage"):
                raise ValueError("job is not paused with a resume stage")
            target = str(checkpoint["resume_stage"])
            checkpoint["stage"] = target
            checkpoint["resume_stage"] = None
            checkpoint.pop("pause_reason", None)
            save_checkpoint(job_dir, checkpoint)
            record_event(job_dir, "job-resumed", {"to": target})
            result = status_result(job_dir, job, checkpoint)

        elif args.command == "set-stage":
            if args.to not in {"proposed", "completed", "failed"}:
                raise ValueError(
                    "this stage is pipeline-managed; use the matching build, validation, "
                    "or application command"
                )
            if args.to in {"proposed", "completed"} and not args.artifact:
                raise ValueError(f"--artifact is required for stage {args.to}")
            current = str(checkpoint.get("stage"))
            if args.to != current and args.to not in ALLOWED_TRANSITIONS.get(current, set()):
                raise ValueError(f"invalid transition: {current} -> {args.to}")
            if args.artifact:
                relative, digest = artifact_in_job(job_dir, args.artifact)
                if args.to == "completed":
                    report = json.loads(args.artifact.expanduser().resolve().read_text(encoding="utf-8"))
                    if not isinstance(report, dict) or report.get("clean") is not True:
                        raise ValueError("completion artifact must be a clean verification report")
                checkpoint.setdefault("artifacts", {})[f"stage_{args.to}"] = relative
                checkpoint["artifacts"][f"stage_{args.to}_sha256"] = digest
                save_checkpoint(job_dir, checkpoint)
            checkpoint = transition(job_dir, checkpoint, args.to, args.reason)
            result = status_result(job_dir, job, checkpoint)

        elif args.command == "record-batch":
            batches = checkpoint.get("batches", {})
            if args.batch_id not in batches:
                raise ValueError(f"unknown batch id: {args.batch_id}")
            entry = batches[args.batch_id]
            entry["status"] = args.status
            entry["updated_at"] = utc_now()
            if args.artifact:
                relative, digest = artifact_in_job(job_dir, args.artifact)
                entry["artifact"] = relative
                entry["artifact_sha256"] = digest
            checkpoint["batches"] = batches
            save_checkpoint(job_dir, checkpoint)
            record_event(job_dir, "batch-status-recorded", {"batch_id": args.batch_id, "status": args.status})
            result = status_result(job_dir, job, checkpoint)

        elif args.command == "validate-candidates":
            candidate_path = args.file.expanduser().resolve()
            relative, digest = artifact_in_job(job_dir, candidate_path)
            validation = validate_candidates(job_dir, candidate_path)
            if args.accept:
                if not validation["valid"]:
                    raise ValueError("candidate file is invalid and cannot be accepted")
                unfinished = sorted(
                    batch_id
                    for batch_id, entry in checkpoint.get("batches", {}).items()
                    if entry.get("status") not in {"classified", "skipped"}
                )
                if unfinished:
                    raise ValueError(
                        f"all batches must be classified or skipped before acceptance: {unfinished[:10]}"
                    )
                checkpoint = transition(job_dir, checkpoint, "classified", "validated candidate set accepted")
                checkpoint.setdefault("artifacts", {})["candidates"] = relative
                checkpoint["artifacts"]["candidates_sha256"] = digest
                checkpoint["summary"]["classification"] = validation
                save_checkpoint(job_dir, checkpoint)
                record_event(job_dir, "candidates-accepted", {"path": relative, **validation})
            result = {"artifact": relative, "sha256": digest, **validation}

        elif args.command == "validate-reconciliation":
            decision_path = args.file.expanduser().resolve()
            relative, digest = artifact_in_job(job_dir, decision_path)
            validation = validate_reconciliation(job_dir, decision_path)
            if args.accept:
                if not validation["valid"]:
                    raise ValueError("reconciliation file is invalid and cannot be accepted")
                checkpoint = transition(
                    job_dir,
                    checkpoint,
                    "reconciled",
                    "complete reconciliation decision set accepted",
                )
                checkpoint.setdefault("artifacts", {})["reconciliation_decisions"] = relative
                checkpoint["artifacts"]["reconciliation_decisions_sha256"] = digest
                checkpoint["summary"]["reconciliation_decisions"] = validation
                save_checkpoint(job_dir, checkpoint)
                record_event(job_dir, "reconciliation-decisions-accepted", validation)
            result = {"artifact": relative, "sha256": digest, **validation}

        else:
            if checkpoint.get("stage") not in {"proposed", "partially-applied"}:
                raise ValueError("applications can be recorded only after proposal")
            target_relative = require_relative_path(args.target_path)
            target_root = Path(job["target_root"]).resolve()
            target = (target_root / target_relative).resolve()
            if not path_within(target, target_root) or not target.is_file():
                raise ValueError(f"target file is missing or outside target root: {target}")
            manifest_ids = {record["file_id"] for record in iter_jsonl(job_dir / "source-manifest.jsonl")}
            unknown = sorted(set(args.source_file_id) - manifest_ids)
            if unknown:
                raise ValueError(f"unknown source file ids: {unknown}")
            applied_path = job_dir / "applied.jsonl"
            existing = list(iter_jsonl(applied_path)) if applied_path.exists() else []
            after_hash = sha256_file(target)
            previous = next((item for item in existing if item.get("change_id") == args.change_id), None)
            source_file_ids = sorted(set(args.source_file_id))
            if previous:
                expected_identity = {
                    "proposal_id": args.proposal_id,
                    "target_path": target_relative.as_posix(),
                    "source_file_ids": source_file_ids,
                    "after_sha256": after_hash,
                }
                mismatched = [
                    key for key, value in expected_identity.items() if previous.get(key) != value
                ]
                if mismatched:
                    raise ValueError(
                        f"change id already recorded with different {', '.join(mismatched)}: "
                        f"{args.change_id}"
                    )
            if not previous:
                existing.append(
                    {
                        "schema_version": 1,
                        "recorded_at": utc_now(),
                        "proposal_id": args.proposal_id,
                        "change_id": args.change_id,
                        "target_path": target_relative.as_posix(),
                        "after_sha256": after_hash,
                        "source_file_ids": source_file_ids,
                    }
                )
                write_jsonl(applied_path, existing)
            checkpoint = transition(job_dir, checkpoint, "partially-applied", "approved application recorded")
            checkpoint.setdefault("artifacts", {})["applied"] = "applied.jsonl"
            checkpoint["artifacts"]["applied_sha256"] = artifact_sha256(applied_path)
            save_checkpoint(job_dir, checkpoint)
            record_event(job_dir, "application-recorded", {"change_id": args.change_id})
            result = {"recorded": not bool(previous), "change_id": args.change_id, "after_sha256": after_hash}

        print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
