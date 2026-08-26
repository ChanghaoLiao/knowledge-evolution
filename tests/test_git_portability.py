from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class GitPortabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_script(
        self, name: str, *arguments: str, expected: int = 0
    ) -> tuple[dict[str, object], subprocess.CompletedProcess[str]]:
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / name), *arguments],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            expected,
            msg=f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )
        stream = completed.stdout if expected == 0 else completed.stderr
        return json.loads(stream), completed

    def git(self, repo: Path | None, *arguments: str) -> str:
        command = ["git"]
        if repo is not None:
            command.extend(["-C", str(repo)])
        command.extend(arguments)
        completed = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            msg=f"command: {command}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )
        return completed.stdout.strip()

    def configure_identity(self, repo: Path) -> None:
        self.git(repo, "config", "user.name", "Knowledge Evolution Tests")
        self.git(repo, "config", "user.email", "tests@example.invalid")

    def test_scaffold_copies_existing_knowledge_without_modifying_source(self) -> None:
        source = self.root / "source-vault"
        source.mkdir()
        note = source / "Existing.md"
        note.write_text("# Existing\n\nPreserve this source.\n", encoding="utf-8")
        secret = source / ".env"
        secret.write_text("EXAMPLE_SECRET=must-not-copy\n", encoding="utf-8")
        nested_git = source / ".git"
        nested_git.mkdir()
        (nested_git / "config").write_text("private metadata\n", encoding="utf-8")
        outside = self.root / "outside.txt"
        outside.write_text("outside scope\n", encoding="utf-8")
        (source / "outside-link").symlink_to(outside)
        before = digest(note)
        secret_before = digest(secret)
        repository = self.root / "portable"

        result, _ = self.run_script(
            "create_portable_repository.py",
            "--repo-root",
            str(repository),
            "--name",
            "Test Knowledge",
            "--knowledge-source",
            str(source),
            "--copy-knowledge",
            "--bootstrap-status",
            "adopted",
            "--bootstrap-route",
            "adopt",
            "--proposal-id",
            "BOOTSTRAP-TEST-001",
            "--initialized-at",
            "2026-08-25",
            "--no-git-init",
        )

        self.assertEqual(result["knowledge_mode"], "copied")
        self.assertEqual(before, digest(note))
        self.assertEqual(secret_before, digest(secret))
        self.assertEqual(before, digest(repository / "Knowledge" / "Existing.md"))
        self.assertFalse((repository / "Knowledge" / ".env").exists())
        self.assertFalse((repository / "Knowledge" / ".git").exists())
        self.assertFalse((repository / "Knowledge" / "outside-link").exists())
        self.assertEqual(
            result["knowledge_copy_exclusions"], [".env", ".git", "outside-link"]
        )
        self.assertTrue(
            (repository / ".agents" / "skills" / "knowledge-evolution" / "SKILL.md").is_file()
        )
        self.assertFalse((repository / ".agents" / "skills" / "knowledge-evolution" / ".git").exists())
        self.assertTrue((repository / "Knowledge" / "System" / "Profile" / "User Profile.md").is_file())
        self.assertTrue((repository / ".local" / "device.yaml").is_file())
        self.assertIn(".local/device.yaml", (repository / ".gitignore").read_text(encoding="utf-8"))
        config = (repository / "Knowledge" / "System" / "knowledge-evolution.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn('status: "adopted"', config)
        self.assertIn('proposal_id: "BOOTSTRAP-TEST-001"', config)
        self.assertIn('initialized_at: "2026-08-25"', config)
        self.assertIn('mode: "git"', config)
        self.assertFalse((repository / ".git").exists())

    def test_scaffold_requires_explicit_copy_authorization(self) -> None:
        source = self.root / "source"
        source.mkdir()
        result, _ = self.run_script(
            "create_portable_repository.py",
            "--repo-root",
            str(self.root / "destination"),
            "--knowledge-source",
            str(source),
            "--no-git-init",
            expected=2,
        )
        self.assertIn("never copied implicitly", str(result["error"]))

    def test_installer_is_idempotent_for_same_link_and_refuses_overwrite(self) -> None:
        repository = self.root / "portable"
        self.run_script(
            "create_portable_repository.py",
            "--repo-root",
            str(repository),
            "--no-git-init",
        )
        destination = self.root / "global-skills" / "knowledge-evolution"
        first, _ = self.run_script(
            "install_portable_skill.py",
            "--repository-root",
            str(repository),
            "--destination",
            str(destination),
            "--mode",
            "symlink",
        )
        second, _ = self.run_script(
            "install_portable_skill.py",
            "--repository-root",
            str(repository),
            "--destination",
            str(destination),
            "--mode",
            "symlink",
        )
        self.assertTrue(first["installed"])
        self.assertTrue(second["already_linked"])
        self.assertEqual(
            destination.resolve(),
            (repository / ".agents" / "skills" / "knowledge-evolution").resolve(),
        )

        conflicting = self.root / "conflicting-skill"
        conflicting.mkdir()
        result, _ = self.run_script(
            "install_portable_skill.py",
            "--repository-root",
            str(repository),
            "--destination",
            str(conflicting),
            expected=2,
        )
        self.assertIn("refusing to overwrite", str(result["error"]))

    def test_sync_pull_and_scoped_publish(self) -> None:
        remote = self.root / "remote.git"
        first = self.root / "first"
        second = self.root / "second"
        self.git(None, "init", "--bare", str(remote))
        self.git(None, "init", "-b", "main", str(first))
        self.configure_identity(first)
        (first / "Knowledge").mkdir()
        note = first / "Knowledge" / "Note.md"
        note.write_text("# Note\n\nVersion one.\n", encoding="utf-8")
        self.git(first, "add", "Knowledge/Note.md")
        self.git(first, "commit", "-m", "initial knowledge")
        self.git(first, "remote", "add", "origin", str(remote))
        self.git(first, "push", "--set-upstream", "origin", "main")
        self.git(None, "clone", "--branch", "main", str(remote), str(second))
        self.configure_identity(second)

        note.write_text("# Note\n\nVersion two.\n", encoding="utf-8")
        self.git(first, "add", "Knowledge/Note.md")
        self.git(first, "commit", "-m", "update knowledge")
        self.git(first, "push")

        pulled, _ = self.run_script(
            "sync_knowledge_repository.py", "pull", "--repo", str(second)
        )
        self.assertTrue(pulled["pulled"])
        self.assertIn("Version two", (second / "Knowledge" / "Note.md").read_text(encoding="utf-8"))

        dirty = second / "local-draft.txt"
        dirty.write_text("not approved\n", encoding="utf-8")
        blocked, _ = self.run_script(
            "sync_knowledge_repository.py",
            "pull",
            "--repo",
            str(second),
            expected=2,
        )
        self.assertIn("dirty", str(blocked["error"]))

        second_note = second / "Knowledge" / "Note.md"
        second_note.write_text("# Note\n\nVersion three.\n", encoding="utf-8")
        published, _ = self.run_script(
            "sync_knowledge_repository.py",
            "publish",
            "--repo",
            str(second),
            "--path",
            "Knowledge/Note.md",
            "--message",
            "knowledge: approved K-01",
        )
        self.assertTrue(published["committed"])
        self.assertFalse(published["pushed"])
        self.assertTrue(dirty.exists())
        self.assertEqual(
            self.git(second, "show", "--pretty=format:", "--name-only", "HEAD"),
            "Knowledge/Note.md",
        )

        second_note.write_text("# Note\n\nVersion four.\n", encoding="utf-8")
        pushed, _ = self.run_script(
            "sync_knowledge_repository.py",
            "publish",
            "--repo",
            str(second),
            "--path",
            "Knowledge/Note.md",
            "--message",
            "knowledge: approved K-02",
            "--push",
            "--allow-non-github-private-remote",
        )
        self.assertTrue(pushed["pushed"])
        self.assertEqual(
            self.git(second, "rev-parse", "HEAD"),
            self.git(None, "--git-dir", str(remote), "rev-parse", "refs/heads/main"),
        )


if __name__ == "__main__":
    unittest.main()
