from __future__ import annotations

import hashlib
import itertools
import json
import logging
import math
import random
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app.models.entities import (
    Candidate,
    CandidateChangeRecord,
    CandidateHypothesis,
    CandidateHypothesisComponent,
    CandidateHypothesisProcessParameter,
    CandidateLineageEdge,
    CandidateSearchSpace,
    GenerationRun,
    GenerationRunResult,
    Material,
    MaterialComponent,
    ReplacementProject,
    SearchSpaceComponentRule,
    SubstitutionRule,
    User,
)
from app.services.conflicts import detect_conflicts_from_observations
from app.services.evaluation import evaluate_constraint
from app.services.selection import build_selection_context
from app.services.specification import compile_specification
from app.services.units import UnitError, convert

FINGERPRINT_VERSION = "candidate-v1"
SEARCH_SPACE_CANONICALIZATION_VERSION = "search-space-v1"
HARD_MAX_CANDIDATES = 1000
HARD_MAX_ENUMERATION = 100000

logger = logging.getLogger("tinkerlab.generation")


STRATEGIES: dict[str, dict[str, Any]] = {
    "known_material_retrieval": {
        "key": "known_material_retrieval", "version": "1.0", "supported_material_families": ["*"],
        "required_inputs": ["material_family"], "creates_hypotheses": False, "deterministic": True,
        "maximum_safe_candidate_count": HARD_MAX_CANDIDATES,
        "description": "Deterministically retrieves existing visible materials without inventing missing properties.",
    },
    "curated_component_substitution": {
        "key": "curated_component_substitution", "version": "1.0", "supported_material_families": ["polymer", "composite", "coating", "adhesive"],
        "required_inputs": ["structured baseline composition", "approved substitution rule"], "creates_hypotheses": True,
        "deterministic": True, "maximum_safe_candidate_count": HARD_MAX_CANDIDATES,
        "description": "Applies only approved curator-defined component substitutions to a concrete baseline representation.",
    },
    "bounded_composition_variation": {
        "key": "bounded_composition_variation", "version": "1.0", "supported_material_families": ["polymer", "composite", "coating", "adhesive"],
        "required_inputs": ["mutable component ranges", "normalization rule"], "creates_hypotheses": True,
        "deterministic": True, "maximum_safe_candidate_count": HARD_MAX_CANDIDATES,
        "description": "Enumerates or deterministically samples only explicit component amount ranges.",
    },
    "bounded_process_variation": {
        "key": "bounded_process_variation", "version": "1.0", "supported_material_families": ["*"],
        "required_inputs": ["process parameter ranges"], "creates_hypotheses": True, "deterministic": True,
        "maximum_safe_candidate_count": HARD_MAX_CANDIDATES,
        "description": "Varies only explicitly permitted process-state parameters; it does not generate executable synthesis instructions.",
    },
    "manual_hypothesis": {
        "key": "manual_hypothesis", "version": "1.0", "supported_material_families": ["*"],
        "required_inputs": ["user-defined concrete components"], "creates_hypotheses": True, "deterministic": True,
        "maximum_safe_candidate_count": 1,
        "description": "Captures a scientist-authored material hypothesis through the same validation, fingerprint, lineage and evidence posture.",
    },
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def checksum(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _norm_float(value: float | None) -> float | None:
    if value is None:
        return None
    return _norm_required_float(value)


def _norm_required_float(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("Non-finite numeric values are not allowed")
    return float(f"{value:.12g}")


def component_key(component: MaterialComponent) -> str:
    if component.component_identifier:
        return component.component_identifier.strip().lower()
    return "_".join(component.component_name.strip().lower().split())


def candidate_payload(material_family: str, components: Iterable[dict[str, Any]], process_parameters: Iterable[dict[str, Any]]) -> dict[str, Any]:
    canonical_components = []
    for c in components:
        canonical_components.append({
            "component_key": str(c["component_key"]).strip().lower(),
            "role": (c.get("role") or "").strip().lower() or None,
            "amount": _norm_float(c.get("amount")),
            "unit": c.get("unit"),
            "basis": c.get("basis"),
            "locked": bool(c.get("locked", False)),
        })
    canonical_components.sort(key=lambda x: (x["component_key"], x["role"] or ""))
    canonical_process = []
    for p in process_parameters:
        canonical_process.append({
            "parameter_key": str(p["parameter_key"]).strip().lower(),
            "value": _norm_float(p["value"]),
            "unit": p["unit"],
        })
    canonical_process.sort(key=lambda x: x["parameter_key"])
    return {
        "fingerprint_version": FINGERPRINT_VERSION,
        "material_family": material_family,
        "components": canonical_components,
        "process_parameters": canonical_process,
    }


def candidate_fingerprint(material_family: str, components: Iterable[dict[str, Any]], process_parameters: Iterable[dict[str, Any]] = ()) -> str:
    return checksum(candidate_payload(material_family, components, process_parameters))


def _search_space_payload(search_space: CandidateSearchSpace) -> dict[str, Any]:
    components = [{
        "component_key": r.component_key,
        "display_name": r.display_name,
        "role": r.role,
        "baseline_component_id": r.baseline_component_id,
        "locked": r.locked, "mutable": r.mutable, "required": r.required, "prohibited": r.prohibited,
        "min_amount": _norm_float(r.min_amount), "max_amount": _norm_float(r.max_amount),
        "step_amount": _norm_float(r.step_amount), "amount_unit": r.amount_unit, "amount_basis": r.amount_basis,
        "sequence": r.sequence,
    } for r in sorted(search_space.component_rules, key=lambda x: (x.sequence, x.component_key))]
    processes = [{
        "parameter_key": r.parameter_key, "min_value": _norm_float(r.min_value), "max_value": _norm_float(r.max_value),
        "step_value": _norm_float(r.step_value), "unit": r.unit, "locked": r.locked,
    } for r in sorted(search_space.process_rules, key=lambda x: x.parameter_key)]
    return {
        "canonicalization_version": SEARCH_SPACE_CANONICALIZATION_VERSION,
        "project_id": search_space.project_id, "version": search_space.version,
        "material_family": search_space.material_family, "amount_basis": search_space.amount_basis,
        "balance_component_key": search_space.balance_component_key, "total_target": _norm_float(search_space.total_target),
        "total_tolerance": _norm_float(search_space.total_tolerance), "max_component_count": search_space.max_component_count,
        "candidate_budget": search_space.candidate_budget, "maximum_enumeration": search_space.maximum_enumeration,
        "components": components, "process_rules": processes,
    }


def search_space_checksum(search_space: CandidateSearchSpace) -> str:
    return checksum(_search_space_payload(search_space))


def get_search_space(db: Session, search_space_id: str) -> CandidateSearchSpace | None:
    return (
        db.query(CandidateSearchSpace)
        .options(selectinload(CandidateSearchSpace.component_rules), selectinload(CandidateSearchSpace.process_rules))
        .filter(CandidateSearchSpace.id == search_space_id)
        .one_or_none()
    )


def _grid(minimum: float, maximum: float, step: float | None) -> list[float]:
    if maximum < minimum:
        return []
    if step is None or abs(maximum - minimum) < 1e-12:
        return [_norm_required_float(minimum)] if abs(maximum - minimum) < 1e-12 else [_norm_required_float(minimum), _norm_required_float(maximum)]
    values: list[float] = []
    value = minimum
    guard = 0
    while value <= maximum + max(abs(step) * 1e-9, 1e-12):
        values.append(_norm_required_float(min(value, maximum)))
        value += step
        guard += 1
        if guard > HARD_MAX_ENUMERATION:
            break
    if values and abs(values[-1] - maximum) > 1e-9:
        values.append(_norm_required_float(maximum))
    return sorted(set(values))


def estimate_cardinality(search_space: CandidateSearchSpace, strategy_key: str | None = None, approved_rule_count: int = 0) -> int:
    if strategy_key == "known_material_retrieval":
        return search_space.candidate_budget
    if strategy_key == "curated_component_substitution":
        return approved_rule_count
    if strategy_key == "bounded_process_variation":
        values = [_grid(r.min_value, r.max_value, r.step_value) for r in search_space.process_rules if not r.locked]
    else:
        values = [_grid(r.min_amount, r.max_amount, r.step_amount) for r in search_space.component_rules if r.mutable and not r.prohibited and r.min_amount is not None and r.max_amount is not None]
    if not values:
        return 0
    result = 1
    for v in values:
        result *= max(len(v), 1)
        if result > HARD_MAX_ENUMERATION:
            return result
    return result


def validate_search_space(db: Session, search_space: CandidateSearchSpace, strategy_key: str | None = None) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    project = db.get(ReplacementProject, search_space.project_id)
    if not project:
        issues.append({"code": "PROJECT_NOT_FOUND", "path": "project_id", "message": "Replacement project not found.", "severity": "error"})
        return {"valid": False, "estimated_cardinality": 0, "issues": issues, "checksum": search_space.checksum}
    baseline = db.query(Material).options(selectinload(Material.components)).filter(Material.id == project.baseline_material_id).one()
    if baseline.material_family != search_space.material_family:
        issues.append({"code": "MATERIAL_FAMILY_MISMATCH", "path": "material_family", "message": "Search-space material family does not match the baseline material.", "severity": "error"})
    if search_space.candidate_budget < 1 or search_space.candidate_budget > HARD_MAX_CANDIDATES:
        issues.append({"code": "CANDIDATE_BUDGET_OUT_OF_RANGE", "path": "candidate_budget", "message": f"Candidate budget must be between 1 and {HARD_MAX_CANDIDATES}.", "severity": "error"})
    keys = [r.component_key for r in search_space.component_rules]
    if len(keys) != len(set(keys)):
        issues.append({"code": "DUPLICATE_COMPONENT_KEY", "path": "component_rules", "message": "Component keys must be unique within a search space.", "severity": "error"})
    baseline_by_id = {c.id: c for c in baseline.components}
    for i, rule in enumerate(search_space.component_rules):
        path = f"component_rules[{i}]"
        if rule.min_amount is not None and rule.max_amount is not None and rule.max_amount < rule.min_amount:
            issues.append({"code": "INVALID_AMOUNT_RANGE", "path": path, "message": "Maximum amount is below minimum amount.", "severity": "error"})
        if rule.prohibited and (rule.required or rule.locked or rule.mutable):
            issues.append({"code": "PROHIBITED_COMPONENT_CONFIGURATION", "path": path, "message": "A prohibited component cannot also be required, locked, or mutable.", "severity": "error"})
        base = baseline_by_id.get(rule.baseline_component_id) if rule.baseline_component_id else None
        if rule.baseline_component_id and not base:
            issues.append({"code": "BASELINE_COMPONENT_NOT_FOUND", "path": path, "message": "Referenced baseline component does not exist on the project baseline.", "severity": "error"})
        if base and base.is_redacted and rule.mutable:
            issues.append({"code": "REDACTED_BASELINE_COMPONENT", "path": path, "message": "Component cannot be mutated because its identity or amount is redacted.", "severity": "error"})
        if rule.mutable and base and base.amount_value is None:
            issues.append({"code": "INCOMPLETE_BASELINE_AMOUNT", "path": path, "message": "Mutable baseline component requires a concrete amount.", "severity": "error"})
        if rule.mutable and (rule.min_amount is None or rule.max_amount is None):
            issues.append({"code": "MUTABLE_RANGE_REQUIRED", "path": path, "message": "Mutable component requires explicit min/max amount.", "severity": "error"})
        if base and rule.amount_basis and base.amount_basis != rule.amount_basis:
            issues.append({"code": "INCOMPATIBLE_AMOUNT_BASIS", "path": path, "message": "Search-space basis differs from baseline component basis.", "severity": "error"})
    if search_space.balance_component_key:
        balance = next((r for r in search_space.component_rules if r.component_key == search_space.balance_component_key), None)
        if not balance:
            issues.append({"code": "BALANCE_COMPONENT_NOT_FOUND", "path": "balance_component_key", "message": "Balance component must exist in component rules.", "severity": "error"})
        elif balance.prohibited:
            issues.append({"code": "BALANCE_COMPONENT_PROHIBITED", "path": "balance_component_key", "message": "Balance component cannot be prohibited.", "severity": "error"})
    for i, process_rule in enumerate(search_space.process_rules):
        path = f"process_rules[{i}]"
        if process_rule.max_value < process_rule.min_value:
            issues.append({"code": "INVALID_PROCESS_RANGE", "path": path, "message": "Process maximum is below minimum.", "severity": "error"})
        try:
            convert(process_rule.min_value, process_rule.unit, process_rule.unit)
            convert(process_rule.max_value, process_rule.unit, process_rule.unit)
        except UnitError as exc:
            issues.append({"code": "INVALID_PROCESS_UNIT", "path": path, "message": str(exc), "severity": "error"})
    approved_count = db.query(SubstitutionRule).filter(
        SubstitutionRule.organisation_id == project.organisation_id,
        or_(SubstitutionRule.project_id == project.id, SubstitutionRule.project_id.is_(None)),
        SubstitutionRule.status == "approved",
        SubstitutionRule.material_family == search_space.material_family,
    ).count()
    cardinality = estimate_cardinality(search_space, strategy_key, approved_count)
    if cardinality > min(search_space.maximum_enumeration, HARD_MAX_ENUMERATION):
        issues.append({"code": "SEARCH_SPACE_TOO_LARGE", "path": "candidate_budget", "message": f"Estimated enumeration {cardinality} exceeds configured safe enumeration limit.", "severity": "error"})
    if strategy_key == "curated_component_substitution" and approved_count == 0:
        issues.append({"code": "NO_APPROVED_SUBSTITUTION_RULES", "path": "substitution_rules", "message": "No approved substitution rules are available for this project/material family.", "severity": "error"})
    if strategy_key == "bounded_composition_variation" and not any(r.mutable for r in search_space.component_rules):
        issues.append({"code": "NO_MUTABLE_COMPONENTS", "path": "component_rules", "message": "Composition variation requires at least one mutable component.", "severity": "error"})
    if strategy_key == "bounded_process_variation" and not any(not r.locked for r in search_space.process_rules):
        issues.append({"code": "NO_MUTABLE_PROCESS_PARAMETERS", "path": "process_rules", "message": "Process variation requires at least one mutable process parameter.", "severity": "error"})
    return {"valid": not any(i["severity"] == "error" for i in issues), "estimated_cardinality": cardinality, "issues": issues, "checksum": search_space.checksum}


def _baseline_concrete_components(db: Session, project: ReplacementProject, search_space: CandidateSearchSpace) -> list[dict[str, Any]]:
    baseline = db.query(Material).options(selectinload(Material.components)).filter(Material.id == project.baseline_material_id).one()
    by_id = {c.id: c for c in baseline.components}
    result: list[dict[str, Any]] = []
    for rule in sorted(search_space.component_rules, key=lambda x: (x.sequence, x.component_key)):
        if rule.prohibited:
            continue
        base = by_id.get(rule.baseline_component_id) if rule.baseline_component_id else None
        if not base:
            continue
        if base.is_redacted or base.amount_value is None:
            raise ValueError(f"Baseline component {rule.component_key} does not have a concrete mutable representation")
        result.append({
            "component_key": rule.component_key, "display_name": rule.display_name or base.component_name,
            "role": rule.role or base.component_role, "amount": base.amount_value,
            "unit": rule.amount_unit or base.amount_unit, "basis": rule.amount_basis or base.amount_basis,
            "source_baseline_component_id": base.id, "substitution_rule_id": None, "locked": rule.locked,
            "metadata": {},
        })
    return result


def structural_screen(search_space: CandidateSearchSpace, components: list[dict[str, Any]], process_parameters: list[dict[str, Any]]) -> list[str]:
    reasons: list[str] = []
    keys = [c["component_key"] for c in components]
    if len(keys) != len(set(keys)):
        reasons.append("duplicate_component_identity")
    rules = {r.component_key: r for r in search_space.component_rules}
    prohibited = {r.component_key for r in search_space.component_rules if r.prohibited}
    required = {r.component_key for r in search_space.component_rules if r.required}
    if prohibited.intersection(keys):
        reasons.append("prohibited_component_present")
    if not required.issubset(set(keys)):
        reasons.append("required_component_missing")
    if len(components) > search_space.max_component_count:
        reasons.append("maximum_component_count_exceeded")
    for c in components:
        if c.get("amount") is not None and c["amount"] < 0:
            reasons.append(f"negative_amount:{c['component_key']}")
        rule = rules.get(c["component_key"])
        if rule and rule.mutable and c.get("amount") is not None:
            if rule.min_amount is not None and c["amount"] < rule.min_amount - 1e-9:
                reasons.append(f"amount_below_range:{c['component_key']}")
            if rule.max_amount is not None and c["amount"] > rule.max_amount + 1e-9:
                reasons.append(f"amount_above_range:{c['component_key']}")
    if search_space.total_target is not None and components and all(c.get("amount") is not None for c in components):
        same_basis = {c.get("basis") for c in components}
        if len(same_basis) == 1 and next(iter(same_basis)) in {"weight_percent", "atomic_percent", "volume_fraction"}:
            total = sum(float(c["amount"]) for c in components)
            if abs(total - search_space.total_target) > search_space.total_tolerance:
                reasons.append("composition_total_outside_tolerance")
    process_rules = {r.parameter_key: r for r in search_space.process_rules}
    for p in process_parameters:
        process_rule = process_rules.get(p["parameter_key"])
        if not process_rule:
            reasons.append(f"process_parameter_not_allowed:{p['parameter_key']}")
            continue
        if p["value"] < process_rule.min_value - 1e-9 or p["value"] > process_rule.max_value + 1e-9:
            reasons.append(f"process_parameter_outside_range:{p['parameter_key']}")
        if p["unit"] != process_rule.unit:
            try:
                convert(p["value"], p["unit"], process_rule.unit)
            except UnitError:
                reasons.append(f"process_parameter_unit_invalid:{p['parameter_key']}")
    return sorted(set(reasons))


@dataclass
class Proposal:
    display_label: str
    components: list[dict[str, Any]]
    process_parameters: list[dict[str, Any]]
    changes: list[dict[str, Any]]
    rationale: str


def _apply_balance(search_space: CandidateSearchSpace, components: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    if search_space.total_target is None:
        return components
    if not search_space.balance_component_key:
        total = sum(c["amount"] for c in components if c.get("amount") is not None)
        return components if abs(total - search_space.total_target) <= search_space.total_tolerance else None
    balance = next((c for c in components if c["component_key"] == search_space.balance_component_key), None)
    if not balance:
        return None
    other = sum(float(c["amount"]) for c in components if c is not balance and c.get("amount") is not None)
    balance_amount = search_space.total_target - other
    if balance_amount < 0:
        return None
    balance["amount"] = _norm_float(balance_amount)
    return components


def _composition_proposals(db: Session, project: ReplacementProject, search_space: CandidateSearchSpace, budget: int, seed: int) -> list[Proposal]:
    base = _baseline_concrete_components(db, project, search_space)
    # A mutable component rule without an explicit bounded range enumerates nothing rather than
    # reaching _grid(None, None, ...), which previously raised a TypeError at runtime.
    mutable: list[SearchSpaceComponentRule] = []
    grids: list[list[float]] = []
    for rule in search_space.component_rules:
        if not rule.mutable or rule.prohibited:
            continue
        low, high = rule.min_amount, rule.max_amount
        if low is None or high is None:
            continue
        mutable.append(rule)
        grids.append(_grid(low, high, rule.step_amount))
    combos = list(itertools.product(*grids)) if grids else []
    # deterministic seeded subset only when budget truncates a larger bounded grid
    if len(combos) > budget:
        rng = random.Random(seed)
        idx = sorted(rng.sample(range(len(combos)), budget))
        combos = [combos[i] for i in idx]
    proposals: list[Proposal] = []
    base_by_key = {c["component_key"]: c for c in base}
    for n, combo in enumerate(combos):
        components = [dict(c) for c in base]
        changes: list[dict[str, Any]] = []
        by_key = {c["component_key"]: c for c in components}
        for rule, amount in zip(mutable, combo, strict=True):
            before = by_key[rule.component_key]["amount"]
            by_key[rule.component_key]["amount"] = amount
            if abs(float(before) - float(amount)) > 1e-12:
                changes.append({"change_type": "component_amount_change", "target_path": f"components.{rule.component_key}.amount", "before": {"value": before, "unit": by_key[rule.component_key]["unit"]}, "after": {"value": amount, "unit": by_key[rule.component_key]["unit"]}, "rule_id": None, "rationale": "Amount varied within the curator-defined search-space range."})
        balanced = _apply_balance(search_space, components)
        if balanced is None:
            continue
        components = balanced
        if search_space.balance_component_key and search_space.balance_component_key in base_by_key:
            after = next(c for c in components if c["component_key"] == search_space.balance_component_key)["amount"]
            before = base_by_key[search_space.balance_component_key]["amount"]
            if abs(float(after) - float(before)) > 1e-12:
                changes.append({"change_type": "component_amount_change", "target_path": f"components.{search_space.balance_component_key}.amount", "before": {"value": before, "unit": base_by_key[search_space.balance_component_key]["unit"]}, "after": {"value": after, "unit": base_by_key[search_space.balance_component_key]["unit"]}, "rule_id": None, "rationale": "Balance component adjusted deterministically to satisfy the configured total."})
        proposals.append(Proposal(f"Composition hypothesis {n+1}", components, [], changes, "Bounded composition variation from the project baseline."))
    return proposals[:budget]


def _substitution_proposals(db: Session, project: ReplacementProject, search_space: CandidateSearchSpace, budget: int) -> list[Proposal]:
    base = _baseline_concrete_components(db, project, search_space)
    rules = db.query(SubstitutionRule).filter(
        SubstitutionRule.organisation_id == project.organisation_id,
        or_(SubstitutionRule.project_id == project.id, SubstitutionRule.project_id.is_(None)),
        SubstitutionRule.material_family == search_space.material_family,
        SubstitutionRule.status == "approved",
    ).order_by(SubstitutionRule.source_component_key, SubstitutionRule.replacement_component_key, SubstitutionRule.version, SubstitutionRule.id).all()
    proposals: list[Proposal] = []
    for rule in rules:
        components = [dict(c) for c in base]
        source = next((c for c in components if c["component_key"] == rule.source_component_key), None)
        if not source:
            continue
        if rule.allowed_min_amount is not None and source["amount"] < rule.allowed_min_amount:
            continue
        if rule.allowed_max_amount is not None and source["amount"] > rule.allowed_max_amount:
            continue
        before = {"component_key": source["component_key"], "display_name": source["display_name"], "amount": source["amount"], "unit": source["unit"]}
        source["component_key"] = rule.replacement_component_key
        source["display_name"] = rule.replacement_display_name
        source["substitution_rule_id"] = rule.id
        after = {"component_key": source["component_key"], "display_name": source["display_name"], "amount": source["amount"], "unit": source["unit"]}
        proposals.append(Proposal(
            f"Substitution: {before['display_name']} → {after['display_name']}", components, [],
            [{"change_type": "component_substitution", "target_path": f"components.{rule.source_component_key}", "before": before, "after": after, "rule_id": rule.id, "rationale": f"Approved substitution rule v{rule.version}: {rule.reason}"}],
            "Curator-approved component substitution from the project baseline.",
        ))
        if len(proposals) >= budget:
            break
    return proposals


def _process_proposals(db: Session, project: ReplacementProject, search_space: CandidateSearchSpace, budget: int, seed: int) -> list[Proposal]:
    base = _baseline_concrete_components(db, project, search_space)
    mutable = [r for r in search_space.process_rules if not r.locked]
    grids = [_grid(r.min_value, r.max_value, r.step_value) for r in mutable]
    combos = list(itertools.product(*grids)) if grids else []
    if len(combos) > budget:
        rng = random.Random(seed)
        idx = sorted(rng.sample(range(len(combos)), budget))
        combos = [combos[i] for i in idx]
    proposals: list[Proposal] = []
    for n, combo in enumerate(combos):
        process = []
        changes = []
        for rule, value in zip(mutable, combo, strict=True):
            process.append({"process_label": "proposed process state", "parameter_key": rule.parameter_key, "value": value, "unit": rule.unit, "source_baseline_state_id": None, "metadata": {}})
            changes.append({"change_type": "process_parameter_change", "target_path": f"process.{rule.parameter_key}", "before": {}, "after": {"value": value, "unit": rule.unit}, "rule_id": None, "rationale": "Process-state value selected from an explicitly bounded search-space range; this is not an executable synthesis protocol."})
        proposals.append(Proposal(f"Process-state hypothesis {n+1}", [dict(c) for c in base], process, changes, "Bounded process-state variation."))
    return proposals[:budget]




def rank_known_materials(db: Session, project: ReplacementProject, search_space: CandidateSearchSpace, limit: int) -> list[tuple[Material, dict[str, Any]]]:
    materials = (
        db.query(Material)
        .options(selectinload(Material.observations))
        .filter(Material.id != project.baseline_material_id, Material.material_family == search_space.material_family)
        .filter(or_(Material.visibility == "public", Material.owner_organisation_id == project.organisation_id))
        .order_by(Material.canonical_name, Material.id)
        .all()
    )
    if not materials:
        return []
    context = build_selection_context(db, [m.id for m in materials])
    hard_constraints = [c for c in project.constraints if c.hard_or_soft == "hard"]
    ranked: list[tuple[Material, dict[str, Any]]] = []
    for material in materials:
        conflict_keys = {c["property_key"] for c in detect_conflicts_from_observations(material.observations)}
        evaluations = [evaluate_constraint(db, material, c, context.definitions_by_key, context, conflict_keys) for c in hard_constraints]
        passed = sum(e["status"] == "PASS" for e in evaluations)
        failed = sum(e["status"] == "FAIL" for e in evaluations)
        unknown = sum(e["status"] == "UNKNOWN" for e in evaluations)
        exact = sum(e.get("applicability") == "exact" for e in evaluations)
        fallback = sum(e.get("applicability") == "fallback" for e in evaluations)
        coverage = sum(e["status"] != "UNKNOWN" for e in evaluations)
        matrix = {
            "hard_constraints_known_pass": passed,
            "hard_constraints_known_fail": failed,
            "hard_constraints_unknown": unknown,
            "evidence_coverage": coverage,
            "scientific_conflicts": len(conflict_keys),
            "exact_condition_matches": exact,
            "fallback_condition_matches": fallback,
        }
        ranked.append((material, matrix))
    ranked.sort(key=lambda item: (
        item[1]["hard_constraints_known_fail"],
        -item[1]["hard_constraints_known_pass"],
        item[1]["hard_constraints_unknown"],
        -item[1]["evidence_coverage"],
        item[1]["scientific_conflicts"],
        item[0].canonical_name,
        item[0].id,
    ))
    return ranked[:limit]

def _result_checksum(fingerprints: list[str]) -> str:
    return checksum({"fingerprint_version": FINGERPRINT_VERSION, "ordered_fingerprints": fingerprints})


def preview_generation(db: Session, project: ReplacementProject, search_space: CandidateSearchSpace, strategy_key: str, seed: int, candidate_budget: int | None, configuration: dict[str, Any]) -> dict[str, Any]:
    descriptor = STRATEGIES.get(strategy_key)
    if not descriptor or strategy_key == "manual_hypothesis":
        raise ValueError("Unknown or non-runnable generation strategy")
    validation = validate_search_space(db, search_space, strategy_key)
    budget = min(candidate_budget or search_space.candidate_budget, search_space.candidate_budget, HARD_MAX_CANDIDATES)
    spec = compile_specification(project)
    config_checksum = checksum(configuration)
    return {
        "valid": validation["valid"], "strategy": descriptor,
        "specification_checksum": spec["checksum"], "search_space_checksum": search_space.checksum,
        "search_space_version": search_space.version, "configuration_checksum": config_checksum,
        "random_seed": seed, "candidate_budget": budget, "estimated_cardinality": validation["estimated_cardinality"],
        "expected_truncation": validation["estimated_cardinality"] > budget, "issues": validation["issues"],
    }


def _persist_hypothesis(db: Session, project: ReplacementProject, run: GenerationRun | None, strategy_key: str, proposal: Proposal, fingerprint: str, structural_reasons: list[str], manual: bool = False) -> tuple[CandidateHypothesis, Candidate, bool]:
    existing = db.query(CandidateHypothesis).filter_by(project_id=project.id, deterministic_fingerprint=fingerprint).one_or_none()
    if existing:
        candidate = db.query(Candidate).filter_by(project_id=project.id, hypothesis_id=existing.id).one()
        return existing, candidate, True
    status = "rejected" if structural_reasons else "proposed"
    hypothesis = CandidateHypothesis(
        project_id=project.id, organisation_id=project.organisation_id, display_label=proposal.display_label,
        material_family=project.baseline_material.material_family, baseline_material_id=project.baseline_material_id,
        generation_run_id=run.id if run else None, generator_strategy_key=strategy_key,
        generator_strategy_version=STRATEGIES[strategy_key]["version"], deterministic_fingerprint=fingerprint,
        fingerprint_version=FINGERPRINT_VERSION, status=status,
        structural_validity="invalid" if structural_reasons else "valid",
        rejection_reason="; ".join(structural_reasons) if structural_reasons else None,
        notes="Manual scientist hypothesis; no property evidence is implied." if manual else "Generated material hypothesis; no property evidence is implied.",
    )
    db.add(hypothesis); db.flush()
    for i, c in enumerate(proposal.components):
        db.add(CandidateHypothesisComponent(
            hypothesis_id=hypothesis.id, sequence=i, component_key=c["component_key"], display_name=c["display_name"],
            role=c.get("role"), amount=c.get("amount"), unit=c.get("unit"), basis=c.get("basis"),
            source_baseline_component_id=c.get("source_baseline_component_id"), substitution_rule_id=c.get("substitution_rule_id"),
            locked=bool(c.get("locked", False)), metadata_json=c.get("metadata", {}),
        ))
    for p in proposal.process_parameters:
        db.add(CandidateHypothesisProcessParameter(
            hypothesis_id=hypothesis.id, process_label=p.get("process_label", "proposed process state"), parameter_key=p["parameter_key"],
            value=p["value"], unit=p["unit"], source_baseline_state_id=p.get("source_baseline_state_id"), metadata_json=p.get("metadata", {}),
        ))
    for i, ch in enumerate(proposal.changes):
        db.add(CandidateChangeRecord(
            hypothesis_id=hypothesis.id, generation_run_id=run.id if run else None, sequence=i,
            change_type=ch["change_type"], target_path=ch["target_path"], before_value=ch.get("before", {}),
            after_value=ch.get("after", {}), substitution_rule_id=ch.get("rule_id"), rationale=ch["rationale"],
        ))
    db.add(CandidateLineageEdge(
        child_hypothesis_id=hypothesis.id, parent_material_id=project.baseline_material_id,
        relationship_type="manual_from_baseline" if manual else "generated_from_baseline",
        generation_run_id=run.id if run else None, sequence=0, rationale=proposal.rationale,
    ))
    candidate = Candidate(
        project_id=project.id, candidate_kind="hypothesis", material_id=None, hypothesis_id=hypothesis.id,
        candidate_source="manual" if manual else "generated_future", status="rejected" if structural_reasons else "proposed",
        notes="Hypothesis — not yet predicted, simulated, or experimentally validated.",
    )
    db.add(candidate); db.flush()
    return hypothesis, candidate, False


def execute_generation(db: Session, project: ReplacementProject, search_space: CandidateSearchSpace, strategy_key: str, seed: int, candidate_budget: int | None, configuration: dict[str, Any], created_by: str, run_id: str | None = None) -> GenerationRun:
    started = time.perf_counter()
    preview = preview_generation(db, project, search_space, strategy_key, seed, candidate_budget, configuration)
    if not preview["valid"]:
        codes = ", ".join(i["code"] for i in preview["issues"] if i["severity"] == "error")
        logger.warning(
            "candidate_generation_rejected project_id=%s strategy=%s spec_checksum=%s search_space_checksum=%s seed=%s failure_code=%s",
            project.id, strategy_key, preview["specification_checksum"][:12], preview["search_space_checksum"][:12], seed, codes or "SEARCH_SPACE_INVALID",
        )
        raise ValueError(f"Search space is invalid for generation: {codes}")
    if not db.get(User, created_by):
        raise ValueError("created_by user not found")
    run = GenerationRun(
        **({"id": run_id} if run_id else {}),
        project_id=project.id, organisation_id=project.organisation_id,
        replacement_specification_checksum=preview["specification_checksum"], search_space_id=search_space.id,
        search_space_version=search_space.version, search_space_checksum=search_space.checksum,
        strategy_key=strategy_key, strategy_version=STRATEGIES[strategy_key]["version"],
        configuration_checksum=preview["configuration_checksum"], random_seed=seed,
        requested_candidate_budget=preview["candidate_budget"], status="running", started_at=datetime.now(UTC),
        created_by=created_by, metadata_json={"fingerprint_version": FINGERPRINT_VERSION, "configuration": configuration},
    )
    db.add(run); db.flush()
    budget = preview["candidate_budget"]
    fingerprints: list[str] = []
    generated = rejected = duplicates = accepted = 0

    if strategy_key == "known_material_retrieval":
        ranked_materials = rank_known_materials(db, project, search_space, budget)
        for seq, (material, evidence_matrix) in enumerate(ranked_materials):
            fp = checksum({"fingerprint_version": FINGERPRINT_VERSION, "kind": "known_material", "canonical_name": material.canonical_name})
            fingerprints.append(fp); generated += 1
            candidate = db.query(Candidate).filter_by(project_id=project.id, material_id=material.id).one_or_none()
            duplicate = candidate is not None
            if not candidate:
                candidate = Candidate(project_id=project.id, candidate_kind="known_material", material_id=material.id, hypothesis_id=None, candidate_source="retrieved_future", status="proposed", notes="Retrieved existing material; missing evidence remains UNKNOWN.")
                db.add(candidate); db.flush(); accepted += 1
            else:
                duplicates += 1
            db.add(GenerationRunResult(generation_run_id=run.id, sequence=seq, candidate_fingerprint=fp, candidate_id=candidate.id, material_id=material.id, disposition="duplicate" if duplicate else "accepted", metadata_json={"kind": "known_material", "evidence_matrix": evidence_matrix}))
    else:
        if strategy_key == "curated_component_substitution":
            proposals = _substitution_proposals(db, project, search_space, budget)
        elif strategy_key == "bounded_composition_variation":
            proposals = _composition_proposals(db, project, search_space, budget, seed)
        elif strategy_key == "bounded_process_variation":
            proposals = _process_proposals(db, project, search_space, budget, seed)
        else:
            raise ValueError("Unsupported generation strategy")
        for seq, proposal in enumerate(proposals):
            fp = candidate_fingerprint(search_space.material_family, proposal.components, proposal.process_parameters)
            fingerprints.append(fp); generated += 1
            structural_reasons = structural_screen(search_space, proposal.components, proposal.process_parameters)
            hypothesis, candidate, duplicate = _persist_hypothesis(db, project, run, strategy_key, proposal, fp, structural_reasons)
            if duplicate:
                duplicates += 1
                disposition = "duplicate"
            elif structural_reasons:
                rejected += 1
                disposition = "rejected"
            else:
                accepted += 1
                disposition = "accepted"
            db.add(GenerationRunResult(
                generation_run_id=run.id, sequence=seq, candidate_fingerprint=fp, candidate_id=candidate.id,
                hypothesis_id=hypothesis.id, disposition=disposition,
                rejection_reason="; ".join(structural_reasons) if structural_reasons else None,
                metadata_json={"kind": "hypothesis"},
            ))
    run.generated_count = generated; run.accepted_count = accepted; run.rejected_count = rejected; run.duplicate_count = duplicates
    run.result_checksum = _result_checksum(fingerprints); run.status = "completed"; run.completed_at = datetime.now(UTC)
    db.commit(); db.refresh(run)
    logger.info(
        "candidate_generation_completed run_id=%s project_id=%s strategy=%s strategy_version=%s spec_checksum=%s search_space_checksum=%s seed=%s generated=%s accepted=%s rejected=%s duplicates=%s duration_ms=%s",
        run.id, project.id, run.strategy_key, run.strategy_version, run.replacement_specification_checksum[:12], run.search_space_checksum[:12], run.random_seed,
        run.generated_count, run.accepted_count, run.rejected_count, run.duplicate_count, round((time.perf_counter() - started) * 1000, 2),
    )
    return run


def create_manual_hypothesis(db: Session, project: ReplacementProject, display_label: str, material_family: str, components: list[dict[str, Any]], process_parameters: list[dict[str, Any]], notes: str | None = None) -> tuple[CandidateHypothesis, Candidate, bool]:
    if material_family != project.baseline_material.material_family:
        raise ValueError("Manual hypothesis material family must match the project baseline in Phase 3")
    fp = candidate_fingerprint(material_family, components, process_parameters)
    # Manual capture receives generic structural checks without a search-space range assumption.
    seen = set(); reasons = []
    for c in components:
        key = c["component_key"]
        if key in seen: reasons.append("duplicate_component_identity")
        seen.add(key)
        if c.get("amount") is not None and c["amount"] < 0: reasons.append(f"negative_amount:{key}")
    existing = db.query(CandidateHypothesis).filter_by(project_id=project.id, deterministic_fingerprint=fp).one_or_none()
    if existing:
        candidate = db.query(Candidate).filter_by(project_id=project.id, hypothesis_id=existing.id).one()
        return existing, candidate, True
    # a tiny synthetic search-space object is not persisted; persist directly so manual capture remains independent of active search-space availability
    hypothesis = CandidateHypothesis(
        project_id=project.id, organisation_id=project.organisation_id, display_label=display_label,
        material_family=material_family, baseline_material_id=project.baseline_material_id, generation_run_id=None,
        generator_strategy_key="manual_hypothesis", generator_strategy_version=STRATEGIES["manual_hypothesis"]["version"],
        deterministic_fingerprint=fp, fingerprint_version=FINGERPRINT_VERSION, status="rejected" if reasons else "proposed",
        structural_validity="invalid" if reasons else "valid", rejection_reason="; ".join(sorted(set(reasons))) if reasons else None,
        notes=notes or "Manual scientist hypothesis; no property evidence is implied.",
    )
    db.add(hypothesis); db.flush()
    for i, c in enumerate(components):
        db.add(CandidateHypothesisComponent(
            hypothesis_id=hypothesis.id, sequence=i, component_key=c["component_key"], display_name=c["display_name"], role=c.get("role"),
            amount=c.get("amount"), unit=c.get("unit"), basis=c.get("basis"), source_baseline_component_id=c.get("source_baseline_component_id"),
            substitution_rule_id=c.get("substitution_rule_id"), locked=bool(c.get("locked", False)), metadata_json=c.get("metadata", {}),
        ))
    for p in process_parameters:
        db.add(CandidateHypothesisProcessParameter(hypothesis_id=hypothesis.id, process_label=p.get("process_label", "proposed process state"), parameter_key=p["parameter_key"], value=p["value"], unit=p["unit"], source_baseline_state_id=p.get("source_baseline_state_id"), metadata_json=p.get("metadata", {})))
    db.add(CandidateChangeRecord(hypothesis_id=hypothesis.id, generation_run_id=None, sequence=0, change_type="manual_hypothesis", target_path="hypothesis", before_value={"baseline_material_id": project.baseline_material_id}, after_value={"fingerprint": fp}, rationale="Scientist-authored hypothesis captured manually; no evidence or performance is implied."))
    db.add(CandidateLineageEdge(child_hypothesis_id=hypothesis.id, parent_material_id=project.baseline_material_id, relationship_type="manual_from_baseline", generation_run_id=None, sequence=0, rationale="Manual scientist hypothesis associated with the project baseline."))
    candidate = Candidate(project_id=project.id, candidate_kind="hypothesis", material_id=None, hypothesis_id=hypothesis.id, candidate_source="manual", status="rejected" if reasons else "proposed", notes="Hypothesis — not yet predicted, simulated, or experimentally validated.")
    db.add(candidate); db.commit(); db.refresh(hypothesis); db.refresh(candidate)
    return hypothesis, candidate, False
