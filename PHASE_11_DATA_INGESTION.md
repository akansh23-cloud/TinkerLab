# Phase 11 / 11.1 — Governed External Data Ingestion

Phase 11 connects TinkerLab to external materials, chemical and regulatory databases without
weakening the evidence, identity and decision guarantees established in Phases 1–10. Phase 11.1
hardens the scientific and legal boundaries discovered during adversarial review.

The guiding rule is simple: external data may expand the evidence graph, but it may not silently
change what a material is, what kind of evidence a value represents, whether a dataset is
reproducible, or whether a dossier may legally redistribute the underlying records.

## 1. Structural licence policy

`SourceProvider` records licence state as structured fields rather than prose:

- `license_identifier`, `license_url`;
- `commercial_use_permitted`;
- `redistribution_permitted`;
- `attribution_required`, `attribution_text`;
- `license_reviewed_at`, `license_reviewed_by`.

Connector declarations are defaults, not authority to erase a legal review. Connector-managed rows
may be refreshed by the adapter; a row explicitly reviewed by a person remains authoritative until
a reviewer changes it.

The ingest gate blocks an unreviewed provider and blocks commercial ingestion when commercial use
is not permitted. Redistribution is a separate concern: internally usable evidence may still be
non-redistributable. The dossier licence audit therefore blocks export when any referenced provider
is `UNREVIEWED`, `COMMERCIAL_USE_FORBIDDEN`, or `REDISTRIBUTION_RESTRICTED`.

OPTIMADE is a protocol, not a licensor. TinkerLab registers OPTIMADE provenance per originating
provider (`optimade:<provider-prefix>`). Unknown provider terms remain unreviewed and are refused by
the ingest gate instead of inheriting a fictional federation-wide licence.

The licence positions bundled with connectors are implementation defaults and must be re-reviewed
against current provider terms before a production campaign.

## 2. Content-addressed dataset snapshots

Every connector fetch produces a `DatasetSnapshot`. Its content checksum includes:

- connector framework/version;
- dataset key;
- provider dataset/database version when one is actually exposed;
- exact query descriptor;
- a sorted set of each external record ID and the SHA-256 checksum of that raw record.

Therefore the same external IDs and version string with changed values produce a different snapshot
checksum.

`SourceRecord.raw_payload` retains the actual provider record. The normalized representation is not
substituted for raw input.

A provider API/software version is **not** a dataset version. In particular, OPTIMADE
`meta.api_version` is retained only as API provenance. A snapshot is marked reproducible only when
the provider exposes a genuine dataset/database release and the requested result set is known to be
complete. Unversioned or incomplete pulls are retained with `is_reproducible = false` and an
explicit reason rather than receiving a false reproducibility claim.

Dossier section 23 is derived transitively from the evidence used by that dossier. Unrelated
organisation-level imports are excluded.

## 3. Complete, bounded retrieval

OPTIMADE follows `links.next` and observes `meta.more_data_available`. A result that indicates more
pages without a usable next link is marked incomplete/non-reproducible rather than silently treated
as complete.

Materials Project retrieval is bounded by explicit page/record caps and records whether the
requested result was complete. Provider pagination contracts remain a live-integration validation
boundary because external APIs can change independently of this repository.

## 4. Conservative canonical material identity

External records are routed through the existing identity resolver before a new `Material` is
created.

- Exact trusted identifiers may merge onto an existing canonical material.
- Name-only or composition-only probable/ambiguous matches are recorded but do not auto-merge.
- Identifier namespaces are normalized and organisation-scoped.
- Namespace matching is case-insensitive.

Important namespaces include `materials_project`, `pubchem_cid`, `inchikey`, `inchi`, `smiles`, and
`dtxsid`. An OPTIMADE record originating from Materials Project can therefore converge on the same
canonical material as a Materials Project API record when the trusted identifier matches.

This is deliberately conservative: two polymorphs that share a formula are not automatically
collapsed into one material.

## 5. Stoichiometry is never fabricated

The former fallback that assigned `1.0` to every listed element has been removed. A conservative
formula parser supports ordinary element/count formulas, nested parentheses/brackets and middle-dot
hydrates, validates element symbols, and fails closed on unsupported or ambiguous syntax.

Examples:

```text
Ga2O3  -> Ga:2, O:3
Al2O3  -> Al:2, O:3
invalid/ambiguous formula -> no inferred composition
```

Anonymous OPTIMADE formulas such as `AB2` are display metadata only and are not interpreted as
chemical composition.

## 6. Evidence origin remains explicit

External database data is not promoted into a stronger evidence class merely because a value is
numeric.

- PubChem reference/provider-derived properties use `reference_database_record`; they are not
  asserted to be experimental measurements.
- CompTox list membership is regulatory evidence, not a physical measurement and not an automatic
  legal verdict.
- OPTIMADE structural records are structural-reference evidence unless an originating provider
  explicitly supplies calculation provenance.
- Computational Materials Project values remain computational evidence.

Only actual measurement workflows should use the experimental evidence class.

## 7. Computational provenance fails closed

Known calculation descriptors can map to reviewed method classes such as PBE, SCAN, HSE06 or
GGA+U. If Materials Project does not expose enough calculation provenance, TinkerLab records
`dft_unspecified_static`; it does **not** invent PBE. When a provider record exposes different
calculation provenance for different properties, TinkerLab creates method-specific child evidence
for those observations rather than assigning one workflow to the whole record.

Method-risk magnitude bands in the catalogue are warning heuristics, not universal scientific error
bars and never correction factors. They are not silently applied to values. Unknown calculation
provenance produces a high-severity warning so a computed value can remain useful for screening
without masquerading as governing evidence.

Static-lattice DFT state is represented at its nominal 0 K boundary rather than as an ambient
measurement. Requirement/state mismatch warnings are preserved in evidence provenance.

## 8. CompTox substance identity

A regulatory list name is not a substance identifier. `DTXSID` is load-bearing for substance
identity; list name remains membership/context evidence. Multiple chemicals on the same list remain
multiple materials.

External `IndustrialEvidence` links to the originating `SourceRecord`, allowing licence and dataset
snapshot provenance to be followed from a dossier back to the exact source record.

## 9. Product surfaces

Phase 11.1 is accessible through the application service/API rather than only via Python connector
classes:

- `GET /external-data/providers`
- `GET /external-data/methods`
- `POST /external-data/ingest`
- `GET /external-data/snapshots`
- `GET /external-data/snapshots/{id}`
- Web: `/data-sources`

Materials Project and EPA CompTox credentials are server-side settings only. They are never sent to
the browser.

Operator-supplied OPTIMADE targets must be credential-free HTTPS endpoints. Obvious local/private
network targets are rejected before connection, and request/query size is bounded.

Existing material/evidence responses expose provider licence fields, source-record snapshot IDs,
evidence snapshot IDs, computational-method IDs and applicability warnings so provenance is visible
to clients rather than stored only internally.

## 10. Transport and deployment

Connectors receive an injected `Transport`. Production `HttpTransport` uses the already-pinned
`httpx` dependency with bounded retry/rate limiting; tests use `FixtureTransport`, so connector
regressions are deterministic and do not depend on live provider availability.

The web Docker dependency stage copies `package-lock.json` and uses `npm ci`.

Server-side keys:

```env
MATERIALS_PROJECT_API_KEY=
EPA_COMPTOX_API_KEY=
```

## 11. Dossier changes

The Phase 11 dossier adds:

- **§22 External Data Attribution** — attribution and provider licence position for evidence actually
  used by the dossier.
- **§23 External Dataset Versions** — exact referenced snapshots, checksums and reproducibility
  status.

A dossier containing evidence whose redistribution rights are not cleared raises
`LicenceComplianceError` rather than being exported as legally cleared.

## 12. Migration

`0013_phase11` is additive and follows `0012_phase10`. It adds external dataset/method provenance and
structured licence fields. Phase 11.1 fixes application logic and outward schemas without requiring
a destructive migration.

Current chain:

```text
... -> 0011_phase9_1b -> 0012_phase10 -> 0013_phase11
```

## 13. Verification boundary

The offline regression suite covers connector normalization, content-addressed snapshots,
pagination semantics, identity convergence, ORM persistence, stoichiometry, evidence origin,
licence/export enforcement, human licence overrides, dossier snapshot scoping, API provenance and
security input guards.

The repository does **not** claim that offline fixtures prove current live-provider schemas or legal
terms. Before a production campaign:

1. validate each connector against the live provider API;
2. re-record/review fixtures from current response shapes;
3. review current provider terms with the appropriate legal/compliance owner;
4. pin or explicitly mark any dataset that cannot expose an immutable release;
5. verify provider-specific pagination and calculation-provenance fields;
6. keep unknown OPTIMADE providers blocked until their terms are reviewed.

See `PHASE_11_1_HARDENING_REPORT.md` for the adversarial defects closed by Phase 11.1.
