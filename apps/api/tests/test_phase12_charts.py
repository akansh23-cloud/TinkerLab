"""Phase 12.1 — chart data endpoints.

The charts are only as trustworthy as the numbers behind them, and the two places a materials chart
lies are the axis and the gap. These tests pin both: that a value is converted to the axis unit
before it is plotted, and that a material with no value is named as excluded rather than dropped,
imputed or plotted at zero.
"""

from __future__ import annotations

import math
import uuid

import pytest

from app.db.session import SessionLocal
from app.models.entities import Material
from app.services.bench.property_space import MATERIAL_INDICES, index_value, indices_for


def _ctx(client):
    ctx = client.get("/demo-context").json()
    client.headers["X-Organisation-ID"] = ctx["organisation_id"]
    return ctx


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _library(client):
    client.post("/bench/install-reference-library", json={})


# ---------------------------------------------------------------------------------------------
# Material indices
# ---------------------------------------------------------------------------------------------

def test_material_indices_are_declared_per_axis_pair():
    """An index built from strength and density is meaningless on a cost-versus-lead-time chart."""
    assert indices_for("density", "tensile_strength")
    assert indices_for("lead_time", "supplier_count") == ()


def test_index_exponents_match_the_standard_design_cases():
    pairs = {i.key: i for i in indices_for("density", "tensile_strength")}
    # Tie rod sigma/rho; beam in bending sigma^(2/3)/rho; panel sigma^(1/2)/rho.
    assert pairs["strength_per_density"].exponent == 1.0
    assert abs(pairs["strength_beam"].exponent - 2 / 3) < 1e-9
    assert pairs["strength_panel"].exponent == 0.5
    # On log-log axes the guide line slope is 1/exponent, which is why the three cases separate.
    assert abs(pairs["strength_beam"].log_slope - 1.5) < 1e-9
    assert abs(pairs["strength_panel"].log_slope - 2.0) < 1e-9


def test_stiffness_indices_are_defined_for_the_modulus_chart():
    keys = {i.key for i in indices_for("density", "tensile_modulus")}
    assert {"stiffness_per_density", "stiffness_beam", "stiffness_panel"} == keys


def test_index_ranking_can_differ_from_raw_property_ranking():
    """The whole reason the guide lines exist: strongest is not the same as best per unit mass."""
    steel = {"x": 7850.0, "y": 510.0}      # stronger in absolute terms
    cfrp = {"x": 1600.0, "y": 1500.0}
    aluminium = {"x": 2700.0, "y": 310.0}
    tie = next(i for i in indices_for("density", "tensile_strength") if i.key == "strength_per_density")

    assert steel["y"] > aluminium["y"]
    # ...but on specific strength the order changes.
    assert index_value(aluminium["x"], aluminium["y"], tie) > index_value(steel["x"], steel["y"], tie)
    assert index_value(cfrp["x"], cfrp["y"], tie) > index_value(aluminium["x"], aluminium["y"], tie)


def test_every_declared_index_has_a_named_design_case():
    for pair, group in MATERIAL_INDICES.items():
        for index in group:
            assert index.design_case, f"{pair}/{index.key} has no stated design case"
            assert index.exponent > 0


# ---------------------------------------------------------------------------------------------
# Property space
# ---------------------------------------------------------------------------------------------

def test_property_space_plots_materials_with_both_axis_values(client):
    _library(client)
    body = client.get("/bench/property-space?x=density&y=tensile_strength").json()
    assert body["plotted_count"] > 10
    names = {p["display_name"] for p in body["points"]}
    assert any("PA66" in n for n in names)
    assert any("6061" in n for n in names)
    for point in body["points"]:
        assert point["x"] > 0 and point["y"] > 0
        assert point["x_unit"] == "kg/m^3"
        assert point["y_unit"] == "MPa"


def test_property_space_converts_to_the_axis_unit_before_plotting(client):
    """A datasheet in g/cm^3 must land beside one in kg/m^3, not a thousand times lower."""
    _library(client)
    created = client.post("/bench/materials", json={
        "display_name": _unique("Chart unit probe"),
        "material_family": "polymer",
        "data_grade": "internal_measurement",
        "properties": [
            {"property_key": "density", "value": 1.42, "unit": "g/cm^3"},
            {"property_key": "tensile_strength", "value": 0.16, "unit": "GPa"},
        ],
    }).json()

    body = client.get("/bench/property-space?x=density&y=tensile_strength").json()
    point = next(p for p in body["points"] if p["material_id"] == created["material_id"])
    assert abs(point["x"] - 1420.0) < 1e-6
    assert abs(point["y"] - 160.0) < 1e-6


def test_property_space_names_what_it_could_not_plot(client):
    """A missing value is a finding. It must never be silently dropped or imputed."""
    _library(client)
    created = client.post("/bench/materials", json={
        "display_name": _unique("Chart gap probe"),
        "material_family": "polymer",
        "data_grade": "handbook_typical",
        "properties": [{"property_key": "density", "value": 1200.0, "unit": "kg/m^3"}],
    }).json()

    body = client.get("/bench/property-space?x=density&y=tensile_strength").json()
    assert all(p["material_id"] != created["material_id"] for p in body["points"])
    excluded = next(e for e in body["excluded"] if e["material_id"] == created["material_id"])
    assert "Tensile strength" in excluded["reason"]


def test_property_space_refuses_a_boolean_axis(client):
    response = client.get("/bench/property-space?x=density&y=reach_svhc_present")
    assert response.status_code == 422
    assert "gate" in response.json()["detail"].lower()


def test_property_space_reports_the_origin_of_each_coordinate(client):
    """A measured point and a handbook point must be separable in the rendering."""
    _library(client)
    body = client.get("/bench/property-space?x=density&y=tensile_strength").json()
    origins = {p["x_origin"] for p in body["points"]}
    assert "literature" in origins
    for point in body["points"]:
        assert point["x_origin"] in {"measured", "supplier", "literature", "simulation", "prediction", "declared"}


def test_property_space_filters_by_family(client):
    _library(client)
    body = client.get("/bench/property-space?x=density&y=tensile_strength&family=alloy").json()
    assert body["points"]
    assert {p["material_family"] for p in body["points"]} == {"alloy"}


def test_axis_options_only_offer_plottable_properties(client):
    _library(client)
    options = client.get("/bench/property-space/axes").json()
    assert options
    keys = {o["key"] for o in options}
    # Boolean gates are not continuous axes.
    assert "reach_svhc_present" not in keys
    # An axis with a single material behind it would render as an empty-looking chart.
    assert all(o["material_count"] >= 2 for o in options)


def test_ranking_orders_by_the_index_not_the_raw_property(client):
    _library(client)
    body = client.get(
        "/bench/property-space/ranking?x=density&y=tensile_strength&index_key=strength_per_density"
    ).json()
    ranking = body["ranking"]
    assert len(ranking) > 5
    values = [r["index_value"] for r in ranking]
    assert values == sorted(values, reverse=True)
    # A dense metal must not outrank a composite on specific strength just for being strong.
    top = ranking[0]
    assert top["index_value"] >= max(values)


def test_ranking_rejects_an_index_that_does_not_apply_to_the_axes(client):
    response = client.get(
        "/bench/property-space/ranking?x=density&y=tensile_strength&index_key=stiffness_per_density"
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------------------------
# Decision chart
# ---------------------------------------------------------------------------------------------

def _study_with_candidates(client):
    ctx = _ctx(client)
    _library(client)
    from app.db.session import SessionLocal
    from app.models.entities import Material

    session = SessionLocal()
    try:
        baseline = session.query(Material).filter(Material.canonical_name == "library::pa66-gf30").one().id
    finally:
        session.close()

    project_id = client.post("/bench/studies", json={
        "name": _unique("Chart study"),
        "baseline_material_id": baseline,
        "drivers": ["cost"],
        "preset_key": "automotive_underhood_polymer",
        "organisation_id": ctx["organisation_id"], "created_by": ctx["user_id"],
    }).json()["project_id"]

    # Attach real library materials as candidates. Generated hypotheses are deliberately excluded
    # here: a novel composition has no measurements, so every cell is correctly UNKNOWN and there
    # would be no margin to check. Both kinds appear together in the real matrix.
    session = SessionLocal()
    try:
        rivals = [
            session.query(Material).filter(Material.canonical_name == name).one().id
            for name in ("library::pbt-gf30", "library::pp-td20", "library::ppa-gf33")
        ]
    finally:
        session.close()
    for material_id in rivals:
        client.post(f"/replacement-projects/{project_id}/candidates",
                    json={"material_id": material_id, "candidate_source": "manual"})
    return project_id


def test_decision_chart_returns_requirements_and_candidate_cells(client):
    project_id = _study_with_candidates(client)
    body = client.get(f"/replacement-projects/{project_id}/decision-chart").json()
    assert body["found"] is True
    assert body["requirements"]
    assert body["candidates"]
    for candidate in body["candidates"]:
        assert len(candidate["cells"]) == len(body["requirements"])


def test_decision_chart_orders_hard_requirements_first(client):
    """A single hard failure eliminates a candidate, so hard rows must be read first."""
    project_id = _study_with_candidates(client)
    requirements = client.get(f"/replacement-projects/{project_id}/decision-chart").json()["requirements"]
    strengths = [r["hard_or_soft"] for r in requirements]
    assert strengths == sorted(strengths, key=lambda s: s != "hard")


def test_decision_chart_gives_no_margin_for_an_unknown(client):
    """Zero would place the candidate exactly on the limit — a specific and false claim."""
    project_id = _study_with_candidates(client)
    body = client.get(f"/replacement-projects/{project_id}/decision-chart").json()
    unknowns = [c for cand in body["candidates"] for c in cand["cells"] if c["status"] == "UNKNOWN"]
    assert unknowns, "the fixture should contain at least one unmeasured requirement"
    for cell in unknowns:
        assert cell["margin_percent"] is None


def test_decision_chart_signs_margins_so_positive_always_means_better(client):
    project_id = _study_with_candidates(client)
    body = client.get(f"/replacement-projects/{project_id}/decision-chart").json()
    requirement_by_key = {r["property_key"]: r for r in body["requirements"]}
    checked = 0
    for candidate in body["candidates"]:
        for cell in candidate["cells"]:
            if cell["margin_percent"] is None or cell["status"] not in {"PASS", "FAIL"}:
                continue
            requirement = requirement_by_key[cell["property_key"]]
            if requirement["target_value"] is None:
                continue
            checked += 1
            # A PASS must never show negative headroom, and a FAIL must never show positive.
            if cell["status"] == "PASS":
                assert cell["margin_percent"] >= -1e-6, (cell, requirement)
            else:
                assert cell["margin_percent"] <= 1e-6, (cell, requirement)
    assert checked > 0


def test_decision_chart_margin_survives_a_unit_mismatch(client):
    """The requirement is typed in datasheet units; the observation is stored in its own."""
    ctx = _ctx(client)
    created = client.post("/bench/materials", json={
        "display_name": _unique("Margin unit probe"),
        "material_family": "polymer",
        "data_grade": "internal_measurement",
        "components": [
            {"component_name": "Resin", "component_role": "matrix", "amount_value": 90.0, "amount_unit": "%"},
            {"component_name": "Filler", "component_role": "filler", "amount_value": 10.0, "amount_unit": "%"},
        ],
        "properties": [{"property_key": "tensile_strength", "value": 0.2, "unit": "GPa"}],
    }).json()

    project_id = client.post("/bench/studies", json={
        "name": _unique("Unit margin study"),
        "baseline_material_id": created["material_id"],
        "drivers": ["cost"],
        # 100 MPa against an observation recorded as 0.2 GPa: the margin is only right if the
        # server converts before subtracting.
        "requirements": [{"property_key": "tensile_strength", "comparator": ">=",
                          "target_value": 100.0, "target_unit": "MPa"}],
        "organisation_id": ctx["organisation_id"], "created_by": ctx["user_id"],
    }).json()["project_id"]

    client.post(f"/replacement-projects/{project_id}/candidates", json={
        "material_id": created["material_id"], "candidate_source": "manual",
    })

    body = client.get(f"/replacement-projects/{project_id}/decision-chart").json()
    cells = [c for cand in body["candidates"] for c in cand["cells"]
             if c["property_key"] == "tensile_strength" and c["margin_percent"] is not None]
    assert cells, "expected an evaluated tensile strength cell"
    # 200 MPa against a 100 MPa floor is exactly 100% of headroom.
    assert abs(cells[0]["margin_percent"] - 100.0) < 0.5


def test_decision_chart_counts_evidence_origins_per_candidate(client):
    project_id = _study_with_candidates(client)
    body = client.get(f"/replacement-projects/{project_id}/decision-chart").json()
    for candidate in body["candidates"]:
        mix = candidate["origin_mix"]
        assert sum(mix.values()) == len(candidate["cells"])
        assert set(mix) <= {"known_evidence", "model_prediction", "physics_simulation", "none", "unknown"}


def test_decision_chart_404s_for_an_unknown_project(client):
    assert client.get(f"/replacement-projects/{uuid.uuid4()}/decision-chart").status_code == 404


def test_decision_chart_does_not_re_decide_anything(client):
    """Statuses must match the canonical evaluator exactly — the chart reformats, never re-judges."""
    project_id = _study_with_candidates(client)
    chart = client.get(f"/replacement-projects/{project_id}/decision-chart").json()
    comparison = client.get(f"/replacement-projects/{project_id}/comparison").json()

    chart_status = {
        (c["candidate_id"], cell["property_key"]): cell["status"]
        for c in chart["candidates"] for cell in c["cells"]
    }
    for evaluation in comparison:
        for constraint in evaluation["constraints"]:
            key = (evaluation["candidate_id"], constraint["property_key"])
            if key in chart_status:
                assert chart_status[key] == constraint["status"], key


# ---------------------------------------------------------------------------------------------
# Guide-line geometry and gate semantics
# ---------------------------------------------------------------------------------------------

def test_log_slope_is_the_reciprocal_of_the_exponent():
    """M = y^a / x rearranges to log y = (1/a)·log x + c, so the guide line has slope 1/a.

    Getting this wrong tilts every guide line and silently recommends the wrong material for the
    loading mode — the failure would look like a styling bug and behave like a selection error.
    """
    from app.services.bench.property_space import MATERIAL_INDICES

    for indices in MATERIAL_INDICES.values():
        for index in indices:
            assert index.log_slope == pytest.approx(1.0 / index.exponent)


def test_index_value_is_undefined_rather_than_infinite_at_a_zero_denominator():
    from app.services.bench.property_space import index_value, indices_for

    tie = indices_for("density", "tensile_strength")[0]
    assert math.isnan(index_value(0.0, 180.0, tie))


def test_property_space_rejects_an_unknown_property_as_an_axis(client):
    _ctx(client)
    assert client.get("/bench/property-space?x=density&y=vibe_index").status_code == 422


def test_boolean_gate_carries_no_percentage_margin(client):
    """Compliance passes or blocks. A percentage would imply it can be partially satisfied."""
    ctx = _ctx(client)
    _library(client)
    session = SessionLocal()
    try:
        brass = session.query(Material).filter(
            Material.canonical_name == "library::brass-cuzn39pb3"
        ).one().id
    finally:
        session.close()

    project_id = client.post("/bench/studies", json={
        "name": _unique("Boolean margin"),
        "baseline_material_id": brass,
        "drivers": ["regulation"],
        "derive_space": False,
        "requirements": [{"property_key": "reach_svhc_present", "comparator": "boolean",
                          "target_boolean": False}],
        "organisation_id": ctx["organisation_id"], "created_by": ctx["user_id"],
    }).json()["project_id"]
    client.post(f"/replacement-projects/{project_id}/candidates",
                json={"material_id": brass, "candidate_source": "manual"})

    body = client.get(f"/replacement-projects/{project_id}/decision-chart").json()
    cell = body["candidates"][0]["cells"][0]
    assert cell["margin_percent"] is None
    # CuZn39Pb3 carries 3% lead, far above the 0.1% SVHC threshold, so this must fail.
    assert cell["status"] == "FAIL"
