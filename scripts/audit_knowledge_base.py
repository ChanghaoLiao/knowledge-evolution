#!/usr/bin/env python3
"""Produce a bounded, read-only inventory of a Markdown knowledge base."""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
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
DEFAULT_STRUCTURE_HINTS = {
    "00 inbox",
    "10 concepts",
    "20 projects",
    "30 decisions",
    "40 experiences",
    "50 resources",
    "system",
    "inbox",
    "concepts",
    "projects",
    "decisions",
    "resources",
    "archive",
    "templates",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect a user-approved directory without modifying it and report "
            "signals useful for knowledge-base onboarding."
        )
    )
    parser.add_argument("root", type=Path, help="Approved knowledge-base root")
    parser.add_argument(
        "--max-files",
        type=int,
        default=20_000,
        help="Stop after this many non-ignored files (default: 20000)",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=30,
        help="Maximum relative Markdown paths to include (default: 30)",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    return parser.parse_args()


def read_markdown_signals(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            text = handle.read(131_072)
    except OSError as exc:
        return {"error": str(exc)}

    return {
        "frontmatter": text.startswith("---\n") or text.startswith("---\r\n"),
        "wikilinks": len(re.findall(r"\[\[[^\]]+\]\]", text)),
        "markdown_links": len(re.findall(r"\[[^\]]+\]\([^)]+\)", text)),
        "headings": len(re.findall(r"(?m)^#{1,6}\s+", text)),
    }


def recommend_route(profile: str) -> str:
    return {
        "not-found": "create-portable-markdown-space",
        "not-a-directory": "choose-a-directory",
        "empty": "initialize-minimal-structure",
        "non-markdown": "inspect-approved-import-sources",
        "unstructured-markdown": "map-in-place-before-reorganizing",
        "structured-markdown": "adopt-existing-taxonomy",
    }[profile]


def audit(root: Path, max_files: int, sample_limit: int) -> dict[str, Any]:
    requested = str(root.expanduser())
    root = root.expanduser().resolve()

    if not root.exists():
        profile = "not-found"
        return {
            "schema_version": 1,
            "root": requested,
            "profile": profile,
            "recommended_route": recommend_route(profile),
            "read_only": True,
        }
    if not root.is_dir():
        profile = "not-a-directory"
        return {
            "schema_version": 1,
            "root": str(root),
            "profile": profile,
            "recommended_route": recommend_route(profile),
            "read_only": True,
        }

    obsidian_detected = (root / ".obsidian").is_dir()
    top_level_dirs: list[str] = []
    top_level_files: list[str] = []
    for item in sorted(root.iterdir(), key=lambda value: value.name.casefold()):
        if item.name in IGNORED_FILES or item.name in IGNORED_DIRS:
            continue
        if item.name.startswith(".") and item.name != ".obsidian":
            continue
        if item.is_dir():
            top_level_dirs.append(item.name)
        elif item.is_file():
            top_level_files.append(item.name)

    markdown_paths: list[str] = []
    extension_counts: Counter[str] = Counter()
    directory_counts: Counter[str] = Counter()
    total_files = 0
    frontmatter_files = 0
    wikilinks = 0
    markdown_links = 0
    headings = 0
    read_errors = 0
    skipped_symlinks = 0
    truncated = False

    for current, dirs, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        kept_dirs = []
        for dirname in dirs:
            candidate = current_path / dirname
            if dirname in IGNORED_DIRS or dirname.startswith("."):
                continue
            if candidate.is_symlink():
                skipped_symlinks += 1
                continue
            kept_dirs.append(dirname)
        dirs[:] = sorted(kept_dirs, key=str.casefold)

        for filename in sorted(files, key=str.casefold):
            if filename in IGNORED_FILES:
                continue
            path = current_path / filename
            if path.is_symlink():
                skipped_symlinks += 1
                continue
            if total_files >= max_files:
                truncated = True
                break

            total_files += 1
            relative = path.relative_to(root)
            suffix = path.suffix.casefold() or "[no-extension]"
            extension_counts[suffix] += 1
            top_dir = relative.parts[0] if len(relative.parts) > 1 else "[root]"
            directory_counts[top_dir] += 1

            if suffix != ".md":
                continue

            if len(markdown_paths) < sample_limit:
                markdown_paths.append(relative.as_posix())
            signals = read_markdown_signals(path)
            if "error" in signals:
                read_errors += 1
                continue
            frontmatter_files += int(signals["frontmatter"])
            wikilinks += int(signals["wikilinks"])
            markdown_links += int(signals["markdown_links"])
            headings += int(signals["headings"])

        if truncated:
            break

    markdown_files = extension_counts[".md"]
    content_top_level_dirs = [name for name in top_level_dirs if name != ".obsidian"]
    visible_entries = len(content_top_level_dirs) + len(top_level_files)
    structure_hits = sorted(
        name for name in top_level_dirs if name.casefold() in DEFAULT_STRUCTURE_HINTS
    )
    structured_signal = (
        len(structure_hits) >= 2
        or (
            len(top_level_dirs) >= 3
            and markdown_files > 0
            and (frontmatter_files > 0 or wikilinks + markdown_links >= markdown_files)
        )
    )

    if visible_entries == 0 and total_files == 0:
        profile = "empty"
    elif markdown_files == 0:
        profile = "non-markdown"
    elif structured_signal:
        profile = "structured-markdown"
    else:
        profile = "unstructured-markdown"

    return {
        "schema_version": 1,
        "root": str(root),
        "profile": profile,
        "recommended_route": recommend_route(profile),
        "read_only": True,
        "obsidian_detected": obsidian_detected,
        "counts": {
            "files_scanned": total_files,
            "markdown_files": markdown_files,
            "frontmatter_files": frontmatter_files,
            "wikilinks": wikilinks,
            "markdown_links": markdown_links,
            "headings": headings,
            "read_errors": read_errors,
            "skipped_symlinks": skipped_symlinks,
        },
        "top_level": {
            "directories": top_level_dirs,
            "files": top_level_files[:sample_limit],
            "recognized_structure": structure_hits,
        },
        "files_by_extension": dict(extension_counts.most_common(20)),
        "files_by_top_directory": dict(directory_counts.most_common(20)),
        "markdown_samples": markdown_paths,
        "truncated": truncated,
        "limits": {"max_files": max_files, "sample_limit": sample_limit},
    }


def main() -> int:
    args = parse_args()
    if args.max_files < 1 or args.sample_limit < 0:
        raise SystemExit("--max-files must be positive and --sample-limit cannot be negative")
    result = audit(args.root, args.max_files, args.sample_limit)
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
