# TinkerLab — Material Replacement Operating System (through Phase 11.1)

TinkerLab is an evidence-first operating system for material replacement studies. The current repository implements the scientific workflow through **Phase 11.1 — External Data Integrity & Scientific Provenance Hardening**.

The platform keeps scientific and industrial claim classes separate:

- `MaterialPropertyObservation` — observed/literature evidence with provenance.
- `PropertyPrediction` — model output with applicability and uncertainty.
- `SimulationResult` — physics-simulation output; computational evidence, never physical evidence.
- `IndustrialEvidence` — manufacturing, economic, supply, environmental and regulatory claims with their own comparability context.
- `Measurement` — physical experimental evidence admitted through protocol, sample, instrument, calibration and run-state checks.

Candidate hypotheses remain distinct from canonical materials. Unknown, insufficient, conflicting and non-comparable evidence are explicit states; they are never converted into success to simplify the UI.

## Current implementation status

| Phase | Status | Core capability |
|---|---|---|
| 1–2 | Implemented | Evidence model, replacement projects, deterministic requirements/comparison |
| 3 | Implemented | Bounded Candidate Lab and hypothesis lineage |
| 4 | Implemented | Versioned prediction models, applicability and uncertainty |
| 5 | Implemented | Bounded virtual campaigns and uncertainty-aware Pareto reasoning |
| 6 | Implemented | Physics Simulation OS with reviewed LAMMPS/QE boundaries and deterministic software fixture |
| 7 | Implemented + 9.1 hardening | Industrial viability, manufacturing routes, constraints, maturity and industrial evidence |
| 8 | Implemented + 9.1 hardening | Functional decomposition, material-state-aware reasoning and evidence gaps |
| 9 | Implemented + 9.1 hardening | Protocols, samples, instruments, experiment plans/runs, measurements and validation |
| 9.1 | **Implemented in this package** | Unit/state integrity, tenant isolation, evidence admissibility, deterministic experimental support/contradiction and transparent next-gate decisions |
| 10 | **Implemented** | Closed-loop replacement decision OS, convergence, immutable recommendations and technical dossier |
| 11 | Implemented + 11.1 hardening | Governed external scientific/regulatory ingestion with dataset snapshots and licence provenance |
| 11.1 | **Implemented in this package** | Scientific identity, stoichiometry, content checksums, pagination, export licensing and external-data product workflow hardening |

## Phase 11 / 11.1 external data ingestion

Phase 11 connects TinkerLab to the open materials, chemical and regulatory data ecosystem without
weakening Phase 10's determinism guarantee.

- **Connectors** for OPTIMADE (federated structures), Materials Project (computed properties),
  PubChem (substance identity) and EPA CompTox (regulatory lists, including PFAS).
- **Licence is structural and enforced at the correct boundary.** Unreviewed/commercial-use policy
  gates ingestion; redistribution restrictions gate dossier export. Human review outranks connector defaults.
- **Dataset snapshots** hash the actual returned record content plus query/provider release metadata.
  API software versions are never misrepresented as dataset releases, and incomplete pagination is explicit.
- **Conservative identity and stoichiometry.** Existing trusted identifiers are reused across providers;
  formulas such as `Ga2O3` preserve 2:3 stoichiometry and invalid formulas never fall back to 1:1.
- **Evidence-method provenance.** Unknown DFT method stays unknown; mixed provider workflows can bind
  methods per property; PubChem/regulatory/structural records are never promoted to measurements.
- **Export licence firewall.** Unreviewed, commercial-use-forbidden **and redistribution-restricted**
  evidence blocks an exportable dossier. Human legal review is not overwritten by connector defaults.
- **Product workflow.** `/data-sources` and `/external-data/*` expose governed ingestion and snapshot history;
  provider API keys remain server-side.

Documentation: [`docs/PHASE_11_DATA_INGESTION.md`](docs/PHASE_11_DATA_INGESTION.md),
[`docs/PHASE_11_1_HARDENING_REPORT.md`](docs/PHASE_11_1_HARDENING_REPORT.md).

## Phase 10 closed-loop replacement decision OS

Phase 10 composes the existing Phase 7/8/9.1 engines into a defensible replacement decision. It adds
no new science engine and reimplements none of them.

- **Replacement programmes** bind one application role, one incumbent state, one candidate portfolio
  and one versioned decision policy. Program state is resolved from evidence, never set by a client
  (except `PAUSED` and `ARCHIVED`, which express human intent).
- **Decision matrix** of requirement × candidate, where `UNKNOWN`, `INCONCLUSIVE`, `CONFLICTING` and
  `NOT_COMPARABLE` are first-class outcomes that never reject a candidate on their own.
- **Eligibility partition** (BLOCKED / UNRESOLVED / ELIGIBLE) evaluated before any ranking, so a
  blocked candidate can never out-rank an eligible one.
- **Evidence gaps and next-best actions**, prioritized by a transparent, reproducible decision-value
  formula that is explicitly not an expected value of information. Recommending an action never
  starts it.
- **Convergence** reported as a state plus counted metrics. The progress percentage is presentation
  only and always carries a disclaimer that it is not a probability of success.
- **Recommendations** that are immutable, versioned, explained by a `DecisionDelta`, and allowed to
  conclude `NO_SUITABLE_CANDIDATE`.
- **Technical dossier** of 21 sections, every value read from stored data; absent evidence renders as
  an explicit `UNKNOWN` rather than being omitted or invented.

No LLM decides a PASS/FAIL, ranking, rejection, convergence state, next action or recommendation.

Documentation: [`docs/PHASE_10_REPLACEMENT_DECISION_OS.md`](docs/PHASE_10_REPLACEMENT_DECISION_OS.md),
[`docs/PHASE_10_DECISION_METHODOLOGY.md`](docs/PHASE_10_DECISION_METHODOLOGY.md),
[`docs/PHASE_10_IMPLEMENTATION_REPORT.md`](docs/PHASE_10_IMPLEMENTATION_REPORT.md).

## Phase 9.1 scientific integrity guarantees

Phase 9.1 adds two sequential hardening layers:

### 9.1-A — Scientific Integrity, Provenance & Decision Correctness

- numerical requirements are compared only after compatible unit conversion;
- material-state identity preserves meaningful composition fractions and doping quantities;
- missing state-defining context does not silently become compatibility;
- private prediction, simulation, maturity, industrial and experimental evidence is organisation-scoped;
- candidate/project/target cross-references are semantically validated;
- Phase-5 `feasibility_class` feeds Phase-7 scientific suitability correctly;
- industrial conflicts are gated by context comparability (jurisdiction, geography, process and cost basis as applicable);
- monetary ranges require currency, currency year and cost basis;
- composite viability weights are finite, non-negative and produce bounded scores;
- nullable target uniqueness for manufacturing compatibility is enforced with PostgreSQL partial unique indexes.

### 9.1-B — Experimental Admissibility & Closed-Loop Validation

- accepted measurement existence is **not** equivalent to requirement support;
- accepted experiments can support, contradict, conflict with or be inconclusive for a requirement;
- experiment runs have explicit `planned → ready → running → completed` lifecycle semantics plus invalidation/cancellation;
- planned/ready measurements cannot become accepted physical evidence; running measurements remain provisional;
- protocol property, instrument capability, sample provenance, calibration validity, conditions and unit compatibility feed one admission service;
- invalidating a run preserves measurement history while removing it from governing evidence;
- experimental conflicts are assessed only for comparable conditions/states;
- validation snapshots preserve the measurements, protocol checksums, instruments/calibrations and reasoning checksum used;
- project workflows are candidate-centric across Industrial Viability and Scientific Validation;
- a transparent replacement-decision endpoint exposes blockers/unresolved evidence and **does not claim commercial approval**.

See:

- `docs/PHASE_9_1_A_IMPLEMENTATION_REPORT.md`
- `docs/PHASE_9_1_B_IMPLEMENTATION_REPORT.md`
- `docs/PHASE_9_1_SCIENTIFIC_INTEGRITY.md`

## Scientific boundaries

Every virtual-campaign surface must be understood as model-based evaluation, not a physical experiment. Every simulation result remains computational evidence. An accepted experiment is a separate evidence origin and never overwrites prediction or simulation history.

TinkerLab does **not** autonomously operate laboratory hardware. Manual experimental record entry is implemented. LIMS, instrument API, robotic-platform and contract-laboratory integration kinds remain declared adapter boundaries, not simulated connections.

`EXPERIMENTALLY_SUPPORTED` means the configured experimental gates are supported by admissible measurements. It does **not** by itself mean certified, qualified, regulatory-approved or authorized for commercial replacement.

## Candidate-centric workflow

```text
Replacement Project
    ↓
Functional Requirements
    ↓
Candidate Lab
    ↓
Prediction
    ↓
Virtual Evaluation
    ↓
Physics Simulation
    ↓
Industrial Viability
    ↓
State-Aware Reasoning / Evidence Gaps
    ↓
Experiment Recommendation
    ↓
Protocol-Pinned Experiment Plan
    ↓
Run + Sample + Instrument + Calibration
    ↓
Admissible Physical Measurement
    ↓
Requirement-Level Experimental Outcome
    ↓
Transparent Replacement Next-Gate Decision
```

The project page links directly to Candidate Lab, Prediction Lab, Virtual Experiment Lab, Industrial Viability and Scientific Validation.

## Clean-machine run

Prerequisites: Docker + Docker Compose.

```bash
cp .env.example .env
docker compose up --build
```

Open:

- Web: `http://localhost:3000`
- API/OpenAPI: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

The current Alembic chain runs through:

```text
0001 → … → 0010_phase9_1a → 0011_phase9_1b → 0012_phase10 → 0013_phase11
```

and the deterministic seed data is then loaded.

## Local development

### API

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL='postgresql+psycopg://tinkerlab:tinkerlab@localhost:5432/tinkerlab'
alembic upgrade head
python -m app.db.seed
uvicorn app.main:app --reload --port 8000
```

### Web

```bash
cd apps/web
npm ci
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
NEXT_PUBLIC_ORGANISATION_ID=0b5ec369-282c-57b5-9781-471f818a07c3 \
npm run dev
```

`X-Organisation-ID` / `NEXT_PUBLIC_ORGANISATION_ID` remains a **development scoping seam, not production authentication**. Production identity/authorization hardening remains future work.

## External scientific runtimes

The Phase-6 LAMMPS and Quantum ESPRESSO adapters refuse honestly when required binaries/artifacts are unavailable. A clean machine must not fabricate solver output. CALPHAD and ML interatomic-potential providers remain interface boundaries unless a reviewed provider is explicitly available.

## Verification

Validated for Phase 11.1: **444 backend tests passed; 6 solver-runtime tests were skipped because the external LAMMPS/QE binaries were unavailable.**

Run the current repository gate from `apps/api`:

```bash
pytest
python -m compileall app tests
alembic upgrade head --sql
```

Where frontend dependencies are installed, also run the repository web test/type/lint/build commands. The implementation reports record the exact verification performed for this Phase-9.1 package and explicitly identify unavailable external/runtime checks rather than claiming them.
