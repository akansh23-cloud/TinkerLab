# Scientific representations

A material's *name* or *formulation* is not a physics input. Phase 6 introduces an explicit
representation layer so the system can state precisely what it knows about a target's structure.

## Formats and types

| Format | Representation type | Adequate for |
| --- | --- | --- |
| `software_fixture_json_v1` | `software_validation_fixture` | The reduced-unit software fixture only |
| `periodic_structure_json_v1` | `periodic_atomic_structure` | Periodic DFT |
| `atomistic_topology_json_v1` | `molecular_topology` | Classical MD |
| `phase_description_json_v1` | `phase_description` | CALPHAD (interface-only in Phase 6) |
| `formulation_summary_json_v1` | `formulation_only` | Bookkeeping only — never atomistic methods |

The format implies the type. A caller cannot relabel a formulation as a crystal structure.

## Three separate questions

Validation reports these independently and never collapses them:

1. **Syntax** — did the payload parse against the declared format? (`valid` / `invalid_syntax` / `structurally_invalid`)
2. **Structural completeness** — does it contain everything the format requires? (`complete` / `incomplete` / `redacted`)
3. **Method applicability** — decided by the router, never by the validator.

A file that parses is not thereby chemically correct, and the system never says it is.

## What is never inferred

* Atomic identity: an unrecognised element symbol is a rejection, not a guess.
* Topology: bonds and atom types are never derived from component labels.
* Force-field mapping: a topology without an explicit `force_field_key` is `incomplete`.
* Symmetry: a space group that was not supplied is reported as not supplied, not computed from coordinates.
* Phases: candidate phases must be declared.
* Redacted composition: flagged as `redacted`, never filled in with a plausible substitute.

## Checksums

`normalized_checksum = sha256(canonical_json({contract, format, validator, normalized_content}))`.

Content only. Labels, ownership, timestamps and row ids never participate. Sites and components are
sorted into a stable order so submission order does not change identity, while any change to a lattice
vector, coordinate or element does. Bounds: 512,000 bytes per payload and 512 atomic sites.
