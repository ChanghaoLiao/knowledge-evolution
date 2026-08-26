#!/usr/bin/env python3
"""Install a portable repository's vendored Skill without overwriting an existing one."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path


class InstallError(RuntimeError):
    """An installation precondition was not satisfied."""


def default_destination() -> Path:
    codex_root = os.environ.get("CODEX_HOME")
    base = Path(codex_root).expanduser() if codex_root else Path.home() / ".codex"
    return base / "skills" / "knowledge-evolution"


def same_symlink(destination: Path, source: Path) -> bool:
    if not destination.is_symlink():
        return False
    try:
        return destination.resolve() == source.resolve()
    except OSError:
        return False


def install(args: argparse.Namespace) -> dict[str, object]:
    repo_root = Path(args.repository_root).expanduser().resolve()
    source = repo_root / ".agents" / "skills" / "knowledge-evolution"
    if not (source / "SKILL.md").is_file():
        raise InstallError(f"portable Skill snapshot not found: {source}")

    destination_input = (
        Path(args.destination).expanduser() if args.destination else default_destination()
    )
    # Preserve the destination path itself. Path.resolve() would follow an
    # existing symlink and make an idempotent second run look like a conflict.
    destination = Path(os.path.abspath(destination_input))
    if same_symlink(destination, source):
        return {
            "installed": False,
            "already_linked": True,
            "mode": "symlink",
            "source": str(source),
            "destination": str(destination),
        }
    if destination.exists() or destination.is_symlink():
        raise InstallError(
            f"destination already exists; refusing to overwrite: {destination}"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    mode = args.mode
    if mode == "auto":
        mode = "copy" if os.name == "nt" else "symlink"
    if mode == "symlink":
        destination.symlink_to(source, target_is_directory=True)
    else:
        shutil.copytree(source, destination)

    return {
        "installed": True,
        "already_linked": False,
        "mode": mode,
        "source": str(source),
        "destination": str(destination),
        "note": (
            "copy mode is independent and can become stale"
            if mode == "copy"
            else "symlink follows the cloned repository snapshot"
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Make a portable repository's vendored Skill globally discoverable."
    )
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--destination", help="Override the global Skill destination")
    parser.add_argument("--mode", choices=("auto", "symlink", "copy"), default="auto")
    parser.add_argument("--pretty", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = install(args)
    except (OSError, InstallError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
