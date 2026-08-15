const EXTERNAL_API = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
const USE_EXTERNAL_API = process.env.NEXT_PUBLIC_API_MODE === "external";

// Production is same-origin by default. A stale NEXT_PUBLIC_API_BASE_URL can therefore no longer
// send a Phase 12.2 frontend to a Phase 9/11 backend. Explicit external mode remains available
// for local development or a deliberately split deployment.
export const API = USE_EXTERNAL_API && EXTERNAL_API
  ? EXTERNAL_API
  : process.env.NODE_ENV === "production"
    ? "/api"
    : EXTERNAL_API ?? "http://localhost:8000";
const ORG = process.env.NEXT_PUBLIC_ORGANISATION_ID;

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(ORG ? {"X-Organisation-ID": ORG} : {}),
        ...(options?.headers ?? {}),
      },
      cache: "no-store",
    });
  } catch (error) {
    const cause = error instanceof Error ? error.message : "network error";
    throw new Error(`Cannot reach TinkerLab API at ${API}${path}: ${cause}`);
  }
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") message = body.detail;
      else if (typeof body?.detail?.message === "string") message = body.detail.message;
      else if (typeof body?.error?.message === "string") message = body.error.message;
    } catch {}
    throw new Error(message);
  }
  return response.json();
}

export type MaterialSummary = {
  id: string; canonical_name: string; display_name: string; material_family: string;
  description?: string; source_type: string; is_seed_data: boolean; visibility?: string; owner_organisation_id?: string;
};
export type ProjectSummary = {
  id: string; name: string; description?: string; status: string; replacement_reasons: string[];
  baseline_material: MaterialSummary; constraint_count: number; candidate_count: number;
};
export type Constraint = {
  id: string; property_key: string; comparator: string; target_value?: number; target_value_upper?: number;
  target_boolean?: boolean; target_unit?: string; hard_or_soft: string; weight: number; severity: number;
};
export type Objective = { id:string; property_key:string; direction:string; weight:number; priority:number; target_value?:number; target_unit?:string };
export type Candidate = { id:string; candidate_kind?:"known_material"|"hypothesis"; material?:MaterialSummary; hypothesis_id?:string; candidate_source:string; status:string; notes?:string };
export type ProjectDetail = ProjectSummary & {
  organisation_id:string; created_by:string; constraints:Constraint[]; objectives:Objective[]; candidates:Candidate[];
};
export type Specification = {
  specification_version:string; project_id:string; checksum:string; human_readable:string; canonical_payload:unknown; generated_at:string;
};
export type EvaluationConstraint = {
  property_key:string; status:"PASS"|"FAIL"|"UNKNOWN"; observed_value?:number|boolean; observed_unit?:string;
  canonical_value?:number; canonical_unit?:string; unknown_reason?:string; evidence_id?:string; confidence?:number;
  selected_observation_id?:string; selection_rationale:string[]; applicability?:string; alternatives_count:number; conflict:boolean;
  value_origin?:"known_evidence"|"model_prediction"|"none"; prediction_id?:string; model_version?:string; prediction_interval?:[number,number]; applicability_status?:string; uncertainty_crosses_constraint?:boolean;
};
export type Evaluation = {
  candidate_id:string; candidate_kind?:"known_material"|"hypothesis"; material_id?:string; hypothesis_id?:string; material_name:string; evidence_posture?:string; hard_passed:number; hard_failed:number; unknown:number; soft_passed:number; completeness:number;
  constraints:EvaluationConstraint[];
  properties:Array<{property_key:string;display_name:string;baseline_value?:number;candidate_value?:number;canonical_unit?:string;delta?:number;percentage_delta?:number;evidence_id?:string;confidence?:number;selected_observation_id?:string;selection_rationale:string[];applicability?:string;alternatives_count:number;conflict:boolean;value_origin?:"known_evidence"|"model_prediction"|"none";prediction_id?:string;model_version?:string;prediction_interval?:[number,number];applicability_status?:string}>;
};

export type ConditionSet = {
  id:string; temperature_value?:number; temperature_unit?:string; pressure_value?:number; pressure_unit?:string;
  humidity_percent?:number; strain_rate?:number; sample_orientation?:string; frequency_value?:number; frequency_unit?:string;
  material_state?:string; metadata:Record<string,unknown>;
};
export type Evidence = {
  id:string; evidence_type:string; title:string; source_reference?:string; description?:string; method?:string; confidence?:number;
  metadata:Record<string,unknown>; provider_id?:string; source_record_id?:string; visibility:string; status:string;
  curator_note?:string; source_quality?:string; provider?:{id:string;key:string;display_name:string;provider_type:string;adapter_version:string};
  source_record?:{id:string;external_record_id:string;raw_checksum:string;normalized_checksum:string;parser_version:string;status:string};
};
export type Observation = {
  id:string; property_definition_id:string; value_type:"numeric"|"boolean"; numeric_value?:number; boolean_value?:boolean; unit?:string;
  conditions:Record<string,unknown>; condition_set_id?:string; condition_set?:ConditionSet; uncertainty?:number; uncertainty_type?:string;
  uncertainty_lower?:number; uncertainty_upper?:number; uncertainty_stddev?:number; confidence?:number; method?:string; status:string;
  curator_preferred:boolean; curator_note?:string; source_record_id?:string;
  property_definition:{id:string;key:string;display_name:string;quantity_type:string;canonical_unit?:string;conflict_policy:string}; evidence:Evidence;
};
export type MaterialDetailV2 = MaterialSummary & {
  composition_summary?:string; observations:Observation[];
  identifiers:Array<{id:string;namespace:string;value:string;normalized_value:string;is_primary:boolean;visibility:string;evidence_id?:string}>;
  components:Array<{id:string;component_name:string;component_identifier?:string;component_role?:string;amount_value?:number;amount_lower?:number;amount_upper?:number;amount_unit?:string;amount_basis:string;uncertainty?:number;evidence_id?:string;is_redacted:boolean;redaction_label?:string;sequence:number;notes?:string}>;
  process_states:Array<{id:string;state_label:string;process_name?:string;sequence:number;parameters:Record<string,unknown>;evidence_id?:string;notes?:string}>;
};
export type ExplorerMaterial = {
  id:string; display_name:string; canonical_name:string; material_family:string; source_type:string; is_seed_data:boolean; visibility:string;
  identifiers:Array<{namespace:string;value:string;is_primary:boolean}>; observation_count:number; evidence_types:string[]; conflict_count:number;
};

export type SearchSpaceComponentRule = {
  id:string; baseline_component_id?:string; component_key:string; display_name:string; role?:string;
  locked:boolean; mutable:boolean; required:boolean; prohibited:boolean; min_amount?:number; max_amount?:number;
  step_amount?:number; amount_unit?:string; amount_basis?:string; sequence:number; metadata:Record<string,unknown>;
};
export type SearchSpaceProcessRule = {
  id:string; parameter_key:string; display_name:string; min_value:number; max_value:number; step_value?:number;
  unit:string; locked:boolean; metadata:Record<string,unknown>;
};
export type CandidateSearchSpace = {
  id:string; project_id:string; organisation_id:string; version:number; material_family:string; amount_basis:string;
  balance_component_key?:string; total_target?:number; total_tolerance:number; max_component_count:number;
  candidate_budget:number; maximum_enumeration:number; notes?:string; active:boolean; checksum:string;
  metadata:Record<string,unknown>; created_at:string; component_rules:SearchSpaceComponentRule[]; process_rules:SearchSpaceProcessRule[];
};
export type SearchSpaceValidation = {
  valid:boolean; estimated_cardinality:number; checksum:string;
  issues:Array<{code:string;path:string;message:string;severity:"error"|"warning"}>;
};
export type SubstitutionRule = {
  id:string; organisation_id:string; project_id?:string; material_family:string; source_component_key:string;
  replacement_component_key:string; replacement_display_name:string; allowed_min_amount?:number; allowed_max_amount?:number;
  amount_basis?:string; reason:string; evidence_id?:string; status:string; version:number; created_at:string;
};
export type GenerationStrategy = {
  key:string; version:string; supported_material_families:string[]; required_inputs:string[]; creates_hypotheses:boolean;
  deterministic:boolean; maximum_safe_candidate_count:number; description:string;
};
export type GenerationPreview = {
  valid:boolean; strategy:GenerationStrategy; specification_checksum:string; search_space_checksum:string; search_space_version:number;
  configuration_checksum:string; random_seed:number; candidate_budget:number; estimated_cardinality:number; expected_truncation:boolean;
  issues:Array<{code:string;path:string;message:string;severity:"error"|"warning"}>;
};
export type GenerationRun = {
  id:string; project_id:string; organisation_id:string; replacement_specification_checksum:string; search_space_id:string;
  search_space_version:number; search_space_checksum:string; strategy_key:string; strategy_version:string;
  configuration_checksum:string; random_seed:number; requested_candidate_budget:number; generated_count:number;
  accepted_count:number; rejected_count:number; duplicate_count:number; result_checksum?:string; status:string;
  started_at?:string; completed_at?:string; created_by:string; metadata:Record<string,unknown>; created_at:string;
};
export type CandidateLabItem = {
  id:string; project_id:string; candidate_kind:"known_material"|"hypothesis"; material_id?:string; hypothesis_id?:string;
  display_name:string; candidate_source:string; status:string; structural_validity?:string; deterministic_fingerprint?:string;
  generation_run_id?:string; evidence_posture:string; change_count:number; hard_passed:number; hard_failed:number; hard_unknown:number;
  evidence_completeness:number; scientific_conflicts:number; created_at:string;
};
export type CandidatePage = {items:CandidateLabItem[]; total:number; offset:number; limit:number};
export type CandidateHypothesis = {
  id:string; project_id:string; organisation_id:string; display_label:string; material_family:string; baseline_material_id:string;
  generation_run_id?:string; generator_strategy_key:string; generator_strategy_version:string; deterministic_fingerprint:string;
  fingerprint_version:string; status:string; structural_validity:string; rejection_reason?:string; notes?:string; created_at:string; updated_at:string;
  components:Array<{id:string;sequence:number;component_key:string;display_name:string;role?:string;amount?:number;unit?:string;basis?:string;source_baseline_component_id?:string;substitution_rule_id?:string;locked:boolean;metadata:Record<string,unknown>}>;
  process_parameters:Array<{id:string;process_label:string;parameter_key:string;value:number;unit:string;source_baseline_state_id?:string;metadata:Record<string,unknown>}>;
  changes:Array<{id:string;sequence:number;change_type:string;target_path:string;before_value:Record<string,unknown>;after_value:Record<string,unknown>;substitution_rule_id?:string;rationale:string}>;
  warning:string;
};
export type CandidateLineage = {
  id:string; child_hypothesis_id:string; parent_material_id?:string; parent_candidate_id?:string; parent_hypothesis_id?:string;
  relationship_type:string; generation_run_id?:string; sequence:number; rationale:string;
};

export type PredictionModel = {
  id:string; organisation_id?:string; key:string; display_name:string; description?:string; model_type:string;
  owner_provider:string; status:string; supported_material_families:string[]; supported_property_keys:string[];
  metadata:Record<string,unknown>; created_at:string; updated_at:string;
};
export type PredictionModelVersion = {
  id:string; model_id:string; version:string; predictor_key:string; predictor_contract_version:string; artifact_format:string;
  artifact_checksum:string; feature_schema_version:string; feature_schema:Record<string,unknown>; feature_schema_checksum:string;
  target_property_key:string; canonical_output_unit:string; uncertainty_method:string; applicability_policy_version:string;
  training_data_descriptor:Record<string,unknown>; training_data_checksum?:string; calibration_metrics:Record<string,unknown>;
  validation_metrics:Record<string,unknown>; approved_at?:string; retired_at?:string; immutable_metadata:Record<string,unknown>;
  created_at:string; applicability_domain?:{material_families:string[];required_feature_keys:string[];numeric_feature_ranges:Record<string,unknown>;target_condition_ranges:Record<string,unknown>;redacted_input_policy:string;borderline_tolerance:number};
};
export type PredictionTargetRequest = {candidate_id?:string;material_id?:string;hypothesis_id?:string};
export type ApplicabilityIssue = {code:string;message:string;feature?:string;value?:unknown;allowed?:unknown};
export type PredictionPreviewTarget = {
  target_kind:string;target_id:string;candidate_id?:string;applicability_status:string;reasons:ApplicabilityIssue[];
  feature_checksum:string;missing_features:string[];redaction_flags:string[];
};
export type PredictionPreview = {
  valid:boolean;model_id:string;model_version_id:string;model_version:string;model_label:string;demo_warning?:string;
  property_key:string;feature_schema_version:string;target_condition_checksum:string;configuration_checksum:string;
  target_count:number;in_domain_count:number;borderline_count:number;inapplicable_count:number;expected_model_executions:number;
  targets:PredictionPreviewTarget[];validation_problems:string[];
};
export type PredictionRun = {
  id:string;organisation_id:string;project_id:string;model_version_id:string;property_key:string;configuration_checksum:string;
  target_condition_checksum:string;requested_target_count:number;predicted_count:number;inapplicable_count:number;failed_count:number;
  status:string;run_seed?:number;started_at?:string;completed_at?:string;created_by:string;result_checksum?:string;
  metadata:Record<string,unknown>;created_at:string;
};
export type PropertyPrediction = {
  id:string;prediction_run_id:string;prediction_target_id:string;model_version_id:string;input_snapshot_id:string;
  property_definition_id:string;applicability_status:string;applicability_rationale:Array<Record<string,unknown>>;domain_distance?:number;
  numeric_point_estimate?:number;output_unit?:string;canonical_value?:number;canonical_unit?:string;uncertainty_lower?:number;
  uncertainty_upper?:number;uncertainty_stddev?:number;uncertainty_method:string;calibrated_coverage_level?:number;
  warnings:string[];status:string;deterministic_result_checksum:string;created_at:string;scientific_origin:string;
};
export type PredictionResultPage = {items:Array<PropertyPrediction & {target?:Record<string,unknown>}>;total:number;offset:number;limit:number};
export type PredictionDetail = {
  prediction:PropertyPrediction;target:Record<string,unknown>;model:Record<string,unknown>;model_version:Record<string,unknown>;
  feature_snapshot:Record<string,unknown>;demo_warning?:string;
};
export type PredictionHistoryItem = {
  id:string;prediction_run_id:string;model_version_id:string;applicability_status:string;numeric_point_estimate?:number;
  output_unit?:string;uncertainty_lower?:number;uncertainty_upper?:number;status:string;warnings:string[];scientific_origin:string;
};

export type VirtualPolicy = {
  key:string;version:string;deterministic:boolean;min_objectives:number;max_objectives:number;
  uncertainty_semantics:string;unknown_handling:string;maximum_safe_candidate_pool:number;
};
export type VirtualCampaign = {
  id:string;organisation_id:string;project_id:string;name:string;description?:string;replacement_specification_checksum:string;
  search_space_id:string;search_space_version:number;search_space_checksum:string;policy_key:string;policy_version:string;
  configuration_checksum:string;random_seed:number;max_iterations:number;max_total_new_candidates:number;
  max_candidates_per_iteration:number;max_parents_per_iteration:number;status:string;stop_reason?:string;created_by:string;
  started_at?:string;completed_at?:string;result_checksum?:string;metadata:Record<string,unknown>;created_at:string;updated_at:string;
};
export type CampaignObjective = {
  id:string;campaign_id:string;property_key:string;direction:"maximize"|"minimize"|"target";weight:number;priority:number;
  target_value?:number;target_unit?:string;model_version_id:string;evaluation_mode:string;sequence:number;metadata:Record<string,unknown>;
};
export type CampaignIteration = {
  id:string;campaign_id:string;iteration_number:number;input_pool_checksum:string;parent_selection_checksum?:string;
  generation_run_ids:string[];prediction_run_ids:string[];evaluated_candidate_count:number;feasible_count:number;uncertain_count:number;
  infeasible_count:number;pareto_front_count:number;pareto_front_checksum?:string;selected_for_exploration_count:number;
  new_candidate_count:number;duplicate_count:number;decision_checksum?:string;status:string;started_at?:string;completed_at?:string;
  stop_signal:boolean;stop_reason?:string;metadata:Record<string,unknown>;
};
export type VirtualCampaignDetail = {
  campaign:VirtualCampaign;objectives:CampaignObjective[];constraint_policies:Array<Record<string,unknown>>;
  iterations:CampaignIteration[];warning:string;
};
export type CampaignPreview = {
  valid:boolean;campaign_id:string;policy_key:string;policy_version:string;specification_checksum:string;search_space_checksum:string;
  configuration_checksum:string;candidate_pool_size:number;objective_count:number;objective_models:Array<Record<string,unknown>>;
  applicability_forecast:Record<string,Record<string,number>>;estimated_prediction_runs:number;estimated_mutation_cardinality:number;
  budgets:Record<string,number>;validation_issues:Array<{code:string;message:string;severity:"error"|"warning";path?:string}>;warning:string;
};
export type VirtualCandidateEvaluation = {
  id:string;campaign_iteration_id:string;candidate_id:string;hypothesis_id?:string;feasibility_class:"robustly_feasible"|"uncertain"|"robustly_infeasible";
  hard_pass_count:number;hard_fail_count:number;hard_unknown_count:number;
  objective_vector:Record<string,{point?:number;conservative_value?:number;unit?:string;direction:string;completeness:string}>;
  objective_intervals:Record<string,{lower?:number;upper?:number;unit?:string;uncertainty_width?:number}>;
  objective_origins:Record<string,{origin:string;prediction_id?:string;model_version_id?:string;applicability?:string}>;
  pareto_rank?:number;dominance_count:number;diversity_metric?:number;uncertainty_burden:Record<string,number>;
  normalized_utility_components:Record<string,number>;acquisition_components:Record<string,unknown>;selected_as_parent:boolean;
  selected_for_next_evaluation:boolean;disposition:string;rationale:string;deterministic_evaluation_checksum:string;
  metadata:Record<string,unknown>;created_at:string;scientific_origin:string;
};
export type VirtualEvaluationPage = {items:VirtualCandidateEvaluation[];total:number;offset:number;limit:number};
export type ParetoFront = {id:string;campaign_iteration_id:string;front_number:number;ordered_candidate_ids:string[];objective_space_checksum:string;policy_key:string;policy_version:string;created_at:string};
export type OptimizationDecision = {id:string;campaign_id:string;campaign_iteration_id:string;candidate_id?:string;hypothesis_id?:string;sequence:number;decision_type:string;policy_key:string;policy_version:string;input_checksum:string;metrics:Record<string,unknown>;rationale:string;created_at:string};
export type VirtualCampaignRunResult = {campaign:VirtualCampaign;iterations:CampaignIteration[];final_front_candidate_ids:string[];warning:string};

// ---------------------------------------------------------------------------------------------
// Phase 6 — Physics & Simulation Operating System.
// A simulation result is a third scientific origin: not evidence, not an ML prediction.
// ---------------------------------------------------------------------------------------------
export type RepresentationFormat = {format:string;validator_version:string;representation_type:string};
export type Representation = {
  id:string;organisation_id?:string;visibility:string;material_id?:string;hypothesis_id?:string;label:string;
  representation_type:string;representation_format:string;representation_version:string;normalized_checksum:string;
  content_bytes:number;periodicity?:string;dimensionality?:number;atom_count?:number;component_count?:number;
  chemical_elements:string[];validator_key:string;validator_version:string;validation_status:string;
  completeness_status:string;validation_messages:Array<Record<string,unknown>>;redaction_flags:string[];
  provenance_note?:string;status:string;created_at:string;
};
export type RepresentationValidation = {
  representation_format:string;representation_type:string;validator_key:string;validator_version:string;
  validation_status:string;completeness_status:string;usable:boolean;messages:Array<{code:string;path?:string;message:string}>;
  normalized_checksum?:string;atom_count?:number;component_count?:number;chemical_elements:string[];redaction_flags:string[];
};
export type SimulationProvider = {
  id:string;organisation_id?:string;key:string;display_name:string;provider_type:string;method_family:string;
  description?:string;safety_class:string;approved_execution_mode:string;status:string;created_at:string;
};
export type SimulationProviderVersion = {
  id:string;provider_id:string;version:string;adapter_key:string;adapter_contract_version:string;executable_key?:string;
  executable_version?:string;parser_key:string;parser_version:string;input_builder_key:string;input_builder_version:string;
  convergence_evaluator_key:string;convergence_evaluator_version:string;supported_method_keys:string[];
  supported_material_families:string[];supported_representation_types:string[];supported_representation_formats:string[];
  supported_property_keys:string[];required_artifact_types:string[];artifact_manifest_checksum:string;fidelity:string;
  deterministic:boolean;execution_supported:boolean;maximum_target_size:number;maximum_wall_time_seconds:number;
  resource_class:string;known_limitations:string[];approved_at?:string;retired_at?:string;created_at:string;
};
export type ProviderAvailability = {
  provider_version_id:string;available:boolean;reason_code:string;detail:string;
  executable_name?:string;executable_version?:string;
};
export type SimulationMethod = {
  key:string;display_name:string;method_family:string;purpose:string;description?:string;fidelity:string;
  required_representation_types:string[];required_parameters:Record<string,Record<string,unknown>>;
  output_property_keys:string[];output_units:Record<string,string>;convergence_semantics:Record<string,unknown>;
  known_limitations:string[];status:string;definition_version:string;
};
export type SimulationRoutePreview = {
  target_kind:string;target_id:string;target_display_name:string;material_family:string;requested_purpose:string;
  requested_property_key?:string;
  representations_considered:Array<{id:string;representation_type:string;representation_format:string;checksum:string;validation_status:string;completeness_status:string}>;
  routes:Array<{
    method_key:string;method_display_name:string;method_family:string;provider_key:string;provider_display_name:string;
    provider_version_id:string;provider_version:string;adapter_key:string;representation_id?:string;
    representation_checksum?:string;route_status:string;reasons:Array<{code:string;message:string}>;
    missing_representation_types:string[];missing_artifact_types:string[];fidelity:string;
    estimated_resource_class:string;limitations:string[];route_checksum:string;route_policy_version:string;
  }>;
  warning:string;evidence_separation:string;
};
export type SimulationWorkflowPreview = {
  valid:boolean;validation_problems:string[];target_kind:string;target_id:string;
  route:SimulationRoutePreview["routes"][number];
  method:{key:string;display_name:string;fidelity:string;convergence_semantics:Record<string,unknown>;known_limitations:string[];output_property_keys:string[];output_units:Record<string,string>};
  provider_version:{id:string;provider_key:string;version:string;adapter_key:string;executable_key?:string;artifact_manifest_checksum:string;parser:[string,string];input_builder:[string,string];convergence_evaluator:[string,string]};
  representation?:{id:string;checksum:string;representation_type:string};
  normalized_parameters:Record<string,unknown>;target_conditions:Record<string,unknown>;input_checksum?:string;
  input_files:string[];input_file_preview:Record<string,string>;
  artifact_references:Array<Record<string,unknown>>;workflow_template:{key:string;version:string;steps:string[]};
  resource_request:Record<string,unknown>;warning:string;executes_nothing:boolean;
};
export type SimulationWorkflow = {
  id:string;organisation_id:string;project_id?:string;candidate_id?:string;campaign_id?:string;target_kind:string;
  target_scientific_id:string;route_id:string;input_snapshot_id:string;provider_version_id:string;method_definition_id:string;
  workflow_template_key:string;workflow_template_version:string;requested_purpose:string;requested_property_key?:string;
  requested_fidelity:string;max_steps:number;max_wall_time_seconds:number;status:string;failure_code?:string;
  started_at?:string;completed_at?:string;workflow_checksum?:string;created_at:string;
};
export type SimulationResult = {
  id:string;workflow_id:string;job_id?:string;target_kind:string;target_scientific_id:string;method_definition_id:string;
  provider_version_id:string;operational_status:string;scientific_status:string;convergence_metrics:Record<string,unknown>;
  convergence_criteria:Record<string,unknown>;convergence_evaluator_version:string;parser_key:string;parser_version:string;
  parsed_quantities:Record<string,{value:number;unit:string}>;warnings:string[];method_limitations:string[];
  output_artifact_checksums:string[];result_checksum:string;scientific_origin:string;created_at:string;
};
export type SimulationPropertyEstimate = {
  id:string;simulation_result_id:string;property_definition_id:string;numeric_value?:number;raw_unit?:string;
  canonical_value?:number;canonical_unit?:string;numerical_tolerance?:number;tolerance_basis?:string;
  method_limitations:string[];target_conditions:Record<string,unknown>;extractor_key:string;extractor_version:string;
  estimate_checksum:string;scientific_origin:string;
};
export type SimulationWorkflowDetail = {
  workflow:SimulationWorkflow;
  steps:Array<{id:string;sequence:number;step_key:string;method_key:string;status:string;input_checksum:string;output_checksum?:string;requires_convergence:boolean}>;
  jobs:Array<{id:string;attempt_number:number;command_descriptor:Record<string,unknown>;resource_request:Record<string,unknown>;compute_backend_key:string;status:string;process_exit_code?:number;failure_code?:string;elapsed_seconds?:number;operational_checksum:string}>;
  artifacts:Array<{id:string;artifact_type:string;content_role:string;file_name:string;storage_reference:string;content_checksum:string;content_bytes:number;truncated:boolean;inline_preview?:string}>;
  result?:SimulationResult;property_estimates:SimulationPropertyEstimate[];warning:string;evidence_separation:string;
};
export type SimulationHistory = {
  items:Array<{workflow_id:string;status:string;failure_code?:string;requested_property_key?:string;requested_fidelity:string;
    workflow_checksum?:string;created_at:string;scientific_status?:string;result_checksum?:string;scientific_origin:string}>;
  total:number;offset:number;limit:number;warning:string;
};

// ---------------------------------------------------------------------------------------------
// Phase 7 — Industrial Viability Engine.
// Industrial evidence is a separate claim class again: not evidence, not prediction, not simulation.
// ---------------------------------------------------------------------------------------------
export type IndustrialState = "pass"|"fail"|"partial"|"unknown"|"insufficient_evidence"|"conflicting_evidence";
export type ManufacturingRoute = {
  id:string;organisation_id?:string;visibility:string;key:string;display_name:string;process_family:string;
  description?:string;applies_to_material_families:string[];applies_to_elements:string[];required_equipment:string[];
  process_temperature_k_min?:number;process_temperature_k_max?:number;achievable_thickness_m_min?:number;
  achievable_thickness_m_max?:number;achievable_tolerance_m?:number;typical_yield_fraction?:number;
  throughput_units_per_hour?:number;capex_class?:string;process_maturity:string;scale_up_maturity:string;
  known_limitations:string[];status:string;created_at:string;
};
export type IndustrialEvidence = {
  id:string;material_id?:string;hypothesis_id?:string;category:string;metric_key:string;display_label:string;
  numeric_value?:number;lower_bound?:number;upper_bound?:number;uncertainty?:number;unit?:string;
  boolean_value?:boolean;categorical_value?:string;currency?:string;currency_year?:number;cost_basis?:string;
  quantity_basis_value?:number;quantity_basis_unit?:string;geography?:string;jurisdiction?:string;
  process_context?:string;manufacturing_route_id?:string;conditions:Record<string,unknown>;
  as_of_date?:string;valid_until?:string;source_type:string;source_reference?:string;extraction_method?:string;
  confidence?:number;is_estimate:boolean;scientific_origin:string;notes?:string;content_checksum:string;
  status:string;created_at:string;
};
export type IndustrialConstraint = {
  id:string;project_id:string;category:string;constraint_kind:string;metric_key?:string;display_label:string;
  strength:string;weight:number;target_value?:number;target_value_upper?:number;target_unit?:string;
  currency?:string;currency_year?:number;cost_basis?:string;banned_elements:string[];
  allowed_jurisdictions:string[];required_route_keys:string[];minimum_maturity?:string;
  minimum_supplier_count?:number;treat_missing_evidence_as:string;rationale?:string;created_at:string;
};
export type ConstraintResult = {
  constraint_id:string;display_label:string;category:string;constraint_kind:string;strength:string;
  metric_key?:string;weight:number;state:IndustrialState;detail?:string;evidence_ids?:string[];
  observed_interval?:number[];limit?:number;required_range?:number[];unit?:string;stale?:boolean;
  offending?:string[];observed?:Record<string,string>|string;required?:string;conflicts?:Array<Record<string,unknown>>;
};
export type DimensionDetail = {
  state:IndustrialState;detail?:string|null;constraint_results?:ConstraintResult[];evidence_ids?:string[];
  evidence_count?:number;stale_evidence_ids?:string[];estimate_evidence_ids?:string[];
  conflicts?:Array<Record<string,unknown>>;stage?:string;justification?:string|null;
  converged_simulation_count?:number;candidate_id?:string;origin_note?:string;
};
export type ViabilityAssessment = {
  project_id:string;target_kind:string;target_id:string;target_display_name:string;declared_elements:string[];
  dimension_states:Record<string,IndustrialState>;dimension_details:Record<string,DimensionDetail>;
  hard_constraint_failures:ConstraintResult[];soft_constraint_results:ConstraintResult[];
  unknown_dimensions:string[];conflicting_evidence:Array<Record<string,unknown>>;overall_state:IndustrialState;
  maturity_stage:string;composite_score?:number|null;composite_methodology?:string|null;
  composite_weights:Record<string,number>;composite_is_partial:boolean;
  evidence_coverage:{total_records:number;by_category:Record<string,number>;stale_records:number;
    estimate_records:number;dimensions_with_no_evidence:string[]};
  missing_evidence:Array<{constraint_id:string;display_label:string;metric_key?:string;category:string;state:string;detail?:string}>;
  policy_version:string;separation_note:string;assessment_checksum:string;assessment_id?:string;
};
export type ViabilityComparison = {
  project_id:string;dimensions:string[];candidates:ViabilityAssessment[];
  comparability_note:string;separation_note:string;
};
export type MaturityCurrent = {
  target_kind:string;target_id:string;stage:string;assessment_id?:string;justification?:string;note:string;
};

// ---------------------------------------------------------------------------------------------
// Phase 8 — Functional decomposition & replacement reasoning.
// ---------------------------------------------------------------------------------------------
export type RequirementStatusValue =
  "pass"|"fail"|"partial"|"unknown"|"insufficient_evidence"|"conflicting_evidence"|"state_mismatch";
export type OriginClass = "observed"|"literature"|"predicted"|"simulated"|"experimental"|"industrial"|"unknown";
export type MaterialStateRecord = {
  id:string;material_id?:string;hypothesis_id?:string;label:string;description?:string;
  is_reference_state:boolean;representation_id?:string;crystal_system?:string;space_group_number?:number;
  space_group_symbol?:string;lattice_parameters:Record<string,unknown>;polymorph?:string;phase?:string;
  phase_fraction?:number;structure_identity?:string;structure_identity_basis?:string;
  composition_signature?:string;microstructure_id?:string;processing_history_id?:string;
  temperature_k?:number;pressure_pa?:number;environment?:string;conditions:Record<string,unknown>;
  state_checksum:string;provenance_note?:string;status:string;created_at:string;
};
export type RoleDecomposition = {
  application?:{id:string;display_name:string};
  component?:{id:string;display_name:string};
  role:{id:string;key:string;display_name:string;incumbent_material_id?:string;incumbent_state_id?:string};
  functions:Array<{
    id:string;key:string;display_name:string;category:string;criticality:number;
    requirements:Array<{id:string;key:string;display_name:string;requirement_kind:string;direction:string;
      property_key?:string;target_value?:number;target_value_upper?:number;target_unit?:string;
      conditions:Record<string,unknown>;rationale?:string}>;
  }>;
};
export type OriginValueRecord = {
  origin:OriginClass;value?:number|null;unit?:string|null;interval?:number[]|null;state_id?:string|null;
  state_match:string;state_reasons:string[];source_id:string;source_kind:string;detail:string;usable:boolean;
};
export type RequirementResult = {
  requirement_id:string;requirement_key:string;display_name:string;requirement_kind:string;
  direction:string;property_key?:string;target_value?:number;target_value_upper?:number;
  target_unit?:string;weight:number;conditions:Record<string,unknown>;status:RequirementStatusValue;
  detail:string;values?:OriginValueRecord[];origin_counts?:Record<string,number>;
  outcomes?:Array<{origin:string;source_id:string;status:string;detail:string}>;
  governing_origin?:OriginClass|null;governing_source_id?:string;governing_state_match?:string;
  origin_note?:string;function_id:string;function_key:string;function_display_name:string;
  function_criticality:number;
};
export type MechanismPath = {
  property_key:string;
  chain:Array<{kind:string;id:string}>;
  edges:Array<{edge_id:string;edge_kind:string;scope?:string;confidence?:number;source_type:string;
    source_reference?:string;note?:string}>;
  weakest_confidence?:number|null;
};
export type CandidateReasoning = {
  role:{id:string;key:string;display_name:string;component?:string|null;application?:string|null;
    incumbent_material_id?:string;incumbent_state_id?:string};
  target_kind:string;target_id:string;
  state?:{id:string;label:string;structure_identity?:string|null;composition_signature?:string|null}|null;
  state_warning?:string|null;
  requirement_results:RequirementResult[];
  function_coverage:Record<string,{function_id:string;display_name:string;category:string;
    criticality:number;requirement_count:number;status:RequirementStatusValue;statuses:string[]}>;
  satisfied_requirements:string[];failed_requirements:string[];unknown_requirements:string[];
  evidence_gaps:Array<{requirement_id:string;display_name:string;property_key?:string;status:string;
    function_key:string;criticality:number;requirement_kind:string;detail:string;what_would_resolve_it:string}>;
  origin_breakdown:Record<string,number>;mechanism_paths:MechanismPath[];mechanism_note:string;
  assumptions:string[];generation_rationale?:string|null;overall_status:RequirementStatusValue;
  policy_version:string;origin_separation_note:string;structured_first_note:string;
  reasoning_checksum:string;reasoning_result_id?:string;
};

// ---------------------------------------------------------------------------------------------
// Phase 9 — Experimental design & validation.
// ---------------------------------------------------------------------------------------------
export type MeasurementRecord = {
  id:string;run_id:string;sample_id?:string;instrument_id?:string;property_definition_id:string;
  numeric_value?:number;unit?:string;canonical_value?:number;canonical_unit?:string;
  uncertainty?:number;uncertainty_type?:string;method?:string;conditions:Record<string,unknown>;
  replicate_index:number;measured_at?:string;quality:string;quality_reasons:string[];admissibility_codes:string[];
  scientific_origin:string;measurement_checksum:string;notes?:string;created_at:string;
};
export type SampleRecord = {
  id:string;candidate_id?:string;sample_code:string;display_name?:string;sample_kind:string;material_id?:string;
  hypothesis_id?:string;material_state_id?:string;parent_sample_id?:string;batch_reference?:string;
  geometry?:string;dimensions:Record<string,unknown>;mass_kg?:number;preparation_date?:string;
  provenance_complete:boolean;provenance_gaps:string[];status:string;created_at:string;
};
export type ReasoningRole = {
  id:string;key:string;display_name:string;application_id:string;application_name:string;
  component_id:string;component_name:string;incumbent_material_id?:string;incumbent_state_id?:string;
};
export type ValidationRequirementOutcome = {
  requirement_id:string;property_key?:string;requirement_kind?:string;reasoning_status?:string;
  outcome:string;reason_code:string;measurement_outcomes?:Array<Record<string,unknown>>;
  conflicting_measurements?:Array<Record<string,unknown>>;
};
export type ValidationResultRecord = {
  role_id:string;candidate_id?:string;target_kind:string;target_id:string;validation_state:string;rationale:string;
  per_property_comparisons:Array<{requirement_id:string;property_key:string;requirement_status:string;experimental_outcome:string;
    experimental_values:Array<{measurement_id:string;value?:number;unit?:string;raw_value?:number;raw_unit?:string;uncertainty?:number;
      method?:string;sample_id?:string;conditions?:Record<string,unknown>;admissibility?:string;admissibility_codes?:string[]}>;
    other_origin_values:Array<Record<string,unknown>>;
    pairwise_comparisons:Array<{verdict:string;detail:string;absolute_difference?:number;unit?:string}>;
    conflicting_experiments:Array<Record<string,unknown>>;note:string}>;
  agreements:Array<Record<string,unknown>>;disagreements:Array<{verdict:string;detail:string;property_key:string}>;
  conflicting_experiments:Array<{measurement_ids:string[];values:number[];unit?:string;detail:string}>;
  requirement_outcomes:ValidationRequirementOutcome[];
  experimentally_supported_requirements:string[];experimentally_contradicted_requirements:string[];
  inconclusive_requirements:string[];outstanding_requirements:string[];
  measurement_ids:string[];policy_version:string;methodology_version:string;evidence_snapshot:Record<string,unknown>;
  separation_note:string;autonomy_note:string;assessment_checksum:string;validation_assessment_id?:string;
};
export type ExperimentPlanRecord = {
  id:string;project_id?:string;candidate_id?:string;role_id?:string;requirement_id?:string;display_name:string;objective:string;
  design_kind:string;protocol_version_id:string;factors:Array<Record<string,unknown>>;replicate_count:number;control_plan?:string;
  planned_run_count:number;design_checksum:string;status:string;created_at:string;
};
export type ExperimentRunRecord = {
  id:string;plan_id?:string;protocol_version_id:string;protocol_checksum_at_run:string;run_code:string;sample_id?:string;instrument_id?:string;
  replicate_index:number;is_control:boolean;factor_levels:Record<string,unknown>;conditions:Record<string,unknown>;
  started_at?:string;completed_at?:string;status:string;deviation_notes?:string;invalidation_reason?:string;integration_kind:string;created_at:string;
};
export type ReplacementDecisionRecord = {
  candidate_id:string;project_id:string;role_id:string;target_kind:string;target_id:string;
  scientific_requirements:{validation_state:string;requirement_outcomes:ValidationRequirementOutcome[];reasoning_checksum?:string};
  simulation_status:string;industrial_status:string;industrial_assessment_id?:string;experimental_status:string;
  blocking_requirements:Array<{requirement_id:string;property_key?:string;reason_code:string}>;
  unresolved_requirements:Array<{requirement_id:string;property_key?:string;reason_code:string}>;
  conflicting_evidence:Array<Record<string,unknown>>;decision:"READY_FOR_NEXT_GATE"|"NOT_READY"|"REJECTED"|"INCONCLUSIVE";
  reason_codes:string[];methodology_version:string;qualification_note:string;validation:ValidationResultRecord;
};
export type ExperimentRecommendationRecord = {
  requirement_id:string;requirement_display_name:string;property_key?:string;property_definition_id?:string;unresolved_status:string;
  why_it_matters:string;current_evidence_summary:Record<string,unknown>;expected_evidence_type:string;
  proposed_measurement:string;suggested_protocol_id?:string|null;suggested_protocol_key?:string|null;priority_score:number;
  priority_factors:Record<string,number>;priority_weights:Record<string,number>;
  priority_methodology:string;priority_note:string;
};
export type RecommendationResponse = {
  role_id:string;target_kind:string;target_id:string;
  recommendations:ExperimentRecommendationRecord[];methodology:string;
  weights:Record<string,number>;autonomy_note:string;
};

// --- Phase 10: closed-loop replacement decision OS ---------------------------------------------
export type GateResult = {gate:string;satisfied:boolean;reason:string;evidence?:unknown};
export type ProgramHeader = {
  program_id:string;name:string;key:string;project_id:string;
  application_name?:string;application_domain?:string;role_id?:string;
  incumbent_material:{id?:string;display_name?:string};incumbent_state:{id?:string;label?:string};
  program_state:string;program_state_reason_codes:string[];
  convergence_state?:string;convergence_progress_percent?:number;
  active_candidates:number;blocked_candidates:number;blocking_gaps:number;
  decision_policy_version:string;is_demonstration_data:boolean;
  last_evidence_update?:string;last_event_kind?:string;
};
export type ReplacementProgramRecord = {
  id:string;organisation_id:string;project_id:string;key:string;name:string;description?:string;
  application_id?:string;application_component_id?:string;role_id?:string;
  application_name?:string;application_domain?:string;application_context:Record<string,unknown>;
  incumbent_material_id?:string;incumbent_state_id?:string;
  decision_policy_id?:string;decision_policy_version:string;
  status:string;status_override?:string;status_reason_codes:string[];
  validation_strategy:Record<string,unknown>;is_demonstration_data:boolean;
  created_at:string;updated_at:string;
};
export type MatrixCell = {
  status:string;governing_origin?:string;governing_evidence?:Record<string,unknown>;
  coverage_score:number;outcomes:Array<Record<string,unknown>>;missing_evidence:string[];
  why:string;
};
export type DecisionMatrixRow = {
  requirement_id:string;requirement_key:string;display_name:string;property_key?:string;
  criticality:string;requirement_kind:string;is_gating:boolean;direction?:string;
  target_value?:number;target_unit?:string;cells:Record<string,MatrixCell>;
};
export type DecisionMatrix = {
  program_id:string;rows:DecisionMatrixRow[];
  candidates:Array<{candidate_id:string;display_name:string;candidate_kind:string}>;
  incumbent:Record<string,unknown>;methodology_version:string;note:string;
};
export type PortfolioRow = {
  candidate_id:string;display_name:string;candidate_kind:string;candidate_source?:string;
  eligibility:string;portfolio_state:string;gates_satisfied:boolean;gate_results:GateResult[];
  definitive_blocking_failures:Array<Record<string,unknown>>;
  unresolved_gating_requirements:Array<Record<string,unknown>>;
  validation_state:string;industrial_state:string;next_gate_decision?:string;
  blocking_failure_count:number;unknown_count:number;conflict_count:number;
  gating_requirement_count:number;evidence_coverage:number;
  blocking_gap_count:number;gap_count:number;
  next_action?:ScientificActionRecord|null;rank?:number|null;rank_excluded_reason?:string|null;
  pareto_front:boolean;dominated_by:string[];reason_codes:string[];
};
export type PortfolioBoard = {
  program_id:string;candidates:PortfolioRow[];
  counts:{total:number;eligible:number;unresolved:number;blocked:number;decision_ready:number;pareto_front:number};
  methodology_version:string;note:string;
};
export type EvidenceGapRecord = {
  gap_id:string;candidate_id:string;candidate_display_name:string;
  requirement_id:string;requirement_key:string;display_name?:string;property_key?:string;
  criticality:string;gap_class:string;gap_kinds:string[];governing_status:string;
  coverage_score:number;missing_evidence:string[];why_unresolved:string;
  what_would_resolve_it:string;
};
export type ProgramGaps = {
  program_id:string;gaps:EvidenceGapRecord[];by_class:Record<string,EvidenceGapRecord[]>;
  by_candidate:Record<string,EvidenceGapRecord[]>;counts:Record<string,number>;
  blocking_gap_count:number;methodology_version:string;note:string;
};
export type ScientificActionRecord = {
  id?:string;program_id?:string;candidate_id?:string;candidate_display_name?:string;
  requirement_id?:string;requirement_key?:string;action_type:string;action_signature:string;
  status:string;priority:number;priority_factors:Record<string,unknown>;
  decision_value_class:string;cost_class:string;reason_code:string;reason:string;
  gap_class?:string;resolves_gap_kind?:string;what_it_could_resolve?:string;
  depends_on:string[];methodology_version:string;created_at?:string;
};
export type ConvergenceRecord = {
  program_id:string;convergence_state:string;metrics:Record<string,number>;
  per_candidate:Array<Record<string,unknown>>;reason_codes:string[];reasons:string[];
  presentation_progress_percent:number;decision_policy_version:string;
  methodology_version:string;note:string;probability_disclaimer:string;
};
export type RankingRow = {
  candidate_id:string;display_name:string;score?:number|null;rank:number;
  raw_factors:Record<string,number|null>;normalized_factors:Record<string,number|null>;
  weights:Record<string,number>;excluded_dimensions:string[];
  hard_blockers:Array<Record<string,unknown>>;methodology_version:string;
};
export type RankingResponse = {
  program_id:string;ranked:RankingRow[];
  excluded:Array<{candidate_id:string;display_name:string;eligibility:string;reason:string}>;
  pareto:{front_candidate_ids:string[];dominated_by:Record<string,string[]>;objectives:string[];note:string};
  weights:Record<string,number>;objectives:string[];objective_directions:Record<string,string>;
  methodology_version:string;note:string;
  sensitivity?:{stability:string;reason:string;scenario_count:number;baseline_winner?:string|null;note?:string};
};
export type ReplacementRecommendationRecord = {
  id?:string;recommendation_id?:string;program_id:string;version?:number;status:string;
  recommended_candidate_ids:string[];rejected_candidate_ids:string[];held_candidate_ids:string[];
  incumbent_reference:Record<string,unknown>;requirement_summary:Record<string,unknown>;
  per_candidate:Array<Record<string,unknown>>;
  blocking_requirements:Array<Record<string,unknown>>;
  unresolved_requirements:Array<Record<string,unknown>>;
  conflicting_evidence:Array<Record<string,unknown>>;
  evidence_gaps:EvidenceGapRecord[];next_actions:ScientificActionRecord[];
  convergence_state:string;reason_codes:string[];rationale:string;
  decision_policy_version:string;methodology_versions:Record<string,string>;
  qualification_note:string;recommendation_checksum?:string;
  possible_program_actions?:string[];requirement_relaxation_note?:string;created_at?:string;
};
export type TechnicalDossierRecord = {
  id:string;program_id:string;version:number;candidate_id?:string;title:string;
  sections:Array<{number:number;title:string;content:Record<string,unknown>}>;
  snapshot_id?:string;recommendation_id?:string;evidence_ids:string[];
  methodology_versions:Record<string,string>;decision_policy_version:string;
  llm_narrative_used:boolean;dossier_checksum:string;generated_at:string;
};
export type TimelineEventRecord = {
  id:string;program_id:string;candidate_id?:string;requirement_id?:string;
  event_kind:string;summary:string;payload:Record<string,unknown>;
  reference_kind?:string;reference_id?:string;occurred_at:string;
};
export type CandidateExplanation = {
  candidate_id:string;display_name:string;why_proposed:string;
  why_requirements_passed:Array<Record<string,unknown>>;
  why_requirements_failed:Array<Record<string,unknown>>;
  why_blocked:string;why_experiment_recommended:string;why_ranked:string;
  gate_results:GateResult[];reason_codes:string[];
  methodology_version:string;llm_boundary_note:string;
};
