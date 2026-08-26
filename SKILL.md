---
name: knowledge-evolution
description: Turn conversations, agent tool activity, workspace changes, and one or more existing source folders into reviewable, evidence-linked updates to a personal Markdown knowledge base or Obsidian vault. Use when a user asks to initialize, create, adopt, import, audit, organize, migrate, or safely sync a knowledge base; batch-process old notes or documents; capture durable knowledge from a discussion; reconcile project work with notes; create a private Git or GitHub-backed knowledge repository for multiple computers; propose or apply knowledge changes; maintain concepts, projects, decisions, experiences, resources, maps, or change history; or says things such as "整理这次讨论", "导入这些资料", "更新知识库", "初始化我的 Obsidian", "把知识库放到私有 GitHub", or "结合工作区变化沉淀知识".
---

# Knowledge Evolution

Treat a knowledge base as a governed system that evolves through reviewed changes, not as a destination for automatic summaries. Support ordinary Markdown first and Obsidian when present.

## Core contract

- Inspect before writing. Restrict every scan to roots the user supplied or approved.
- Bootstrap an unknown knowledge environment before running a normal update.
- Observe the current conversation, relevant tool activity, workspace changes, and existing knowledge.
- Label every candidate as `observed`, `stated`, or `inferred`; never present inference as fact.
- Generate a change proposal before editing the knowledge base. Require explicit approval by default.
- For an already configured Git-backed knowledge repository, synchronize once before reading canonical knowledge to generate a proposal. Do not synchronize again during Apply.
- Preserve the user's existing taxonomy, naming, frontmatter, links, and language.
- Never invent an existing note, folder, or target path. Mark unresolved targets as `TBD` and block Apply until the knowledge root and target are verified.
- Treat Bootstrap as a persistent state transition, not a temporary prompt. Preserve approved initialization choices and provenance across later Evolve runs.
- Keep the public Skill, user workspace, and user knowledge data logically separate. A user-approved portable repository may vendor an unchanged Skill snapshot for repository-scoped discovery, but personal configuration must remain outside that snapshot and no installed Skill may self-modify.
- Treat every registered Import/Adopt source as read-only. Preserve original files, use an isolated resumable job directory, and write only approved changes to the target knowledge root.
- Never read or persist secret values. Report only that sensitive material was excluded.
- Never claim that an agent caused a workspace change unless a session baseline or tool record supports attribution.

## Select the operating mode

1. Use **Bootstrap/Create** when the user has no existing material and needs a new Markdown knowledge space.
2. Use **Bootstrap/Adopt** when an existing knowledge base remains the target and should be mapped in place.
3. Use **Bootstrap/Import** when one or more external source folders must be analyzed and migrated into a separate target knowledge root.
4. Use **Evolve** for a normal conversation-and-workspace knowledge update after initialization.
5. Use **Audit** for a read-only health check, duplication review, or knowledge-map refresh.
6. Use **Apply** only for a proposal the user has explicitly approved.

Git portability is an optional deployment layer for any mode, not a seventh knowledge mode. Local-only use remains the default.

## Run the workflow

### 1. Establish scope

Identify the knowledge root, relevant workspace roots, capture window, requested mode, and allowed write scope. Discover what can be discovered safely before asking the user. Do not scan a home directory, desktop, cloud drive, or unrelated repository as a substitute for a missing scope.

Do not assume the current workspace is the knowledge base. If no knowledge root is supplied or safely discoverable, continue only with path-free candidate analysis or a conditional proposal, label every target `TBD`, and request the missing root before Apply.

If the knowledge environment is not initialized, read [onboarding.md](references/onboarding.md) completely and follow its route. Use `scripts/audit_knowledge_base.py` for a bounded, read-only inventory.

If Bootstrap includes existing notes, exported data, documents, project folders, or more than one source root, read [import-adopt.md](references/import-adopt.md) completely. Register explicit roots before scanning, keep operational state outside source and target content, and use the resumable Import/Adopt pipeline. Do not substitute an untracked recursive read or a one-shot bulk rewrite.

If the user asks for Git, GitHub, a private repository, multiple-computer access, portable Codex discovery, pull/push, or knowledge sync, read [git-portability.md](references/git-portability.md) completely. Keep repository creation, knowledge initialization, global Skill installation, and remote publication as separately reviewable actions. Default the remote to private and verify that visibility before the first knowledge push.

When a configured Git-backed run will produce a proposal, complete the pre-proposal synchronization before using the repository as canonical evidence. A local-only knowledge base or first Bootstrap before a remote and upstream exist records synchronization as not applicable. An Apply-only run must not fetch or pull; it works from the approved local proposal state and the local verification required below.

If persistent configuration reports `initialized` or `adopted`, do not run Bootstrap again. Use Evolve or Audit unless the user explicitly requests reinitialization or migration.

### 2. Run Import/Adopt when existing sources are in scope

Skip this step for Create and ordinary Evolve. For Import or Adopt, follow [import-adopt.md](references/import-adopt.md) from registration through proposal:

1. register approved sources and exclusions;
2. build a read-only hashed manifest;
3. extract supported content with file and locator provenance;
4. prepare deterministic batches and checkpoints;
5. classify durable knowledge batch by batch;
6. shortlist and review duplicates, conflicts, and versions;
7. generate a bounded migration proposal;
8. verify source stability before applying any approved change.

Deterministic scripts manage files, hashes, batching, state, and verification. The Agent performs semantic classification and reconciliation. The user authorizes target writes. Never collapse these roles.

### 3. Collect evidence

Collect four evidence streams when available:

- Conversation: goals, reasoning, explicit decisions, corrections, and unresolved questions.
- Tool activity: commands, edits, generated artifacts, tests, and externally reported results.
- Workspace: git state or a before/after snapshot, plus the relevant changed content.
- Knowledge base: existing notes, terminology, links, status, and recorded decisions.

Read [observation.md](references/observation.md) completely before inspecting a workspace. Use `scripts/workspace_changes.py` to capture a baseline, compare snapshots, or summarize current git state. Treat a post-hoc dirty tree as current evidence with uncertain session attribution.

### 4. Reconcile evidence

Prefer direct artifacts over summaries for what currently exists. Use explicit user statements for intent and rationale. Use the existing knowledge base for established names and historical state until stronger evidence updates it.

When evidence conflicts, preserve both sides in the proposal and state the conflict. For example, record that the conversation selected one implementation while the workspace still contains another; do not silently choose one.

### 5. Extract durable changes

Discard greetings, repetition, temporary debugging noise, unverified speculation, and facts that have no expected future value. Classify durable candidates using [knowledge-schema.md](references/knowledge-schema.md). Prefer updating an existing note over creating a near-duplicate.

### 6. Propose a knowledge diff

Use `assets/templates/import-proposal.md` for Import or content-migration work; it also carries the Bootstrap decision for that route. Use `assets/templates/update-proposal.md` for Create, ordinary Evolve, and Adopt work limited to minimal system records. Include:

- each target path and operation;
- a concise before/after or addition/removal diff;
- knowledge type, evidence references, confidence, and rationale;
- conflicts, privacy exclusions, and intentionally discarded material;
- map, link, and ledger consequences;
- a risk label for every move, merge, overwrite, or deletion.

Use an exact target path only after verifying that it exists or defining it as a new path under an approved knowledge root. Otherwise write `TBD` and, if useful, show a clearly labeled recommended relative path rather than presenting it as an existing file.

Read [governance.md](references/governance.md) completely before presenting or applying a proposal.

### 7. Review

Let the user approve all changes, approve selected change IDs, request revisions, or reject the proposal. Do not interpret silence or approval of an earlier design discussion as approval to change the knowledge base.

Stop after the proposal when the user requested analysis, audit, or a preview only.

### 8. Apply approved changes

Apply only approved change IDs. Preserve unrelated content and make the smallest coherent edits. Require separate confirmation for destructive or broad structural operations even when low-risk auto-apply is configured.

For Import/Adopt jobs, verify that registered source hashes still match the proposal evidence immediately before Apply. Record each applied change ID and resulting target hash in the job state. A recorded application is not permission to apply any other change.

Update the knowledge map, source registry, affected backlinks, and change ledger when present. Record what changed, why, which evidence supported it, and which proposal approval authorized it.

Do not fetch or pull the knowledge repository during Apply. For a Git-backed repository, a knowledge Apply approval does not automatically authorize a commit or push. After verification, publish only approved repository paths and never force-push. A normal push that is rejected because the remote advanced must leave the local approved commit intact and stop without pull, rebase, merge, or automatic conflict resolution. Use `scripts/sync_knowledge_repository.py` for pre-proposal fast-forward synchronization, private-remote verification, and scoped publication.

### 9. Verify and report

Re-read changed files. Validate paths, frontmatter, internal links, duplicate titles, and ledger entries. Report applied, skipped, failed, and still-uncertain changes separately. Include a rollback pointer such as a backup location, prior snapshot, or git commit when one exists.

## Use the bundled resources

- Read [onboarding.md](references/onboarding.md) for first-run discovery, migration, and default structure.
- Read [import-adopt.md](references/import-adopt.md) for multi-folder registration, manifests, extraction, batching, resume, reconciliation, proposals, and source-preservation verification.
- Read [knowledge-schema.md](references/knowledge-schema.md) for note types, identity, linking, and quality gates.
- Read [observation.md](references/observation.md) for workspace attribution, privacy, git, snapshots, and conflict handling.
- Read [governance.md](references/governance.md) for proposals, approval, risk, apply, ledger, and rollback.
- Read [git-portability.md](references/git-portability.md) for optional private Git repositories, repository-scoped Skill snapshots, device-local configuration, safe synchronization, and new-computer recovery.
- Copy and adapt files from `assets/templates/` only after choosing a structure or receiving approval.
- Run scripts with `--help` before first use. Scripts do not authorize broader scanning or writing.

## Invocation examples

- `用 $knowledge-evolution 初始化一个不依赖 Obsidian 的个人知识库。`
- `用 $knowledge-evolution 只读扫描这两个资料文件夹，分批生成导入提案，保留原文件。`
- `用 $knowledge-evolution 接管这个现有 Vault，先建立索引，不要移动或改写原笔记。`
- `用 $knowledge-evolution 整理这次讨论，同时核对当前项目实际修改了什么。`
- `用 $knowledge-evolution 只生成知识更新提案，不要写入文件。`
- `用 $knowledge-evolution 应用提案中的 K-01 和 K-03。`
- `用 $knowledge-evolution 为我的知识库设计一个私有 GitHub 仓库，让另一台电脑克隆后可以继续使用；先给我提案。`
