# Privacy and Scope Model

Phase 3 extends the Phase-2 organisation-visibility seam.

## Scoped resources

The following require explicit `X-Organisation-ID` matching the owning project/organisation:

- candidate search spaces;
- substitution-rule mutations;
- generation runs/results;
- Candidate Lab mixed candidate lists;
- candidate hypothesis detail/lineage/status;
- comparison responses when `include_hypotheses=true`.

Known-material retrieval considers public materials plus private materials owned by the project organisation; it cannot retrieve another organisation's private material.

Checksums/fingerprints are one-way SHA-256 digests of canonicalized scientific structure and are not intended as reversible storage of raw private payloads. Generation logs include IDs/checksum prefixes/counts but not raw formulations.

## Important limitation

`X-Organisation-ID` is a **development scoping mechanism only**. It is not authentication or authorization. Production identity/RBAC/SSO is deferred to the enterprise phase and must replace this seam before production multi-tenant use.

## Phase 4 prediction privacy

Prediction runs/results/targets are organisation/project scoped. Private material or hypothesis features are only exposed in an explicitly scoped prediction-detail response; normal list/run result APIs do not return the full normalized feature vector.

Logs must not contain raw private formulations or full feature payloads. Global model training from customer data is not performed by Phase 4 and is not an implied default.

`X-Organisation-ID` remains only a development scoping seam and must be replaced by real authentication/authorization before production use.

## Phase 5 campaign privacy

Campaigns, iterations, evaluations, decisions and hypothesis campaign history require explicit organisation scope. A campaign may not pin another organisation's private model version or include another organisation's private candidate/hypothesis/material.

Campaign API responses expose one-way checksums and decision metadata without returning raw private feature vectors/formulations unless an already-scoped scientific detail endpoint explicitly requires them. Structured campaign logs should contain IDs, count metrics and checksum prefixes only.

Phase 5 does not use private campaign/customer data to retrain global models.

The development `X-Organisation-ID` seam is now permitted by CORS but remains **not authentication or authorization**. Production deployment must replace it with verified identity/RBAC before genuine multi-tenant use.


## Phase 6 — simulation privacy

- Representations, snapshots, workflows, jobs, artifacts, results and estimates are all organisation-scoped.
- Cross-tenant access returns **404**, never 403 — a 403 would confirm the row exists.
- Artifacts are private by default; storage references are opaque `simulation://` locators and no host
  filesystem path is ever returned through the API (asserted by test).
- Redaction flags from a representation propagate into the input snapshot, so redacted components stay
  redacted through the whole provenance chain.
- Child processes receive an environment allowlist only; database URLs and credentials are never inherited.
- Structured logs record checksum prefixes, provider keys and status codes — never file contents,
  proprietary composition or absolute paths.
