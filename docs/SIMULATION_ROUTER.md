# The simulation router

## Contract

The router answers: *given this target, what can be simulated honestly, and what cannot?* It returns
one entry per method/provider pair with a typed status and explicit reasons. **It persists nothing.**

## Statuses

| Status | Meaning |
| --- | --- |
| `ready` | Representation, artifacts, lifecycle and runtime availability all check out |
| `incomplete_representation` | The required representation is absent, invalid or incomplete |
| `missing_registered_artifact` | An approved potential / pseudopotential / database is not registered |
| `provider_unavailable` | Lifecycle blocked, interface-only, or the binary is not installed |
| `unsupported_property` | The method does not produce the requested property |
| `unsupported_conditions` | The requested conditions are outside the method's support |
| `not_applicable` | The method does not apply to this target |

## Ordering

Deterministic: status rank, then reason count, then provider key, method key and version. **Fidelity
never orders routes on its own** — a DFT route is not "better" than an MD route in the abstract, and
the router does not pretend otherwise.

## Refusal is a first-class outcome

A refusal is the correct scientific answer when the inputs do not support a method. Every refusal
states what is missing and what would unlock the route. The canonical example: a formulation-level
polymer description routes to DFT and MD as refusals, because atoms, topology and force fields cannot
be inferred from component names.

## Cross-tenant behaviour

A target outside the caller's scope returns 404, not 403 — a 403 would confirm the row exists.
