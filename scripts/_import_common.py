#!/usr/bin/env python3
"""Shared, dependency-free helpers for the Import/Adopt pipeline."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator


SCHEMA_VERSION = 1
STAGES = (
    "registered",
    "inventoried",
    "extracted",
    "batched",
    "classified",
    "reconciliation-ready",
    "reconciled",
    "proposed",
    "partially-applied",
    "completed",
    "paused",
    "failed",
)
IGNORED_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".cache",
    ".next",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "__pycache__",
}
IGNORED_FILE_NAMES = {".DS_Store", "Thumbs.db"}
SENSITIVE_EXACT_NAMES = {
    ".authinfo",
    ".git-credentials",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "_netrc",
    "id_ed25519",
    "id_rsa",
}
SENSITIVE_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".kdb", ".kdbx"}
SENSITIVE_TERM_PATTERN = re.compile(
    r"(?:^|[._-])(?:credentials?|secrets?|tokens?)(?:[._-]|$)", re.IGNORECASE
)
SENSITIVE_CONTENT_PATTERNS = (
    re.compile(
        r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\b(?:gh[pousr]_|github_pat_|sk-)[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)(://[^\s:/@]+:)[^\s@/]+(@)"),
    re.compile(
        r"(?im)(\b(?:api[_-]?key|access[_-]?key|client[_-]?secret|password|passwd|pwd|secret|token|authorization)\b\s*[:=]\s*)[^\s,;]+"
    ),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"expected JSON object at {path}:{line_number}")
            yield value


def write_jsonl(path: Path, values: Iterable[dict[str, Any]]) -> None:
    text = "".join(json.dumps(value, ensure_ascii=False) + "\n" for value in values)
    atomic_write_text(path, text)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(prefix: str, *parts: str, length: int = 20) -> str:
    digest = sha256_text("\0".join(parts))[:length]
    return f"{prefix}-{digest}"


def normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def redact_sensitive_text(value: str) -> tuple[str, int]:
    redactions = 0
    result = value
    for pattern in SENSITIVE_CONTENT_PATTERNS:
        if pattern.pattern.startswith("(?i)(://"):
            result, count = pattern.subn(r"\1[REDACTED]\2", result)
        elif pattern.pattern.startswith("(?im)(\\b"):
            result, count = pattern.subn(r"\1[REDACTED]", result)
        else:
            result, count = pattern.subn("[REDACTED]", result)
        redactions += count
    return result, redactions


def is_sensitive(relative: Path) -> bool:
    name = relative.name.casefold()
    if name in SENSITIVE_EXACT_NAMES:
        return True
    if name == ".env" or name.startswith(".env."):
        return True
    if relative.suffix.casefold() in SENSITIVE_SUFFIXES:
        return True
    return any(SENSITIVE_TERM_PATTERN.search(part.casefold()) for part in relative.parts)


def is_ignored(relative: Path) -> bool:
    return relative.name in IGNORED_FILE_NAMES or any(
        part in IGNORED_DIR_NAMES for part in relative.parts
    )


def matches_patterns(relative: Path, patterns: list[str]) -> bool:
    path = relative.as_posix()
    return any(fnmatch.fnmatch(path, pattern) or relative.match(pattern) for pattern in patterns)


def included_by_source(relative: Path, source: dict[str, Any]) -> bool:
    includes = source.get("include") or ["*", "**/*"]
    excludes = source.get("exclude") or []
    return matches_patterns(relative, includes) and not matches_patterns(relative, excludes)


def path_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def require_relative_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"expected safe relative path, got: {value}")
    return path


def job_dir_path(value: Path) -> Path:
    return value.expanduser().resolve()


def load_job(job_dir: Path) -> dict[str, Any]:
    job_dir = job_dir_path(job_dir)
    job = load_json(job_dir / "job.json")
    if job.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported job schema in {job_dir / 'job.json'}")
    return job


def load_checkpoint(job_dir: Path) -> dict[str, Any]:
    checkpoint_path = job_dir_path(job_dir) / "checkpoint.json"
    if not checkpoint_path.exists():
        raise ValueError(f"missing checkpoint: {checkpoint_path}")
    return load_json(checkpoint_path)


def save_checkpoint(job_dir: Path, checkpoint: dict[str, Any]) -> None:
    checkpoint["updated_at"] = utc_now()
    write_json(job_dir_path(job_dir) / "checkpoint.json", checkpoint)


def record_event(job_dir: Path, event: str, details: dict[str, Any] | None = None) -> None:
    path = job_dir_path(job_dir) / "events.jsonl"
    existing = list(iter_jsonl(path)) if path.exists() else []
    existing.append(
        {
            "timestamp": utc_now(),
            "event": event,
            "details": details or {},
        }
    )
    write_jsonl(path, existing)


def set_stage(
    job_dir: Path,
    stage: str,
    *,
    artifact_updates: dict[str, Any] | None = None,
    summary_updates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if stage not in STAGES:
        raise ValueError(f"unsupported stage: {stage}")
    checkpoint = load_checkpoint(job_dir)
    previous = checkpoint.get("stage")
    checkpoint["stage"] = stage
    if artifact_updates:
        checkpoint.setdefault("artifacts", {}).update(artifact_updates)
    if summary_updates:
        checkpoint.setdefault("summary", {}).update(summary_updates)
    save_checkpoint(job_dir, checkpoint)
    record_event(job_dir, "stage-changed", {"from": previous, "to": stage})
    return checkpoint


def source_map(job: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {source["id"]: source for source in job.get("sources", [])}


def resolve_source_file(job: dict[str, Any], record: dict[str, Any]) -> Path:
    sources = source_map(job)
    source_id = record.get("source_id")
    if source_id not in sources:
        raise ValueError(f"unknown source id in record: {source_id}")
    relative = require_relative_path(str(record.get("relative_path", "")))
    root = Path(sources[source_id]["root"]).resolve()
    path = (root / relative).resolve()
    if not path_within(path, root):
        raise ValueError(f"source path escapes root: {path}")
    return path


def artifact_sha256(path: Path) -> str:
    return sha256_file(path) if path.exists() else ""
