/** Client contracts for the chart-ready decision view (`/replacement-projects/{id}/decision-chart`). */

export type DecisionRequirement = {
  property_key: string;
  display_name: string;
  comparator: string;
  target_value: number | null;
  target_value_upper?: number | null;
  target_boolean: boolean | null;
  target_unit: string | null;
  canonical_target_value?: number | null;
  canonical_target_value_upper?: number | null;
  canonical_unit: string | null;
  hard_or_soft: string;
  severity: number;
  rationale: string | null;
};

export type DecisionCell = {
  property_key: string;
  status: string;
  observed_value: number | boolean | null;
  observed_unit: string | null;
  canonical_value: number | null;
  canonical_unit: string | null;
  /** Signed percentage against the threshold; null for UNKNOWN and for boolean gates. */
  margin_percent: number | null;
  value_origin: string | null;
  evidence_type?: string | null;
  source_quality?: string | null;
  provenance_category?: string | null;
  selected_observation_id?: string | null;
  conflict: boolean;
  confidence: number | null;
  unknown_reason: string | null;
};

export type DecisionCandidate = {
  candidate_id: string;
  candidate_kind: string;
  display_name: string;
  hard_passed: number;
  hard_failed: number;
  unknown: number;
  completeness: number;
  cells: DecisionCell[];
  origin_mix: Record<string, number>;
  provenance_mix?: Record<string, number>;
  properties: {
    property_key: string;
    display_name: string;
    baseline_value?: number;
    candidate_value?: number;
    percentage_delta?: number;
    canonical_unit?: string;
    value_origin?: string;
    direction?: string;
  }[];
};

export type DecisionChart = {
  found: boolean;
  project_id: string;
  project_name: string;
  baseline: { id: string; display_name: string; material_family: string };
  requirements: DecisionRequirement[];
  candidates: DecisionCandidate[];
  candidate_count: number;
  candidate_total?: number;
  excluded_candidate_count?: number;
  excluded_candidates?: { candidate_id: string; display_name: string; reason_code: string; message: string }[];
};

export type PropertySpaceAxis = {
  key: string;
  display_name: string;
  canonical_unit: string | null;
  direction: string;
  test_standard: string | null;
  why_it_matters: string | null;
};

export type PropertySpaceResponse = {
  x_axis: PropertySpaceAxis;
  y_axis: PropertySpaceAxis;
  points: {
    material_id: string;
    display_name: string;
    material_family: string;
    is_seed_data: boolean;
    x: number;
    y: number;
    x_origin: string;
    y_origin: string;
    x_provenance?: string;
    y_provenance?: string;
    weakest_origin?: string;
    x_observation_id?: string;
    y_observation_id?: string;
    x_evidence_type?: string | null;
    y_evidence_type?: string | null;
    x_source_quality?: string | null;
    y_source_quality?: string | null;
    x_conditions?: Record<string, unknown>;
    y_conditions?: Record<string, unknown>;
    x_confidence: number | null;
    y_confidence: number | null;
    highlighted: boolean;
  }[];
  excluded: { material_id: string; display_name: string; reason: string }[];
  material_indices: {
    key: string; label: string; design_case: string;
    exponent: number; log_slope: number; maximise: boolean;
  }[];
  plotted_count: number;
  excluded_count: number;
};

export type AxisOption = {
  key: string;
  display_name: string;
  domain: string;
  canonical_unit: string | null;
  material_count: number;
  direction: string;
};

export type IndexRanking = {
  index: { key: string; label: string; design_case: string; exponent: number };
  x_axis: PropertySpaceAxis;
  y_axis: PropertySpaceAxis;
  ranking: {
    material_id: string; display_name: string; material_family: string;
    index_value: number; x: number; y: number; lowest_origin: string;
  }[];
  excluded_count: number;
};
