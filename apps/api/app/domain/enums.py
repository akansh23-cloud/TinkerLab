from enum import StrEnum


class MaterialFamily(StrEnum):
    POLYMER = "polymer"
    ALLOY = "alloy"
    COMPOSITE = "composite"
    CERAMIC = "ceramic"
    CRYSTALLINE_INORGANIC = "crystalline_inorganic"
    COATING = "coating"
    ADHESIVE = "adhesive"
    UNKNOWN = "unknown"


class EvidenceType(StrEnum):
    EXPERIMENTAL = "experimental"
    LITERATURE = "literature"
    SUPPLIER = "supplier"
    COMPUTATIONAL = "computational"
    PREDICTED = "predicted"
    USER_PROVIDED = "user_provided"
    SEED_DEMO = "seed_demo"


class ReplacementReason(StrEnum):
    COST = "cost"
    REGULATION = "regulation"
    SUPPLY_RISK = "supply_risk"
    SUSTAINABILITY = "sustainability"
    PERFORMANCE = "performance"
    WEIGHT = "weight"
    TOXICITY = "toxicity"
    AVAILABILITY = "availability"
    CUSTOM = "custom"


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class Comparator(StrEnum):
    LT = "<"
    LTE = "<="
    EQ = "="
    GTE = ">="
    GT = ">"
    BETWEEN = "between"
    BOOLEAN = "boolean"


class ConstraintKind(StrEnum):
    PROPERTY = "property"
    BOOLEAN = "boolean"


class ConstraintStrength(StrEnum):
    HARD = "hard"
    SOFT = "soft"


class ObjectiveDirection(StrEnum):
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"
    TARGET = "target"


class CandidateSource(StrEnum):
    MANUAL = "manual"
    SEED_DEMO = "seed_demo"
    RETRIEVED_FUTURE = "retrieved_future"
    GENERATED_FUTURE = "generated_future"


class CandidateStatus(StrEnum):
    PROPOSED = "proposed"
    REVIEWING = "reviewing"
    REJECTED = "rejected"
    ACCEPTED = "accepted"


class EvaluationStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"

class Visibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"


class EvidenceStatus(StrEnum):
    REPORTED = "reported"
    REVIEWED = "reviewed"
    SUPERSEDED = "superseded"
    RETRACTED = "retracted"


class ObservationStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    RETRACTED = "retracted"


class IdentityMatchClass(StrEnum):
    EXACT = "exact"
    PROBABLE = "probable"
    AMBIGUOUS = "ambiguous"
    NONE = "none"


class CompositionBasis(StrEnum):
    MASS_FRACTION = "mass_fraction"
    WEIGHT_PERCENT = "weight_percent"
    MOLE_FRACTION = "mole_fraction"
    ATOMIC_PERCENT = "atomic_percent"
    VOLUME_FRACTION = "volume_fraction"
    PARTS_BY_WEIGHT = "parts_by_weight"
    QUALITATIVE = "qualitative"


# Phase 6 — physics/simulation operating system.
# A simulation result is a third scientific origin: not evidence, not an ML prediction.
class ScientificOrigin(StrEnum):
    KNOWN_EVIDENCE = "known_evidence"
    MODEL_PREDICTION = "model_prediction"
    PHYSICS_SIMULATION = "physics_simulation"
    UNKNOWN = "unknown"


class RepresentationType(StrEnum):
    PERIODIC_ATOMIC_STRUCTURE = "periodic_atomic_structure"
    MOLECULAR_TOPOLOGY = "molecular_topology"
    COARSE_GRAINED_TOPOLOGY = "coarse_grained_topology"
    PHASE_DESCRIPTION = "phase_description"
    CONTINUUM_MODEL = "continuum_model"
    FORMULATION_ONLY = "formulation_only"
    SOFTWARE_VALIDATION_FIXTURE = "software_validation_fixture"


class RepresentationValidationStatus(StrEnum):
    VALID = "valid"
    INVALID_SYNTAX = "invalid_syntax"
    STRUCTURALLY_INVALID = "structurally_invalid"
    UNVALIDATED = "unvalidated"


class RepresentationCompleteness(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    REDACTED = "redacted"


class SimulationProviderType(StrEnum):
    SOFTWARE_FIXTURE = "software_fixture"
    LOCAL_EXECUTABLE = "local_executable"
    CONTAINER = "container"
    REMOTE_HPC_FUTURE = "remote_hpc_future"


class SimulationMethodFamily(StrEnum):
    ANALYTICAL_FIXTURE = "analytical_fixture"
    DFT = "dft"
    MD = "md"
    CALPHAD = "calphad"
    CONTINUUM_FUTURE = "continuum_future"
    ML_FORCE_FIELD_FUTURE = "ml_force_field_future"


class SimulationFidelity(StrEnum):
    """Descriptive label only. It is not a universal quality score and never orders routes alone."""
    SOFTWARE_FIXTURE = "software_fixture"
    EMPIRICAL_ATOMISTIC = "empirical_atomistic"
    ML_INTERATOMIC_FUTURE = "ml_interatomic_future"
    FIRST_PRINCIPLES = "first_principles"
    THERMODYNAMIC_PHASE_MODEL = "thermodynamic_phase_model"
    CONTINUUM_FUTURE = "continuum_future"


class ProviderLifecycleStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    DISABLED = "disabled"
    RETIRED = "retired"


class SimulationRouteStatus(StrEnum):
    READY = "ready"
    NOT_APPLICABLE = "not_applicable"
    INCOMPLETE_REPRESENTATION = "incomplete_representation"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    MISSING_REGISTERED_ARTIFACT = "missing_registered_artifact"
    UNSUPPORTED_PROPERTY = "unsupported_property"
    UNSUPPORTED_CONDITIONS = "unsupported_conditions"


class SimulationWorkflowStatus(StrEnum):
    PREPARED = "prepared"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SimulationJobStatus(StrEnum):
    """Operational only. Operational success is never scientific convergence."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class SimulationScientificStatus(StrEnum):
    CONVERGED = "converged"
    UNCONVERGED = "unconverged"
    PARTIAL = "partial"
    PARSER_FAILED = "parser_failed"
    NOT_APPLICABLE = "not_applicable"


class SimulationArtifactType(StrEnum):
    INPUT = "input"
    OUTPUT = "output"
    LOG = "log"
    TRAJECTORY = "trajectory"
    STRUCTURE = "structure"
    FORCE_FIELD = "force_field"
    PSEUDOPOTENTIAL = "pseudopotential"
    THERMODYNAMIC_DATABASE = "thermodynamic_database"
    MANIFEST = "manifest"


class SimulationValueSelectionPolicy(StrEnum):
    """Default behaviour is unchanged: simulations are shown, never silently preferred."""
    EVIDENCE_THEN_PREDICTION = "evidence_then_prediction_v1"
    EXPLICIT_SIMULATION_WORKFLOW = "explicit_simulation_workflow_v1"


# ---------------------------------------------------------------------------------------------
# Phase 7 — Industrial Viability Engine
# ---------------------------------------------------------------------------------------------
class IndustrialCategory(StrEnum):
    """Top-level dimensions of industrial evidence. Deliberately separate from scientific origin."""

    MANUFACTURING = "manufacturing"
    ECONOMIC = "economic"
    SUPPLY_CHAIN = "supply_chain"
    ENVIRONMENTAL = "environmental"
    REGULATORY = "regulatory"
    MATURITY = "maturity"


class IndustrialSourceType(StrEnum):
    """Where an industrial claim came from. An estimate is never recorded as a measurement."""

    PUBLISHED_DATASET = "published_dataset"
    GOVERNMENT_STATISTIC = "government_statistic"
    STANDARDS_BODY = "standards_body"
    PEER_REVIEWED = "peer_reviewed"
    INDUSTRY_REPORT = "industry_report"
    VENDOR_QUOTATION = "vendor_quotation"
    INTERNAL_MEASUREMENT = "internal_measurement"
    INTERNAL_ESTIMATE = "internal_estimate"
    EXPERT_JUDGEMENT = "expert_judgement"
    SEED_DEMONSTRATION = "seed_demonstration"


class IndustrialAssessmentState(StrEnum):
    """A dimension outcome. INSUFFICIENT_EVIDENCE and UNKNOWN are distinct and both are real answers."""

    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"
    UNKNOWN = "unknown"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"


class IndustrialConstraintKind(StrEnum):
    MAX_VALUE = "max_value"
    MIN_VALUE = "min_value"
    RANGE = "range"
    BANNED_ELEMENT = "banned_element"
    REQUIRED_PROCESS_COMPATIBILITY = "required_process_compatibility"
    ALLOWED_JURISDICTION = "allowed_jurisdiction"
    MINIMUM_MATURITY = "minimum_maturity"
    SUPPLIER_DIVERSITY = "supplier_diversity"


class IndustrialConstraintStrength(StrEnum):
    HARD = "hard"
    SOFT = "soft"
    PREFERENCE = "preference"


class ManufacturingProcessFamily(StrEnum):
    SYNTHESIS = "synthesis"
    DEPOSITION = "deposition"
    CASTING = "casting"
    FORMING = "forming"
    MACHINING = "machining"
    SINTERING = "sintering"
    HEAT_TREATMENT = "heat_treatment"
    COATING = "coating"
    JOINING = "joining"
    WAFER_PROCESSING = "wafer_processing"
    DOPING = "doping"
    ADDITIVE_MANUFACTURING = "additive_manufacturing"
    OTHER = "other"


class ProcessCompatibility(StrEnum):
    COMPATIBLE = "compatible"
    CONDITIONALLY_COMPATIBLE = "conditionally_compatible"
    INCOMPATIBLE = "incompatible"
    UNKNOWN = "unknown"


class MaturityStage(StrEnum):
    """Evidence-backed maturity. Deliberately NOT called TRL: TRL has a formal assessment procedure
    this system does not perform, and borrowing the label would overstate what the evidence supports."""

    THEORETICAL = "theoretical"
    COMPUTATIONALLY_EVALUATED = "computationally_evaluated"
    EXPERIMENTALLY_DEMONSTRATED = "experimentally_demonstrated"
    LABORATORY_REPRODUCIBLE = "laboratory_reproducible"
    PILOT_DEMONSTRATED = "pilot_demonstrated"
    MANUFACTURING_DEMONSTRATED = "manufacturing_demonstrated"
    INDUSTRIALLY_ESTABLISHED = "industrially_established"
    UNKNOWN = "unknown"


MATURITY_ORDER: tuple[str, ...] = (
    MaturityStage.THEORETICAL,
    MaturityStage.COMPUTATIONALLY_EVALUATED,
    MaturityStage.EXPERIMENTALLY_DEMONSTRATED,
    MaturityStage.LABORATORY_REPRODUCIBLE,
    MaturityStage.PILOT_DEMONSTRATED,
    MaturityStage.MANUFACTURING_DEMONSTRATED,
    MaturityStage.INDUSTRIALLY_ESTABLISHED,
)


class CostBasis(StrEnum):
    PER_KILOGRAM = "per_kilogram"
    PER_TONNE = "per_tonne"
    PER_LITRE = "per_litre"
    PER_WAFER = "per_wafer"
    PER_UNIT = "per_unit"
    PER_SQUARE_METRE = "per_square_metre"
    PER_BATCH = "per_batch"


# ---------------------------------------------------------------------------------------------
# Phase 8 — Material Functional Decomposition & Replacement Reasoning
# ---------------------------------------------------------------------------------------------
class ComponentRole(StrEnum):
    """What an element does in a composition. A dopant at 1e-6 is not an alloying element."""

    HOST = "host"
    ALLOYING = "alloying"
    DOPANT = "dopant"
    IMPURITY = "impurity"
    ADDITIVE = "additive"
    REINFORCEMENT = "reinforcement"
    MATRIX = "matrix"
    UNKNOWN = "unknown"


class ProcessingStepKind(StrEnum):
    ANNEALING = "annealing"
    QUENCHING = "quenching"
    TEMPERING = "tempering"
    COLD_WORKING = "cold_working"
    HOT_WORKING = "hot_working"
    DEPOSITION = "deposition"
    SINTERING = "sintering"
    EPITAXY = "epitaxy"
    IRRADIATION = "irradiation"
    DOPING = "doping"
    CURING = "curing"
    SOLUTION_TREATMENT = "solution_treatment"
    OTHER = "other"


class StateMatchQuality(StrEnum):
    """How well a property's recorded state matches the state being asked about.

    Properties do not propagate across incompatible states, so this is a first-class outcome rather
    than a similarity score used for silent substitution.
    """

    EXACT = "exact"
    COMPATIBLE = "compatible"
    CONDITIONALLY_COMPATIBLE = "conditionally_compatible"
    DIFFERENT_STATE = "different_state"
    UNKNOWN_STATE = "unknown_state"


class FunctionCategory(StrEnum):
    ELECTRONIC = "electronic"
    THERMAL = "thermal"
    MECHANICAL = "mechanical"
    OPTICAL = "optical"
    MAGNETIC = "magnetic"
    CHEMICAL = "chemical"
    ELECTROCHEMICAL = "electrochemical"
    BARRIER = "barrier"
    STRUCTURAL = "structural"
    PROCESSING = "processing"
    OTHER = "other"


class RequirementKind(StrEnum):
    HARD_CONSTRAINT = "hard_constraint"
    SOFT_CONSTRAINT = "soft_constraint"
    OBJECTIVE = "objective"
    PREFERENCE = "preference"
    INFORMATIONAL = "informational"


class RequirementDirection(StrEnum):
    MINIMUM = "minimum"
    MAXIMUM = "maximum"
    RANGE = "range"
    TARGET = "target"
    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"
    CATEGORICAL = "categorical"


class RequirementStatus(StrEnum):
    """The outcome of testing one requirement against one candidate state.

    UNKNOWN is not a soft failure and not a soft pass. It is the honest answer when no evidence of
    any origin addresses the requirement in a compatible state.
    """

    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"
    UNKNOWN = "unknown"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    STATE_MISMATCH = "state_mismatch"


class ReasoningNodeKind(StrEnum):
    MATERIAL_STATE = "material_state"
    STRUCTURAL_FEATURE = "structural_feature"
    MECHANISM = "mechanism"
    PROPERTY = "property"
    FUNCTION = "function"
    REQUIREMENT = "requirement"


class ReasoningEdgeKind(StrEnum):
    """Typed edges of the replacement reasoning graph.

    Every edge carries provenance, confidence, scope and conditions. A universal causal rule without
    evidence is never created.
    """

    STATE_EXHIBITS_FEATURE = "state_exhibits_feature"
    FEATURE_ENABLES_MECHANISM = "feature_enables_mechanism"
    MECHANISM_GOVERNS_PROPERTY = "mechanism_governs_property"
    PROPERTY_DELIVERS_FUNCTION = "property_delivers_function"
    FUNCTION_SATISFIES_REQUIREMENT = "function_satisfies_requirement"


class EvidenceOriginClass(StrEnum):
    """Where a value used in reasoning came from. Rendered distinctly and never merged."""

    OBSERVED = "observed"
    LITERATURE = "literature"
    PREDICTED = "predicted"
    SIMULATED = "simulated"
    EXPERIMENTAL = "experimental"
    INDUSTRIAL = "industrial"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------------------------
# Phase 9 — Experimental Design & Validation OS
# ---------------------------------------------------------------------------------------------
class SampleKind(StrEnum):
    SYNTHESIZED = "synthesized"
    PROCURED = "procured"
    SUBDIVIDED = "subdivided"
    REFERENCE_STANDARD = "reference_standard"
    CONTROL = "control"
    UNKNOWN = "unknown"


class InstrumentCalibrationStatus(StrEnum):
    """Calibration is never assumed. UNKNOWN is the default, not CALIBRATED."""

    CALIBRATED = "calibrated"
    OVERDUE = "overdue"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class ExperimentDesignKind(StrEnum):
    """Only designs that are actually implemented mathematically are offered.

    Response-surface methods, Bayesian optimization and active learning are deliberately absent:
    naming a design that is not implemented would misrepresent what the system can do.
    """

    SINGLE_RUN = "single_run"
    ONE_FACTOR = "one_factor"
    FULL_FACTORIAL = "full_factorial"
    PARAMETER_SWEEP = "parameter_sweep"


class ExperimentRunStatus(StrEnum):
    PLANNED = "planned"
    READY = "ready"
    RUNNING = "running"
    # Backward-compatible legacy status accepted for pre-9.1 records. New transitions use RUNNING.
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABORTED = "aborted"
    INVALIDATED = "invalidated"
    CANCELLED = "cancelled"


class MeasurementQuality(StrEnum):
    """Whether a measurement is admissible as experimental evidence, and why not when it is not."""

    ACCEPTED = "accepted"
    PROVISIONAL = "provisional"
    REJECTED = "rejected"
    INCOMPLETE_PROVENANCE = "incomplete_provenance"
    INVALIDATED_SOURCE = "invalidated_source"


class ValidationState(StrEnum):
    """How well supported a candidate is for a role.

    'Validated' is never used when only simulation exists — that is what SIMULATION_SUPPORTED means.
    """

    COMPUTATIONAL_ONLY = "computational_only"
    SIMULATION_SUPPORTED = "simulation_supported"
    EXPERIMENT_RECOMMENDED = "experiment_recommended"
    EXPERIMENT_PENDING = "experiment_pending"
    EXPERIMENT_IN_PROGRESS = "experiment_in_progress"
    PARTIALLY_VALIDATED = "partially_validated"
    EXPERIMENTALLY_SUPPORTED = "experimentally_supported"
    EXPERIMENTALLY_CONTRADICTED = "experimentally_contradicted"
    CONFLICTING_EXPERIMENTS = "conflicting_experiments"
    # Backward-compatible label retained for legacy persisted rows/UI. New decisions use
    # EXPERIMENTALLY_CONTRADICTED.
    CONTRADICTED = "contradicted"
    INCONCLUSIVE = "inconclusive"


class AgreementVerdict(StrEnum):
    """Comparison of values from different origins. Disagreement is exposed, never averaged."""

    AGREES_WITHIN_UNCERTAINTY = "agrees_within_uncertainty"
    DISAGREES = "disagrees"
    INCOMPARABLE = "incomparable"
    INSUFFICIENT_DATA = "insufficient_data"


class RecommendationPriorityFactor(StrEnum):
    REQUIREMENT_CRITICALITY = "requirement_criticality"
    EVIDENCE_GAP = "evidence_gap"
    UNCERTAINTY = "uncertainty"
    RANKING_SENSITIVITY = "ranking_sensitivity"
    EXPERIMENT_COST = "experiment_cost"
    EXPERIMENT_DURATION = "experiment_duration"
    DESTRUCTIVENESS = "destructiveness"


class LabIntegrationKind(StrEnum):
    """Boundaries for future integrations. Phase 9 implements none of them."""

    MANUAL_ENTRY = "manual_entry"
    LIMS = "lims"
    INSTRUMENT_API = "instrument_api"
    ROBOTIC_PLATFORM = "robotic_platform"
    CONTRACT_LABORATORY = "contract_laboratory"


# ---------------------------------------------------------------------------------------------
# Phase 10 — Closed-Loop Material Replacement Decision OS
#
# Phase 10 orchestrates the Phase 1–9.1 capabilities into one auditable replacement decision. It
# introduces no new evaluator: every PASS/FAIL/UNKNOWN below is produced by the canonical Phase-8/9.1
# services and merely classified here. Nothing in this module is decided by a language model.
# ---------------------------------------------------------------------------------------------
class ProgramState(StrEnum):
    """Deterministically resolved lifecycle state of a replacement program.

    Resolved from the program's own evidence, never set directly by a frontend action. PAUSED and
    ARCHIVED are the only operator-set states because they express intent rather than evidence.
    """

    DRAFT = "draft"
    REQUIREMENTS_DEFINED = "requirements_defined"
    CANDIDATES_GENERATED = "candidates_generated"
    SCREENING = "screening"
    VALIDATING = "validating"
    EXPERIMENTING = "experimenting"
    CONVERGING = "converging"
    DECISION_READY = "decision_ready"
    RECOMMENDED = "recommended"
    NO_SUITABLE_CANDIDATE = "no_suitable_candidate"
    PAUSED = "paused"
    ARCHIVED = "archived"


OPERATOR_SET_PROGRAM_STATES: frozenset[str] = frozenset({ProgramState.PAUSED, ProgramState.ARCHIVED})


class RequirementCriticality(StrEnum):
    """How a requirement participates in the decision.

    A hard gate and an optimization objective are different concepts and are never collapsed into a
    single weight: BLOCKING and CRITICAL gate advancement, IMPORTANT and DESIRABLE only rank.
    """

    BLOCKING = "blocking"
    CRITICAL = "critical"
    IMPORTANT = "important"
    DESIRABLE = "desirable"
    INFORMATIONAL = "informational"


# Requirements that can gate advancement. DESIRABLE/INFORMATIONAL never block a candidate.
GATING_CRITICALITIES: frozenset[str] = frozenset(
    {RequirementCriticality.BLOCKING, RequirementCriticality.CRITICAL}
)
# Requirements that contribute to ranking rather than eligibility.
RANKING_CRITICALITIES: frozenset[str] = frozenset(
    {RequirementCriticality.IMPORTANT, RequirementCriticality.DESIRABLE}
)


class RequirementOrigin(StrEnum):
    """Why a requirement exists. Provenance for requirements, not only for evidence."""

    USER_DEFINED = "user_defined"
    INCUMBENT_BASELINE = "incumbent_baseline"
    APPLICATION_TEMPLATE = "application_template"
    REGULATION = "regulation"
    MANUFACTURING_PROCESS = "manufacturing_process"
    CUSTOMER_SPECIFICATION = "customer_specification"
    INFERRED_AND_CONFIRMED = "inferred_and_confirmed"


class RequirementApprovalStatus(StrEnum):
    """An automatically proposed requirement is never scientifically authoritative until accepted."""

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class PortfolioCandidateState(StrEnum):
    """Portfolio lifecycle state. Derived from Phase-8/9.1 validation, never stored in parallel."""

    PROPOSED = "proposed"
    SCREENING = "screening"
    SCREENED_IN = "screened_in"
    SCREENED_OUT = "screened_out"
    COMPUTATION_PENDING = "computation_pending"
    COMPUTATION_SUPPORTED = "computation_supported"
    COMPUTATION_CONTRADICTED = "computation_contradicted"
    INDUSTRIAL_REVIEW = "industrial_review"
    EXPERIMENT_RECOMMENDED = "experiment_recommended"
    EXPERIMENT_PENDING = "experiment_pending"
    EXPERIMENT_IN_PROGRESS = "experiment_in_progress"
    PARTIALLY_VALIDATED = "partially_validated"
    EXPERIMENTALLY_SUPPORTED = "experimentally_supported"
    EXPERIMENTALLY_CONTRADICTED = "experimentally_contradicted"
    DECISION_READY = "decision_ready"
    ADVANCE = "advance"
    HOLD = "hold"
    REJECT = "reject"


class CandidateEligibility(StrEnum):
    """The three-way partition that precedes any ranking.

    Ranking never runs across this boundary: a blocked candidate cannot out-rank an eligible one by
    scoring well on optimization objectives.
    """

    ELIGIBLE = "eligible"
    UNRESOLVED = "unresolved"
    BLOCKED = "blocked"


class MatrixCellStatus(StrEnum):
    """The status of one requirement for one candidate in the decision matrix.

    UNKNOWN, INCONCLUSIVE and NOT_COMPARABLE are distinct honest answers, not shades of failure.
    """

    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"
    CONFLICTING = "conflicting"
    INCONCLUSIVE = "inconclusive"
    NOT_COMPARABLE = "not_comparable"


class EvidenceGapClass(StrEnum):
    BLOCKING_GAP = "blocking_gap"
    HIGH_VALUE_GAP = "high_value_gap"
    NORMAL_GAP = "normal_gap"
    OPTIONAL_GAP = "optional_gap"


class EvidenceGapKind(StrEnum):
    """What specifically is missing or wrong. Drives the next-action mapping deterministically."""

    MISSING_ALL_EVIDENCE = "missing_all_evidence"
    MISSING_COMPUTATIONAL_EVIDENCE = "missing_computational_evidence"
    MISSING_SIMULATION = "missing_simulation"
    MISSING_EXPERIMENT = "missing_experiment"
    INSUFFICIENT_REPLICATES = "insufficient_replicates"
    UNCERTAIN_EVIDENCE = "uncertain_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    OUTDATED_EVIDENCE = "outdated_evidence"
    STATE_MISMATCH = "state_mismatch"
    UNIT_NOT_COMPARABLE = "unit_not_comparable"
    MISSING_INDUSTRIAL_EVIDENCE = "missing_industrial_evidence"
    UNRESOLVED_REGULATORY_CONTEXT = "unresolved_regulatory_context"
    UNRESOLVED_SUPPLY_CONTEXT = "unresolved_supply_context"
    REQUIREMENT_NOT_TESTABLE = "requirement_not_testable"


class ScientificActionType(StrEnum):
    COLLECT_REFERENCE_DATA = "collect_reference_data"
    RUN_PROPERTY_PREDICTION = "run_property_prediction"
    RUN_PHYSICS_SIMULATION = "run_physics_simulation"
    RUN_ADDITIONAL_SIMULATION = "run_additional_simulation"
    RESOLVE_MATERIAL_STATE = "resolve_material_state"
    ADD_INDUSTRIAL_EVIDENCE = "add_industrial_evidence"
    CHECK_REGULATION = "check_regulation"
    CHECK_SUPPLY = "check_supply"
    CREATE_EXPERIMENT_PLAN = "create_experiment_plan"
    RUN_EXPERIMENT = "run_experiment"
    RUN_ADDITIONAL_REPLICATE = "run_additional_replicate"
    RUN_CONTROL = "run_control"
    INVESTIGATE_CONFLICT = "investigate_conflict"
    REJECT_CANDIDATE = "reject_candidate"
    ADVANCE_CANDIDATE = "advance_candidate"
    NO_ACTION_REQUIRED = "no_action_required"


class ScientificActionStatus(StrEnum):
    """Actions are superseded with provenance, never deleted when evidence changes."""

    PROPOSED = "proposed"
    READY = "ready"
    BLOCKED = "blocked"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"
    DEFERRED = "deferred"


OPEN_ACTION_STATUSES: frozenset[str] = frozenset({
    ScientificActionStatus.PROPOSED, ScientificActionStatus.READY,
    ScientificActionStatus.BLOCKED, ScientificActionStatus.RUNNING,
})


class DecisionValueClass(StrEnum):
    """A transparent decision-value class, deliberately NOT called Bayesian information gain.

    No EVSI/EVPI mathematics is implemented anywhere in Phase 10, so no probability is claimed.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class ActionCostClass(StrEnum):
    """Declared effort class. UNKNOWN is used whenever no cost metadata exists; it is never guessed."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class ConvergenceState(StrEnum):
    """How far the program is from a defensible decision. Never a probability of success."""

    EARLY = "early"
    SCREENING = "screening"
    EVIDENCE_BUILDING = "evidence_building"
    VALIDATION_REQUIRED = "validation_required"
    CONFLICT_RESOLUTION = "conflict_resolution"
    NEAR_DECISION = "near_decision"
    DECISION_READY = "decision_ready"
    NO_VIABLE_CANDIDATE = "no_viable_candidate"


class ReplacementRecommendationStatus(StrEnum):
    ADVANCE_CANDIDATE = "advance_candidate"
    ADVANCE_MULTIPLE_CANDIDATES = "advance_multiple_candidates"
    HOLD_FOR_EVIDENCE = "hold_for_evidence"
    REJECT_CANDIDATE = "reject_candidate"
    NO_SUITABLE_CANDIDATE = "no_suitable_candidate"
    INCONCLUSIVE = "inconclusive"


class ProgramEventKind(StrEnum):
    """Internal domain events. Handled synchronously in-process; no broker is introduced."""

    PROGRAM_CREATED = "program_created"
    REQUIREMENT_CHANGED = "requirement_changed"
    REQUIREMENT_APPROVED = "requirement_approved"
    CANDIDATE_ADDED = "candidate_added"
    CANDIDATE_REJECTED = "candidate_rejected"
    CANDIDATE_ADVANCED = "candidate_advanced"
    PREDICTION_CREATED = "prediction_created"
    SIMULATION_COMPLETED = "simulation_completed"
    INDUSTRIAL_EVIDENCE_ADDED = "industrial_evidence_added"
    MATERIAL_STATE_UPDATED = "material_state_updated"
    EXPERIMENT_RECOMMENDED = "experiment_recommended"
    EXPERIMENT_PLANNED = "experiment_planned"
    EXPERIMENT_STARTED = "experiment_started"
    MEASUREMENT_ACCEPTED = "measurement_accepted"
    MEASUREMENT_INVALIDATED = "measurement_invalidated"
    CONFLICT_DETECTED = "conflict_detected"
    ACTION_PROPOSED = "action_proposed"
    ACTION_ACCEPTED = "action_accepted"
    ACTION_DEFERRED = "action_deferred"
    ACTION_CANCELLED = "action_cancelled"
    ACTION_COMPLETED = "action_completed"
    CONVERGENCE_ASSESSED = "convergence_assessed"
    RECOMMENDATION_GENERATED = "recommendation_generated"
    DECISION_POLICY_CHANGED = "decision_policy_changed"
    SNAPSHOT_CREATED = "snapshot_created"
    DOSSIER_GENERATED = "dossier_generated"


class RankingObjectiveKey(StrEnum):
    """Ranking objectives. Every one is reported with its normalized value and its weight."""

    PERFORMANCE_MARGIN = "performance_margin"
    INDUSTRIAL_VIABILITY = "industrial_viability"
    COST = "cost"
    SUPPLY_SECURITY = "supply_security"
    MANUFACTURING_FIT = "manufacturing_fit"
    SUSTAINABILITY = "sustainability"
    EVIDENCE_CONFIDENCE = "evidence_confidence"


class RankingStability(StrEnum):
    STABLE_WINNER = "stable_winner"
    WEIGHT_SENSITIVE = "weight_sensitive"
    NEAR_EQUIVALENT_CANDIDATES = "near_equivalent_candidates"
    NOT_APPLICABLE = "not_applicable"
