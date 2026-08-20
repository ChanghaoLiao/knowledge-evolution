#!/usr/bin/env python3
"""Extract normalized, provenance-linked chunks from an Import/Adopt manifest."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree

from _import_common import (
    artifact_sha256,
    iter_jsonl,
    load_checkpoint,
    load_job,
    record_event,
    redact_sensitive_text,
    resolve_source_file,
    set_stage,
    sha256_file,
    sha256_text,
    stable_id,
    write_jsonl,
)


class VisibleHTMLParser(HTMLParser):
    BLOCK_TAGS = {
        "article",
        "blockquote",
        "br",
        "div",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "li",
        "main",
        "p",
        "section",
        "table",
        "td",
        "th",
        "tr",
    }
    HIDDEN_TAGS = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.HIDDEN_TAGS:
            self.hidden_depth += 1
        elif not self.hidden_depth and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.HIDDEN_TAGS and self.hidden_depth:
            self.hidden_depth -= 1
        elif not self.hidden_depth and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)

    def text(self) -> str:
        return "\n".join(line.strip() for line in "".join(self.parts).splitlines() if line.strip())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract text into JSONL chunks while retaining source, file, and locator IDs. "
            "Source files remain read-only. PDF extraction uses pypdf/PyPDF2 or pdftotext when available."
        )
    )
    parser.add_argument("--job-dir", type=Path, required=True)
    parser.add_argument("--chunk-characters", type=int, default=8_000)
    parser.add_argument("--max-characters-per-file", type=int, default=2_000_000)
    parser.add_argument("--max-total-characters", type=int, default=50_000_000)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args()


def decode_text(path: Path, max_characters: int) -> tuple[str, str, bool]:
    max_bytes = max_characters * 4
    with path.open("rb") as handle:
        raw = handle.read(max_bytes + 1)
    byte_truncated = len(raw) > max_bytes
    if byte_truncated:
        raw = raw[:max_bytes]
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16")
        truncated = byte_truncated or len(text) > max_characters
        return text[:max_characters], "utf-16", truncated
    if raw and raw.count(b"\0") / len(raw) > 0.01:
        raise ValueError("file appears to be binary")
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = raw.decode(encoding)
            truncated = byte_truncated or len(text) > max_characters
            return text[:max_characters], encoding, truncated
        except UnicodeDecodeError:
            continue
    raise ValueError("unable to decode text")


def line_segments(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    return [(f"lines:{index}-{index}", line) for index, line in enumerate(lines, start=1) if line.strip()]


def notebook_segments(text: str) -> list[tuple[str, str]]:
    notebook = json.loads(text)
    result: list[tuple[str, str]] = []
    for index, cell in enumerate(notebook.get("cells", []), start=1):
        source = cell.get("source", [])
        value = "".join(source) if isinstance(source, list) else str(source)
        if value.strip():
            result.append((f"cell:{index}:{cell.get('cell_type', 'unknown')}", value))
    return result


def html_segments(text: str) -> list[tuple[str, str]]:
    parser = VisibleHTMLParser()
    parser.feed(text)
    return line_segments(parser.text())


def docx_segments(path: Path) -> list[tuple[str, str]]:
    with zipfile.ZipFile(path) as archive:
        document_xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(document_xml)
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    result: list[tuple[str, str]] = []
    paragraph_index = 0
    for paragraph in root.iter(f"{namespace}p"):
        paragraph_index += 1
        text = "".join(node.text or "" for node in paragraph.iter(f"{namespace}t"))
        if text.strip():
            result.append((f"paragraph:{paragraph_index}", text))
    return result


def pdf_segments(path: Path) -> tuple[list[tuple[str, str]], str]:
    reader_class = None
    backend = ""
    try:
        from pypdf import PdfReader  # type: ignore

        reader_class = PdfReader
        backend = "pypdf"
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore

            reader_class = PdfReader
            backend = "PyPDF2"
        except ImportError:
            reader_class = None
    if reader_class is not None:
        reader = reader_class(str(path))
        pages: list[tuple[str, str]] = []
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append((f"page:{index}", text))
        return pages, backend

    executable = shutil.which("pdftotext")
    if executable:
        completed = subprocess.run(
            [executable, "-layout", str(path), "-"],
            check=True,
            capture_output=True,
            text=True,
        )
        pages = completed.stdout.split("\f")
        return [
            (f"page:{index}", page)
            for index, page in enumerate(pages, start=1)
            if page.strip()
        ], "pdftotext"
    raise RuntimeError("PDF extractor unavailable; install pypdf or pdftotext")


def cap_segments(
    segments: Iterable[tuple[str, str]], max_characters: int
) -> tuple[list[tuple[str, str]], bool]:
    result: list[tuple[str, str]] = []
    used = 0
    truncated = False
    for locator, text in segments:
        if used >= max_characters:
            truncated = True
            break
        remaining = max_characters - used
        value = text[:remaining]
        if len(value) < len(text):
            truncated = True
        if value.strip():
            result.append((locator, value))
            used += len(value)
        if truncated:
            break
    return result, truncated


def combine_segments(
    segments: list[tuple[str, str]], chunk_characters: int
) -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []
    locators: list[str] = []
    parts: list[str] = []
    size = 0
    for locator, text in segments:
        value = text.strip()
        if not value:
            continue
        if parts and size + len(value) + 1 > chunk_characters:
            chunks.append((f"{locators[0]}..{locators[-1]}", "\n".join(parts)))
            locators, parts, size = [], [], 0
        while len(value) > chunk_characters:
            if parts:
                chunks.append((f"{locators[0]}..{locators[-1]}", "\n".join(parts)))
                locators, parts, size = [], [], 0
            chunks.append((locator, value[:chunk_characters]))
            value = value[chunk_characters:]
        if value:
            locators.append(locator)
            parts.append(value)
            size += len(value) + 1
    if parts:
        chunks.append((f"{locators[0]}..{locators[-1]}", "\n".join(parts)))
    return chunks


def extract_record(
    path: Path,
    record: dict[str, Any],
    max_characters: int,
) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    extractor = record["extractor"]
    metadata: dict[str, Any] = {"backend": extractor, "truncated": False}
    if extractor == "unsupported":
        return [], {**metadata, "status": "unsupported"}
    if extractor in {"text", "structured-text", "html", "ipynb"}:
        text, encoding, truncated = decode_text(path, max_characters)
        metadata.update({"encoding": encoding, "truncated": truncated})
        if extractor == "html":
            segments = html_segments(text)
        elif extractor == "ipynb":
            segments = notebook_segments(text)
        else:
            segments = line_segments(text)
        return segments, {**metadata, "status": "extracted"}
    if extractor == "docx":
        segments, truncated = cap_segments(docx_segments(path), max_characters)
        return segments, {**metadata, "status": "extracted", "truncated": truncated}
    if extractor == "pdf":
        segments, backend = pdf_segments(path)
        segments, truncated = cap_segments(segments, max_characters)
        return segments, {
            **metadata,
            "status": "extracted",
            "backend": backend,
            "truncated": truncated,
        }
    return [], {**metadata, "status": "unsupported"}


def main() -> int:
    args = parse_args()
    try:
        if min(args.chunk_characters, args.max_characters_per_file, args.max_total_characters) < 1:
            raise ValueError("character limits must be positive")
        job_dir = args.job_dir.expanduser().resolve()
        job = load_job(job_dir)
        checkpoint = load_checkpoint(job_dir)
        if checkpoint.get("stage") not in {"inventoried", "extracted"} and not args.refresh:
            raise ValueError(
                f"job is at stage {checkpoint.get('stage')}; pass --refresh to rebuild extraction"
            )
        manifest_path = job_dir / "source-manifest.jsonl"
        if not manifest_path.exists():
            raise ValueError("source-manifest.jsonl is missing")
        manifest_hash = artifact_sha256(manifest_path)
        expected_hash = checkpoint.get("artifacts", {}).get("source_manifest_sha256")
        if expected_hash and manifest_hash != expected_hash:
            raise ValueError("source manifest changed outside the pipeline")

        chunk_records: list[dict[str, Any]] = []
        index_records: list[dict[str, Any]] = []
        total_characters = 0
        total_redactions = 0
        counts: dict[str, int] = {}
        for record in iter_jsonl(manifest_path):
            status = "error"
            try:
                if total_characters >= args.max_total_characters:
                    metadata = {"status": "deferred", "reason": "max-total-characters reached"}
                    chunks: list[tuple[str, str]] = []
                else:
                    path = resolve_source_file(job, record)
                    if record.get("sha256"):
                        if sha256_file(path) != record["sha256"]:
                            raise ValueError("source changed after inventory; refresh manifest")
                    else:
                        stat = path.stat()
                        if (stat.st_size, stat.st_mtime_ns) != (
                            record.get("size"),
                            record.get("mtime_ns"),
                        ):
                            raise ValueError("source changed after inventory; refresh manifest")
                    segments, metadata = extract_record(path, record, args.max_characters_per_file)
                    redacted_segments: list[tuple[str, str]] = []
                    file_redactions = 0
                    for locator, text in segments:
                        redacted, redactions = redact_sensitive_text(text)
                        redacted_segments.append((locator, redacted))
                        file_redactions += redactions
                    segments = redacted_segments
                    metadata["redaction_operations"] = file_redactions
                    total_redactions += file_redactions
                    chunks = combine_segments(segments, args.chunk_characters)
                status = str(metadata["status"])
                file_chunk_count = 0
                file_characters = 0
                for chunk_index, (locator, text) in enumerate(chunks, start=1):
                    remaining = args.max_total_characters - total_characters
                    if remaining <= 0:
                        metadata["truncated"] = True
                        break
                    value = text[:remaining]
                    chunk_id = stable_id("chunk", record["file_id"], str(chunk_index), sha256_text(value))
                    chunk_records.append(
                        {
                            "schema_version": 1,
                            "chunk_id": chunk_id,
                            "file_id": record["file_id"],
                            "source_id": record["source_id"],
                            "source_mode": record["source_mode"],
                            "relative_path": record["relative_path"],
                            "locator": locator,
                            "text": value,
                            "character_count": len(value),
                            "content_sha256": sha256_text(value),
                        }
                    )
                    total_characters += len(value)
                    file_characters += len(value)
                    file_chunk_count += 1
                index_records.append(
                    {
                        "schema_version": 1,
                        "file_id": record["file_id"],
                        "source_id": record["source_id"],
                        "relative_path": record["relative_path"],
                        "extractor": record["extractor"],
                        "status": status,
                        "backend": metadata.get("backend"),
                        "encoding": metadata.get("encoding"),
                        "truncated": bool(metadata.get("truncated")),
                        "redaction_operations": int(metadata.get("redaction_operations", 0)),
                        "chunks": file_chunk_count,
                        "characters": file_characters,
                        "manifest_sha256": manifest_hash,
                    }
                )
            except Exception as exc:
                index_records.append(
                    {
                        "schema_version": 1,
                        "file_id": record["file_id"],
                        "source_id": record["source_id"],
                        "relative_path": record["relative_path"],
                        "extractor": record["extractor"],
                        "status": "error",
                        "error": str(exc),
                        "chunks": 0,
                        "characters": 0,
                        "manifest_sha256": manifest_hash,
                    }
                )
                status = "error"
            counts[status] = counts.get(status, 0) + 1

        chunks_path = job_dir / "extracted-chunks.jsonl"
        index_path = job_dir / "extraction-index.jsonl"
        write_jsonl(chunks_path, chunk_records)
        write_jsonl(index_path, index_records)
        chunks_hash = artifact_sha256(chunks_path)
        index_hash = artifact_sha256(index_path)
        summary = {
            "files": len(index_records),
            "chunks": len(chunk_records),
            "characters": total_characters,
            "redaction_operations": total_redactions,
            "by_status": counts,
        }
        set_stage(
            job_dir,
            "extracted",
            artifact_updates={
                "extraction_index": "extraction-index.jsonl",
                "extraction_index_sha256": index_hash,
                "extracted_chunks": "extracted-chunks.jsonl",
                "extracted_chunks_sha256": chunks_hash,
                "extraction_manifest_sha256": manifest_hash,
                "downstream_stale": bool(args.refresh),
            },
            summary_updates={"extraction": summary},
        )
        record_event(job_dir, "documents-extracted", summary)
        print(
            json.dumps(
                {
                    "job_id": job["job_id"],
                    "stage": "extracted",
                    "source_files_modified": False,
                    "summary": summary,
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
