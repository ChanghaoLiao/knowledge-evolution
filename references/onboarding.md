# Onboarding and Knowledge Bootstrap

Use this workflow when the knowledge root or its structure is unknown. Keep discovery read-only until the user approves a bootstrap or migration proposal.

## Contents

- [Bootstrap lifecycle](#bootstrap-lifecycle)
- [Establish the environment](#establish-the-environment)
- [Choose one route](#choose-one-route)
- [Produce the bootstrap proposal](#produce-the-bootstrap-proposal)
- [Initialize system records](#initialize-system-records)
- [Finish onboarding](#finish-onboarding)

## Bootstrap lifecycle

Treat Bootstrap as a one-way, recorded transition:

1. `uninitialized`: no approved knowledge-system state exists;
2. `proposed`: discovery is complete, but no persistent changes are authorized;
3. `initialized`: a new knowledge base and its system records were approved and verified;
4. `adopted`: an existing knowledge base was mapped and its minimal system records were approved;
5. `migration-required`: an explicit user request or incompatible future schema requires a new proposal.

Never replace `initialized` or `adopted` with a fresh bootstrap merely because the Skill is invoked again. Route normal later work to Evolve or Audit.

Keep the installed Skill directory separate from user data. Bootstrap may change only approved paths inside the chosen knowledge root. Do not self-modify the Skill, alter Codex settings, edit `.obsidian/`, or change workspace source files as a Bootstrap side effect.

## Establish the environment

Discover or ask for only the missing items:

- the intended knowledge root, if one exists;
- whether Obsidian is installed or merely desired;
- other user-approved sources such as exported notes, project folders, documents, or chat archives;
- preferred language, link style, and naming conventions;
- directories that are out of scope or sensitive.

Do not require Obsidian. A Markdown directory created by this Skill can later be opened as an Obsidian vault without conversion.

Run:

```text
python3 scripts/audit_knowledge_base.py /approved/knowledge/root --pretty
```

Treat the resulting profile as a routing signal, not as a judgment of quality.

## Choose one route

The routes belong to three operational families:

- **Create**: Route A or B, with no historical material to ingest.
- **Adopt**: Route C or D, where the existing knowledge root remains the target.
- **Import**: Route E, where external sources remain unchanged and knowledge is proposed into a separate target.

For Adopt or Import, read `import-adopt.md` completely and create an isolated resumable job. The simple audit is only a routing profile; it is not a replacement for content inventory, extraction, semantic classification, reconciliation, or migration proposals.

### Route A: No knowledge base

Propose a new portable Markdown space. Use this default only when the user has no preferred structure:

```text
00 Inbox/
10 Concepts/
20 Projects/
30 Decisions/
40 Experiences/
50 Resources/
System/
```

Explain that folders are starting views, not a permanent ontology. Create only approved folders and system files. Use templates from `assets/templates/`.

### Route B: Empty knowledge base

Preserve the chosen root. Detect Obsidian settings if `.obsidian/` exists, but do not edit them. Propose the smallest starter structure and create it only after approval.

### Route C: Existing but unstructured notes

Adopt and map in place before reorganizing. Register the existing knowledge root as the read-only Adopt source during discovery, then inventory and process it in batches. Produce:

- an inventory;
- recurring topics and note types;
- duplicate or conflicting candidates;
- an initial knowledge map;
- minimal additions that improve navigation without moving notes.

Do not bulk rename, move, retag, rewrite, or merge existing notes during onboarding.

### Route D: Existing structured knowledge base

Adopt the user's taxonomy. Register the existing knowledge root as the Adopt source, locate index notes, templates, link conventions, metadata fields, archive rules, and project/status vocabulary, and reconcile candidates against that existing structure. Propose only the system records and content changes needed for this Skill, and place them where the existing system expects such files.

### Route E: Knowledge in another system

Use Import. Prefer exports supplied by the user and register every approved folder separately. Preserve original exports as read-only sources. Build a hashed manifest, extract supported content with locators, classify it in resumable batches, and reconcile duplicates, conflicts, and versions before proposing target changes. Track stable source, file, chunk, candidate, proposal, and change identifiers so future imports can resume or reconcile without duplication.

Never import the entire archive in one approval wave. Propose bounded batches, record progress, and verify that source files still match the inventory immediately before Apply.

## Produce the bootstrap proposal

Include:

1. detected state and confidence;
2. approved source roots and exclusions;
3. recommended route and why;
4. files and folders to create, without changing existing notes;
5. mapping or migration stages;
6. Import/Adopt job location, batch limits, retention choice, and source-preservation checks when applicable;
7. privacy concerns and content intentionally excluded;
8. confirmation choices.

Use `assets/templates/update-proposal.md` for Create and for Adopt work that only adds minimal system records. When Bootstrap includes Import or content migration, use `assets/templates/import-proposal.md` as the combined Bootstrap-and-Proposal-Wave document; set its `kind` to `import` or `adopt` as appropriate and include the detected route and persistent initialization changes. Do not require two overlapping proposals unless the user explicitly wants environment initialization reviewed separately from content migration.

## Initialize system records

Adapt these templates rather than forcing their exact paths:

- `knowledge-evolution.yaml`: roots, link style, approval policy, and exclusions;
- `Knowledge Map.md`: navigational overview and knowledge landscape;
- `Source Registry.md`: origins, boundaries, and last-observed state;
- `Change Ledger.md`: approved knowledge changes and rollback pointers.
- `Proposals/`: approved proposal versions, including the Bootstrap proposal.

Set persistent Bootstrap fields only after approved changes have been applied and verified. Record the route, date, proposal ID, and schema version. Preserve these fields across later updates.

Do not store absolute paths if the user intends to sync the knowledge base across devices; prefer paths relative to a configured root.

## Finish onboarding

Archive the approved Bootstrap proposal, append its ledger entry, and verify that the initialized space opens as ordinary Markdown, no original content was overwritten, the source registry matches the approved scope, and the next normal run can use **Evolve** mode without repeating discovery.

Temporary audit output, rejected proposal drafts, and raw discovery dialogue may be discarded for privacy and clutter control. Never discard the accepted initialization choices, scope, directory mapping, Bootstrap proposal reference, or applied-change history.
