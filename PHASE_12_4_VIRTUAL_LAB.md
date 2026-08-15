# Phase 12.4 — Virtual Experiment Lab (No AI)

## Product decision

Generative AI has been removed from the Virtual Experiment Lab. The lab is intentionally deterministic and evidence-driven.

## What remains

- Hybrid industrial 2D animation + interactive 3D specimen visualization.
- Thermal/furnace, dielectric-breakdown, and mechanical-loading test bays.
- Operator-controlled visualization setpoints.
- Evidence-linked PASS / FAIL / UNKNOWN states.
- Candidate ADVANCE / REJECT / HOLD / TEST decisions.
- Deterministic Decision Rationale showing what is known, what evidence is missing, and the next workflow action.
- Explicit boundary that a visual cycle does not create a measurement.

## Removed

- Gemini integration.
- `GEMINI_API_KEY` and `GEMINI_MODEL`.
- Lab Copilot API routes, schemas, services, tests, and frontend controls.
- AI status indicators and AI guardrail UI.

## Scientific boundary

The Virtual Lab visualizes an experiment setup and operating sequence. It does not manufacture physical measurements. Authoritative decisions remain downstream of stored evidence, validated computation, physical-validation records, and deterministic replacement rules.

## Deployment

No additional integration is required for the Virtual Lab itself. Keep the existing Neon/Postgres configuration. Materials Project remains optional for external computational/reference data ingestion.
