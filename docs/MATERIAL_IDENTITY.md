# Material Identity

## Resolution order

1. Exact scoped trusted identifier match.
2. Normalized canonical/display-name signal.
3. Exact structured composition signature signal.
4. No match.

The service returns `exact`, `probable`, `ambiguous`, or `none`, plus reasons and candidate materials. Only exact identifier resolution is safe for automatic import attachment. Probable/ambiguous results halt import for curator review.

## Scope

Public identifiers are globally visible. Private identifiers must belong to an organisation and may only be attached to private material entities in Phase 2. A public partial unique index protects public namespace/value uniqueness; organisation-scoped uniqueness protects private identifiers.

## Non-goals

No fuzzy embeddings, LLM entity resolution, structure matching or crystallographic equivalence engine is implemented yet.
