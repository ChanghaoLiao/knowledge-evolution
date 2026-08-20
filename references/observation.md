# Conversation and Workspace Observation

Use this workflow to determine what changed without confusing intent, implementation, and inference.

## Set an observation boundary

Record:

- approved workspace roots;
- start and end of the capture window;
- available conversation and tool records;
- baseline type: session snapshot, git reference, tool log, or none;
- ignored paths and privacy exclusions.

Never widen the boundary merely because a parent directory is accessible.

## Capture before work when possible

For a non-git workspace, create a bounded metadata-and-hash snapshot before agent work:

```text
python3 scripts/workspace_changes.py snapshot /approved/workspace --output /safe/baseline.json
```

Compare after work:

```text
python3 scripts/workspace_changes.py compare /approved/workspace --baseline /safe/baseline.json --pretty
```

Store baselines outside the observed workspace when possible so the snapshot does not observe itself.

For a git workspace, use:

```text
python3 scripts/workspace_changes.py git /approved/workspace --pretty
```

Then inspect only relevant diffs with native git commands. The script reports paths and states, not file contents.

## Attribute carefully

Use these attribution labels:

- `session-confirmed`: a before/after snapshot or tool log proves the change occurred in the capture window;
- `git-observed`: git proves a difference from the selected reference, but not who caused it;
- `currently-observed`: the artifact exists now, with no reliable baseline;
- `conversation-stated`: the user or agent explicitly described an intent or result;
- `inferred`: the conclusion follows from evidence but was not directly stated.

Never label a dirty working-tree change as agent-created merely because it appears after the conversation. It may predate the session.

## Inspect relevant content

After obtaining the change list, read the smallest content slice needed to understand durable meaning:

- source and configuration diffs for implemented behavior;
- tests and validation results for verified behavior;
- generated documents for deliverable content;
- project records for status changes;
- filenames and metadata only for large or binary artifacts unless visual inspection is necessary.

Ignore build products, dependency directories, caches, logs without durable value, and generated noise unless they are the requested deliverable.

## Protect sensitive data

Do not read or persist values from `.env`, credential stores, private keys, tokens, cookies, browser profiles, authentication caches, or similarly sensitive sources. Mention an exclusion without reproducing its value. Treat file paths as potentially sensitive when presenting a proposal outside the local environment.

## Reconcile evidence conflicts

Use this order for different questions:

- **What exists now?** Prefer direct workspace artifacts.
- **Why was it chosen?** Prefer explicit user statements, then recorded rationale.
- **Did it work?** Prefer tests or observed results; do not infer success from code presence.
- **What should happen next?** Prefer explicit commitments over generated suggestions.
- **What was already known?** Prefer dated knowledge-base records and their sources.

If the conversation says a migration is complete but the workspace shows both old and new implementations, propose a project-status correction and record the ambiguity instead of selecting a convenient story.

## Create evidence references

Use compact references that remain checkable:

```text
conversation:<turn-or-date>
workspace:<relative-path>#L<line>
git:<commit-or-baseline>:<relative-path>
tool:<action-or-result-id>
knowledge:<relative-note-path>#<heading>
```

Do not invent line numbers, commit identifiers, timestamps, or tool results.
