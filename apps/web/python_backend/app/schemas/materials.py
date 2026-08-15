from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.domain.enums import CompositionBasis, EvidenceType, MaterialFamily, Visibility
from app.schemas.common import ORMModel


class SourceProviderOut(ORMModel):
    id: str
    key: str
    display_name: str
    provider_type: str
    reference_url: str | None
    licensing_notes: str | None
    license_identifier: str | None = None
    license_url: str | None = None
    commercial_use_permitted: bool | None = None
    redistribution_permitted: bool | None = None
    attribution_required: bool = True
    attribution_text: str | None = None
    license_reviewed_at: datetime | None = None
    license_reviewed_by: str | None = None
    enabled: bool
    adapter_version: str


class CitationOut(ORMModel):
    id: str
    title: str
    doi: str | None
    authors: list[dict[str, Any]]
    journal_or_source: str | None
    publication_year: int | None
    reference_url: str | None
    publisher: str | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")


class SourceRecordOut(ORMModel):
    id: str
    provider_id: str
    organisation_id: str | None
    visibility: str
    external_record_id: str
    retrieved_at: datetime
    imported_at: datetime
    source_version: str | None
    dataset_snapshot_id: str | None = None
    parser_version: str
    raw_checksum: str
    normalized_checksum: str
    status: str
    error_details: str | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")
    provider: SourceProviderOut | None = None


class EvidenceOut(ORMModel):
    id: str
    evidence_type: str
    title: str
    source_reference: str | None
    description: str | None
    method: str | None
    confidence: float | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")
    provider_id: str | None = None
    source_record_id: str | None = None
    citation_id: str | None = None
    computational_method_id: str | None = None
    dataset_snapshot_id: str | None = None
    applicability_warnings: list[dict[str, Any]] = Field(default_factory=list)
    organisation_id: str | None = None
    visibility: str = "public"
    status: str = "reported"
    curator_note: str | None = None
    source_quality: str | None = None
    created_at: datetime
    provider: SourceProviderOut | None = None
    source_record: SourceRecordOut | None = None
    citation: CitationOut | None = None


class EvidenceCreate(BaseModel):
    evidence_type: EvidenceType
    title: str = Field(min_length=2, max_length=300)
    source_reference: str | None = None
    description: str | None = None
    method: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    provider_id: str | None = None
    source_record_id: str | None = None
    citation_id: str | None = None
    organisation_id: str | None = None
    visibility: Visibility = Visibility.PUBLIC
    source_quality: str | None = None


class PropertyDefinitionOut(ORMModel):
    id: str
    key: str
    display_name: str
    quantity_type: str
    canonical_unit: str | None
    description: str | None
    applicable_material_families: list[str]
    allowed_comparators: list[str]
    allow_negative: bool
    conflict_policy: str = "informational"
    conflict_absolute_tolerance: float | None = None
    conflict_relative_tolerance: float | None = None


class ConditionSetCreate(BaseModel):
    temperature_value: float | None = None
    temperature_unit: str | None = None
    pressure_value: float | None = None
    pressure_unit: str | None = None
    humidity_percent: float | None = Field(default=None, ge=0, le=100)
    strain_rate: float | None = Field(default=None, ge=0)
    sample_orientation: str | None = Field(default=None, max_length=120)
    frequency_value: float | None = Field(default=None, ge=0)
    frequency_unit: str | None = None
    material_state: str | None = Field(default=None, max_length=160)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unit_pairs(self):
        for value, unit, label in [
            (self.temperature_value, self.temperature_unit, "temperature"),
            (self.pressure_value, self.pressure_unit, "pressure"),
            (self.frequency_value, self.frequency_unit, "frequency"),
        ]:
            if (value is None) != (unit is None):
                raise ValueError(f"{label} value and unit must be provided together")
        return self


class ConditionSetOut(ORMModel):
    id: str
    temperature_value: float | None
    temperature_unit: str | None
    pressure_value: float | None
    pressure_unit: str | None
    humidity_percent: float | None
    strain_rate: float | None
    sample_orientation: str | None
    frequency_value: float | None
    frequency_unit: str | None
    material_state: str | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")


class ObservationOut(ORMModel):
    id: str
    property_definition_id: str
    value_type: str
    numeric_value: float | None
    boolean_value: bool | None
    unit: str | None
    conditions: dict[str, Any]
    condition_set_id: str | None = None
    uncertainty: float | None
    uncertainty_type: str | None = None
    uncertainty_lower: float | None = None
    uncertainty_upper: float | None = None
    uncertainty_stddev: float | None = None
    confidence: float | None
    method: str | None = None
    status: str = "active"
    curator_preferred: bool = False
    curator_note: str | None = None
    source_record_id: str | None = None
    created_at: datetime
    property_definition: PropertyDefinitionOut
    evidence: EvidenceOut
    condition_set: ConditionSetOut | None = None


class MaterialIdentifierOut(ORMModel):
    id: str
    namespace: str
    value: str
    normalized_value: str
    is_primary: bool
    visibility: str
    evidence_id: str | None


class MaterialComponentOut(ORMModel):
    id: str
    component_name: str
    component_identifier: str | None
    component_role: str | None
    amount_value: float | None
    amount_lower: float | None
    amount_upper: float | None
    amount_unit: str | None
    amount_basis: str
    uncertainty: float | None
    evidence_id: str | None
    is_redacted: bool
    redaction_label: str | None
    sequence: int
    notes: str | None


class MaterialProcessStateOut(ORMModel):
    id: str
    state_label: str
    process_name: str | None
    sequence: int
    parameters: dict[str, Any]
    evidence_id: str | None
    notes: str | None


class MaterialCreate(BaseModel):
    canonical_name: str = Field(min_length=2, max_length=240, pattern=r"^[A-Za-z0-9._()\- ]+$")
    display_name: str = Field(min_length=2, max_length=240)
    material_family: MaterialFamily = MaterialFamily.UNKNOWN
    description: str | None = None
    composition_summary: str | None = None
    source_type: str = "user_provided"
    owner_organisation_id: str | None = None
    visibility: Visibility = Visibility.PUBLIC


class MaterialSummary(ORMModel):
    id: str
    canonical_name: str
    display_name: str
    material_family: str
    description: str | None
    source_type: str
    is_seed_data: bool
    visibility: str = "public"
    owner_organisation_id: str | None = None


class MaterialDetail(MaterialSummary):
    composition_summary: str | None
    created_at: datetime
    updated_at: datetime
    observations: list[ObservationOut]
    identifiers: list[MaterialIdentifierOut] = []
    components: list[MaterialComponentOut] = []
    process_states: list[MaterialProcessStateOut] = []


class ObservationCreate(BaseModel):
    property_key: str
    value_type: Literal["numeric", "boolean"] = "numeric"
    numeric_value: float | None = None
    boolean_value: bool | None = None
    unit: str | None = None
    evidence_id: str
    conditions: dict[str, Any] = Field(default_factory=dict)
    condition_set: ConditionSetCreate | None = None
    uncertainty: float | None = Field(default=None, ge=0)
    uncertainty_type: str | None = None
    uncertainty_lower: float | None = None
    uncertainty_upper: float | None = None
    uncertainty_stddev: float | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    method: str | None = None
    source_record_id: str | None = None

    @model_validator(mode="after")
    def validate_value_shape(self):
        if self.value_type == "numeric":
            if self.numeric_value is None or self.unit is None:
                raise ValueError("numeric observation requires numeric_value and unit")
            if self.boolean_value is not None:
                raise ValueError("numeric observation cannot contain boolean_value")
        else:
            if self.boolean_value is None:
                raise ValueError("boolean observation requires boolean_value")
            if self.numeric_value is not None or self.unit is not None:
                raise ValueError("boolean observation cannot contain numeric_value or unit")
            if any(x is not None for x in [self.uncertainty, self.uncertainty_lower, self.uncertainty_upper, self.uncertainty_stddev]):
                raise ValueError("boolean observation cannot use numeric uncertainty")
        return self


class MaterialIdentifierCreate(BaseModel):
    namespace: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=300)
    is_primary: bool = False
    evidence_id: str | None = None
    organisation_id: str | None = None
    visibility: Visibility = Visibility.PUBLIC


class MaterialComponentCreate(BaseModel):
    component_name: str = Field(min_length=1, max_length=300)
    component_identifier: str | None = None
    component_role: str | None = None
    amount_value: float | None = None
    amount_lower: float | None = None
    amount_upper: float | None = None
    amount_unit: str | None = None
    amount_basis: CompositionBasis = CompositionBasis.QUALITATIVE
    uncertainty: float | None = Field(default=None, ge=0)
    evidence_id: str | None = None
    is_redacted: bool = False
    redaction_label: str | None = None
    sequence: int = 0
    notes: str | None = None

    @model_validator(mode="after")
    def validate_amount(self):
        if self.is_redacted:
            if not self.redaction_label:
                raise ValueError("redacted component requires redaction_label")
            return self
        if self.amount_basis != CompositionBasis.QUALITATIVE:
            if self.amount_value is None and self.amount_lower is None:
                raise ValueError("quantitative component requires amount_value or amount range")
            if self.amount_lower is not None and self.amount_upper is None:
                raise ValueError("amount_lower requires amount_upper")
            if self.amount_upper is not None and self.amount_lower is None:
                raise ValueError("amount_upper requires amount_lower")
            if self.amount_lower is not None and self.amount_upper is not None and self.amount_upper < self.amount_lower:
                raise ValueError("amount_upper must be >= amount_lower")
        return self


class MaterialProcessStateCreate(BaseModel):
    state_label: str = Field(min_length=1, max_length=160)
    process_name: str | None = Field(default=None, max_length=160)
    sequence: int = 0
    parameters: dict[str, Any] = Field(default_factory=dict)
    evidence_id: str | None = None
    notes: str | None = None


class IdentityResolveRequest(BaseModel):
    canonical_name: str | None = None
    material_family: str | None = None
    identifiers: list[dict[str, str]] = Field(default_factory=list)
    composition: list[dict[str, Any]] = Field(default_factory=list)
    organisation_id: str | None = None


class IdentityCandidate(BaseModel):
    material_id: str
    material_name: str
    match_class: str
    reasons: list[str]


class IdentityResolveResponse(BaseModel):
    match_class: str
    selected_material_id: str | None
    reasons: list[str]
    candidates: list[IdentityCandidate]


class SelectionPreviewRequest(BaseModel):
    material_id: str
    context: ConditionSetCreate | None = None
    allowed_evidence_types: list[str] | None = None


class SelectionObservation(BaseModel):
    observation_id: str
    numeric_value: float | None = None
    boolean_value: bool | None = None
    unit: str | None = None
    canonical_value: float | None = None
    canonical_unit: str | None = None
    applicability: str
    evidence_type: str
    evidence_title: str
    status: str
    curator_preferred: bool


class SelectionPreviewResponse(BaseModel):
    property_key: str
    selected: SelectionObservation | None
    rationale: list[str]
    alternatives: list[SelectionObservation]
    excluded: list[dict[str, Any]]
    conflict: bool
    unknown_reason: str | None = None
