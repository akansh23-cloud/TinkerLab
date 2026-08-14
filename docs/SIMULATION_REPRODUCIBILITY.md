# Simulation reproducibility

## The checksum chain

```
representation.normalized_checksum
  → input_snapshot.input_checksum
      (representation + provider version identity + method + normalized parameters
       + conditions + artifact checksums + builder version + unit normalization version)
    → job.operational_checksum  (input + command descriptor + environment manifest + resources + attempt)
      → result.result_checksum  (input + provider identity + parser version + parse status
                                 + quantities + convergence status/metrics/criteria + artifact checksums)
        → workflow.workflow_checksum  (template + ordered step checksums + result + scientific status)
```

## What never participates

Timestamps, elapsed times, row ids, display names, ownership and workdir tokens are excluded from every
scientific checksum. Two runs of the same science produce the same `result_checksum` even though every
row id differs — verified by a replay test against the seeded workflow.

## Determinism claims are per-provider

`deterministic` is declared per provider version. The software fixture is deterministic and its replay
identity is tested. LAMMPS is declared non-deterministic; TinkerLab does not claim bit-identical
reproduction for a solver that does not offer it. Changing any scientific parameter changes the input
checksum — also tested.

## Immutable snapshots

The input snapshot is written before execution and never updated. A later edit to the source
representation cannot retroactively change what a past run actually consumed.
