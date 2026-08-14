# Observation Selection Policy

Selection is deterministic and explainable.

Default rules:

1. Exclude retracted/superseded observations.
2. Exclude evidence marked retracted/superseded.
3. Apply explicit allowed-evidence policy when supplied.
4. An exact requested-condition match outranks a missing-condition fallback.
5. A contradictory reported condition is excluded as inapplicable.
6. Explicit curator preference outranks otherwise eligible peers and records rationale.
7. Equal top candidates remain a visible tie; TinkerLab chooses a deterministic display row but states that this is not scientific consensus.

The service returns selected observation, applicability, rationale, alternatives, exclusions and unknown reason. Project comparison stores no hidden aggregate truth value.
