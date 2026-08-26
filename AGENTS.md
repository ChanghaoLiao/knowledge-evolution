# Knowledge Evolution Skill Workspace

## Purpose

Maintain the public `knowledge-evolution` Codex Skill. It turns conversations, Agent actions, workspace changes, and approved source folders into governed personal-knowledge updates.

## Non-negotiable product decisions

- Keep Obsidian optional. A normal Markdown directory must be a complete knowledge base.
- Bootstrap first-time users before attempting routine updates.
- Support Create, Adopt, and Import as distinct Bootstrap routes.
- Observe both the conversation and the user-approved workspace.
- Separate facts observed in files from intentions stated in conversation and from Agent inference.
- Propose knowledge-base changes before applying them. Require explicit review by default.
- Adapt to an existing knowledge structure; never reorganize a mature vault automatically.
- Register existing sources as read-only, retain provenance, and process large imports in resumable classification batches.
- Keep Import/Adopt job state outside source and target content; write to the target only after proposal approval.
- Keep local-only behavior as the default and offer private Git portability as an optional deployment layer, not a knowledge mode.
- Keep the public Skill generic. Store personal profile, knowledge, and device mappings outside any vendored repository-scoped Skill snapshot.
- Separate approval for local knowledge writes, source copies, local Git initialization, remote creation, global Skill installation, commit, and push.
- Pull only from a clean worktree with fast-forward-only behavior. Never force-push or auto-resolve Git conflicts.
- Require verified `PRIVATE` GitHub visibility before the first knowledge push; fail closed when verification is unavailable.
- Avoid secrets, credentials, private keys, and unrelated personal data.
- Use a dedicated temporary knowledge root for testing; never point tests at a live personal vault.

## Repository map

- `SKILL.md`: concise runtime workflow and resource routing.
- `README.md`: public installation, usage, architecture, lifecycle, safety, and troubleshooting guide requested by the product owner.
- `references/`: detailed rules loaded only for the relevant workflow, including optional Git portability.
- `assets/templates/`: reusable knowledge-base, portability, device-config, job, and proposal templates.
- `assets/portable-repository/`: files copied into a newly approved private personal-knowledge repository.
- `scripts/`: read-only inspection, Import/Adopt state, portable-repository creation, safe Git sync, deterministic batching, reconciliation-shortlist, and verification utilities.
- `tests/`: temporary-fixture integration tests for source preservation, resume, provenance, idempotency, portable setup, and safe Git behavior.
- `docs/images/`: product screenshots used by the public README.
- `agents/openai.yaml`: Codex UI metadata generated from `SKILL.md`.

## Development rules

- Keep `SKILL.md` below 500 lines and link every optional reference directly from it.
- Keep detailed schemas and examples out of `SKILL.md`.
- Use only the Python standard library in bundled scripts unless a dependency is essential and documented.
- Make inspection commands read-only. Permit writes only for an explicitly supplied state artifact or an approved knowledge update.
- Keep deterministic filesystem work in scripts and semantic classification/reconciliation in the Agent. Scripts must not claim semantic truth.
- Preserve registered source files. Tests must compare source hashes before and after the pipeline.
- Keep job commands resumable and application recording idempotent.
- Keep portable-repository creation local-only. Remote creation and publication remain separate external operations.
- Never overwrite an existing global Skill during portable installation.
- Never put raw Import extraction state, device-local absolute paths, Obsidian workspace state, or credentials into a generated Git repository.
- Test scripts against temporary fixtures, never against a live personal vault.
- Keep the requested public `README.md` accurate, but do not add redundant quick-reference or changelog files.
- Do not publish generated job state, extracted private text, credentials, or user knowledge-base contents.

## Validation

Run:

```text
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" .
python3 -m unittest discover -s tests -v
python3 scripts/audit_knowledge_base.py --help
python3 scripts/workspace_changes.py --help
python3 scripts/create_portable_repository.py --help
python3 scripts/install_portable_skill.py --help
python3 scripts/sync_knowledge_repository.py --help
python3 scripts/register_sources.py --help
python3 scripts/build_source_manifest.py --help
python3 scripts/extract_documents.py --help
python3 scripts/prepare_import_batches.py --help
python3 scripts/manage_import_state.py --help
python3 scripts/find_duplicate_candidates.py --help
python3 scripts/verify_import.py --help
```

## Project record

- 2026-08-20: Established proposal-first governance, portable Markdown storage, and persistent Bootstrap provenance.
- 2026-08-20: Added Create, Adopt, and Import routes plus conversation/workspace evidence handling.
- 2026-08-20: Added the multi-folder Import/Adopt pipeline with read-only manifests, provenance-linked extraction, resumable batches, reconciliation candidates, application records, and verification.
- 2026-08-20: Added content-level secret redaction, strict candidate/reconciliation provenance gates, Adopt-aware verification, and idempotent application identity checks.
- 2026-08-20: Passed four automated integration tests and an independent forward test through `proposed` with zero source or target writes.
- 2026-08-20: Promoted the validated test copy to the public `knowledge-evolution` Skill and added product screenshots and public documentation.
- 2026-08-25: Added optional private Git portability with repository-scoped Skill snapshots, device-local path mappings, fail-closed GitHub privacy checks, safe fast-forward synchronization, scoped publication, public documentation, and temporary-repository integration tests.
