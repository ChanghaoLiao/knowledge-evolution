# Private Git Knowledge Portability

Read this file completely when a user asks to use Git or GitHub, share one knowledge system across computers, clone a configured Skill environment, or synchronize a Markdown/Obsidian knowledge base.

## Contents

- [Architecture](#architecture)
- [Approval boundaries](#approval-boundaries)
- [Portable repository layout](#portable-repository-layout)
- [Bootstrap routes](#bootstrap-routes)
- [Device-local configuration](#device-local-configuration)
- [Safe synchronization](#safe-synchronization)
- [GitHub privacy verification](#github-privacy-verification)
- [New-computer recovery](#new-computer-recovery)
- [Updates and conflicts](#updates-and-conflicts)

## Architecture

Keep two independent products:

1. the public Knowledge Evolution Skill is the generic engine;
2. the user's private Git repository is a generated personal instance containing knowledge, shared profile/configuration, history, and optionally an unchanged repository-scoped Skill snapshot.

Never put user profile data, source paths, tokens, private knowledge, or local preferences into the public `SKILL.md`. A portable repository may vendor a snapshot at `.agents/skills/knowledge-evolution/` so an Agent opened in that repository can discover the same rules. Keep personalized state elsewhere so replacing the snapshot cannot overwrite it.

Git is the transport and rollback layer, not the authority for semantic truth. Proposal-first governance, evidence labels, source preservation, and explicit Apply approval still govern knowledge changes.

## Approval boundaries

Treat these as separate actions. Approval of one does not imply the others:

- create or update knowledge files locally;
- copy an existing knowledge base into a new repository;
- initialize a local Git repository;
- create a remote repository or change its visibility;
- install or link the vendored Skill into a global Codex Skill directory;
- commit approved paths;
- push a commit to a remote;
- replace the vendored Skill snapshot with a newer public release.

Do not let an earlier design discussion, Bootstrap approval, or knowledge Apply silently authorize external repository creation or publication.

## Portable repository layout

Use the smallest layout compatible with the user's existing structure. For a new knowledge system, the reference layout is:

```text
personal-knowledge/
├── AGENTS.md
├── .agents/skills/knowledge-evolution/  # generic vendored snapshot
├── Knowledge/                           # user knowledge and shared profile
│   ├── 00 Inbox/
│   ├── 10 Concepts/
│   ├── 20 Projects/
│   ├── 30 Decisions/
│   ├── 40 Experiences/
│   ├── 50 Resources/
│   └── System/
│       ├── Profile/
│       ├── Knowledge Map.md
│       ├── Source Registry.md
│       ├── Change Ledger.md
│       └── knowledge-evolution.yaml
├── .knowledge-evolution/                # shared portability policy only
├── .local/device.yaml                    # ignored device mappings
├── .local/device.yaml.example            # tracked schema example
├── .gitignore
└── README.md
```

Do not force this layout onto an existing mature repository. Preserve its knowledge root and place the Skill snapshot and portability policy where repository rules permit.

Default exclusions must cover `.env*`, credentials, private keys, auth caches, Import extraction text, temporary job state, `.obsidian/workspace*.json`, `.obsidian/cache/`, operating-system noise, and device-local mappings. Review attachments and large binaries before the first commit; use Git LFS only when the user chooses it.

Do not run Obsidian Sync, iCloud/Dropbox folder sync, and Git automation against the same Vault without a user-approved conflict strategy. Multiple independent writers can create duplicate or corrupted state.

## Bootstrap routes

### Local-only

Keep existing behavior. Do not initialize Git or add a vendored Skill.

### Existing Git repository

1. Verify the repository root and current branch.
2. Inspect status, remotes, ignore rules, and upstream without changing them.
3. Confirm the approved knowledge root and whether it is already tracked.
4. Propose placement of shared configuration, local exclusions, and optional Skill snapshot.
5. Apply only approved paths, verify, then request separate commit/push approval.

Never use `git reset --hard`, clean untracked files, rewrite history, or force-push to make an existing repository fit the template.

### New private GitHub repository

1. Create the local portable layout with `scripts/create_portable_repository.py` only after its paths are approved.
2. Initialize local Git only when approved. This creates no remote.
3. Ask separately before running a GitHub creation action such as `gh repo create ... --private`.
4. Verify that the remote reports `PRIVATE` before the first knowledge push.
5. Publish only the approved initial paths and record the resulting commit as the rollback pointer.

If GitHub authentication or private-visibility verification is unavailable, stop before the first push. Do not fall back to public visibility.

## Device-local configuration

Shared configuration stores logical source identities, for example `ai-coding-projects`. Each device maps those IDs to its own absolute paths in ignored `.local/device.yaml`:

```yaml
device_id: "macbook-example"
source_paths:
  ai-coding-projects: "/Users/example/Projects/ai-coding"
```

Another device can map the same ID to a different path. Never infer that a missing local path means the shared source or its knowledge should be deleted. Mark it `unavailable-on-this-device` and continue with other evidence streams.

Do not commit `.local/device.yaml`. Commit only `.local/device.yaml.example` with placeholders.

## Safe synchronization

At the beginning of a Git-backed Evolve or Audit run:

1. run repository status;
2. pull only when the worktree and index are clean;
3. use fast-forward-only pull;
4. stop on divergence, conflicts, detached HEAD, missing upstream, or authentication failure;
5. load shared profile, configuration, and knowledge only after the repository is current or the stale state is clearly reported.

After an approved Apply:

1. verify changed knowledge and system records;
2. list the exact repository paths covered by approval;
3. require a separate publish instruction when policy does not already authorize it;
4. stage only those paths;
5. commit with a proposal or change reference;
6. push normally, never with `--force`;
7. report the commit and whether push succeeded.

Use `scripts/sync_knowledge_repository.py status`, `pull`, `verify-private`, and `publish`. It must refuse unsafe pull state and unrelated pre-staged changes.

No bundled component is a background daemon. Synchronization happens during an explicit user or Agent task.

## GitHub privacy verification

For a GitHub remote, verify privacy with authenticated GitHub CLI metadata immediately before the first knowledge push and whenever the remote changes:

```text
python3 scripts/sync_knowledge_repository.py verify-private --repo /approved/repository
```

The check must fail closed when the remote is public, metadata cannot be obtained, or the remote cannot be identified safely. Never print embedded credentials from a remote URL.

## New-computer recovery

Git clone never executes repository scripts. The supported flow is:

1. authenticate to the private Git provider;
2. clone the repository;
3. open the cloned repository in Codex for repository-scoped Skill discovery;
4. create `.local/device.yaml` from the tracked example and add this device's path mappings;
5. run `scripts/install_portable_skill.py` only if global discovery from unrelated projects is desired;
6. run status and a read-only Audit before the first Apply.

The installer must refuse to overwrite an unrelated global Skill. A symlink keeps the global entry attached to the cloned snapshot; copy mode is an explicit fallback and can become stale.

## Updates and conflicts

Replace a vendored Skill snapshot only through an explicit reviewed update. Preserve `Knowledge/`, shared profile/configuration, `.local/`, and ledger history. Validate the new snapshot before committing it.

On a content conflict, do not auto-select a winner merely because one commit is newer. Preserve both versions, inspect their evidence and intent, and create a reconciliation proposal. On a Git history conflict or divergence, stop and report the affected paths and branches; do not stash, reset, rebase, or merge without user direction.
