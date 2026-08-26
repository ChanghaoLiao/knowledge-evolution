#!/usr/bin/env python3
"""Inspect and safely synchronize a Git-backed knowledge repository.

The tool permits only fast-forward pulls and path-scoped commits. It never
stashes, resets, rebases, auto-merges, rewrites history, or force-pushes.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit, urlunsplit


class SyncError(RuntimeError):
    """A synchronization safety precondition was not satisfied."""


CREDENTIAL_URL = re.compile(r"(https?://)([^/@\s]+)@", re.IGNORECASE)


def redact(text: str) -> str:
    return CREDENTIAL_URL.sub(r"\1***@", text)


def run(
    command: list[str], *, cwd: Path | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and completed.returncode != 0:
        detail = redact(completed.stderr.strip() or completed.stdout.strip())
        raise SyncError(detail or f"command failed with exit code {completed.returncode}")
    return completed


def git(repo: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(["git", "-C", str(repo), *arguments], check=check)


def resolve_repo(path: str) -> Path:
    requested = Path(path).expanduser().resolve()
    if shutil.which("git") is None:
        raise SyncError("git is not installed")
    completed = git(requested, "rev-parse", "--show-toplevel", check=False)
    if completed.returncode != 0:
        raise SyncError(f"not a Git repository: {requested}")
    return Path(completed.stdout.strip()).resolve()


def branch_name(repo: Path) -> str:
    completed = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    if completed.returncode != 0 or not completed.stdout.strip():
        raise SyncError("detached HEAD is not supported for synchronization")
    return completed.stdout.strip()


def upstream_name(repo: Path) -> str | None:
    completed = git(
        repo,
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{upstream}",
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def porcelain(repo: Path) -> list[str]:
    output = git(repo, "status", "--porcelain=v1", "--untracked-files=all").stdout
    return [line for line in output.splitlines() if line]


def staged_paths(repo: Path) -> list[str]:
    output = git(repo, "diff", "--cached", "--name-only", "-z").stdout
    return [path for path in output.split("\0") if path]


def remote_url(repo: Path, name: str = "origin") -> str | None:
    completed = git(repo, "remote", "get-url", name, check=False)
    return completed.stdout.strip() if completed.returncode == 0 else None


def safe_remote_url(url: str | None) -> str | None:
    if not url:
        return None
    if url.startswith("git@") and ":" in url:
        return url
    parsed = urlsplit(url)
    if parsed.scheme in {"http", "https", "ssh"} and parsed.hostname:
        host = parsed.hostname
        if parsed.port:
            host += f":{parsed.port}"
        username = "git@" if parsed.scheme == "ssh" and parsed.username else ""
        return urlunsplit((parsed.scheme, username + host, parsed.path, "", ""))
    return redact(url)


def github_slug(url: str) -> str | None:
    path: str | None = None
    if url.startswith("git@github.com:"):
        path = url.split(":", 1)[1]
    else:
        parsed = urlsplit(url)
        if parsed.hostname and parsed.hostname.lower() == "github.com":
            path = parsed.path.lstrip("/")
    if not path:
        return None
    if path.endswith(".git"):
        path = path[:-4]
    parts = [part for part in path.split("/") if part]
    if len(parts) != 2:
        return None
    return "/".join(parts)


def status(repo: Path) -> dict[str, Any]:
    changes = porcelain(repo)
    branch = branch_name(repo)
    upstream = upstream_name(repo)
    ahead = behind = None
    if upstream:
        counts = git(
            repo, "rev-list", "--left-right", "--count", f"HEAD...{upstream}", check=False
        )
        if counts.returncode == 0:
            left, right = counts.stdout.strip().split()
            ahead, behind = int(left), int(right)
    origin = remote_url(repo)
    return {
        "repository_root": str(repo),
        "branch": branch,
        "upstream": upstream,
        "clean": not changes,
        "changes": changes,
        "ahead": ahead,
        "behind": behind,
        "origin": safe_remote_url(origin),
        "github_repository": github_slug(origin) if origin else None,
    }


def verify_private(repo: Path, remote: str = "origin") -> dict[str, Any]:
    url = remote_url(repo, remote)
    if not url:
        raise SyncError(f"remote is not configured: {remote}")
    slug = github_slug(url)
    if not slug:
        raise SyncError("private visibility verification currently supports GitHub remotes only")
    if shutil.which("gh") is None:
        raise SyncError("GitHub CLI is required to verify private repository visibility")
    completed = run(
        ["gh", "repo", "view", slug, "--json", "nameWithOwner,visibility,url"],
        check=False,
    )
    if completed.returncode != 0:
        raise SyncError(redact(completed.stderr.strip()) or "GitHub visibility lookup failed")
    try:
        metadata = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SyncError("GitHub visibility lookup returned invalid JSON") from exc
    visibility = str(metadata.get("visibility", "")).upper()
    if visibility != "PRIVATE":
        raise SyncError(f"remote visibility is {visibility or 'unknown'}, not PRIVATE")
    return {
        "repository": metadata.get("nameWithOwner", slug),
        "url": metadata.get("url"),
        "visibility": visibility,
        "private": True,
    }


def pull(repo: Path) -> dict[str, Any]:
    before = status(repo)
    if not before["clean"]:
        raise SyncError("worktree or index is dirty; refusing to pull")
    if not before["upstream"]:
        raise SyncError("current branch has no upstream; refusing to guess a pull source")
    completed = git(repo, "pull", "--ff-only")
    after = status(repo)
    return {
        "pulled": True,
        "strategy": "fast-forward-only",
        "output": redact(completed.stdout.strip()),
        "before": before,
        "after": after,
    }


def approved_path(repo: Path, raw: str) -> str:
    candidate = PurePosixPath(raw.replace("\\", "/"))
    if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
        raise SyncError(f"approved path must be relative and inside the repository: {raw}")
    if candidate.parts[0] == ".git" or str(candidate) in {".", ""}:
        raise SyncError(f"approved path is too broad or unsafe: {raw}")
    resolved = (repo / Path(*candidate.parts)).resolve()
    try:
        resolved.relative_to(repo)
    except ValueError as exc:
        raise SyncError(f"approved path escapes the repository: {raw}") from exc
    return candidate.as_posix()


def path_is_approved(path: str, approved: list[str]) -> bool:
    item = PurePosixPath(path)
    for root in approved:
        candidate = PurePosixPath(root)
        if item == candidate or candidate in item.parents:
            return True
    return False


def publish(args: argparse.Namespace, repo: Path) -> dict[str, Any]:
    branch = branch_name(repo)
    existing_staged = staged_paths(repo)
    if existing_staged:
        raise SyncError(
            "index already contains staged paths; refusing to mix them with this publication: "
            + ", ".join(existing_staged)
        )
    approved = [approved_path(repo, raw) for raw in args.path]
    approved = list(dict.fromkeys(approved))
    if not args.message.strip():
        raise SyncError("commit message must not be empty")

    privacy: dict[str, Any] | None = None
    origin = remote_url(repo)
    if args.push:
        if not origin:
            raise SyncError("origin is not configured; refusing to create a commit intended for push")
        if github_slug(origin):
            privacy = verify_private(repo)
        elif not args.allow_non_github_private_remote:
            raise SyncError(
                "non-GitHub remote privacy cannot be verified; pass "
                "--allow-non-github-private-remote only after separate verification"
            )

    git(repo, "add", "-A", "--", *approved)
    staged = staged_paths(repo)
    if not staged:
        return {
            "committed": False,
            "pushed": False,
            "reason": "no changes under approved paths",
            "approved_paths": approved,
        }
    unapproved = [path for path in staged if not path_is_approved(path, approved)]
    if unapproved:
        raise SyncError("git staged paths outside approval: " + ", ".join(unapproved))

    git(repo, "commit", "-m", args.message)
    commit = git(repo, "rev-parse", "HEAD").stdout.strip()
    pushed = False
    push_output = None
    if args.push:
        upstream = upstream_name(repo)
        if upstream:
            completed = git(repo, "push")
        else:
            completed = git(repo, "push", "--set-upstream", "origin", branch)
        pushed = True
        push_output = redact(completed.stdout.strip() or completed.stderr.strip())
    return {
        "committed": True,
        "commit": commit,
        "staged_paths": staged,
        "approved_paths": approved,
        "pushed": pushed,
        "push_output": push_output,
        "privacy_verification": privacy,
    }


def add_common(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--repo", required=True, help="Path inside the Git repository")
    subparser.add_argument("--pretty", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely inspect, fast-forward pull, verify, and publish a knowledge repository."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Report branch, upstream, remote, and changes")
    add_common(status_parser)

    pull_parser = subparsers.add_parser("pull", help="Pull only from a clean tree with --ff-only")
    add_common(pull_parser)

    private_parser = subparsers.add_parser(
        "verify-private", help="Fail closed unless the GitHub remote is private"
    )
    add_common(private_parser)
    private_parser.add_argument("--remote", default="origin")

    publish_parser = subparsers.add_parser(
        "publish", help="Commit only approved paths and optionally push without force"
    )
    add_common(publish_parser)
    publish_parser.add_argument("--path", action="append", required=True)
    publish_parser.add_argument("--message", required=True)
    publish_parser.add_argument("--push", action="store_true")
    publish_parser.add_argument(
        "--allow-non-github-private-remote",
        action="store_true",
        help="Acknowledge that a non-GitHub remote was separately verified private",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        repo = resolve_repo(args.repo)
        if args.command == "status":
            result = status(repo)
        elif args.command == "pull":
            result = pull(repo)
        elif args.command == "verify-private":
            result = verify_private(repo, args.remote)
        else:
            result = publish(args, repo)
    except (OSError, SyncError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
