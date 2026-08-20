# Import and Adopt Pipeline

Read this file completely whenever Bootstrap includes one or more existing folders. This pipeline turns bounded source folders into traceable migration proposals; it never authorizes a write by itself.

## Contents

- [Choose the route](#choose-the-route)
- [Safety contract](#safety-contract)
- [Job state and artifacts](#job-state-and-artifacts)
- [1. Register approved sources](#1-register-approved-sources)
- [2. Inventory and extract](#2-inventory-and-extract)
- [3. Prepare resumable batches](#3-prepare-resumable-batches)
- [4. Agent semantic classification](#4-agent-semantic-classification)
- [5. Reconcile duplicates, conflicts, and versions](#5-reconcile-duplicates-conflicts-and-versions)
- [6. Propose in bounded waves](#6-propose-in-bounded-waves)
- [7. Apply only approved changes](#7-apply-only-approved-changes)
- [8. Verify and complete](#8-verify-and-complete)

## Choose the route

- **Adopt**: the existing knowledge root remains the target. Register that same path once with `mode: "adopt"`. Add navigation or system records in place only after approval.
- **Import**: one or more external folders are read-only sources and a separate knowledge root is the target. Source and target paths must not overlap.
- **Create**: there are no source materials. Do not start an Import/Adopt job; follow the new-space route in `onboarding.md`.

Do not mix Adopt and Import casually. If an existing knowledge root also needs external material, register the knowledge root as the single Adopt source and the external folders as Import sources only after verifying that the target is not nested inside an external source.

## Safety contract

1. Register only roots and include/exclude rules that the user approved.
2. Keep the job directory outside every source and outside the target knowledge content.
3. Treat every source as read-only. The scripts never rename, move, delete, or rewrite a source file.
4. Exclude secrets before content hashing or extraction. Do not override the built-in secret exclusions.
5. Keep each extracted claim linked to a `source_id`, `file_id`, `chunk_id`, relative path, and locator.
6. Treat duplicate and conflict results as candidates for review, not automatic merge decisions.
7. Create a proposal before any target write. Apply only approved change IDs.
8. Preserve the original files. Import creates or updates governed notes in the target; it does not “clean up” the sources.
9. Re-run verification immediately before Apply. If source hashes changed, refresh and regenerate stale downstream artifacts.

## Job state and artifacts

Use a private working directory for each import job. It contains operational state, not the user's knowledge base:

```text
job.json
checkpoint.json
events.jsonl
source-manifest.jsonl
extraction-index.jsonl
extracted-chunks.jsonl
batches/<batch-set>/
candidates.jsonl
reconciliation-candidates.jsonl
source-duplicates.jsonl
reconciliation-decisions.jsonl
proposal.md
applied.jsonl
verification-report.json
```

The lifecycle is:

```text
registered -> inventoried -> extracted -> batched -> classified
           -> reconciliation-ready -> reconciled -> proposed
           -> partially-applied -> completed
```

Any active stage can be paused. `checkpoint.json` records the resume stage, processed batches, artifact digests, and summary counts. Never delete or rebuild a job merely to resume it.

## 1. Register approved sources

Copy `assets/templates/import-job.json` for external sources or `assets/templates/adopt-job.json` for an in-place knowledge base, edit it outside the source roots, and then run:

```text
python3 scripts/register_sources.py --config /approved/import-job.json --job-dir /private/job-directory --pretty
```

Each source needs a stable lowercase `id`, absolute `root`, `mode`, and optional `include` and `exclude` globs. Registration validates path boundaries but does not scan content. A source is always recorded with `writable: false`; the target uses `proposal-approved` writes.

If external material is being imported into a target that already contains knowledge, include that target once as an `adopt` source and include each external folder as an `import` source in the same job. This lets reconciliation compare incoming candidates against the target's actual content. During discovery the Adopt source is still read-only; later approved writes use the separate target policy.

## 2. Inventory and extract

Build the read-only content manifest:

```text
python3 scripts/build_source_manifest.py --job-dir /private/job-directory --pretty
```

The manifest records paths, sizes, modification times, extractors, and hashes where allowed. It skips symlinks, common generated folders, explicit exclusions, and sensitive names. Extraction also redacts common embedded keys, tokens, authorization values, credentialed URLs, and private-key blocks before writing chunks. The `redaction_operations` count measures regex replacement operations, not sensitive files, lines, or unique secrets; more than one rule may match a line. Treat this as a defense in depth, not permission to include known secret-bearing folders.

Extract normalized, provenance-linked text:

```text
python3 scripts/extract_documents.py --job-dir /private/job-directory --pretty
```

Built-in extraction supports Markdown, plain text, common source code, JSON/CSV/YAML, HTML, DOCX, and notebooks. PDF text extraction uses `pypdf`, `PyPDF2`, or `pdftotext` when available; unavailable or unsupported formats remain visible in the extraction report rather than disappearing.

Do not send raw extraction artifacts to the final knowledge base. They are temporary evidence and may contain private source text.

## 3. Prepare resumable batches

```text
python3 scripts/prepare_import_batches.py --job-dir /private/job-directory --pretty
```

Classification batch IDs and locations are deterministic for the same extracted content. Process one classification batch at a time. After classifying it, save its Agent output inside the job directory and record its status:

```text
python3 scripts/manage_import_state.py --job-dir /private/job-directory record-batch --batch-id batch-0001 --status classified --artifact /private/job-directory/batch-0001-candidates.jsonl
```

Pause and resume without losing progress:

```text
python3 scripts/manage_import_state.py --job-dir /private/job-directory pause --reason "等待用户确认范围"
python3 scripts/manage_import_state.py --job-dir /private/job-directory resume
python3 scripts/manage_import_state.py --job-dir /private/job-directory --pretty status
```

Global options such as `--pretty` go before the subcommand.

## 4. Agent semantic classification

The scripts prepare evidence; the Agent performs semantic work. For every batch, identify durable knowledge and emit JSONL candidates with this minimum schema:

```json
{
  "candidate_id": "candidate-stable-id",
  "knowledge_type": "concept",
  "title": "Durable title",
  "content": "Evidence-grounded candidate content",
  "confidence": "high",
  "evidence_class": "observed",
  "source_refs": [
    {
      "source_id": "old-notes",
      "file_id": "file-...",
      "chunk_id": "chunk-...",
      "relative_path": "notes/example.md",
      "locator": "lines:1-12"
    }
  ]
}
```

Allowed knowledge types are `concept`, `project`, `decision`, `experience`, `resource`, and `inbox`. Allowed confidence values are `high`, `medium`, and `low`. Set `evidence_class` to `observed`, `stated`, or `inferred`; for example, observing a sentence in an old note proves that the note contains that statement, not necessarily that the statement is objectively true. Stable candidate IDs should survive a resume. Do not infer unsupported dates, owners, status, or causal claims.

Combine the reviewed per-batch outputs into `candidates.jsonl`, then validate and accept it:

```text
python3 scripts/manage_import_state.py --job-dir /private/job-directory validate-candidates --file /private/job-directory/candidates.jsonl --accept
```

Validation checks IDs, types, content, confidence, and source references. It does not certify semantic correctness.
Every prepared batch must first be recorded as `classified` or intentionally `skipped`; acceptance fails while any batch remains pending or failed.

## 5. Reconcile duplicates, conflicts, and versions

Generate deterministic shortlists:

```text
python3 scripts/find_duplicate_candidates.py --job-dir /private/job-directory --pretty
```

Review `source-duplicates.jsonl` and `reconciliation-candidates.jsonl` against the actual candidate evidence and the target knowledge base. For each relation, decide one of:

- `merge`: same durable knowledge; preserve all provenance;
- `link`: related but distinct;
- `version`: newer evidence supersedes an older state without erasing history;
- `conflict`: both claims remain unresolved;
- `keep-separate`: false positive;
- `discard`: non-durable or unsupported material, with reason.

Save one JSONL decision per `relation_id` in the job directory. Include `decision` and a non-empty `reason`. Use `preserve-sources` for exact source-file groups because detection never authorizes deletion. Advance only when every shortlisted relation has an explicit disposition:

```text
python3 scripts/manage_import_state.py --job-dir /private/job-directory validate-reconciliation --file /private/job-directory/reconciliation-decisions.jsonl --accept
```

The validator rejects missing, duplicate, or unknown relation IDs. It checks completeness and vocabulary, not whether the semantic decision is wise.

## 6. Propose in bounded waves

Use `assets/templates/import-proposal.md` for Import and any Adopt route that migrates or reorganizes content. For a pure Adopt route that only adds minimal system records, use `assets/templates/update-proposal.md`. The proposal must include source coverage, exclusions, unresolved items, every intended target path, create/update/merge operation, evidence references, rollback pointer, and change IDs.

For large imports, complete the relevant classification batches and cross-batch reconciliation first, then present Proposal Wave 1 with a bounded set such as 20–50 target changes. A proposal wave is a user-review unit; it is not the same as a classification batch. Do not request blanket approval for the entire archive. Save the current draft proposal under review in the job directory, then record the stage:

```text
python3 scripts/manage_import_state.py --job-dir /private/job-directory set-stage --to proposed --reason "迁移提案已提交审核" --artifact /private/job-directory/proposal.md
```

## 7. Apply only approved changes

Immediately before writing, verify source stability:

```text
python3 scripts/verify_import.py --job-dir /private/job-directory --require-source-unchanged --pretty
```

If verification reports a changed source, stop. Refresh inventory and extraction with `--refresh`, rebuild batches, and re-review affected candidates.

Apply only approved change IDs to the target knowledge root. Preserve unrelated target content. After each successful write, record the resulting target hash:

```text
python3 scripts/manage_import_state.py --job-dir /private/job-directory record-application --proposal-id IMPORT-001 --change-id K-01 --target-path "10 Concepts/Example.md" --source-file-id file-...
```

Recording is idempotent for the same change ID and target hash. It does not edit the target itself and therefore cannot replace the Agent's approval checks.

## 8. Verify and complete

Run verification again and create `assets/templates/import-report.md` from the results. Report applied, skipped, failed, deferred, unsupported, unresolved, and source-changed items separately.

For Adopt jobs, a modified existing target note is not treated as unexplained source drift when its current hash exactly matches a recorded, approved application. It is reported separately as an approved Adopt target change. Any other change still blocks strict verification.

Advance to `completed` only when the current approved wave is applied and verified:

```text
python3 scripts/manage_import_state.py --job-dir /private/job-directory set-stage --to completed --reason "获批变更已应用并验证" --artifact /private/job-directory/verification-report.json
```

If the job configuration says not to retain extracted text, remove temporary extraction artifacts only after completion and only from the isolated job directory. Keep `job.json`, checkpoint, manifest metadata, reconciliation decisions, proposal, applied records, verification report, and the target knowledge base's source registry/ledger entries.
