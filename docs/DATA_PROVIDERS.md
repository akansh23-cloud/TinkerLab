# Data Provider Contracts

`MaterialDataProvider` / `ProviderAdapter` exposes provider key, adapter version, capabilities and deterministic normalization.

Phase 2 ships one exercised provider: `local_import`.

A `phase2_demo` provider exists only for deterministic seed provenance and does not represent an external scientific database.

Materials Project integration is intentionally not claimed in this bundle because live API/client requirements could not be exercised in the offline build environment. A future adapter must use current official Materials Project documentation, preserve MP IDs/source records and mark provider-computed properties as computational rather than experimental.
