---
proposal_id: "KE-{{date}}-{{sequence}}"
version: 1
mode: "bootstrap | evolve | audit"
created: "{{timestamp}}"
knowledge_root: "{{knowledge_root}}"
status: "awaiting-review"
---

# Knowledge Update Proposal

## Scope

- Conversation window: {{conversation_window}}
- Workspace roots: {{workspace_roots}}
- Baseline: {{baseline_type_and_reference}}
- Exclusions: {{scope_exclusions}}

## Summary

{{plain_language_summary}}

## Proposed changes

### K-01 — {{short_title}}

- Operation: `create | update | link | move | merge | archive | delete`
- Target: `{{verified_relative_path_or_TBD}}`
- Knowledge type: `{{type}}`
- Evidence: `{{evidence_reference}}`
- Attribution: `session-confirmed | git-observed | currently-observed | conversation-stated | inferred`
- Confidence: `high | medium | low`
- Risk: `low | medium | high`
- Rationale: {{future_value}}
- Rollback: {{rollback_method}}

```diff
{{proposed_diff}}
```

Dependencies: {{map_link_registry_or_ledger_updates}}

## Conflicts and uncertainty

- {{conflict_or_none}}

## Excluded for privacy

- {{excluded_material_without_secret_values_or_none}}

## Deliberately discarded

- {{transient_or_low_value_material_or_none}}

## Review choices

- Approve the complete current proposal.
- Approve selected IDs: `{{ids}}`.
- Request revisions: `{{instructions}}`.
- Reject the proposal.
