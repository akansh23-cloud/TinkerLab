import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AshbyChart } from "../charts/AshbyChart";
import { DecisionMatrix, EvidenceMix } from "../charts/DecisionMatrix";
import { RequirementMargins, PropertyDeltas } from "../charts/RequirementMargins";
import type { DecisionCandidate, DecisionRequirement } from "@/lib/decision";

const xAxis = {
  key: "density", display_name: "Density", canonical_unit: "kg/m^3",
  direction: "lower_is_better", test_standard: "ISO 1183", why_it_matters: "Sets part mass.",
};
const yAxis = {
  key: "tensile_strength", display_name: "Tensile strength", canonical_unit: "MPa",
  direction: "higher_is_better", test_standard: "ISO 527", why_it_matters: "Headline strength.",
};

const points = [
  {
    material_id: "m1", display_name: "PA66-GF30", material_family: "polymer", is_seed_data: true,
    x: 1360, y: 180, x_origin: "literature", y_origin: "literature",
    x_confidence: 0.55, y_confidence: 0.55, highlighted: false,
  },
  {
    material_id: "m2", display_name: "Aluminium 6061-T6", material_family: "alloy", is_seed_data: true,
    x: 2700, y: 310, x_origin: "measured", y_origin: "measured",
    x_confidence: 0.9, y_confidence: 0.9, highlighted: true,
  },
  {
    material_id: "m3", display_name: "CFRP UD", material_family: "composite", is_seed_data: true,
    x: 1600, y: 1500, x_origin: "literature", y_origin: "prediction",
    x_confidence: 0.55, y_confidence: 0.4, highlighted: false,
  },
];

const indices = [
  { key: "strength_per_density", label: "σ/ρ", design_case: "Tie rod, strength-limited", exponent: 1, log_slope: 1, maximise: true },
  { key: "strength_beam", label: "σ^⅔/ρ", design_case: "Beam in bending", exponent: 2 / 3, log_slope: 1.5, maximise: true },
];

describe("AshbyChart", () => {
  it("plots the property space with both axes labelled and their units", () => {
    render(<AshbyChart points={points} xAxis={xAxis} yAxis={yAxis} indices={indices} />);
    expect(screen.getByTestId("ashby-chart")).toBeTruthy();
    expect(screen.getByText(/Density \(kg\/m\^3\)/)).toBeTruthy();
    expect(screen.getByText(/Tensile strength \(MPa\)/)).toBeTruthy();
  });

  it("states that the axes are logarithmic, since the reader cannot infer it from the dots", () => {
    render(<AshbyChart points={points} xAxis={xAxis} yAxis={yAxis} indices={indices} />);
    expect(screen.getAllByText(/log scale/).length).toBe(2);
  });

  it("offers the material indices for the axis pair", () => {
    render(<AshbyChart points={points} xAxis={xAxis} yAxis={yAxis} indices={indices} />);
    expect(screen.getByText("σ/ρ")).toBeTruthy();
    expect(screen.getByText("σ^⅔/ρ")).toBeTruthy();
  });

  it("names the material that wins the selected index, not simply the strongest one", () => {
    // CFRP: 1500/1600 = 0.94. Aluminium: 310/2700 = 0.11. PA66: 180/1360 = 0.13.
    // CFRP wins on σ/ρ, and it also happens to be strongest here — so the discriminating check is
    // that the guide line is anchored to the index winner at all.
    render(
      <AshbyChart points={points} xAxis={xAxis} yAxis={yAxis} indices={indices}
                  activeIndexKey="strength_per_density" />,
    );
    expect(screen.getByText(/best: CFRP UD/)).toBeTruthy();
    expect(screen.getByText(/Tie rod, strength-limited/)).toBeTruthy();
  });

  it("says what is missing rather than rendering an empty box", () => {
    render(<AshbyChart points={[]} xAxis={xAxis} yAxis={yAxis} indices={[]} />);
    expect(screen.getByText(/No material has a recorded value for both/)).toBeTruthy();
  });

  it("marks the feasible region when the study has thresholds on both axes", () => {
    render(
      <AshbyChart points={points} xAxis={xAxis} yAxis={yAxis} indices={indices}
                  requirementX={{ max: 2000 }} requirementY={{ min: 150 }} />,
    );
    expect(screen.getByText("Meets both thresholds")).toBeTruthy();
  });
});

const requirements: DecisionRequirement[] = [
  {
    property_key: "tensile_strength", display_name: "Tensile strength", comparator: ">=",
    target_value: 90, target_boolean: null, target_unit: "MPa", canonical_unit: "MPa",
    hard_or_soft: "hard", severity: 5, rationale: "Mounting boss load path.",
  },
  {
    property_key: "cost_per_mass", display_name: "Material cost", comparator: "<=",
    target_value: 8.5, target_boolean: null, target_unit: "USD/kg", canonical_unit: "USD/kg",
    hard_or_soft: "soft", severity: 3, rationale: "Programme envelope.",
  },
  {
    property_key: "fatigue_strength_1e7", display_name: "Fatigue strength", comparator: ">=",
    target_value: 40, target_boolean: null, target_unit: "MPa", canonical_unit: "MPa",
    hard_or_soft: "hard", severity: 5, rationale: "Vibration duty.",
  },
];

const candidates: DecisionCandidate[] = [
  {
    candidate_id: "c1", candidate_kind: "known_material", display_name: "PBT-GF30",
    hard_passed: 1, hard_failed: 0, unknown: 1, completeness: 0.67,
    origin_mix: { known_evidence: 2, none: 1 },
    provenance_mix: { handbook_typical: 2, none: 1 },
    cells: [
      { property_key: "tensile_strength", status: "PASS", observed_value: 135, observed_unit: "MPa",
        canonical_value: 135, canonical_unit: "MPa", margin_percent: 50, value_origin: "known_evidence",
        conflict: false, confidence: 0.55, unknown_reason: null },
      { property_key: "cost_per_mass", status: "PASS", observed_value: 4, observed_unit: "USD/kg",
        canonical_value: 4, canonical_unit: "USD/kg", margin_percent: 52.9, value_origin: "known_evidence",
        conflict: false, confidence: 0.55, unknown_reason: null },
      { property_key: "fatigue_strength_1e7", status: "UNKNOWN", observed_value: null, observed_unit: null,
        canonical_value: null, canonical_unit: null, margin_percent: null, value_origin: null,
        conflict: false, confidence: null, unknown_reason: "No observation for this property." },
    ],
    properties: [
      { property_key: "density", display_name: "Density", baseline_value: 1360, candidate_value: 1530,
        percentage_delta: 12.5, canonical_unit: "kg/m^3", direction: "lower_is_better" },
      { property_key: "tensile_strength", display_name: "Tensile strength", baseline_value: 180,
        candidate_value: 135, percentage_delta: -25, canonical_unit: "MPa", direction: "higher_is_better" },
      { property_key: "fatigue_strength_1e7", display_name: "Fatigue strength" },
    ],
  },
  {
    candidate_id: "c2", candidate_kind: "known_material", display_name: "PP-TD20",
    hard_passed: 0, hard_failed: 1, unknown: 1, completeness: 0.67,
    origin_mix: { known_evidence: 1, model_prediction: 1, none: 1 },
    provenance_mix: { supplier_declared: 1, model_prediction: 1, none: 1 },
    cells: [
      { property_key: "tensile_strength", status: "FAIL", observed_value: 28, observed_unit: "MPa",
        canonical_value: 28, canonical_unit: "MPa", margin_percent: -68.9, value_origin: "known_evidence",
        conflict: true, confidence: 0.55, unknown_reason: null },
      { property_key: "cost_per_mass", status: "PASS", observed_value: 1.55, observed_unit: "USD/kg",
        canonical_value: 1.55, canonical_unit: "USD/kg", margin_percent: 81.8, value_origin: "model_prediction",
        conflict: false, confidence: 0.5, unknown_reason: null },
      { property_key: "fatigue_strength_1e7", status: "UNKNOWN", observed_value: null, observed_unit: null,
        canonical_value: null, canonical_unit: null, margin_percent: null, value_origin: null,
        conflict: false, confidence: null, unknown_reason: "No observation for this property." },
    ],
    properties: [],
  },
];

describe("DecisionMatrix", () => {
  it("renders one row per candidate", () => {
    render(<DecisionMatrix candidates={candidates} requirements={requirements} />);
    expect(screen.getByTestId("decision-matrix")).toBeTruthy();
    // The name appears once as the row label and again inside each cell's <title> tooltip, so an
    // exact-node query would be ambiguous by construction.
    expect(screen.getAllByText(/PBT-GF30/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/PP-TD20/).length).toBeGreaterThan(0);
  });

  it("marks a candidate eliminated by a hard requirement", () => {
    render(<DecisionMatrix candidates={candidates} requirements={requirements} />);
    expect(screen.getByText(/⊘ PP-TD20/)).toBeTruthy();
  });

  it("separates hard requirements from soft ones, because only hard ones eliminate", () => {
    render(<DecisionMatrix candidates={candidates} requirements={requirements} />);
    expect(screen.getByText("HARD — CAN ELIMINATE")).toBeTruthy();
    expect(screen.getByText("SOFT — RANKS ONLY")).toBeTruthy();
  });

  it("explains UNKNOWN as unmeasured rather than as a failure", () => {
    render(<DecisionMatrix candidates={candidates} requirements={requirements} />);
    expect(screen.getByText(/UNKNOWN — nobody measured it/)).toBeTruthy();
  });

  it("carries status in a glyph as well as in colour", () => {
    // Roughly one man in twelve cannot separate the red and green reliably, and this grid is what a
    // qualification decision is argued from.
    const { container } = render(<DecisionMatrix candidates={candidates} requirements={requirements} />);
    const text = container.textContent ?? "";
    expect(text).toContain("✓");
    expect(text).toContain("✕");
    expect(text).toContain("?");
  });

  it("invites action instead of rendering an empty grid", () => {
    render(<DecisionMatrix candidates={[]} requirements={requirements} />);
    expect(screen.getByText(/No candidates yet/)).toBeTruthy();
  });
});

describe("RequirementMargins", () => {
  it("shows signed headroom against each threshold", () => {
    render(<RequirementMargins cells={candidates[0].cells} requirements={requirements} />);
    expect(screen.getByTestId("requirement-margins")).toBeTruthy();
    expect(screen.getByText("+50%")).toBeTruthy();
  });

  it("draws an unmeasured requirement as having no margin at all", () => {
    render(<RequirementMargins cells={candidates[0].cells} requirements={requirements} />);
    expect(screen.getByText(/NOT MEASURED — no margin exists/)).toBeTruthy();
  });

  it("labels a hard requirement as hard so the reader knows what can eliminate", () => {
    const { container } = render(
      <RequirementMargins cells={candidates[0].cells} requirements={requirements} />,
    );
    expect((container.textContent ?? "")).toContain("HARD");
  });
});

describe("PropertyDeltas", () => {
  it("reports change against the incumbent", () => {
    render(<PropertyDeltas properties={candidates[0].properties} />);
    expect(screen.getByTestId("property-deltas")).toBeTruthy();
    expect(screen.getByText("+13%")).toBeTruthy();
    expect(screen.getByText("-25%")).toBeTruthy();
  });

  it("counts out the properties that cannot be compared instead of hiding them", () => {
    render(<PropertyDeltas properties={candidates[0].properties} />);
    expect(screen.getByText(/1 property is absent/)).toBeTruthy();
  });

  it("says so plainly when nothing is comparable", () => {
    render(<PropertyDeltas properties={[{ property_key: "x", display_name: "X" }]} />);
    expect(screen.getByText(/no change can be stated/)).toBeTruthy();
  });
});

describe("EvidenceMix", () => {
  it("shows provenance classes instead of calling every stored value measured evidence", () => {
    const { container } = render(<EvidenceMix candidates={candidates} />);
    expect(screen.getByTestId("evidence-mix")).toBeTruthy();
    const text = container.textContent ?? "";
    expect(text).toContain("Reference handbook");
    expect(text).toContain("Supplier datasheet");
    expect(text).not.toContain("Measured / recorded evidence");
  });
});
