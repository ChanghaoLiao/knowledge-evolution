#!/usr/bin/env python3
"""End-to-end safety tests for the dependency-free Import/Adopt pipeline."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): file_hash(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class ImportPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="knowledge-evolution-")
        self.root = Path(self.temporary.name)
        self.source_a = self.root / "source-a"
        self.source_b = self.root / "source-b"
        self.target = self.root / "target"
        self.job = self.root / "job"
        for path in (self.source_a, self.source_b, self.target):
            path.mkdir(parents=True)

        duplicate = "# Memory Governance\n\nOriginal sources must remain unchanged.\n"
        (self.source_a / "concept.md").write_text(duplicate, encoding="utf-8")
        (self.source_a / "project.md").write_text(
            "# Import Project\n\nStatus: planned\n", encoding="utf-8"
        )
        (self.source_a / ".env").write_text("SECRET=not-for-import\n", encoding="utf-8")
        (self.source_b / "concept-copy.md").write_text(duplicate, encoding="utf-8")
        (self.source_b / "decision.md").write_text(
            "# Storage decision\n\nUse Markdown files.\n", encoding="utf-8"
        )
        (self.source_b / "notes.json").write_text(
            json.dumps({"topic": "provenance", "required": True}), encoding="utf-8"
        )
        (self.source_b / "setup.txt").write_text(
            "Service setup\napi_key=TOPSECRET0123456789\n", encoding="utf-8"
        )
        self.source_hashes_before = {
            "a": tree_hashes(self.source_a),
            "b": tree_hashes(self.source_b),
        }

        self.config = self.root / "config.json"
        self.config.write_text(
            json.dumps(
                {
                    "job_id": "integration-import",
                    "target_root": str(self.target),
                    "sources": [
                        {
                            "id": "old-notes",
                            "root": str(self.source_a),
                            "mode": "import",
                        },
                        {
                            "id": "project-docs",
                            "root": str(self.source_b),
                            "mode": "import",
                        },
                    ],
                    "batch": {"max_files": 2, "max_characters": 100},
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_script(
        self, script: str, *arguments: str, expected: int = 0
    ) -> dict[str, Any]:
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / script), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            completed.returncode,
            expected,
            msg=f"{script} failed\nstdout: {completed.stdout}\nstderr: {completed.stderr}",
        )
        output = completed.stdout if completed.stdout.strip() else completed.stderr
        return json.loads(output)

    def mark_all_batches_classified(self) -> None:
        checkpoint = json.loads((self.job / "checkpoint.json").read_text(encoding="utf-8"))
        for batch_id in checkpoint["batches"]:
            self.run_script(
                "manage_import_state.py",
                "--job-dir",
                str(self.job),
                "record-batch",
                "--batch-id",
                batch_id,
                "--status",
                "classified",
            )

    @staticmethod
    def reference(chunk: dict[str, Any]) -> dict[str, str]:
        return {
            "source_id": str(chunk["source_id"]),
            "file_id": str(chunk["file_id"]),
            "chunk_id": str(chunk["chunk_id"]),
            "relative_path": str(chunk["relative_path"]),
            "locator": str(chunk["locator"]),
        }

    def test_import_is_resumable_provenance_safe_and_idempotent(self) -> None:
        registered = self.run_script(
            "register_sources.py",
            "--config",
            str(self.config),
            "--job-dir",
            str(self.job),
        )
        self.assertTrue(all(not source["writable"] for source in registered["sources"]))
        self.run_script(
            "register_sources.py",
            "--config",
            str(self.config),
            "--job-dir",
            str(self.job),
            expected=2,
        )

        inventory = self.run_script(
            "build_source_manifest.py", "--job-dir", str(self.job)
        )
        self.assertEqual(inventory["summary"]["files"], 6)
        self.assertEqual(inventory["summary"]["sensitive_files_excluded"], 1)
        self.assertFalse(inventory["sources_modified"])

        extraction = self.run_script(
            "extract_documents.py", "--job-dir", str(self.job), "--chunk-characters", "200"
        )
        self.assertEqual(extraction["summary"]["by_status"], {"extracted": 6})
        self.assertEqual(extraction["summary"]["redaction_operations"], 1)
        extracted_text = (self.job / "extracted-chunks.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("TOPSECRET0123456789", extracted_text)
        self.assertIn("[REDACTED]", extracted_text)
        self.assertFalse(extraction["source_files_modified"])
        batching = self.run_script(
            "prepare_import_batches.py", "--job-dir", str(self.job)
        )
        self.assertGreaterEqual(batching["batches"], 3)

        paused = self.run_script(
            "manage_import_state.py",
            "--job-dir",
            str(self.job),
            "pause",
            "--reason",
            "integration test",
        )
        self.assertEqual(paused["stage"], "paused")
        self.assertEqual(paused["resume_stage"], "batched")
        resumed = self.run_script(
            "manage_import_state.py", "--job-dir", str(self.job), "resume"
        )
        self.assertEqual(resumed["stage"], "batched")
        self.mark_all_batches_classified()

        chunks = [
            json.loads(line)
            for line in (self.job / "extracted-chunks.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        by_path = {chunk["relative_path"]: chunk for chunk in chunks}
        candidates = [
            {
                "candidate_id": "candidate-memory-a",
                "knowledge_type": "concept",
                "title": "Memory Governance",
                "content": "Original sources must remain unchanged.",
                "confidence": "high",
                "evidence_class": "observed",
                "source_refs": [self.reference(by_path["concept.md"])],
            },
            {
                "candidate_id": "candidate-memory-b",
                "knowledge_type": "concept",
                "title": "Memory Governance",
                "content": "Original sources must remain unchanged.",
                "confidence": "high",
                "evidence_class": "observed",
                "source_refs": [self.reference(by_path["concept-copy.md"])],
            },
            {
                "candidate_id": "candidate-storage-new",
                "knowledge_type": "decision",
                "title": "Storage decision",
                "content": "Use Markdown files.",
                "confidence": "high",
                "evidence_class": "observed",
                "source_refs": [self.reference(by_path["decision.md"])],
            },
            {
                "candidate_id": "candidate-storage-old",
                "knowledge_type": "decision",
                "title": "Storage decision",
                "content": "Use a relational database as the primary store.",
                "confidence": "low",
                "evidence_class": "inferred",
                "source_refs": [self.reference(by_path["project.md"])],
            },
        ]
        candidate_path = self.job / "candidates.jsonl"
        candidate_path.write_text(
            "".join(json.dumps(value) + "\n" for value in candidates), encoding="utf-8"
        )

        invalid = json.loads(json.dumps(candidates[0]))
        invalid["source_refs"][0]["file_id"] = candidates[2]["source_refs"][0]["file_id"]
        invalid_path = self.job / "invalid-candidates.jsonl"
        invalid_path.write_text(json.dumps(invalid) + "\n", encoding="utf-8")
        invalid_result = self.run_script(
            "manage_import_state.py",
            "--job-dir",
            str(self.job),
            "validate-candidates",
            "--file",
            str(invalid_path),
        )
        self.assertFalse(invalid_result["valid"])

        valid_result = self.run_script(
            "manage_import_state.py",
            "--job-dir",
            str(self.job),
            "validate-candidates",
            "--file",
            str(candidate_path),
            "--accept",
        )
        self.assertTrue(valid_result["valid"])
        reconciliation = self.run_script(
            "find_duplicate_candidates.py", "--job-dir", str(self.job)
        )
        self.assertEqual(reconciliation["summary"]["source_duplicate_groups"], 1)
        self.assertGreaterEqual(reconciliation["summary"]["knowledge_relations"], 2)

        knowledge_relations = [
            json.loads(line)
            for line in (self.job / "reconciliation-candidates.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        source_relations = [
            json.loads(line)
            for line in (self.job / "source-duplicates.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        decisions = self.job / "reconciliation-decisions.jsonl"
        decision_records = []
        for relation in knowledge_relations:
            decision_records.append(
                {
                    "relation_id": relation["relation_id"],
                    "decision": (
                        "merge"
                        if relation["relation"] == "exact-knowledge-duplicate"
                        else "conflict"
                        if relation["relation"] == "possible-conflict-or-version"
                        else "link"
                    ),
                    "reason": "integration reconciliation",
                }
            )
        for relation in source_relations:
            decision_records.append(
                {
                    "relation_id": relation["relation_id"],
                    "decision": "preserve-sources",
                    "reason": "source files remain unchanged",
                }
            )
        decisions.write_text(
            "".join(json.dumps(value) + "\n" for value in decision_records),
            encoding="utf-8",
        )
        self.run_script(
            "manage_import_state.py",
            "--job-dir",
            str(self.job),
            "validate-reconciliation",
            "--file",
            str(decisions),
            "--accept",
        )
        proposal = self.job / "proposal.md"
        proposal.write_text("# Approved integration proposal\n\nK-01\n", encoding="utf-8")
        self.run_script(
            "manage_import_state.py",
            "--job-dir",
            str(self.job),
            "set-stage",
            "--to",
            "proposed",
            "--reason",
            "integration proposal",
            "--artifact",
            str(proposal),
        )

        target_note = self.target / "10 Concepts" / "Memory Governance.md"
        target_note.parent.mkdir(parents=True)
        target_note.write_text(
            "# Memory Governance\n\nOriginal sources must remain unchanged.\n", encoding="utf-8"
        )
        source_file_id = str(by_path["concept.md"]["file_id"])
        first_record = self.run_script(
            "manage_import_state.py",
            "--job-dir",
            str(self.job),
            "record-application",
            "--proposal-id",
            "IMPORT-001",
            "--change-id",
            "K-01",
            "--target-path",
            "10 Concepts/Memory Governance.md",
            "--source-file-id",
            source_file_id,
        )
        second_record = self.run_script(
            "manage_import_state.py",
            "--job-dir",
            str(self.job),
            "record-application",
            "--proposal-id",
            "IMPORT-001",
            "--change-id",
            "K-01",
            "--target-path",
            "10 Concepts/Memory Governance.md",
            "--source-file-id",
            source_file_id,
        )
        self.assertTrue(first_record["recorded"])
        self.assertFalse(second_record["recorded"])
        self.assertEqual(
            len((self.job / "applied.jsonl").read_text(encoding="utf-8").splitlines()), 1
        )

        verification_path = self.job / "verification-report.json"
        verification = self.run_script(
            "verify_import.py",
            "--job-dir",
            str(self.job),
            "--output",
            str(verification_path),
            "--require-source-unchanged",
        )
        self.assertTrue(verification["clean"])
        self.assertEqual(self.source_hashes_before["a"], tree_hashes(self.source_a))
        self.assertEqual(self.source_hashes_before["b"], tree_hashes(self.source_b))

        completed = self.run_script(
            "manage_import_state.py",
            "--job-dir",
            str(self.job),
            "set-stage",
            "--to",
            "completed",
            "--reason",
            "integration verified",
            "--artifact",
            str(verification_path),
        )
        self.assertEqual(completed["stage"], "completed")

        (self.source_a / "concept.md").write_text("changed externally\n", encoding="utf-8")
        changed = self.run_script(
            "verify_import.py",
            "--job-dir",
            str(self.job),
            "--require-source-unchanged",
            expected=2,
        )
        self.assertFalse(changed["clean"])
        self.assertEqual(changed["source_preservation"]["changed_since_inventory"], 1)

    def test_adopt_and_boundary_validation(self) -> None:
        adopt_job = self.root / "adopt-job"
        config = self.root / "adopt.json"
        config.write_text(
            json.dumps(
                {
                    "target_root": str(self.target),
                    "sources": [
                        {"id": "existing-vault", "root": str(self.target), "mode": "adopt"},
                        {"id": "external-notes", "root": str(self.source_a), "mode": "import"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        registered = self.run_script(
            "register_sources.py",
            "--config",
            str(config),
            "--job-dir",
            str(adopt_job),
        )
        self.assertEqual(
            [source["mode"] for source in registered["sources"]], ["adopt", "import"]
        )

        unsafe_job = self.target / "job-inside-target"
        self.run_script(
            "register_sources.py",
            "--config",
            str(config),
            "--job-dir",
            str(unsafe_job),
            expected=2,
        )

    def test_source_change_after_inventory_is_not_extracted_as_current_evidence(self) -> None:
        self.run_script(
            "register_sources.py",
            "--config",
            str(self.config),
            "--job-dir",
            str(self.job),
        )
        self.run_script("build_source_manifest.py", "--job-dir", str(self.job))
        (self.source_a / "concept.md").write_text(
            "# Changed after inventory\n", encoding="utf-8"
        )
        extraction = self.run_script(
            "extract_documents.py", "--job-dir", str(self.job)
        )
        self.assertEqual(extraction["summary"]["by_status"]["error"], 1)
        index = [
            json.loads(line)
            for line in (self.job / "extraction-index.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        changed_record = next(
            record
            for record in index
            if record["source_id"] == "old-notes"
            and record["relative_path"] == "concept.md"
        )
        self.assertEqual(changed_record["status"], "error")
        self.assertIn("refresh manifest", changed_record["error"])
        verification = self.run_script(
            "verify_import.py",
            "--job-dir",
            str(self.job),
            "--require-source-unchanged",
            expected=2,
        )
        self.assertFalse(verification["clean"])

    def test_approved_adopt_target_update_is_not_reported_as_external_source_change(self) -> None:
        existing = self.target / "Decision.md"
        existing.write_text("# Decision\n\nUse SQLite.\n", encoding="utf-8")
        config = self.root / "adopt-apply.json"
        config.write_text(
            json.dumps(
                {
                    "job_id": "adopt-apply",
                    "target_root": str(self.target),
                    "sources": [
                        {"id": "vault", "root": str(self.target), "mode": "adopt"}
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.run_script(
            "register_sources.py",
            "--config",
            str(config),
            "--job-dir",
            str(self.job),
        )
        self.run_script("build_source_manifest.py", "--job-dir", str(self.job))
        self.run_script("extract_documents.py", "--job-dir", str(self.job))
        self.run_script("prepare_import_batches.py", "--job-dir", str(self.job))
        self.mark_all_batches_classified()
        chunk = json.loads(
            (self.job / "extracted-chunks.jsonl").read_text(encoding="utf-8").splitlines()[0]
        )
        candidate_path = self.job / "candidates.jsonl"
        candidate_path.write_text(
            json.dumps(
                {
                    "candidate_id": "candidate-decision",
                    "knowledge_type": "decision",
                    "title": "Database decision",
                    "content": "Use SQLite.",
                    "confidence": "high",
                    "evidence_class": "observed",
                    "source_refs": [self.reference(chunk)],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.run_script(
            "manage_import_state.py",
            "--job-dir",
            str(self.job),
            "validate-candidates",
            "--file",
            str(candidate_path),
            "--accept",
        )
        self.run_script("find_duplicate_candidates.py", "--job-dir", str(self.job))
        decisions = self.job / "reconciliation-decisions.jsonl"
        decisions.write_text("", encoding="utf-8")
        self.run_script(
            "manage_import_state.py",
            "--job-dir",
            str(self.job),
            "validate-reconciliation",
            "--file",
            str(decisions),
            "--accept",
        )
        proposal = self.job / "proposal.md"
        proposal.write_text("# Approved K-01\n", encoding="utf-8")
        self.run_script(
            "manage_import_state.py",
            "--job-dir",
            str(self.job),
            "set-stage",
            "--to",
            "proposed",
            "--reason",
            "approved adopt update",
            "--artifact",
            str(proposal),
        )
        existing.write_text("# Decision\n\nUse PostgreSQL.\n", encoding="utf-8")
        self.run_script(
            "manage_import_state.py",
            "--job-dir",
            str(self.job),
            "record-application",
            "--proposal-id",
            "ADOPT-001",
            "--change-id",
            "K-01",
            "--target-path",
            "Decision.md",
            "--source-file-id",
            str(chunk["file_id"]),
        )
        verification = self.run_script(
            "verify_import.py",
            "--job-dir",
            str(self.job),
            "--require-source-unchanged",
        )
        self.assertTrue(verification["clean"])
        self.assertEqual(
            verification["source_preservation"]["approved_adopt_target_changes"], 1
        )
        self.assertEqual(verification["source_preservation"]["changed_since_inventory"], 0)


if __name__ == "__main__":
    unittest.main()
