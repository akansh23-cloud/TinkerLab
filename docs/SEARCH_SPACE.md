# Candidate Search Space

A `CandidateSearchSpace` is a versioned, project-scoped statement of what a generator is permitted to change.

## Structured controls

`SearchSpaceComponentRule` records support:

- baseline-component reference;
- component key/display name/role;
- locked/mutable/required/prohibited flags;
- min/max/step amount;
- amount unit/basis;
- deterministic sequence.

`SearchSpaceProcessRule` records support bounded numeric process-state parameters with explicit units.

The search space additionally declares material family, balance component, target total/tolerance, maximum component count, candidate budget and maximum enumeration.

## Validation

Validation checks family compatibility, baseline availability, redaction restrictions, ranges, basis, required/prohibited/locked constraints, process units, approved substitution availability and estimated combinatorial cardinality. Scientific validation problems return structured codes rather than generic server errors.

## Versioning

Executed search spaces are treated as auditable inputs. Cloning creates a new version. Search-space version is part of the canonical checksum, so an otherwise identical clone intentionally receives a different auditable checksum.
