# Proposal, Approval, and Apply Governance

Treat every knowledge-base edit as a governed change. Keep the proposal human-readable and independently checkable.

## Proposal requirements

Assign stable change IDs such as `K-01`. For each change include:

- operation: create, update, link, move, merge, archive, or delete;
- verified target path, or `TBD` when the knowledge root or note identity is unresolved;
- knowledge type and current state;
- proposed content diff or structural action;
- evidence and attribution labels;
- rationale and expected future value;
- confidence and unresolved conflicts;
- risk level and rollback approach;
- dependent map, registry, backlink, or ledger updates.

Also list discarded candidates and privacy exclusions so the user can see what the Skill deliberately did not store.

Never invent a plausible-looking existing path. A recommended new relative path must be labeled `recommended` and anchored to an approved root before it becomes actionable. Any `TBD` target blocks Apply for that change.

## Risk levels

### Low

Create a new note, append a bounded section, correct a clearly evidenced fact, add a link, or refresh a map without removing existing information.

### Medium

Rename or move a note, change project status, replace a substantive section, merge notes, alter metadata conventions, or update many backlinks.

### High

Delete or overwrite content, bulk reorganize, expose sensitive data, change the knowledge root, modify application settings, or make an operation difficult to reverse.

When uncertain, use the higher risk level.

## Approval rules

- Require explicit approval by change ID or an unambiguous approval of the whole current proposal.
- Treat revisions as a new proposal version and preserve IDs for unchanged items.
- Do not carry approval across materially changed content.
- Require separate confirmation for high-risk changes.
- Permit low-risk auto-apply only when the user has explicitly configured it in the knowledge system and the current request does not ask for preview-only behavior.
- Never auto-apply deletions, bulk moves, sensitive-content changes, or taxonomy replacement.

## Apply rules

Before applying:

1. verify that the knowledge root and every approved target are resolved and in scope;
2. re-read each target to detect changes since the proposal;
3. stop and revise the proposal if the target changed materially;
4. create a rollback point when the operation is medium or high risk;
5. apply only approved IDs;
6. preserve formatting, metadata order, and unrelated content where practical.

After applying:

1. re-read every changed file;
2. verify links and metadata;
3. update maps and registries promised by the proposal;
4. append a ledger entry;
5. report failures without claiming partial work succeeded.

## Change ledger

Record:

- date and proposal version;
- approved change IDs;
- files created, updated, moved, archived, or deleted;
- evidence summary;
- approval source;
- verification performed;
- rollback pointer;
- unresolved follow-up.

Do not put secret values, raw private conversations, or hidden chain-of-thought in the ledger.

## Structural change safeguards

For moves, merges, and deletions, enumerate affected backlinks and indexes before applying. Prefer archive over delete. Preserve redirects or aliases when the knowledge system supports them. If rollback cannot be made reliable, state that before requesting approval.
