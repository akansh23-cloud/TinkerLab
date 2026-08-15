import { api, API } from "@/lib/api";

/**
 * Phase 12 — client contracts for the intake bench.
 *
 * The organisation scope is deliberately re-exported here. Every Phase-3+ endpoint (search spaces,
 * generation runs, virtual campaigns) is organisation-scoped server-side and returns 404 without
 * the X-Organisation-ID header. On a deployment where NEXT_PUBLIC_ORGANISATION_ID is unset that
 * looks exactly like the labs being broken, so the UI checks for it explicitly and says so.
 */
export const ORGANISATION_ID = process.env.NEXT_PUBLIC_ORGANISATION_ID ?? "";
export const ORGANISATION_CONFIGURED = ORGANISATION_ID.trim().length > 0;
export const API_BASE = API;

export type PropertySpec = {
  key: string;
  display_name: string;
  domain: string;
  quantity_type: string;
  canonical_unit: string | null;
  accepted_units: string[];
  direction: "higher_is_better" | "lower_is_better" | "target_band" | "neutral";
  why_it_matters: string;
  test_standard: string | null;
  datasheet_aliases: string[];
  typical_range: Record<string, number[]>;
  allow_negative: boolean;
  condition_sensitive: boolean;
};

export type CatalogueDomain = {
  key: string;
  display_name: string;
  description: string;
  properties: PropertySpec[];
};

export type PropertyCatalogue = { domains: CatalogueDomain[]; property_count: number };

export type DataGrade = {
  key: string;
  display_name: string;
  description: string;
  evidence_type: string;
  source_quality: string;
  confidence: number;
  requires_reference: boolean;
};

export type RequirementTemplate = {
  property_key: string;
  comparator: string;
  target_value: number | null;
  target_value_upper: number | null;
  target_boolean: boolean | null;
  target_unit: string | null;
  hard_or_soft: string;
  weight: number;
  severity: number;
  rationale: string;
};

export type ObjectiveTemplate = {
  property_key: string;
  direction: string;
  weight: number;
  priority: number;
  rationale: string;
};

export type ApplicationPreset = {
  key: string;
  display_name: string;
  sector: string;
  summary: string;
  expected_family: string;
  typical_drivers: string[];
  requirements: RequirementTemplate[];
  objectives: ObjectiveTemplate[];
  assumptions: string[];
  watch_outs: string[];
};

export type ReplacementDriver = { key: string; display_name: string; description: string };

export type MaterialIndexEntry = {
  id: string;
  display_name: string;
  material_family: string;
  description?: string;
  is_seed_data: boolean;
  observation_count: number;
  source_type: string;
};

export type IntakeWarning = {
  code: string;
  property_key: string;
  value: number;
  typical_min: number;
  typical_max: number;
  message: string;
  severity: string;
};

export type IntakeResponse = {
  material_id: string;
  display_name: string;
  canonical_name: string;
  material_family: string;
  observation_count: number;
  evidence_id: string;
  data_grade: string;
  warnings: IntakeWarning[];
};

export type ReadinessFix = {
  kind: "navigate" | "api";
  label: string;
  href?: string;
  endpoint?: string;
  method?: string;
  because?: string;
  lab?: string;
};

export type ReadinessCheck = {
  code: string;
  label: string;
  status: "ok" | "blocked" | "warning";
  detail: string;
  fix: ReadinessFix | null;
  evidence: Record<string, unknown>;
};

export type LabReadiness = {
  key: string;
  display_name: string;
  purpose: string;
  href: string;
  status: "ok" | "blocked" | "warning";
  checks: ReadinessCheck[];
};

export type ProjectReadiness = {
  project_id: string;
  project_name: string;
  found: boolean;
  labs: LabReadiness[];
  next_action: ReadinessFix | null;
  summary: { blocked: number; warnings: number; ready_labs: number; total_labs: number };
};

export type PlatformReadiness = {
  checks: ReadinessCheck[];
  material_count: number;
  project_count: number;
  approved_model_count: number;
  status: "ok" | "blocked" | "warning";
};

export type DerivedRequirement = RequirementTemplate & { origin: string };
export type DerivedRequirementSet = {
  requirements: DerivedRequirement[];
  skipped: { property_key: string; reason: string }[];
  baseline_property_count: number;
};

export type StudyResult = {
  project_id: string;
  project_name: string;
  requirement_count: number;
  objective_count: number;
  search_space_created: boolean;
  search_space_activated: boolean;
  preset: ApplicationPreset | null;
  notes: string[];
  skipped_requirements: { property_key: string; reason: string }[];
  rejected_requirements: { property_key: string; reason: string }[];
};

export type DerivationBlocker = { code: string; message: string; fix: string };
export type DerivationPreview = {
  derivable: boolean;
  blockers: DerivationBlocker[];
  notes?: string[];
  baseline_material?: { id: string; display_name: string; material_family: string; component_count?: number };
  estimated_cardinality: number;
  component_rules: { component_key: string; display_name: string; mutable: boolean; locked: boolean;
    min_amount: number | null; max_amount: number | null; step_amount: number | null; amount_unit: string | null }[];
};

/** Fires a readiness fix of kind "api". Returns nothing useful; the caller refetches. */
export async function runFix(fix: ReadinessFix): Promise<void> {
  if (fix.kind !== "api" || !fix.endpoint) return;
  await api(fix.endpoint, { method: fix.method ?? "POST" });
}

export const FAMILY_OPTIONS = [
  "polymer", "alloy", "composite", "ceramic", "coating", "adhesive", "crystalline_inorganic", "unknown",
] as const;

export const COMPONENT_ROLES = [
  "matrix", "reinforcement", "filler", "additive", "alloying", "host", "dopant", "impurity", "unknown",
] as const;

export function directionLabel(direction: PropertySpec["direction"]): string {
  if (direction === "higher_is_better") return "Higher is better";
  if (direction === "lower_is_better") return "Lower is better";
  if (direction === "target_band") return "Target band";
  return "Depends on application";
}
