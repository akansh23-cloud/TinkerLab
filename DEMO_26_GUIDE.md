# TinkerLab — August 26 Demo Guide

This build keeps the stable Phase 12.2.4 Vercel runtime and adds a demo-first product layer.

## The one-sentence product story

**TinkerLab is a material-replacement decision OS: define what the incumbent material must do, screen alternatives with traceable evidence, run the next useful test when evidence is missing, reject candidates that fail blocking requirements, and preserve a defensible decision trail.**

## What changed in this build

1. Dashboard now explains the product as a six-step decision loop rather than exposing labs first.
2. New explicit `POST /api/bench/install-flagship-demo` installs the synthetic ADVANCE / REJECT / HOLD programme. It is idempotent and separate from normal deployment bootstrap.
3. Replacement Mission Control opens on a new **Story** tab.
4. Each candidate shows:
   - what was tested;
   - the target;
   - PASS / FAIL / UNKNOWN / conflict;
   - why that verdict was reached;
   - ADVANCE / REJECT / HOLD decision;
   - the next test/action when evidence is insufficient.
5. External Data Sources now has quick Materials Project presets for SiC, GaN, AlN and wide-gap carbon records, with a clear computational-vs-physical evidence boundary.

## Flagship story

Scenario: replace silicon in a high-temperature power-electronics switching application at 525 K and 3.3 kV.

Blocking requirements:
- breakdown field >= 2.0 MV/cm;
- band gap >= 2.5 eV;
- thermal conductivity >= 150 W/(m*K).

Desirable objective:
- higher electron mobility.

### Candidate A — ADVANCE

Synthetic evidence is complete and consistent. Replicated test values support the blocking gates, so the candidate can advance to the next programme stage.

### Candidate B — REJECT

The initial synthetic observation suggests breakdown field = 3.3 MV/cm, but replicated synthetic physical-test records are 1.10 and 1.18 MV/cm. Both are below the 2.0 MV/cm blocking threshold. TinkerLab rejects the candidate instead of allowing strong band gap, thermal conductivity or mobility to average the failure away.

### Candidate C — HOLD / TEST

The band-gap evidence is promising, but breakdown field and thermal conductivity are absent. TinkerLab does not convert missing evidence into a failure or a pass. It keeps the candidate on hold and proposes the evidence needed to resolve the blocking gaps.

## Recommended 5-minute demo sequence

### 0:00–0:40 — Problem

Open Dashboard and use the "What TinkerLab is building" section.

Say: "Material replacement is not just finding a similar material. A substitute must preserve the functions of the incumbent under the application conditions, and every critical requirement has to be defensible."

### 0:40–1:00 — Load the flagship demo

Click **Load flagship ADVANCE / REJECT / HOLD demo**. It redirects directly to Replacement Mission Control.

### 1:00–2:30 — Show the three outcomes

Stay on the **Story** tab.

Show Candidate A first, then Candidate B, then Candidate C. The contrast is the product:
- A: evidence supports advance;
- B: real test logic overrides a promising earlier value and rejects;
- C: missing evidence triggers another test instead of a guess.

### 2:30–3:20 — Open the Decision Matrix

Show that every requirement x candidate cell has an explicit status and rationale. Emphasize that UNKNOWN is not FAIL and a blocking FAIL cannot be averaged away by other strong properties.

### 3:20–4:00 — Show Gaps and Actions

Open **Gaps**, then **Actions**. This is the closed-loop part: TinkerLab tells the team what evidence is missing and what action would resolve it.

### 4:00–4:35 — Show real external data

Open **External data sources**. Use a Materials Project preset such as SiC or GaN and ingest a governed snapshot if the API key is configured.

Say: "This is real computational provider data with provenance. TinkerLab keeps it separate from physical validation. A database value can screen a candidate; it does not become a lab measurement."

### 4:35–5:00 — Close with the decision artifact

Return to Mission Control -> Recommendation. Generate the recommendation / dossier.

Say: "The output is not 'AI says use material X'. The output is a versioned engineering decision with the evidence, blockers, missing tests and methodology that produced it."

## What not to claim in the demo

- Do not call synthetic demo values real measurements.
- Do not say TinkerLab autonomously discovers or qualifies a new material.
- Do not say Materials Project computational values are experimental results.
- Do not call a recommendation regulatory or manufacturing approval.
- Do not hide UNKNOWN values. They are part of the product's credibility.

## Deployment

No new mandatory infrastructure is introduced.

Required:
- Neon/Postgres `DATABASE_URL`;
- `NEXT_PUBLIC_ORGANISATION_ID=0b5ec369-282c-57b5-9781-471f818a07c3`;
- `ENVIRONMENT=production`;
- `LOG_LEVEL=INFO`.

Recommended for the live-data part of the demo:
- `MATERIALS_PROJECT_API_KEY`.

After deployment:
1. verify `/api/health`;
2. open Dashboard;
3. click **Load flagship ADVANCE / REJECT / HOLD demo**;
4. confirm Mission Control opens on **Story** and shows all three candidate outcomes.
