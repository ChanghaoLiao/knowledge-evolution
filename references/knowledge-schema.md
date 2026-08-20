# Knowledge Schema and Quality Rules

Use the existing schema when one exists. Apply this schema only as a fallback for a new or minimally structured knowledge base.

## Knowledge types

### Concept

Capture reusable understanding that remains useful across projects. State the concept in the user's own vocabulary, link related concepts, and separate established understanding from open questions.

### Project

Capture an outcome-oriented effort with a current state. Include goal, status, constraints, confirmed progress, next actions, and links to decisions or outputs. Do not mark work complete because it was discussed; require artifact or user evidence.

### Decision

Capture a choice that changes future action. Include the decision, date, context, alternatives when known, rationale, consequences, evidence, and supersession state. Do not convert a suggestion into a decision.

### Experience

Capture a personally observed event and its reusable lesson. Keep the event separate from the interpretation. Avoid generalizing from a single experience without labeling the inference.

### Resource

Capture an external source or reusable artifact. Preserve its title, origin, access date when relevant, short relevance note, and links to the knowledge it supports. Do not copy large copyrighted content into the knowledge base.

### Inbox

Use for durable material that has not yet earned a stable type or location. Include a review reason. Do not turn Inbox into the default destination for all generated summaries.

### System

Use for maps, registries, templates, policies, ledgers, and maintenance state. Keep system records distinct from the user's substantive knowledge.

## Candidate gate

Persist a candidate only when it is at least one of the following:

- likely to change a future decision or action;
- reusable beyond the current exchange;
- a confirmed project-state change;
- an explicit decision and its rationale;
- a durable relationship between existing knowledge;
- a correction to an existing inaccurate note;
- evidence needed to understand an approved change.

Discard or defer repetition, transient commands, raw chain-of-thought, social filler, obvious restatements, unverified claims, secrets, and low-value debug output.

## Note identity

Search by title, aliases, stable IDs, distinctive phrases, backlinks, and source identifiers before creating a note. Prefer this order:

1. update the canonical note;
2. add a section to a closely scoped note;
3. create a linked note when it has an independent lifecycle;
4. place an uncertain candidate in Inbox with a review reason.

Never merge notes solely because their titles are similar.

## Metadata fallback

When the base has no metadata convention, use only fields that create clear value:

```yaml
type: concept | project | decision | experience | resource
status: active | stable | superseded | archived
created: YYYY-MM-DD
updated: YYYY-MM-DD
tags: []
sources: []
```

Add aliases, owner, due dates, confidence, or sensitivity only when the user needs them. Preserve existing field names instead of introducing synonyms.

## Linking rules

- Link for semantic navigation, provenance, dependency, or supersession.
- Use the base's established Markdown-link or wikilink style.
- Add reciprocal context when a backlink alone would be ambiguous.
- Prefer a meaningful relationship sentence over a bare list of links.
- Do not create links to nonexistent notes unless the base already uses intentional placeholders.

## Quality gate

Before proposing a note change, verify:

- atomicity: the note has a clear subject;
- provenance: claims point to evidence or are labeled as inference;
- freshness: project status and decisions include a relevant date;
- consistency: terminology and metadata match the base;
- connection: the change improves at least one useful relationship or map;
- restraint: the update contains only durable knowledge;
- privacy: sensitive content is excluded or explicitly approved;
- reversibility: broad changes have a rollback path.
