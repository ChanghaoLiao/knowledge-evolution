#!/usr/bin/env python3
"""Create an approved local portable knowledge-repository layout.

This script never creates a remote repository, pushes content, moves source
files, or changes a global Codex installation.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
SKILL_FILES = ("SKILL.md", "LICENSE")
SKILL_DIRECTORIES = ("agents", "assets", "references", "scripts")
DEFAULT_KNOWLEDGE_DIRECTORIES = (
    "00 Inbox",
    "10 Concepts",
    "20 Projects",
    "30 Decisions",
    "40 Experiences",
    "50 Resources",
    "System/Proposals",
    "System/Profile",
)
SENSITIVE_COPY_PATTERNS = (
    ".env",
    ".env.*",
    ".git-credentials",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "*.key",
    "*.pem",
    "*.p12",
    "*.pfx",
    "*credential*",
    "*credentials*",
    "*secret*",
    "*token*",
)


class PortableRepositoryError(RuntimeError):
    """A safe scaffold precondition was not satisfied."""


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def ensure_empty_destination(repo_root: Path) -> None:
    if repo_root.exists() and not repo_root.is_dir():
        raise PortableRepositoryError(f"repository root is not a directory: {repo_root}")
    if repo_root.exists() and any(repo_root.iterdir()):
        raise PortableRepositoryError(
            f"repository root must be new or empty; refusing to overwrite: {repo_root}"
        )
    repo_root.mkdir(parents=True, exist_ok=True)


def copy_skill_snapshot(source: Path, destination: Path) -> list[str]:
    source = source.resolve()
    if not (source / "SKILL.md").is_file():
        raise PortableRepositoryError(f"skill source has no SKILL.md: {source}")
    destination.mkdir(parents=True, exist_ok=False)
    copied: list[str] = []
    for name in SKILL_FILES:
        item = source / name
        if item.is_file():
            shutil.copy2(item, destination / name)
            copied.append(name)
    for name in SKILL_DIRECTORIES:
        item = source / name
        if item.is_dir():
            shutil.copytree(
                item,
                destination / name,
                ignore=shutil.ignore_patterns(
                    ".DS_Store", "__pycache__", "*.pyc", ".pytest_cache", ".git"
                ),
            )
            copied.append(name + "/")
    return copied


def write_new(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def copy_new(source: Path, destination: Path) -> bool:
    if destination.exists():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True


def copy_knowledge_tree(source: Path, destination: Path) -> list[str]:
    excluded: list[str] = []

    def ignore(directory: str, names: list[str]) -> set[str]:
        current = Path(directory)
        relative_dir = current.relative_to(source)
        ignored: set[str] = set()
        for name in names:
            item = current / name
            relative = (relative_dir / name).as_posix()
            lowered = name.lower()
            should_ignore = (
                item.is_symlink()
                or name == ".git"
                or name in {".DS_Store", "Thumbs.db"}
                or any(fnmatch.fnmatch(lowered, pattern.lower()) for pattern in SENSITIVE_COPY_PATTERNS)
                or (
                    relative_dir.as_posix() == ".obsidian"
                    and fnmatch.fnmatch(lowered, "workspace*.json")
                )
                or relative == ".obsidian/cache"
                or relative.startswith(".obsidian/cache/")
            )
            if should_ignore:
                ignored.add(name)
                excluded.append(relative)
        return ignored

    shutil.copytree(source, destination, ignore=ignore, symlinks=True)
    return sorted(set(excluded))


def configured_knowledge_template(
    template: str,
    status: str,
    route: str,
    proposal_id: str | None,
    initialized_at: str | None,
) -> str:
    result = template
    result = result.replace('  status: "uninitialized"', f'  status: "{status}"', 1)
    result = result.replace("  route: null", f'  route: "{route}"', 1)
    if proposal_id:
        result = result.replace("  proposal_id: null", f'  proposal_id: "{proposal_id}"', 1)
    if initialized_at:
        result = result.replace(
            "  initialized_at: null", f'  initialized_at: "{initialized_at}"', 1
        )
    result = result.replace("  enabled: false", "  enabled: true", 1)
    result = result.replace('  mode: "local"', '  mode: "git"', 1)
    result = result.replace("  repository_root: null", '  repository_root: "."', 1)
    result = result.replace('  knowledge_root: "."', '  knowledge_root: "Knowledge"', 1)
    result = result.replace(
        "  skill_snapshot: null",
        '  skill_snapshot: ".agents/skills/knowledge-evolution"',
        1,
    )
    result = result.replace("  device_config: null", '  device_config: ".local/device.yaml"', 1)
    result = result.replace("    provider: null", '    provider: "github"', 1)
    result = result.replace(
        "    pull_before_proposal: false", "    pull_before_proposal: true", 1
    )
    return result


def initialize_git(repo_root: Path) -> None:
    if shutil.which("git") is None:
        raise PortableRepositoryError("git is not installed; rerun with --no-git-init")
    completed = subprocess.run(
        ["git", "init", "-b", "main", str(repo_root)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        fallback = subprocess.run(
            ["git", "init", str(repo_root)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if fallback.returncode != 0:
            raise PortableRepositoryError(fallback.stderr.strip() or "git init failed")


def scaffold(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(args.repo_root).expanduser().resolve()
    skill_source = Path(args.skill_source).expanduser().resolve()
    knowledge_source = (
        Path(args.knowledge_source).expanduser().resolve()
        if args.knowledge_source
        else None
    )

    if knowledge_source and not args.copy_knowledge:
        raise PortableRepositoryError(
            "--knowledge-source requires --copy-knowledge; source material is never copied implicitly"
        )
    if knowledge_source and not knowledge_source.is_dir():
        raise PortableRepositoryError(f"knowledge source is not a directory: {knowledge_source}")
    if knowledge_source and (
        is_relative_to(repo_root, knowledge_source)
        or is_relative_to(knowledge_source, repo_root)
    ):
        raise PortableRepositoryError("knowledge source and repository root must not overlap")
    if args.bootstrap_status != "uninitialized" and (
        not args.proposal_id or not args.initialized_at
    ):
        raise PortableRepositoryError(
            "--proposal-id and --initialized-at are required when marking Bootstrap initialized or adopted"
        )
    if args.initialized_at:
        try:
            datetime.fromisoformat(args.initialized_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PortableRepositoryError(
                "--initialized-at must be an ISO 8601 date or timestamp"
            ) from exc

    ensure_empty_destination(repo_root)
    templates = skill_source / "assets" / "templates"
    portable_assets = skill_source / "assets" / "portable-repository"
    if not templates.is_dir() or not portable_assets.is_dir():
        raise PortableRepositoryError("skill source is missing portability templates")

    snapshot = repo_root / ".agents" / "skills" / "knowledge-evolution"
    copied_skill = copy_skill_snapshot(skill_source, snapshot)

    knowledge_root = repo_root / "Knowledge"
    if knowledge_source:
        knowledge_copy_exclusions = copy_knowledge_tree(knowledge_source, knowledge_root)
        knowledge_mode = "copied"
    else:
        knowledge_root.mkdir(parents=True)
        knowledge_copy_exclusions = []
        knowledge_mode = "created"
    for relative in DEFAULT_KNOWLEDGE_DIRECTORIES:
        (knowledge_root / relative).mkdir(parents=True, exist_ok=True)

    root_readme = (portable_assets / "README.md").read_text(encoding="utf-8")
    root_readme = root_readme.replace("{{REPOSITORY_NAME}}", args.name)
    write_new(repo_root / "README.md", root_readme)
    copy_new(portable_assets / "AGENTS.md", repo_root / "AGENTS.md")
    copy_new(portable_assets / "gitignore", repo_root / ".gitignore")

    copy_new(
        templates / "git-portability.yaml",
        repo_root / ".knowledge-evolution" / "portability.yaml",
    )
    copy_new(
        templates / "device-config.yaml.example",
        repo_root / ".local" / "device.yaml.example",
    )
    write_new(
        repo_root / ".local" / "device.yaml",
        'device_id: null\nsource_paths: {}\n',
    )

    system_root = knowledge_root / "System"
    config_template = (templates / "knowledge-evolution.yaml").read_text(encoding="utf-8")
    configured_config = configured_knowledge_template(
        config_template,
        args.bootstrap_status,
        args.bootstrap_route,
        args.proposal_id,
        args.initialized_at,
    )
    copy_new(templates / "knowledge-map.md", system_root / "Knowledge Map.md")
    copy_new(templates / "source-registry.md", system_root / "Source Registry.md")
    copy_new(templates / "change-ledger.md", system_root / "Change Ledger.md")
    copy_new(templates / "user-profile.md", system_root / "Profile" / "User Profile.md")
    copy_new(
        templates / "knowledge-preferences.md",
        system_root / "Profile" / "Knowledge Preferences.md",
    )

    if not args.no_git_init:
        initialize_git(repo_root)
    config_created = write_new(
        system_root / "knowledge-evolution.yaml", configured_config
    )

    return {
        "repository_root": str(repo_root),
        "knowledge_root": str(knowledge_root),
        "knowledge_mode": knowledge_mode,
        "knowledge_copy_exclusions": knowledge_copy_exclusions,
        "source_preserved": str(knowledge_source) if knowledge_source else None,
        "skill_snapshot": str(snapshot),
        "skill_snapshot_items": copied_skill,
        "bootstrap_status": args.bootstrap_status,
        "knowledge_config_created": config_created,
        "git_initialized": not args.no_git_init,
        "remote_created": False,
        "pushed": False,
        "next_actions": [
            "review generated files and device-local exclusions",
            "create or connect a private remote only after separate approval",
            "verify remote privacy before the first push",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a local portable Knowledge Evolution repository without creating or pushing a remote."
    )
    parser.add_argument("--repo-root", required=True, help="New or empty destination directory")
    parser.add_argument("--name", default="Personal Knowledge", help="Repository display name")
    parser.add_argument(
        "--skill-source",
        default=str(SKILL_ROOT),
        help="Validated Knowledge Evolution Skill source; defaults to this installed Skill",
    )
    parser.add_argument("--knowledge-source", help="Existing knowledge directory to copy")
    parser.add_argument(
        "--copy-knowledge",
        action="store_true",
        help="Explicitly authorize copying --knowledge-source; the source remains unchanged",
    )
    parser.add_argument(
        "--bootstrap-status",
        choices=("uninitialized", "initialized", "adopted"),
        default="uninitialized",
    )
    parser.add_argument(
        "--bootstrap-route", choices=("create", "adopt", "import"), default="create"
    )
    parser.add_argument("--proposal-id", help="Approved Bootstrap proposal ID")
    parser.add_argument(
        "--initialized-at",
        help="Approved initialization date or timestamp; required for initialized/adopted",
    )
    parser.add_argument(
        "--no-git-init", action="store_true", help="Create files without running local git init"
    )
    parser.add_argument("--pretty", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = scaffold(args)
    except (OSError, PortableRepositoryError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
