#!/usr/bin/env python3
"""Capture or compare bounded workspace state without reading secret values."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


IGNORED_DIRS = {
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
IGNORED_FILES = {".DS_Store", "Thumbs.db"}
SENSITIVE_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".kdb", ".kdbx"}
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
SENSITIVE_TERM_PATTERN = re.compile(
    r"(?:^|[._-])(?:credentials?|secrets?|tokens?)(?:[._-]|$)", re.IGNORECASE
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_sensitive(relative: Path) -> bool:
    lowered_parts = [part.casefold() for part in relative.parts]
    name = relative.name.casefold()
    if name in SENSITIVE_EXACT_NAMES:
        return True
    if name == ".env" or name.startswith(".env."):
        return True
    if relative.suffix.casefold() in SENSITIVE_SUFFIXES:
        return True
    return any(SENSITIVE_TERM_PATTERN.search(part) for part in lowered_parts)


def is_ignored(relative: Path) -> bool:
    return relative.name in IGNORED_FILES or any(part in IGNORED_DIRS for part in relative.parts)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def path_within(path: Path, root: Path) -> Path | None:
    try:
        return path.resolve().relative_to(root.resolve())
    except ValueError:
        return None


def build_snapshot(
    workspace: Path,
    max_files: int,
    max_hash_bytes: int,
    excluded_output: Path | None = None,
) -> dict[str, Any]:
    workspace = workspace.expanduser().resolve()
    if not workspace.is_dir():
        raise ValueError(f"workspace is not a directory: {workspace}")

    excluded_relative = path_within(excluded_output, workspace) if excluded_output else None
    entries: dict[str, dict[str, Any]] = {}
    files_seen = 0
    sensitive_excluded = 0
    ignored = 0
    skipped_symlinks = 0
    read_errors = 0
    truncated = False

    for current, dirs, files in os.walk(workspace, followlinks=False):
        current_path = Path(current)
        kept_dirs = []
        for dirname in dirs:
            candidate = current_path / dirname
            relative = candidate.relative_to(workspace)
            if is_ignored(relative):
                ignored += 1
                continue
            if candidate.is_symlink():
                skipped_symlinks += 1
                continue
            kept_dirs.append(dirname)
        dirs[:] = sorted(kept_dirs, key=str.casefold)

        for filename in sorted(files, key=str.casefold):
            path = current_path / filename
            relative = path.relative_to(workspace)
            if excluded_relative is not None and relative == excluded_relative:
                ignored += 1
                continue
            if is_ignored(relative):
                ignored += 1
                continue
            if path.is_symlink():
                skipped_symlinks += 1
                continue
            if is_sensitive(relative):
                sensitive_excluded += 1
                continue
            if files_seen >= max_files:
                truncated = True
                break

            files_seen += 1
            try:
                stat = path.stat()
                entry = {
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "sha256": sha256(path) if stat.st_size <= max_hash_bytes else None,
                }
                entries[relative.as_posix()] = entry
            except OSError:
                read_errors += 1

        if truncated:
            break

    return {
        "schema_version": 1,
        "created_at": utc_now(),
        "workspace": str(workspace),
        "entries": entries,
        "summary": {
            "files_recorded": len(entries),
            "sensitive_files_excluded": sensitive_excluded,
            "ignored_items": ignored,
            "skipped_symlinks": skipped_symlinks,
            "read_errors": read_errors,
            "truncated": truncated,
            "max_files": max_files,
            "max_hash_bytes": max_hash_bytes,
        },
    }


def entry_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    before_hash = before.get("sha256")
    after_hash = after.get("sha256")
    if before_hash is not None and after_hash is not None:
        return before_hash != after_hash
    return (before.get("size"), before.get("mtime_ns")) != (
        after.get("size"),
        after.get("mtime_ns"),
    )


def compact_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {"size": entry.get("size"), "sha256": entry.get("sha256")}


def compare_snapshots(
    baseline: dict[str, Any], current: dict[str, Any], max_changes: int
) -> dict[str, Any]:
    before_entries = baseline.get("entries")
    after_entries = current.get("entries")
    if not isinstance(before_entries, dict) or not isinstance(after_entries, dict):
        raise ValueError("baseline or current snapshot has invalid entries")

    changes: list[dict[str, Any]] = []
    all_paths = sorted(set(before_entries) | set(after_entries), key=str.casefold)
    total_changes = 0
    for path in all_paths:
        before = before_entries.get(path)
        after = after_entries.get(path)
        change: dict[str, Any] | None = None
        if before is None:
            change = {"path": path, "change": "added", "after": compact_entry(after)}
        elif after is None:
            change = {"path": path, "change": "removed", "before": compact_entry(before)}
        elif entry_changed(before, after):
            change = {
                "path": path,
                "change": "modified",
                "before": compact_entry(before),
                "after": compact_entry(after),
            }
        if change is None:
            continue
        total_changes += 1
        if len(changes) < max_changes:
            changes.append(change)

    return {
        "schema_version": 1,
        "attribution": "session-confirmed",
        "baseline_created_at": baseline.get("created_at"),
        "compared_at": current.get("created_at"),
        "baseline_workspace": baseline.get("workspace"),
        "current_workspace": current.get("workspace"),
        "changes": changes,
        "summary": {
            "total_changes": total_changes,
            "reported_changes": len(changes),
            "changes_truncated": total_changes > len(changes),
            "current_snapshot": current.get("summary"),
        },
    }


def git_output(repo: Path, *args: str, text: bool = True) -> str | bytes:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=text,
    )
    return completed.stdout


def optional_git_output(repo: Path, *args: str) -> str | None:
    try:
        return str(git_output(repo, *args)).strip() or None
    except subprocess.CalledProcessError:
        return None


def summarize_git(workspace: Path, max_changes: int) -> dict[str, Any]:
    workspace = workspace.expanduser().resolve()
    if not workspace.is_dir():
        raise ValueError(f"workspace is not a directory: {workspace}")

    try:
        repo_text = git_output(workspace, "rev-parse", "--show-toplevel")
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise ValueError(f"workspace is not inside a git repository: {workspace}") from exc

    repo = Path(str(repo_text).strip()).resolve()
    scoped_relative = workspace.relative_to(repo)
    pathspec = "." if not scoped_relative.parts else scoped_relative.as_posix()
    raw = git_output(
        repo,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--",
        pathspec,
        text=False,
    )
    assert isinstance(raw, bytes)

    records = raw.split(b"\0")
    changes: list[dict[str, Any]] = []
    sensitive_excluded = 0
    ignored = 0
    total_changes = 0
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        decoded = record.decode("utf-8", errors="surrogateescape")
        if len(decoded) < 4:
            continue
        status = decoded[:2]
        path_text = decoded[3:]
        original_path = None
        if "R" in status or "C" in status:
            if index < len(records) and records[index]:
                original_path = records[index].decode("utf-8", errors="surrogateescape")
                index += 1

        repo_relative = Path(path_text)
        try:
            relative = (repo / repo_relative).relative_to(workspace)
        except ValueError:
            continue
        if is_ignored(relative):
            ignored += 1
            continue
        if is_sensitive(relative):
            sensitive_excluded += 1
            continue

        total_changes += 1
        if len(changes) >= max_changes:
            continue
        entry: dict[str, Any] = {
            "path": relative.as_posix(),
            "status": status,
            "index_status": status[0],
            "worktree_status": status[1],
        }
        if original_path is not None:
            original_repo_relative = Path(original_path)
            try:
                entry["original_path"] = (repo / original_repo_relative).relative_to(
                    workspace
                ).as_posix()
            except ValueError:
                entry["original_path"] = "[outside-scope]"
        changes.append(entry)

    return {
        "schema_version": 1,
        "observed_at": utc_now(),
        "workspace": str(workspace),
        "repository": str(repo),
        "scope": pathspec,
        "head": optional_git_output(repo, "rev-parse", "HEAD"),
        "branch": optional_git_output(repo, "rev-parse", "--abbrev-ref", "HEAD"),
        "attribution": "git-observed",
        "content_included": False,
        "changes": changes,
        "summary": {
            "total_changes": total_changes,
            "reported_changes": len(changes),
            "changes_truncated": total_changes > len(changes),
            "sensitive_paths_excluded": sensitive_excluded,
            "ignored_paths": ignored,
        },
    }


def add_scan_limits(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--max-files", type=int, default=20_000)
    parser.add_argument("--max-hash-bytes", type=int, default=5 * 1024 * 1024)
    parser.add_argument("--pretty", action="store_true")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a privacy-aware workspace snapshot, compare it with a baseline, "
            "or summarize current git state without including file contents."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot = subparsers.add_parser("snapshot", help="Write an explicit baseline JSON file")
    snapshot.add_argument("workspace", type=Path)
    snapshot.add_argument("--output", type=Path, required=True)
    snapshot.add_argument("--force", action="store_true", help="Replace an existing output file")
    add_scan_limits(snapshot)

    compare = subparsers.add_parser("compare", help="Compare current state with a baseline")
    compare.add_argument("workspace", type=Path)
    compare.add_argument("--baseline", type=Path, required=True)
    compare.add_argument("--max-changes", type=int, default=5_000)
    add_scan_limits(compare)

    git = subparsers.add_parser("git", help="Summarize scoped git status without diffs")
    git.add_argument("workspace", type=Path)
    git.add_argument("--max-changes", type=int, default=5_000)
    git.add_argument("--pretty", action="store_true")
    return parser.parse_args()


def validate_positive(name: str, value: int) -> None:
    if value < 1:
        raise ValueError(f"{name} must be positive")


def emit(result: dict[str, Any], pretty: bool) -> None:
    print(json.dumps(result, ensure_ascii=False, indent=2 if pretty else None))


def main() -> int:
    args = parse_args()
    try:
        if args.command == "snapshot":
            validate_positive("--max-files", args.max_files)
            validate_positive("--max-hash-bytes", args.max_hash_bytes)
            output = args.output.expanduser().resolve()
            if output.exists() and not args.force:
                raise ValueError(f"output already exists; pass --force to replace it: {output}")
            result = build_snapshot(
                args.workspace, args.max_files, args.max_hash_bytes, excluded_output=output
            )
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            emit(
                {
                    "schema_version": 1,
                    "snapshot_written": str(output),
                    "workspace": result["workspace"],
                    "summary": result["summary"],
                },
                args.pretty,
            )
            return 0

        if args.command == "compare":
            validate_positive("--max-files", args.max_files)
            validate_positive("--max-hash-bytes", args.max_hash_bytes)
            validate_positive("--max-changes", args.max_changes)
            baseline_path = args.baseline.expanduser().resolve()
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            current = build_snapshot(args.workspace, args.max_files, args.max_hash_bytes)
            emit(compare_snapshots(baseline, current, args.max_changes), args.pretty)
            return 0

        validate_positive("--max-changes", args.max_changes)
        emit(summarize_git(args.workspace, args.max_changes), args.pretty)
        return 0
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
