"""Phase 10 — Portfolio assessment context.

Every Phase-10 engine (matrix, coverage, gaps, actions, convergence, ranking, recommendation,
dossier) needs the same underlying facts about the same candidates. Computing them independently
would run the Phase-8 reasoning engine six or seven times per candidate for one screen.

This module loads the portfolio once and memoizes each canonical assessment per candidate, so a
whole-program recomputation costs one reasoning pass and one validation pass per candidate rather
than one per consumer. It contains no evaluation logic of its own: `reason_about_candidate`,
`replacement_decision` and `assess_industrial_viability` remain the only sources of truth for
requirement outcomes, experimental support and industrial state respectively.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.models.entities import (
    Candidate,
    CandidateHypothesis,
    DecisionPolicy,
    FunctionalRequirement,
    IndustrialViabilityAssessment,
    Material,
    MaterialFunction,
    MaterialRole,
    MaterialState,
    ReplacementProgram,
)
from app.services.experiments_lab import replacement_decision
from app.services.industrial import assess_industrial_viability
from app.services.material_states import reference_state, states_for_target
from app.services.reasoning import reason_about_candidate
from app.services.replacement.policy import resolve_criticality, resolve_policy


class PortfolioError(ValueError):
    """Raised when a program cannot be assessed because its own configuration is incomplete."""


@dataclass
class CandidateView:
    """One candidate plus every canonical assessment that applies to it, computed at most once."""

    candidate_id: str
    candidate_kind: str
    target_kind: str
    target_id: str
    display_name: str
    candidate_source: str
    portfolio_status: str
    state_id: str | None
    hypothesis_lineage: list[dict[str, Any]] = field(default_factory=list)
    generation_rationale: str | None = None


class PortfolioContext:
    """Loads a program's portfolio once and caches the canonical assessments for it."""

    def __init__(self, db: Session, program: ReplacementProgram, *, candidate_ids: list[str] | None = None):
        self.db = db
        self.program = program
        self.organisation_id = program.organisation_id
        self.policy: DecisionPolicy = resolve_policy(
            db, organisation_id=program.organisation_id, policy_id=program.decision_policy_id
        )
        self.role: MaterialRole | None = db.get(MaterialRole, program.role_id) if program.role_id else None
        self._requirements: list[FunctionalRequirement] | None = None
        self._functions: list[MaterialFunction] | None = None
        self._candidates: list[CandidateView] | None = None
        self._candidate_filter = set(candidate_ids) if candidate_ids else None
        self._reasoning_cache: dict[str, dict[str, Any]] = {}
        self._decision_cache: dict[str, dict[str, Any]] = {}
        self._industrial_cache: dict[str, dict[str, Any]] = {}
        self._incumbent_reasoning: dict[str, Any] | None = None
        # Shared scratch space for derived engines (decision state, ranking, gaps) so a single HTTP
        # request computes each derived structure once even when several engines consume it.
        self.memo: dict[str, Any] = {}

    # -----------------------------------------------------------------------------------------
    # Requirements
    # -----------------------------------------------------------------------------------------
    def _load_decomposition(self) -> None:
        if self._requirements is not None:
            return
        if self.role is None:
            self._functions, self._requirements = [], []
            return
        functions = (
            self.db.query(MaterialFunction)
            .options(selectinload(MaterialFunction.requirements))
            .filter(MaterialFunction.role_id == self.role.id)
            .order_by(MaterialFunction.key)
            .all()
        )
        self._functions = functions
        requirements: list[FunctionalRequirement] = []
        for function in functions:
            requirements.extend(sorted(function.requirements, key=lambda r: r.key))
        self._requirements = requirements

    @property
    def functions(self) -> list[MaterialFunction]:
        self._load_decomposition()
        return list(self._functions or [])

    @property
    def requirements(self) -> list[FunctionalRequirement]:
        self._load_decomposition()
        return list(self._requirements or [])

    @property
    def requirements_by_id(self) -> dict[str, FunctionalRequirement]:
        return {r.id: r for r in self.requirements}

    def authoritative_requirements(self) -> list[FunctionalRequirement]:
        """Only ACCEPTED requirements gate decisions; PROPOSED ones are reported but not enforced."""
        from app.services.replacement.policy import is_authoritative

        return [r for r in self.requirements if is_authoritative(r)]

    def criticality_of(self, requirement_id: str) -> str:
        requirement = self.requirements_by_id.get(requirement_id)
        if requirement is None:
            # A requirement referenced by an assessment but no longer present cannot be assumed
            # unimportant; the caller sees an explicit fallback rather than a silent DESIRABLE.
            return "important"
        return resolve_criticality(requirement)

    # -----------------------------------------------------------------------------------------
    # Candidates
    # -----------------------------------------------------------------------------------------
    def _load_candidates(self) -> None:
        if self._candidates is not None:
            return
        rows = (
            self.db.query(Candidate)
            .filter(Candidate.project_id == self.program.project_id)
            .order_by(Candidate.id)
            .all()
        )
        views: list[CandidateView] = []
        for row in rows:
            if self._candidate_filter is not None and row.id not in self._candidate_filter:
                continue
            if row.candidate_kind == "known_material" and row.material_id:
                material = self.db.get(Material, row.material_id)
                if material is None:
                    continue
                target_kind, target_id = "known_material", row.material_id
                display = material.display_name
                lineage: list[dict[str, Any]] = []
                rationale = None
            elif row.hypothesis_id:
                hypothesis = self.db.get(CandidateHypothesis, row.hypothesis_id)
                if hypothesis is None or hypothesis.organisation_id != self.organisation_id:
                    # Cross-tenant or missing hypotheses never enter a portfolio assessment.
                    continue
                target_kind, target_id = "hypothesis", row.hypothesis_id
                display = hypothesis.display_label
                lineage = [{
                    "kind": "hypothesis", "id": hypothesis.id,
                    "generation_run_id": hypothesis.generation_run_id,
                    "generator_strategy_key": hypothesis.generator_strategy_key,
                    "generator_strategy_version": hypothesis.generator_strategy_version,
                    "deterministic_fingerprint": hypothesis.deterministic_fingerprint,
                    "baseline_material_id": hypothesis.baseline_material_id,
                    "structural_validity": hypothesis.structural_validity,
                }]
                rationale = hypothesis.notes
            else:
                continue
            state = reference_state(
                self.db, target_kind=target_kind, target_id=target_id,
                organisation_id=self.organisation_id,
            )
            views.append(CandidateView(
                candidate_id=row.id, candidate_kind=row.candidate_kind,
                target_kind=target_kind, target_id=target_id, display_name=display,
                candidate_source=row.candidate_source, portfolio_status=row.status,
                state_id=state.id if state else None,
                hypothesis_lineage=lineage, generation_rationale=rationale,
            ))
        # Stable display order: name first so the UI is readable, id as the deterministic tiebreak.
        self._candidates = sorted(views, key=lambda v: (v.display_name, v.candidate_id))

    @property
    def candidates(self) -> list[CandidateView]:
        self._load_candidates()
        return list(self._candidates or [])

    def candidate(self, candidate_id: str) -> CandidateView | None:
        return next((c for c in self.candidates if c.candidate_id == candidate_id), None)

    # -----------------------------------------------------------------------------------------
    # Canonical assessments — memoized, never reimplemented
    # -----------------------------------------------------------------------------------------
    def reasoning_for(self, view: CandidateView) -> dict[str, Any]:
        """Phase-8 requirement evaluation. One pass per candidate per request."""
        cached = self._reasoning_cache.get(view.candidate_id)
        if cached is not None:
            return cached
        if self.role is None:
            raise PortfolioError(
                "PROGRAM_ROLE_NOT_SET: the program has no material role, so requirements cannot be evaluated"
            )
        result = reason_about_candidate(
            self.db, organisation_id=self.organisation_id, role_id=self.role.id,
            target_kind=view.target_kind, target_id=view.target_id,
            project_id=self.program.project_id, candidate_id=view.candidate_id,
            state_id=view.state_id,
        )
        self._reasoning_cache[view.candidate_id] = result
        return result

    def decision_for(self, view: CandidateView) -> dict[str, Any]:
        """Phase-9.1 next-gate decision, which internally performs experimental admission."""
        cached = self._decision_cache.get(view.candidate_id)
        if cached is not None:
            return cached
        if self.role is None:
            raise PortfolioError(
                "PROGRAM_ROLE_NOT_SET: the program has no material role, so validation cannot run"
            )
        result = replacement_decision(
            self.db, organisation_id=self.organisation_id, role_id=self.role.id,
            candidate_id=view.candidate_id, target_kind=view.target_kind,
            target_id=view.target_id, project_id=self.program.project_id,
            persist_validation=False,
        )
        self._decision_cache[view.candidate_id] = result
        return result

    def industrial_for(self, view: CandidateView) -> dict[str, Any]:
        """Phase-7 industrial viability, computed without persisting a new assessment row."""
        cached = self._industrial_cache.get(view.candidate_id)
        if cached is not None:
            return cached
        try:
            _row, payload = assess_industrial_viability(
                self.db, project_id=self.program.project_id, organisation_id=self.organisation_id,
                target_kind=view.target_kind, target_id=view.target_id,
                candidate_id=view.candidate_id, persist=False,
            )
        except (LookupError, ValueError) as exc:
            # An industrial assessment that cannot be computed is reported as not assessed, with the
            # reason preserved. It is never silently treated as passing.
            payload = {
                "overall_state": "not_assessed", "dimension_states": {}, "dimension_details": {},
                "hard_constraint_failures": [], "unknown_dimensions": [], "conflicting_evidence": [],
                "maturity_stage": None, "composite_score": None,
                "unavailable_reason": str(exc),
            }
        self._industrial_cache[view.candidate_id] = payload
        return payload

    def persisted_industrial(self, candidate_id: str) -> IndustrialViabilityAssessment | None:
        return (
            self.db.query(IndustrialViabilityAssessment)
            .filter(IndustrialViabilityAssessment.organisation_id == self.organisation_id,
                    IndustrialViabilityAssessment.project_id == self.program.project_id,
                    IndustrialViabilityAssessment.candidate_id == candidate_id,
                    IndustrialViabilityAssessment.superseded_by_id.is_(None))
            .order_by(IndustrialViabilityAssessment.created_at.desc(), IndustrialViabilityAssessment.id)
            .first()
        )

    # -----------------------------------------------------------------------------------------
    # Incumbent
    # -----------------------------------------------------------------------------------------
    def incumbent_state(self) -> MaterialState | None:
        if self.program.incumbent_state_id:
            state = self.db.get(MaterialState, self.program.incumbent_state_id)
            if state is not None and state.organisation_id == self.organisation_id:
                return state
        if self.role is not None and self.role.incumbent_state_id:
            return self.db.get(MaterialState, self.role.incumbent_state_id)
        return None

    def incumbent_material(self) -> Material | None:
        material_id = self.program.incumbent_material_id or (
            self.role.incumbent_material_id if self.role else None
        )
        return self.db.get(Material, material_id) if material_id else None

    def incumbent_reasoning(self) -> dict[str, Any] | None:
        """Evaluate the incumbent against the same requirements, for the side-by-side view.

        The incumbent is not a candidate and is never ranked. It is evaluated so a reviewer can see
        whether the requirement set is even satisfied by the material currently in service — a
        requirement the incumbent itself fails is usually a requirement error, not a discovery.
        """
        if self._incumbent_reasoning is not None:
            return self._incumbent_reasoning
        material = self.incumbent_material()
        if material is None or self.role is None:
            return None
        state = self.incumbent_state()
        result = reason_about_candidate(
            self.db, organisation_id=self.organisation_id, role_id=self.role.id,
            target_kind="known_material", target_id=material.id,
            project_id=self.program.project_id, state_id=state.id if state else None,
        )
        self._incumbent_reasoning = result
        return result

    def incumbent_states(self) -> list[MaterialState]:
        material = self.incumbent_material()
        if material is None:
            return []
        return states_for_target(
            self.db, target_kind="known_material", target_id=material.id,
            organisation_id=self.organisation_id,
        )
