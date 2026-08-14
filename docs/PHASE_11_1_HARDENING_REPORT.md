# TinkerLab Phase 11.1 — External Data Integrity & Scientific Provenance Hardening

Phase 11.1 hardens Phase 11 without replacing its connector architecture. The patch preserves all
Phase 1–10 behavior while closing correctness gaps at the external-data boundary.

## Load-bearing fixes

### Content-addressed dataset snapshots

`DatasetSnapshot.content_checksum` now hashes the connector contract, dataset key, provider dataset
version, exact query descriptor, and a sorted set of `{external_id, raw_checksum}` entries. Two
provider responses with the same IDs and version but different values therefore produce different
snapshot checksums.

The exact raw provider record is also retained in `SourceRecord.raw_payload`; normalized data is no
longer substituted for raw input.

### Dataset version semantics and pagination

- OPTIMADE `meta.api_version` is retained as API/software provenance only. It is never used as a
  dataset release.
- OPTIMADE snapshots are reproducible only when an explicit provider dataset/database version is
  exposed **and** the full paginated result set was retrieved.
- OPTIMADE follows `links.next` and honours `meta.more_data_available`; incomplete pagination fails
  closed as non-reproducible.
- Materials Project uses an explicit database/data version only; `api_version` is not a dataset pin.
- Materials Project pagination is bounded and records whether the requested result set was complete.

### Conservative material identity

Phase 11 ingestion now routes normalized identifiers through the existing `resolve_identity()`
service before creating a material. Exact trusted identifiers merge; probable/ambiguous name or
composition signals are recorded but do not trigger an automatic scientific merge.

Provider identifiers are normalized onto the existing ORM contract (`namespace`, `value`,
`normalized_value`) and are organisation-scoped. Important mappings include:

- Materials Project / OPTIMADE-MP -> `materials_project`
- PubChem -> `pubchem_cid`, `inchikey`, `inchi`, `smiles`
- EPA CompTox -> `dtxsid`

This allows a Materials Project record and its OPTIMADE representation to converge on one canonical
material while refusing to merge polymorphs merely because they share a formula.

### Stoichiometry integrity

The former fallback `stoichiometry = 1.0` for every element has been removed. A conservative formula
parser now supports standard element/count formulas, nested parentheses/brackets and middle-dot
hydrates. It validates element symbols and fails closed on unsupported or ambiguous syntax.

Examples:

- `Ga2O3` -> Ga:2, O:3
- `Al2O3` -> Al:2, O:3
- invalid/ambiguous formula -> no inferred composition, never 1:1

Anonymous OPTIMADE formulas such as `AB2` are display labels only and are not treated as chemical
composition.

### PubChem evidence semantics

PubChem values are classified as `reference_database_record`, not `experimental_measured`. PubChem
molar mass therefore becomes external reference evidence; TinkerLab does not claim that PubChem
performed a physical experiment.

### Computation provenance

Unknown Materials Project calculation provenance now maps to `dft_unspecified_static`, not an
invented PBE claim. The value carries a high-severity `COMPUTATIONAL_METHOD_UNSPECIFIED` warning and
remains screening evidence until the method can be recovered.

Explicit HSE/SCAN/GGA+U descriptors continue to resolve to their respective method classes. Provider
calculation descriptors are preserved when present. Property-specific calculation provenance is also
supported: if one provider record aggregates properties from different workflows, each observation
can bind to a method-specific child Evidence row rather than inheriting one record-wide method.

Reference, regulatory and structural database records have separate method families and are not
stored with a `computational_method_id`.

### CompTox substance identity

A CompTox list name is no longer a material identity. `DTXSID` is the substance identity; list name
is regulatory-membership evidence. Multiple chemicals on `PFASMASTER` therefore remain multiple
materials rather than collapsing into one pseudo-material named after the list.

Industrial evidence written from external ingestion now links directly to the originating
`SourceRecord`.

### Licence and export integrity

`REDISTRIBUTION_RESTRICTED` is now an export-blocking status alongside unreviewed and
commercial-use-forbidden positions. Internal use may still be possible, but a dossier containing
restricted third-party records cannot be exported as cleared.

Human compliance review is authoritative. Connector defaults refresh connector-managed licence
rows but do not overwrite a row whose `license_reviewed_by` records a human/legal review.

OPTIMADE licences are registered per originating sub-provider (`optimade:<prefix>`), not as though
the OPTIMADE federation itself licensed all records. Unknown sub-provider terms remain unreviewed and
are blocked at ingest.

### Dossier snapshot scope

Section 23 now contains only dataset snapshots transitively referenced by the dossier's actual
scientific/industrial evidence. Unrelated organisation-level imports can no longer make a dossier
appear non-reproducible or contaminate its provenance manifest.

Industrial evidence IDs are also resolved through `SourceRecord` during licence audit, so regulatory
records cannot bypass the export gate simply because they are not `Evidence` rows.

## Product integration

Phase 11 is now exposed as a product workflow:

- `GET /external-data/providers`
- `POST /external-data/ingest`
- `GET /external-data/methods`
- `GET /external-data/snapshots`
- `GET /external-data/snapshots/{id}`
- Web page: `/data-sources`

Materials Project and EPA API keys are server-side settings only:

```env
MATERIALS_PROJECT_API_KEY=
EPA_COMPTOX_API_KEY=
```

The browser never receives them. Operator-supplied OPTIMADE URLs are restricted to credential-free
HTTPS hosts and private/local network targets are rejected before connection.

The web Docker build now copies `package-lock.json` and uses `npm ci`.

## Regression coverage added

Phase 11.1 includes adversarial tests for:

- same record ID/version with changed content -> changed snapshot checksum;
- OPTIMADE API version not treated as dataset version;
- OPTIMADE pagination completion;
- PubChem end-to-end ORM identifier persistence;
- PubChem reference-vs-experimental classification;
- `Ga2O3` stoichiometry preservation;
- invalid formula -> no invented 1:1 composition;
- distinct DTXSIDs on the same CompTox list remaining distinct materials;
- Materials Project + OPTIMADE exact-identifier convergence;
- redistribution-restricted evidence blocking export;
- human-reviewed licence preservation;
- dossier snapshot manifests containing only referenced snapshots;
- external-data provider/snapshot/method API visibility and evidence-level outward provenance;
- local/private OPTIMADE SSRF rejection and bounded query payloads.

## Verification performed

- Phase 11/11.1 targeted test module: **passes**.
- Full backend pytest suite: **444 passed, 6 skipped**; the six solver-runtime tests remain intentionally skipped when
  LAMMPS / Quantum ESPRESSO binaries are unavailable.
- Python compilation of modified modules: **passes**.
- Frontend type/build verification requires installed npm dependencies. The extracted package did
  not contain `node_modules`; a lockfile install was attempted in the constrained build environment
  but did not complete, so no frontend-build success is claimed here.
- `ruff` was not installed in the execution environment, so no lint success is claimed.

## Remaining production validation boundary

This hardening does not claim that third-party live APIs cannot change. Before a production data
campaign, re-record fixtures against the live provider endpoints and review current provider terms.
A live-provider schema/terms check is an operational release gate, not something an offline fixture
suite can prove.
