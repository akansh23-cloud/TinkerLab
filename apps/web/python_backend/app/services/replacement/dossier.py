"""Phase 10 — Reproducibility snapshots and the technical replacement dossier.

A snapshot records enough references for a technical reviewer to reconstruct exactly how a decision
was reached: which requirement versions, which candidates, which material states, which evidence
rows, which policy, which methodology versions. Its checksum is computed over sorted canonical
content with no timestamps and no randomness, so the same program state always hashes identically.

The dossier is the flagship output. Every number and every status in it is read from stored platform
data — the generator has no path to invent a value, and a section with no evidence renders as an
explicit statement that the evidence is absent rather than being quietly omitted.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import (
    Candidate,
    ExperimentPlan,
    ExperimentProtocolVersion,
    ExperimentRun,
    IndustrialEvidence,
    MaterialPropertyObservation,
    MaterialState,
    Measurement,
    PredictionTarget,
    ProcessingHistory,
    PropertyPrediction,
    ReplacementProgram,
    ReplacementProgramSnapshot,
    ReplacementRecommendation,
    ScientificRepresentation,
    SimulationResult,
    TechnicalDossier,
)
from app.services.replacement.context import PortfolioContext
from app.services.replacement.convergence import latest_convergence
from app.services.replacement.coverage import decision_matrix
from app.services.replacement.gaps import program_gaps
from app.services.replacement.policy import checksum, policy_summary, resolve_criticality
from app.services.replacement.portfolio import candidate_decision_state, portfolio_board
from app.services.replacement.ranking import rank_candidates, sensitivity_analysis
from app.services.replacement.recommendation import (
    METHODOLOGY_VERSIONS,
    QUALIFICATION_NOTE,
    build_recommendation,
)

SNAPSHOT_METHODOLOGY = "program-snapshot-v1"
DOSSIER_METHODOLOGY = "technical-dossier-v2"

UNKNOWN_MARKER = "UNKNOWN"


# ---------------------------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------------------------
def build_snapshot_payload(context: PortfolioContext) -> dict[str, Any]:
    """Collect the reference sets that define a reproducible decision."""
    db = context.db

    requirements_ref = sorted(
        [
            {
                "requirement_id": requirement.id, "key": requirement.key,
                "requirement_version": getattr(requirement, "requirement_version", 1),
                "requirement_kind": requirement.requirement_kind,
                "criticality": resolve_criticality(requirement),
                "approval_status": getattr(requirement, "approval_status", "accepted"),
                "origin": getattr(requirement, "requirement_origin", "user_defined"),
                "direction": requirement.direction, "target_value": requirement.target_value,
                "target_value_upper": requirement.target_value_upper,
                "target_unit": requirement.target_unit,
                "property_key": requirement.property_key,
                "conditions": requirement.conditions or {},
            }
            for requirement in context.requirements
        ],
        key=lambda r: str(r["requirement_id"]),
    )

    portfolio_ref = sorted(
        [
            {
                "candidate_id": view.candidate_id, "candidate_kind": view.candidate_kind,
                "target_kind": view.target_kind, "target_id": view.target_id,
                "state_id": view.state_id, "display_name": view.display_name,
            }
            for view in context.candidates
        ],
        key=lambda r: str(r["candidate_id"]),
    )

    state_ids = sorted({v.state_id for v in context.candidates if v.state_id})
    incumbent_state = context.incumbent_state()
    if incumbent_state is not None:
        state_ids = sorted(set(state_ids) | {incumbent_state.id})
    material_states_ref = []
    for state_id in state_ids:
        state = db.get(MaterialState, state_id)
        if state is None:
            continue
        material_states_ref.append({
            "state_id": state.id, "label": state.label, "phase": state.phase,
            "polymorph": state.polymorph, "temperature_k": state.temperature_k,
            "state_checksum": getattr(state, "state_checksum", None),
        })

    scientific_ref: list[dict[str, Any]] = []
    industrial_ref: list[dict[str, Any]] = []
    experimental_ref: list[dict[str, Any]] = []

    for view in context.candidates:
        reasoning = context.reasoning_for(view)
        for result in reasoning["requirement_results"]:
            for value in (result.get("values") or []):
                scientific_ref.append({
                    "candidate_id": view.candidate_id,
                    "requirement_id": result["requirement_id"],
                    "origin": value.get("origin"), "source_id": value.get("source_id"),
                    "value": value.get("value"), "unit": value.get("unit"),
                    "state_match": value.get("state_match"),
                })
        industrial = context.industrial_for(view)
        for row in ((industrial.get("evidence_snapshot") or {}).get("evidence") or []):
            industrial_ref.append({"candidate_id": view.candidate_id, **row})
        decision = context.decision_for(view)
        for measurement_id in (decision.get("validation", {}).get("measurement_ids") or []):
            measurement = db.get(Measurement, measurement_id)
            if measurement is None:
                continue
            experimental_ref.append({
                "candidate_id": view.candidate_id, "measurement_id": measurement.id,
                "measurement_checksum": measurement.measurement_checksum,
                "quality": measurement.quality, "run_id": measurement.run_id,
                "sample_id": measurement.sample_id, "instrument_id": measurement.instrument_id,
            })

    scientific_ref.sort(key=lambda r: (str(r["candidate_id"]), str(r["requirement_id"]), str(r["source_id"])))
    industrial_ref.sort(key=lambda r: (str(r["candidate_id"]), str(r.get("id"))))
    experimental_ref.sort(key=lambda r: (str(r["candidate_id"]), str(r["measurement_id"])))

    payload = {
        "program_id": context.program.id,
        "requirements_ref": requirements_ref,
        "portfolio_ref": portfolio_ref,
        "material_states_ref": material_states_ref,
        "scientific_evidence_ref": scientific_ref,
        "industrial_evidence_ref": industrial_ref,
        "experimental_evidence_ref": experimental_ref,
        "decision_policy_ref": policy_summary(context.policy),
        "methodology_versions": dict(METHODOLOGY_VERSIONS) | {"snapshot": SNAPSHOT_METHODOLOGY},
    }
    # Deterministic by construction: sorted collections, no timestamps, no generated identifiers.
    payload["snapshot_checksum"] = checksum({
        "methodology": SNAPSHOT_METHODOLOGY,
        "program": context.program.id,
        "requirements": requirements_ref,
        "portfolio": portfolio_ref,
        "material_states": material_states_ref,
        "scientific_evidence": scientific_ref,
        "industrial_evidence": industrial_ref,
        "experimental_evidence": experimental_ref,
        "decision_policy": policy_summary(context.policy),
        "methodology_versions": payload["methodology_versions"],
    })
    return payload


def create_snapshot(
    db: Session, program: ReplacementProgram, *, label: str | None = None,
    created_by: str | None = None,
) -> ReplacementProgramSnapshot:
    from app.services.replacement.programs import record_event

    context = PortfolioContext(db, program)
    payload = build_snapshot_payload(context)
    convergence = latest_convergence(
        db, organisation_id=program.organisation_id, program_id=program.id
    )
    recommendation = (
        db.query(ReplacementRecommendation)
        .filter(ReplacementRecommendation.program_id == program.id,
                ReplacementRecommendation.organisation_id == program.organisation_id,
                ReplacementRecommendation.superseded_by_id.is_(None))
        .order_by(ReplacementRecommendation.version.desc())
        .first()
    )
    row = ReplacementProgramSnapshot(
        organisation_id=program.organisation_id, program_id=program.id, label=label,
        requirements_ref=payload["requirements_ref"], portfolio_ref=payload["portfolio_ref"],
        material_states_ref=payload["material_states_ref"],
        scientific_evidence_ref=payload["scientific_evidence_ref"],
        industrial_evidence_ref=payload["industrial_evidence_ref"],
        experimental_evidence_ref=payload["experimental_evidence_ref"],
        decision_policy_ref=payload["decision_policy_ref"],
        methodology_versions=payload["methodology_versions"],
        convergence_assessment_id=convergence.id if convergence else None,
        recommendation_id=recommendation.id if recommendation else None,
        snapshot_checksum=str(payload["snapshot_checksum"]), created_by=created_by,
    )
    db.add(row)
    db.flush()
    record_event(
        db, program=program, kind="snapshot_created",
        summary=f"Reproducibility snapshot created with checksum {row.snapshot_checksum[:12]}.",
        payload={"snapshot_checksum": row.snapshot_checksum},
        reference_kind="replacement_program_snapshot", reference_id=row.id,
        actor_user_id=created_by,
    )
    return row


# ---------------------------------------------------------------------------------------------
# Technical dossier
# ---------------------------------------------------------------------------------------------
def _section(number: int, title: str, content: dict[str, Any]) -> dict[str, Any]:
    return {"number": number, "title": title, "content": content}


def _incumbent_profile(context: PortfolioContext) -> dict[str, Any]:
    """Assemble the incumbent profile, marking genuinely absent structural data as UNKNOWN.

    Atomic coordinates are never fabricated. When no representation is registered, the profile says
    so; a plausible-looking invented unit cell would be far worse than an honest gap.
    """
    db = context.db
    material = context.incumbent_material()
    state = context.incumbent_state()
    if material is None:
        return {"status": UNKNOWN_MARKER, "detail": "No incumbent material is attached to this program."}

    representation = None
    if state is not None and getattr(state, "representation_id", None):
        representation = db.get(ScientificRepresentation, state.representation_id)

    history = None
    if state is not None and getattr(state, "processing_history_id", None):
        history = db.get(ProcessingHistory, state.processing_history_id)

    observations = (
        db.query(MaterialPropertyObservation)
        .filter(MaterialPropertyObservation.material_id == material.id,
                MaterialPropertyObservation.status == "active")
        .order_by(MaterialPropertyObservation.id)
        .all()
    )
    industrial_rows = (
        db.query(IndustrialEvidence)
        .filter(IndustrialEvidence.material_id == material.id)
        .order_by(IndustrialEvidence.category, IndustrialEvidence.metric_key)
        .all()
    )

    return {
        "material_id": material.id,
        "display_name": material.display_name,
        "material_family": material.material_family,
        "composition_summary": material.composition_summary or UNKNOWN_MARKER,
        "state": {
            "state_id": state.id if state else None,
            "label": state.label if state else UNKNOWN_MARKER,
            "phase": (state.phase if state else None) or UNKNOWN_MARKER,
            "crystal_system": (state.crystal_system if state else None) or UNKNOWN_MARKER,
            "space_group_symbol": (state.space_group_symbol if state else None) or UNKNOWN_MARKER,
            "space_group_number": (state.space_group_number if state else None) or UNKNOWN_MARKER,
            "polymorph": (state.polymorph if state else None) or UNKNOWN_MARKER,
            "temperature_k": (state.temperature_k if state else None),
            "pressure_pa": (state.pressure_pa if state else None),
        },
        "structural_representation": (
            {
                "representation_id": representation.id,
                "label": representation.label,
                "representation_type": representation.representation_type,
                "representation_format": representation.representation_format,
                "validation_status": representation.validation_status,
                "completeness_status": representation.completeness_status,
                "atom_count": representation.atom_count,
                "chemical_elements": list(representation.chemical_elements or []),
                "normalized_checksum": representation.normalized_checksum,
            }
            if representation is not None
            else {
                "status": UNKNOWN_MARKER,
                "detail": "No structural representation is registered for this state. Unit-cell and "
                          "atomic-coordinate data are genuinely unavailable and are not invented.",
            }
        ),
        "processing_history": (
            {"history_id": history.id, "key": history.key, "display_name": history.display_name}
            if history is not None else {"status": UNKNOWN_MARKER}
        ),
        "functional_properties": [
            {"property_definition_id": row.property_definition_id, "value": row.numeric_value,
             "unit": row.unit, "conditions": row.conditions or {}, "evidence_id": row.evidence_id,
             "curator_note": row.curator_note}
            for row in observations
        ] or [{"status": UNKNOWN_MARKER,
               "detail": "No property observation is recorded for the incumbent in this database."}],
        "industrial_context": [
            {"category": row.category, "metric_key": row.metric_key,
             "as_of_date": str(row.as_of_date) if row.as_of_date else UNKNOWN_MARKER,
             "evidence_id": row.id}
            for row in industrial_rows
        ] or [{"status": UNKNOWN_MARKER,
               "detail": "No industrial evidence is recorded for the incumbent."}],
    }


def _experimental_sections(context: PortfolioContext, candidate_id: str | None) -> dict[str, Any]:
    db = context.db
    candidate_ids = [candidate_id] if candidate_id else [v.candidate_id for v in context.candidates]
    plans = (
        db.query(ExperimentPlan)
        .filter(ExperimentPlan.organisation_id == context.organisation_id,
                ExperimentPlan.candidate_id.in_(candidate_ids))
        .order_by(ExperimentPlan.id)
        .all()
    ) if candidate_ids else []
    plan_ids = [p.id for p in plans]
    runs = (
        db.query(ExperimentRun).filter(ExperimentRun.plan_id.in_(plan_ids)).order_by(ExperimentRun.id).all()
        if plan_ids else []
    )
    run_ids = [r.id for r in runs]
    measurements = (
        db.query(Measurement).filter(Measurement.run_id.in_(run_ids)).order_by(Measurement.id).all()
        if run_ids else []
    )

    protocols = []
    for plan in plans:
        version = db.get(ExperimentProtocolVersion, plan.protocol_version_id)
        if version is None:
            continue
        protocols.append({
            "plan_id": plan.id, "protocol_version_id": version.id, "version": version.version,
            "protocol_checksum": version.protocol_checksum, "is_frozen": version.is_frozen,
            "replicate_requirement": version.replicate_requirement,
            "control_requirement": version.control_requirement,
        })

    return {
        "protocols": protocols or [{"status": UNKNOWN_MARKER,
                                    "detail": "No experiment protocol has been used for this candidate."}],
        "runs": [
            {"run_id": run.id, "plan_id": run.plan_id, "status": run.status,
             "is_control": run.is_control, "replicate_index": run.replicate_index,
             "conditions": run.conditions or {},
             "protocol_checksum_at_run": run.protocol_checksum_at_run}
            for run in runs
        ] or [{"status": UNKNOWN_MARKER, "detail": "No experimental run exists."}],
        "measurements": [
            {"measurement_id": m.id, "run_id": m.run_id, "value": m.numeric_value, "unit": m.unit,
             "canonical_value": m.canonical_value, "canonical_unit": m.canonical_unit,
             "uncertainty": m.uncertainty, "quality": m.quality,
             "admissibility_codes": list(m.admissibility_codes or []),
             "measurement_checksum": m.measurement_checksum, "notes": m.notes}
            for m in measurements
        ] or [{"status": UNKNOWN_MARKER, "detail": "No measurement has been recorded."}],
    }


def build_dossier_sections(
    context: PortfolioContext, *, candidate_id: str | None = None,
) -> list[dict[str, Any]]:
    """The 21 dossier sections, every one populated from stored platform data."""
    db = context.db
    program = context.program
    recommendation_payload = build_recommendation(context)
    matrix = decision_matrix(context)
    gaps = program_gaps(context)
    board = portfolio_board(context)
    ranking = rank_candidates(context)
    sensitivity = sensitivity_analysis(context)
    convergence_row = latest_convergence(
        db, organisation_id=program.organisation_id, program_id=program.id
    )
    focus = context.candidate(candidate_id) if candidate_id else None

    predictions: list[dict[str, Any]] = []
    simulations: list[dict[str, Any]] = []
    for view in ([focus] if focus else context.candidates):
        if view is None:
            continue
        # A prediction does not carry its own target discriminator: it points at a PredictionTarget,
        # which holds either a material or a hypothesis. The join below is what keeps a hypothesis
        # prediction from being attributed to a known material that happens to share an identifier.
        target_column = (
            PredictionTarget.material_id if view.target_kind == "known_material"
            else PredictionTarget.hypothesis_id
        )
        prediction_rows = (
            db.query(PropertyPrediction, PredictionTarget)
            .join(PredictionTarget, PropertyPrediction.prediction_target_id == PredictionTarget.id)
            .filter(target_column == view.target_id,
                    PredictionTarget.organisation_id == context.organisation_id)
            .order_by(PropertyPrediction.id).all()
        )
        predictions.extend({
            "candidate_id": view.candidate_id, "prediction_id": row.id,
            "prediction_target_id": target.id,
            "property_definition_id": row.property_definition_id,
            "value": row.numeric_point_estimate, "unit": row.output_unit,
            "canonical_value": row.canonical_value, "canonical_unit": row.canonical_unit,
            "interval_low": row.uncertainty_lower, "interval_high": row.uncertainty_upper,
            "uncertainty_stddev": row.uncertainty_stddev,
            "applicability": row.applicability_status,
        } for row, target in prediction_rows)
        simulation_rows = (
            db.query(SimulationResult)
            .filter(SimulationResult.target_kind == view.target_kind,
                    SimulationResult.target_scientific_id == view.target_id,
                    SimulationResult.organisation_id == context.organisation_id)
            .order_by(SimulationResult.id).all()
        )
        simulations.extend({
            "candidate_id": view.candidate_id, "result_id": row.id,
            "scientific_status": row.scientific_status, "job_id": row.job_id,
        } for row in simulation_rows)

    industrial_sections: list[dict[str, Any]] = []
    for view in ([focus] if focus else context.candidates):
        if view is None:
            continue
        industrial = context.industrial_for(view)
        industrial_sections.append({
            "candidate_id": view.candidate_id,
            "overall_state": industrial.get("overall_state"),
            "dimension_states": industrial.get("dimension_states") or {},
            "hard_constraint_failures": industrial.get("hard_constraint_failures") or [],
            "unknown_dimensions": industrial.get("unknown_dimensions") or [],
            "maturity_stage": industrial.get("maturity_stage") or UNKNOWN_MARKER,
            "composite_score": industrial.get("composite_score"),
        })

    experimental = _experimental_sections(context, focus.candidate_id if focus else None)

    candidate_identity: dict[str, Any] = {"status": UNKNOWN_MARKER}
    if focus is not None:
        state = candidate_decision_state(context, focus)
        candidate_identity = {
            "candidate_id": focus.candidate_id, "display_name": focus.display_name,
            "candidate_kind": focus.candidate_kind, "candidate_source": focus.candidate_source,
            "target_kind": focus.target_kind, "target_id": focus.target_id,
            "state_id": focus.state_id, "lineage": focus.hypothesis_lineage,
            "generation_rationale": focus.generation_rationale or UNKNOWN_MARKER,
            "portfolio_state": state["portfolio_state"], "eligibility": state["eligibility"],
        }

    provenance_appendix = build_snapshot_payload(context)

    sections = [
        _section(1, "Replacement Program", {
            "program_id": program.id, "name": program.name, "key": program.key,
            "description": program.description or UNKNOWN_MARKER,
            "project_id": program.project_id, "program_state": program.status,
            "decision_policy_version": program.decision_policy_version,
            "is_demonstration_data": program.is_demonstration_data,
        }),
        _section(2, "Application Context", {
            "application_id": program.application_id or UNKNOWN_MARKER,
            "application_name": program.application_name or UNKNOWN_MARKER,
            "application_domain": program.application_domain or UNKNOWN_MARKER,
            "role_id": program.role_id or UNKNOWN_MARKER,
            "context": program.application_context or {},
        }),
        _section(3, "Incumbent Material Profile", _incumbent_profile(context)),
        _section(4, "Candidate Identity & Lineage", candidate_identity),
        _section(5, "Functional Requirements", {
            "requirements": [
                {
                    "requirement_id": r.id, "key": r.key, "display_name": r.display_name,
                    "criticality": resolve_criticality(r), "requirement_kind": r.requirement_kind,
                    "origin": getattr(r, "requirement_origin", "user_defined"),
                    "approval_status": getattr(r, "approval_status", "accepted"),
                    "direction": r.direction, "target_value": r.target_value,
                    "target_unit": r.target_unit, "rationale": r.rationale or UNKNOWN_MARKER,
                }
                for r in context.requirements
            ] or [{"status": UNKNOWN_MARKER, "detail": "No requirement is defined."}],
        }),
        _section(6, "Scientific Evidence", {
            "requirement_results": matrix["rows"],
            "note": matrix["note"],
        }),
        _section(7, "Property Predictions", {
            "predictions": predictions or [{"status": UNKNOWN_MARKER,
                                            "detail": "No property prediction exists."}],
        }),
        _section(8, "Physics Simulations", {
            "simulations": simulations or [{"status": UNKNOWN_MARKER,
                                            "detail": "No simulation result exists."}],
        }),
        _section(9, "Industrial Viability", {"assessments": industrial_sections or [
            {"status": UNKNOWN_MARKER, "detail": "No industrial assessment is available."}]}),
        _section(10, "Manufacturing Compatibility", {
            "dimensions": [
                {"candidate_id": row["candidate_id"],
                 "manufacturing_compatibility": (row["dimension_states"] or {}).get(
                     "manufacturing_compatibility", UNKNOWN_MARKER)}
                for row in industrial_sections
            ] or [{"status": UNKNOWN_MARKER}],
        }),
        _section(11, "Cost / Supply / Regulatory Evidence", {
            "dimensions": [
                {"candidate_id": row["candidate_id"],
                 "economic_feasibility": (row["dimension_states"] or {}).get(
                     "economic_feasibility", UNKNOWN_MARKER),
                 "supply_resilience": (row["dimension_states"] or {}).get(
                     "supply_resilience", UNKNOWN_MARKER),
                 "regulatory_compatibility": (row["dimension_states"] or {}).get(
                     "regulatory_compatibility", UNKNOWN_MARKER)}
                for row in industrial_sections
            ] or [{"status": UNKNOWN_MARKER}],
        }),
        _section(12, "Experimental Protocols", {"protocols": experimental["protocols"]}),
        _section(13, "Experimental Results", {
            "runs": experimental["runs"], "measurements": experimental["measurements"],
        }),
        _section(14, "Contradictions & Uncertainty", {
            "conflicting_evidence": recommendation_payload["conflicting_evidence"] or [
                {"status": "NONE", "detail": "No conflicting evidence was detected."}],
        }),
        _section(15, "Evidence Gaps", {
            "by_class": gaps["by_class"], "counts": gaps["counts"],
        }),
        _section(16, "Candidate Comparison", {
            "board": board["candidates"], "counts": board["counts"],
        }),
        _section(17, "Pareto / Ranking Analysis", {
            "ranked": ranking["ranked"], "excluded": ranking["excluded"],
            "pareto": ranking["pareto"], "sensitivity": sensitivity,
            "note": ranking["note"],
        }),
        _section(18, "Convergence State", {
            "convergence_state": convergence_row.convergence_state if convergence_row else UNKNOWN_MARKER,
            "metrics": convergence_row.metrics if convergence_row else {},
            "reasons": list(convergence_row.reasons or []) if convergence_row else [],
            "presentation_progress_percent": (
                convergence_row.presentation_progress_percent if convergence_row else None
            ),
            "note": "Convergence is completed decision work, not a probability of success.",
        }),
        _section(19, "Replacement Recommendation", {
            "status": recommendation_payload["status"],
            "recommended_candidate_ids": recommendation_payload["recommended_candidate_ids"],
            "rejected_candidate_ids": recommendation_payload["rejected_candidate_ids"],
            "held_candidate_ids": recommendation_payload["held_candidate_ids"],
            "rationale": recommendation_payload["rationale"],
            "reason_codes": recommendation_payload["reason_codes"],
            "qualification_note": QUALIFICATION_NOTE,
        }),
        _section(20, "Outstanding Qualification Work", {
            "next_actions": recommendation_payload["next_actions"],
            "note": (
                "These are scientific next steps within TinkerLab. Regulatory qualification, "
                "production release and customer approval are separate processes that TinkerLab "
                "does not perform and does not track."
            ),
        }),
        _section(21, "Complete Provenance Appendix", provenance_appendix),
        _section(22, "External Data Attribution", _attribution_content(db, provenance_appendix)),
        _section(23, "External Dataset Versions", _snapshot_content(db, provenance_appendix)),
    ]
    return sections


def _referenced_evidence_ids(provenance: dict[str, Any]) -> list[str]:
    return sorted({
        str(row.get("source_id")) for row in provenance.get("scientific_evidence_ref", [])
        if row.get("source_id")
    } | {
        str(row.get("id")) for row in provenance.get("industrial_evidence_ref", []) if row.get("id")
    })


def _attribution_content(db: Session, provenance: dict[str, Any]) -> dict[str, Any]:
    """Credits required by attribution licences, plus the compliance position for each provider."""
    from app.services.replacement.licensing import attribution_block, licence_audit

    evidence_ids = _referenced_evidence_ids(provenance)
    audit = licence_audit(db, evidence_ids=evidence_ids)
    block = attribution_block(db, evidence_ids=evidence_ids)
    return {
        "attribution": block["entries"] or [
            {"status": "NONE", "detail": "No third-party licensed data required attribution."}
        ],
        "statement": block["statement"],
        "licence_positions": audit["providers"] or [
            {"status": "NONE", "detail": "All evidence in this dossier was produced locally."}
        ],
        "export_permitted": audit["export_permitted"],
        "restricted_providers": audit["restricted"],
        "note": audit["note"],
    }


def _snapshot_content(db: Session, provenance: dict[str, Any]) -> dict[str, Any]:
    """External dataset releases actually used by this dossier — no organisation-wide leakage."""
    from app.services.replacement.licensing import referenced_snapshot_ids, snapshot_manifest

    evidence_ids = _referenced_evidence_ids(provenance)
    snapshot_ids = referenced_snapshot_ids(db, evidence_ids=evidence_ids)
    if not snapshot_ids:
        return {
            "snapshots": [{"status": UNKNOWN_MARKER,
                           "detail": "No external dataset was used in this programme."}],
            "fully_reproducible": True,
            "note": "All evidence referenced by this dossier originates locally.",
        }
    return snapshot_manifest(db, snapshot_ids=snapshot_ids)


def generate_dossier(
    db: Session, program: ReplacementProgram, *, candidate_id: str | None = None,
    snapshot_id: str | None = None, created_by: str | None = None,
) -> TechnicalDossier:
    """Generate a new dossier version. Regeneration never overwrites a historical dossier."""
    from app.services.replacement.programs import record_event

    context = PortfolioContext(db, program)
    if candidate_id and context.candidate(candidate_id) is None:
        raise LookupError("Candidate not found in this program's portfolio")

    sections = build_dossier_sections(context, candidate_id=candidate_id)
    previous = (
        db.query(TechnicalDossier)
        .filter(TechnicalDossier.program_id == program.id,
                TechnicalDossier.organisation_id == program.organisation_id)
        .order_by(TechnicalDossier.version.desc())
        .first()
    )
    version = (previous.version + 1) if previous else 1

    recommendation = (
        db.query(ReplacementRecommendation)
        .filter(ReplacementRecommendation.program_id == program.id,
                ReplacementRecommendation.organisation_id == program.organisation_id,
                ReplacementRecommendation.superseded_by_id.is_(None))
        .order_by(ReplacementRecommendation.version.desc())
        .first()
    )
    convergence = latest_convergence(
        db, organisation_id=program.organisation_id, program_id=program.id
    )

    provenance = next(s for s in sections if s["number"] == 21)["content"]

    # Refuse to produce an exportable dossier that would breach a data licence. Failing here is
    # recoverable; discovering it after a customer has filed the document is not.
    from app.services.replacement.licensing import LicenceComplianceError, licence_audit

    audit = licence_audit(db, evidence_ids=_referenced_evidence_ids(provenance))
    if not audit["export_permitted"]:
        offenders = ", ".join(
            f"{p['provider_key']} ({p['status']})" for p in audit["blocking"]
        )
        raise LicenceComplianceError(
            "DOSSIER_EXPORT_BLOCKED: this programme draws on evidence whose licence does not "
            f"permit this export (commercial use, redistribution, or review status): {offenders}. "
            "Record a cleared licence position for these providers, or remove their evidence, "
            "before exporting."
        )
    evidence_ids = sorted({
        str(row.get("source_id")) for row in provenance.get("scientific_evidence_ref", [])
        if row.get("source_id")
    } | {
        str(row.get("measurement_id")) for row in provenance.get("experimental_evidence_ref", [])
        if row.get("measurement_id")
    } | {
        str(row.get("id")) for row in provenance.get("industrial_evidence_ref", []) if row.get("id")
    })

    candidate = db.get(Candidate, candidate_id) if candidate_id else None
    title = (
        f"Technical replacement dossier — {program.name}"
        + (f" — candidate {context.candidate(candidate_id).display_name}" if candidate_id else "")
    )

    row = TechnicalDossier(
        organisation_id=program.organisation_id, program_id=program.id, version=version,
        candidate_id=candidate.id if candidate else None, title=title, sections=sections,
        snapshot_id=snapshot_id, recommendation_id=recommendation.id if recommendation else None,
        convergence_assessment_id=convergence.id if convergence else None,
        assessment_ids=[i for i in [
            recommendation.id if recommendation else None,
            convergence.id if convergence else None,
        ] if i],
        evidence_ids=evidence_ids,
        methodology_versions=dict(METHODOLOGY_VERSIONS) | {"dossier": DOSSIER_METHODOLOGY},
        decision_policy_version=program.decision_policy_version,
        # No LLM is invoked anywhere in this generator. The flag exists so that a future optional
        # narrative layer is recorded explicitly rather than becoming invisible.
        llm_narrative_used=False,
        dossier_checksum=checksum({
            "methodology": DOSSIER_METHODOLOGY, "program": program.id,
            "candidate": candidate_id, "sections": sections,
        }),
    )
    db.add(row)
    db.flush()
    record_event(
        db, program=program, kind="dossier_generated",
        summary=f"Technical dossier v{version} generated.",
        payload={"version": version, "candidate_id": candidate_id},
        candidate_id=candidate_id, reference_kind="technical_dossier", reference_id=row.id,
        actor_user_id=created_by,
    )
    return row
