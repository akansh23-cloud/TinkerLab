import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")


def uuid_str() -> str:
    return str(uuid.uuid4())


def now_utc() -> datetime:
    return datetime.now(UTC)


class Organisation(Base):
    __tablename__ = "organisations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class Material(Base):
    __tablename__ = "materials"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    canonical_name: Mapped[str] = mapped_column(String(240), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    material_family: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    composition_summary: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(60), default="user_provided")
    is_seed_data: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    owner_organisation_id: Mapped[str | None] = mapped_column(ForeignKey("organisations.id"), nullable=True, index=True)
    visibility: Mapped[str] = mapped_column(String(20), default="public", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    observations: Mapped[list["MaterialPropertyObservation"]] = relationship(back_populates="material", cascade="all, delete-orphan")
    identifiers: Mapped[list["MaterialIdentifier"]] = relationship(back_populates="material", cascade="all, delete-orphan")
    components: Mapped[list["MaterialComponent"]] = relationship(back_populates="material", cascade="all, delete-orphan")
    process_states: Mapped[list["MaterialProcessState"]] = relationship(back_populates="material", cascade="all, delete-orphan")



class MaterialIdentifier(Base):
    __tablename__ = "material_identifiers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    material_id: Mapped[str] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"), index=True)
    namespace: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(300), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence_id: Mapped[str | None] = mapped_column(ForeignKey("evidence.id"), nullable=True)
    organisation_id: Mapped[str | None] = mapped_column(ForeignKey("organisations.id"), nullable=True, index=True)
    visibility: Mapped[str] = mapped_column(String(20), default="public")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    material: Mapped[Material] = relationship(back_populates="identifiers")
    evidence: Mapped["Evidence | None"] = relationship(foreign_keys=[evidence_id])
    __table_args__ = (
        UniqueConstraint("namespace", "normalized_value", "organisation_id", name="uq_identifier_namespace_scope"),
        Index("ix_identifier_namespace_value", "namespace", "normalized_value"),
        Index("uq_public_identifier_namespace_value", "namespace", "normalized_value", unique=True,
              postgresql_where=(organisation_id.is_(None)), sqlite_where=(organisation_id.is_(None))),
    )


class MaterialPropertyDefinition(Base):
    __tablename__ = "material_property_definitions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(180), nullable=False)
    quantity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    canonical_unit: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    applicable_material_families: Mapped[list[str]] = mapped_column(JSONType, default=list)
    allowed_comparators: Mapped[list[str]] = mapped_column(JSONType, default=list)
    allow_negative: Mapped[bool] = mapped_column(Boolean, default=False)
    conflict_policy: Mapped[str] = mapped_column(String(40), default="informational")
    conflict_absolute_tolerance: Mapped[float | None] = mapped_column(Float)
    conflict_relative_tolerance: Mapped[float | None] = mapped_column(Float)


class SourceProvider(Base):
    __tablename__ = "source_providers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(240), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(60), nullable=False)
    reference_url: Mapped[str | None] = mapped_column(Text)
    licensing_notes: Mapped[str | None] = mapped_column(Text)
    # Licence terms, recorded structurally rather than as prose, so the dossier exporter can
    # actually enforce them. A product that sells defensibility must not ship a customer a report
    # that quietly embeds data it had no right to redistribute.
    license_identifier: Mapped[str | None] = mapped_column(String(80), index=True)
    license_url: Mapped[str | None] = mapped_column(Text)
    commercial_use_permitted: Mapped[bool | None] = mapped_column(Boolean, index=True)
    redistribution_permitted: Mapped[bool | None] = mapped_column(Boolean)
    attribution_required: Mapped[bool] = mapped_column(Boolean, default=True)
    attribution_text: Mapped[str | None] = mapped_column(Text)
    license_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    license_reviewed_by: Mapped[str | None] = mapped_column(String(160))
    rate_limit_per_second: Mapped[float | None] = mapped_column(Float)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    adapter_version: Mapped[str] = mapped_column(String(80), default="1.0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class DatasetSnapshot(Base):
    """A pinned view of an external dataset at a moment in time.

    Phase 10 guarantees that the same evidence produces the same conclusion, verified by checksum.
    External data breaks that guarantee the moment a provider updates its database — the same query
    silently returns different values and a "deterministic" dossier becomes irreproducible.

    A snapshot closes that hole by binding the exact returned record content, query and connector
    contract to a checksum. When a provider exposes a genuine immutable dataset release it is also
    recorded; when it does not, the snapshot is explicitly marked non-reproducible rather than
    pretending an API/software version is a database release.
    """

    __tablename__ = "dataset_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    provider_id: Mapped[str] = mapped_column(ForeignKey("source_providers.id"), index=True)
    organisation_id: Mapped[str | None] = mapped_column(ForeignKey("organisations.id"), nullable=True, index=True)
    dataset_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    provider_version: Mapped[str | None] = mapped_column(String(160), index=True)
    query_descriptor: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    connector_version: Mapped[str] = mapped_column(String(80), nullable=False)
    content_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    is_reproducible: Mapped[bool] = mapped_column(Boolean, default=True)
    reproducibility_note: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    provider: Mapped["SourceProvider"] = relationship()
    __table_args__ = (
        Index("ix_dataset_snapshot_scope", "provider_id", "dataset_key", "retrieved_at"),
    )


class ComputationalMethod(Base):
    """How a computed value was produced, and what that method is known to get wrong.

    A DFT band gap is not a measurement. PBE underestimates band gaps by roughly 40-50%, and a
    platform that ingests a PBE gap as though it were experimental will confidently pass a candidate
    that a real device would fail. Recording the method — and its documented systematic bias —
    lets the evaluator warn instead of silently believing the number.
    """

    __tablename__ = "computational_methods"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(240), nullable=False)
    method_family: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    functional: Mapped[str | None] = mapped_column(String(80), index=True)
    basis_or_code: Mapped[str | None] = mapped_column(String(160))
    # Conditions the method actually represents. Static-lattice DFT is 0 K, not room temperature.
    nominal_temperature_k: Mapped[float | None] = mapped_column(Float)
    includes_thermal_expansion: Mapped[bool] = mapped_column(Boolean, default=False)
    includes_zero_point_energy: Mapped[bool] = mapped_column(Boolean, default=False)
    # Documented systematic bias, per property key, as a directional statement plus a rough factor.
    known_property_bias: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    applicability_note: Mapped[str | None] = mapped_column(Text)
    reference_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Citation(Base):
    __tablename__ = "citations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    doi: Mapped[str | None] = mapped_column(String(200), unique=True, nullable=True, index=True)
    authors: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    journal_or_source: Mapped[str | None] = mapped_column(String(300))
    publication_year: Mapped[int | None] = mapped_column(Integer)
    publication_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reference_url: Mapped[str | None] = mapped_column(Text)
    publisher: Mapped[str | None] = mapped_column(String(300))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SourceRecord(Base):
    __tablename__ = "source_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    provider_id: Mapped[str] = mapped_column(ForeignKey("source_providers.id"), index=True)
    organisation_id: Mapped[str | None] = mapped_column(ForeignKey("organisations.id"), nullable=True, index=True)
    visibility: Mapped[str] = mapped_column(String(20), default="private", index=True)
    external_record_id: Mapped[str] = mapped_column(String(300), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    source_version: Mapped[str | None] = mapped_column(String(120))
    dataset_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("dataset_snapshots.id", ondelete="SET NULL"), nullable=True, index=True)
    parser_version: Mapped[str] = mapped_column(String(80), nullable=False)
    raw_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    normalized_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    status: Mapped[str] = mapped_column(String(40), default="normalized", index=True)
    error_details: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    provider: Mapped[SourceProvider] = relationship()
    __table_args__ = (
        UniqueConstraint("provider_id", "external_record_id", "organisation_id", "raw_checksum", name="uq_source_record_snapshot"),
        Index("ix_source_record_provider_external", "provider_id", "external_record_id"),
    )


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    evidence_type: Mapped[str] = mapped_column(String(60), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    provider_id: Mapped[str | None] = mapped_column(ForeignKey("source_providers.id"), nullable=True, index=True)
    source_record_id: Mapped[str | None] = mapped_column(ForeignKey("source_records.id"), nullable=True, index=True)
    citation_id: Mapped[str | None] = mapped_column(ForeignKey("citations.id"), nullable=True)
    parent_evidence_id: Mapped[str | None] = mapped_column(ForeignKey("evidence.id"), nullable=True)
    organisation_id: Mapped[str | None] = mapped_column(ForeignKey("organisations.id"), nullable=True, index=True)
    visibility: Mapped[str] = mapped_column(String(20), default="public", index=True)
    status: Mapped[str] = mapped_column(String(40), default="reported", index=True)
    evidence_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    curator_note: Mapped[str | None] = mapped_column(Text)
    source_quality: Mapped[str | None] = mapped_column(String(40))
    computational_method_id: Mapped[str | None] = mapped_column(ForeignKey("computational_methods.id", ondelete="SET NULL"), nullable=True, index=True)
    dataset_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("dataset_snapshots.id", ondelete="SET NULL"), nullable=True, index=True)
    applicability_warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    provider: Mapped[SourceProvider | None] = relationship(foreign_keys=[provider_id])
    source_record: Mapped[SourceRecord | None] = relationship(foreign_keys=[source_record_id])
    citation: Mapped[Citation | None] = relationship()


class MaterialComponent(Base):
    __tablename__ = "material_components"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    material_id: Mapped[str] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"), index=True)
    component_name: Mapped[str] = mapped_column(String(300), nullable=False)
    component_identifier: Mapped[str | None] = mapped_column(String(300))
    component_role: Mapped[str | None] = mapped_column(String(120))
    amount_value: Mapped[float | None] = mapped_column(Float)
    amount_lower: Mapped[float | None] = mapped_column(Float)
    amount_upper: Mapped[float | None] = mapped_column(Float)
    amount_unit: Mapped[str | None] = mapped_column(String(80))
    amount_basis: Mapped[str] = mapped_column(String(60), default="qualitative")
    uncertainty: Mapped[float | None] = mapped_column(Float)
    evidence_id: Mapped[str | None] = mapped_column(ForeignKey("evidence.id"), nullable=True)
    is_redacted: Mapped[bool] = mapped_column(Boolean, default=False)
    redaction_label: Mapped[str | None] = mapped_column(String(200))
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    material: Mapped[Material] = relationship(back_populates="components")
    evidence: Mapped[Evidence | None] = relationship()


class MaterialProcessState(Base):
    __tablename__ = "material_process_states"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    material_id: Mapped[str] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"), index=True)
    state_label: Mapped[str] = mapped_column(String(160), nullable=False)
    process_name: Mapped[str | None] = mapped_column(String(160))
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    evidence_id: Mapped[str | None] = mapped_column(ForeignKey("evidence.id"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    material: Mapped[Material] = relationship(back_populates="process_states")
    evidence: Mapped[Evidence | None] = relationship()


class ObservationConditionSet(Base):
    __tablename__ = "observation_condition_sets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    temperature_value: Mapped[float | None] = mapped_column(Float)
    temperature_unit: Mapped[str | None] = mapped_column(String(40))
    pressure_value: Mapped[float | None] = mapped_column(Float)
    pressure_unit: Mapped[str | None] = mapped_column(String(40))
    humidity_percent: Mapped[float | None] = mapped_column(Float)
    strain_rate: Mapped[float | None] = mapped_column(Float)
    sample_orientation: Mapped[str | None] = mapped_column(String(120))
    frequency_value: Mapped[float | None] = mapped_column(Float)
    frequency_unit: Mapped[str | None] = mapped_column(String(40))
    material_state: Mapped[str | None] = mapped_column(String(160))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class MaterialPropertyObservation(Base):
    __tablename__ = "material_property_observations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    material_id: Mapped[str] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"), index=True)
    property_definition_id: Mapped[str] = mapped_column(ForeignKey("material_property_definitions.id"), index=True)
    value_type: Mapped[str] = mapped_column(String(20), default="numeric")
    numeric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    boolean_value: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(80), nullable=True)
    conditions: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    condition_set_id: Mapped[str | None] = mapped_column(ForeignKey("observation_condition_sets.id"), nullable=True, index=True)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence.id"), index=True)
    source_record_id: Mapped[str | None] = mapped_column(ForeignKey("source_records.id"), nullable=True, index=True)
    method: Mapped[str | None] = mapped_column(Text)
    uncertainty: Mapped[float | None] = mapped_column(Float)
    uncertainty_type: Mapped[str | None] = mapped_column(String(40))
    uncertainty_lower: Mapped[float | None] = mapped_column(Float)
    uncertainty_upper: Mapped[float | None] = mapped_column(Float)
    uncertainty_stddev: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    curator_preferred: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    curator_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    material: Mapped[Material] = relationship(back_populates="observations")
    property_definition: Mapped[MaterialPropertyDefinition] = relationship()
    evidence: Mapped[Evidence] = relationship()
    source_record: Mapped[SourceRecord | None] = relationship()
    condition_set: Mapped[ObservationConditionSet | None] = relationship()
    __table_args__ = (
        Index("ix_observation_material_property_status", "material_id", "property_definition_id", "status"),
    )


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("source_providers.id"), index=True)
    input_format: Mapped[str] = mapped_column(String(20), nullable=False)
    payload_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="previewed", index=True)
    summary_json: Mapped[dict[str, Any]] = mapped_column("summary", JSONType, default=dict)
    error_json: Mapped[list[dict[str, Any]]] = mapped_column("errors", JSONType, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("organisation_id", "payload_checksum", "status", name="uq_import_scope_payload_status"),
    )


class ReplacementProject(Base):
    __tablename__ = "replacement_projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    baseline_material_id: Mapped[str] = mapped_column(ForeignKey("materials.id"), index=True)
    replacement_reasons: Mapped[list[str]] = mapped_column(JSONType, default=list)
    status: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    baseline_material: Mapped[Material] = relationship()
    constraints: Mapped[list["Constraint"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    objectives: Mapped[list["Objective"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    # Backward-compatible Phase-1/2 relationship: canonical known-material candidates only.
    # Phase-3 hypothesis candidates are queried through Candidate Lab/all_candidates so legacy scientific workflows do not silently change cardinality.
    candidates: Mapped[list["Candidate"]] = relationship(
        primaryjoin="and_(ReplacementProject.id==Candidate.project_id, Candidate.candidate_kind=='known_material')",
        cascade="all, delete-orphan", overlaps="all_candidates,project",
    )
    all_candidates: Mapped[list["Candidate"]] = relationship(
        primaryjoin="ReplacementProject.id==Candidate.project_id", viewonly=True, overlaps="candidates,project"
    )


class Constraint(Base):
    __tablename__ = "constraints"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    project_id: Mapped[str] = mapped_column(ForeignKey("replacement_projects.id", ondelete="CASCADE"), index=True)
    constraint_type: Mapped[str] = mapped_column(String(40), default="property")
    property_key: Mapped[str] = mapped_column(String(120), index=True)
    comparator: Mapped[str] = mapped_column(String(30), nullable=False)
    target_value: Mapped[float | None] = mapped_column(Float)
    target_value_upper: Mapped[float | None] = mapped_column(Float)
    target_boolean: Mapped[bool | None] = mapped_column(Boolean)
    target_unit: Mapped[str | None] = mapped_column(String(80))
    severity: Mapped[int] = mapped_column(Integer, default=1)
    hard_or_soft: Mapped[str] = mapped_column(String(20), default="hard")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    description: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    project: Mapped[ReplacementProject] = relationship(back_populates="constraints")


class Objective(Base):
    __tablename__ = "objectives"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    project_id: Mapped[str] = mapped_column(ForeignKey("replacement_projects.id", ondelete="CASCADE"), index=True)
    property_key: Mapped[str] = mapped_column(String(120), index=True)
    direction: Mapped[str] = mapped_column(String(30), nullable=False)
    target_value: Mapped[float | None] = mapped_column(Float)
    target_unit: Mapped[str | None] = mapped_column(String(80))
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    priority: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str | None] = mapped_column(Text)
    project: Mapped[ReplacementProject] = relationship(back_populates="objectives")


class Candidate(Base):
    __tablename__ = "candidates"
    __table_args__ = (
        CheckConstraint(
            "(candidate_kind = 'known_material' AND material_id IS NOT NULL AND hypothesis_id IS NULL) OR "
            "(candidate_kind = 'hypothesis' AND material_id IS NULL AND hypothesis_id IS NOT NULL)",
            name="ck_candidate_exactly_one_target",
        ),
        UniqueConstraint("project_id", "material_id", name="uq_project_candidate_material"),
        UniqueConstraint("project_id", "hypothesis_id", name="uq_project_candidate_hypothesis"),
        Index("ix_candidate_project_kind_status", "project_id", "candidate_kind", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    project_id: Mapped[str] = mapped_column(ForeignKey("replacement_projects.id", ondelete="CASCADE"), index=True)
    candidate_kind: Mapped[str] = mapped_column(String(30), default="known_material", index=True)
    material_id: Mapped[str | None] = mapped_column(ForeignKey("materials.id"), nullable=True, index=True)
    hypothesis_id: Mapped[str | None] = mapped_column(ForeignKey("candidate_hypotheses.id", ondelete="CASCADE"), nullable=True, index=True)
    candidate_source: Mapped[str] = mapped_column(String(40), default="manual")
    status: Mapped[str] = mapped_column(String(40), default="proposed")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    project: Mapped[ReplacementProject] = relationship(overlaps="candidates,all_candidates")
    material: Mapped[Material | None] = relationship()
    hypothesis: Mapped["CandidateHypothesis | None"] = relationship(foreign_keys=[hypothesis_id])


class CandidateSearchSpace(Base):
    __tablename__ = "candidate_search_spaces"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_search_space_project_version"),
        Index("ix_search_space_project_active", "project_id", "active"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    project_id: Mapped[str] = mapped_column(ForeignKey("replacement_projects.id", ondelete="CASCADE"), index=True)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    material_family: Mapped[str] = mapped_column(String(60), nullable=False)
    amount_basis: Mapped[str] = mapped_column(String(60), default="weight_percent")
    balance_component_key: Mapped[str | None] = mapped_column(String(300))
    total_target: Mapped[float | None] = mapped_column(Float)
    total_tolerance: Mapped[float] = mapped_column(Float, default=0.001)
    max_component_count: Mapped[int] = mapped_column(Integer, default=20)
    candidate_budget: Mapped[int] = mapped_column(Integer, default=100)
    maximum_enumeration: Mapped[int] = mapped_column(Integer, default=10000)
    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    component_rules: Mapped[list["SearchSpaceComponentRule"]] = relationship(back_populates="search_space", cascade="all, delete-orphan")
    process_rules: Mapped[list["SearchSpaceProcessRule"]] = relationship(back_populates="search_space", cascade="all, delete-orphan")


class SearchSpaceComponentRule(Base):
    __tablename__ = "search_space_component_rules"
    __table_args__ = (UniqueConstraint("search_space_id", "component_key", name="uq_search_space_component_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    search_space_id: Mapped[str] = mapped_column(ForeignKey("candidate_search_spaces.id", ondelete="CASCADE"), index=True)
    baseline_component_id: Mapped[str | None] = mapped_column(ForeignKey("material_components.id"), nullable=True)
    component_key: Mapped[str] = mapped_column(String(300), nullable=False)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    role: Mapped[str | None] = mapped_column(String(120))
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    mutable: Mapped[bool] = mapped_column(Boolean, default=False)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    prohibited: Mapped[bool] = mapped_column(Boolean, default=False)
    min_amount: Mapped[float | None] = mapped_column(Float)
    max_amount: Mapped[float | None] = mapped_column(Float)
    step_amount: Mapped[float | None] = mapped_column(Float)
    amount_unit: Mapped[str | None] = mapped_column(String(80))
    amount_basis: Mapped[str | None] = mapped_column(String(60))
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    search_space: Mapped[CandidateSearchSpace] = relationship(back_populates="component_rules")


class SearchSpaceProcessRule(Base):
    __tablename__ = "search_space_process_rules"
    __table_args__ = (UniqueConstraint("search_space_id", "parameter_key", name="uq_search_space_process_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    search_space_id: Mapped[str] = mapped_column(ForeignKey("candidate_search_spaces.id", ondelete="CASCADE"), index=True)
    parameter_key: Mapped[str] = mapped_column(String(160), nullable=False)
    display_name: Mapped[str] = mapped_column(String(240), nullable=False)
    min_value: Mapped[float] = mapped_column(Float, nullable=False)
    max_value: Mapped[float] = mapped_column(Float, nullable=False)
    step_value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(80), nullable=False)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    search_space: Mapped[CandidateSearchSpace] = relationship(back_populates="process_rules")


class SubstitutionRule(Base):
    __tablename__ = "substitution_rules"
    __table_args__ = (Index("ix_substitution_scope_status", "project_id", "organisation_id", "status"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("replacement_projects.id", ondelete="CASCADE"), nullable=True, index=True)
    material_family: Mapped[str] = mapped_column(String(60), nullable=False)
    source_component_key: Mapped[str] = mapped_column(String(300), nullable=False)
    replacement_component_key: Mapped[str] = mapped_column(String(300), nullable=False)
    replacement_display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    allowed_min_amount: Mapped[float | None] = mapped_column(Float)
    allowed_max_amount: Mapped[float | None] = mapped_column(Float)
    amount_basis: Mapped[str | None] = mapped_column(String(60))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_id: Mapped[str | None] = mapped_column(ForeignKey("evidence.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    evidence: Mapped[Evidence | None] = relationship()


class GenerationRun(Base):
    __tablename__ = "generation_runs"
    __table_args__ = (Index("ix_generation_run_project_status", "project_id", "status"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    project_id: Mapped[str] = mapped_column(ForeignKey("replacement_projects.id", ondelete="CASCADE"), index=True)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    replacement_specification_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    search_space_id: Mapped[str] = mapped_column(ForeignKey("candidate_search_spaces.id"), index=True)
    search_space_version: Mapped[int] = mapped_column(Integer, nullable=False)
    search_space_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    strategy_version: Mapped[str] = mapped_column(String(60), nullable=False)
    configuration_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    random_seed: Mapped[int] = mapped_column(Integer, default=0)
    requested_candidate_budget: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_count: Mapped[int] = mapped_column(Integer, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    result_checksum: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class GenerationRunResult(Base):
    __tablename__ = "generation_run_results"
    __table_args__ = (
        UniqueConstraint("generation_run_id", "sequence", name="uq_generation_run_result_sequence"),
        Index("ix_generation_result_run_fingerprint", "generation_run_id", "candidate_fingerprint"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    generation_run_id: Mapped[str] = mapped_column(ForeignKey("generation_runs.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True, index=True)
    material_id: Mapped[str | None] = mapped_column(ForeignKey("materials.id"), nullable=True)
    hypothesis_id: Mapped[str | None] = mapped_column(ForeignKey("candidate_hypotheses.id", ondelete="SET NULL"), nullable=True, index=True)
    disposition: Mapped[str] = mapped_column(String(40), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)


class CandidateHypothesis(Base):
    __tablename__ = "candidate_hypotheses"
    __table_args__ = (
        UniqueConstraint("project_id", "deterministic_fingerprint", name="uq_hypothesis_project_fingerprint"),
        Index("ix_hypothesis_project_status", "project_id", "status"),
        Index("ix_hypothesis_generation_run", "generation_run_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    project_id: Mapped[str] = mapped_column(ForeignKey("replacement_projects.id", ondelete="CASCADE"), index=True)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    display_label: Mapped[str] = mapped_column(String(300), nullable=False)
    material_family: Mapped[str] = mapped_column(String(60), nullable=False)
    baseline_material_id: Mapped[str] = mapped_column(ForeignKey("materials.id"), index=True)
    generation_run_id: Mapped[str | None] = mapped_column(ForeignKey("generation_runs.id"), nullable=True, index=True)
    generator_strategy_key: Mapped[str] = mapped_column(String(120), nullable=False)
    generator_strategy_version: Mapped[str] = mapped_column(String(60), nullable=False)
    deterministic_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    fingerprint_version: Mapped[str] = mapped_column(String(30), default="candidate-v1")
    status: Mapped[str] = mapped_column(String(40), default="proposed", index=True)
    structural_validity: Mapped[str] = mapped_column(String(30), default="valid", index=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    components: Mapped[list["CandidateHypothesisComponent"]] = relationship(back_populates="hypothesis", cascade="all, delete-orphan")
    process_parameters: Mapped[list["CandidateHypothesisProcessParameter"]] = relationship(back_populates="hypothesis", cascade="all, delete-orphan")
    changes: Mapped[list["CandidateChangeRecord"]] = relationship(back_populates="hypothesis", cascade="all, delete-orphan")


class CandidateHypothesisComponent(Base):
    __tablename__ = "candidate_hypothesis_components"
    __table_args__ = (UniqueConstraint("hypothesis_id", "component_key", name="uq_hypothesis_component_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    hypothesis_id: Mapped[str] = mapped_column(ForeignKey("candidate_hypotheses.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    component_key: Mapped[str] = mapped_column(String(300), nullable=False)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    role: Mapped[str | None] = mapped_column(String(120))
    amount: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(80))
    basis: Mapped[str | None] = mapped_column(String(60))
    source_baseline_component_id: Mapped[str | None] = mapped_column(ForeignKey("material_components.id"), nullable=True)
    substitution_rule_id: Mapped[str | None] = mapped_column(ForeignKey("substitution_rules.id"), nullable=True)
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    hypothesis: Mapped[CandidateHypothesis] = relationship(back_populates="components")


class CandidateHypothesisProcessParameter(Base):
    __tablename__ = "candidate_hypothesis_process_parameters"
    __table_args__ = (UniqueConstraint("hypothesis_id", "parameter_key", name="uq_hypothesis_process_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    hypothesis_id: Mapped[str] = mapped_column(ForeignKey("candidate_hypotheses.id", ondelete="CASCADE"), index=True)
    process_label: Mapped[str] = mapped_column(String(200), default="proposed process state")
    parameter_key: Mapped[str] = mapped_column(String(160), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(80), nullable=False)
    source_baseline_state_id: Mapped[str | None] = mapped_column(ForeignKey("material_process_states.id"), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    hypothesis: Mapped[CandidateHypothesis] = relationship(back_populates="process_parameters")


class CandidateLineageEdge(Base):
    __tablename__ = "candidate_lineage_edges"
    __table_args__ = (Index("ix_lineage_child_sequence", "child_hypothesis_id", "sequence"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    child_hypothesis_id: Mapped[str] = mapped_column(ForeignKey("candidate_hypotheses.id", ondelete="CASCADE"), index=True)
    parent_material_id: Mapped[str | None] = mapped_column(ForeignKey("materials.id"), nullable=True)
    parent_candidate_id: Mapped[str | None] = mapped_column(ForeignKey("candidates.id"), nullable=True)
    parent_hypothesis_id: Mapped[str | None] = mapped_column(ForeignKey("candidate_hypotheses.id"), nullable=True)
    relationship_type: Mapped[str] = mapped_column(String(60), nullable=False)
    generation_run_id: Mapped[str | None] = mapped_column(ForeignKey("generation_runs.id"), nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)


class CandidateChangeRecord(Base):
    __tablename__ = "candidate_change_records"
    __table_args__ = (Index("ix_change_hypothesis_sequence", "hypothesis_id", "sequence"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    hypothesis_id: Mapped[str] = mapped_column(ForeignKey("candidate_hypotheses.id", ondelete="CASCADE"), index=True)
    generation_run_id: Mapped[str | None] = mapped_column(ForeignKey("generation_runs.id"), nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    change_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_path: Mapped[str] = mapped_column(String(300), nullable=False)
    before_value: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    after_value: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    substitution_rule_id: Mapped[str | None] = mapped_column(ForeignKey("substitution_rules.id"), nullable=True)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    hypothesis: Mapped[CandidateHypothesis] = relationship(back_populates="changes")


# Phase 4 — property prediction is deliberately separate from scientific observations.
class PredictionModel(Base):
    __tablename__ = "prediction_models"
    __table_args__ = (
        UniqueConstraint("organisation_id", "key", name="uq_prediction_model_scope_key"),
        Index("ix_prediction_model_scope_status", "organisation_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str | None] = mapped_column(ForeignKey("organisations.id"), nullable=True, index=True)
    key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    model_type: Mapped[str] = mapped_column(String(80), nullable=False)
    owner_provider: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    supported_material_families: Mapped[list[str]] = mapped_column(JSONType, default=list)
    supported_property_keys: Mapped[list[str]] = mapped_column(JSONType, default=list)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    versions: Mapped[list["PredictionModelVersion"]] = relationship(back_populates="model", cascade="all, delete-orphan")


class PredictionModelVersion(Base):
    __tablename__ = "prediction_model_versions"
    __table_args__ = (
        UniqueConstraint("model_id", "version", name="uq_prediction_model_version"),
        Index("ix_prediction_model_version_property", "target_property_key", "approved_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    model_id: Mapped[str] = mapped_column(ForeignKey("prediction_models.id", ondelete="CASCADE"), index=True)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    predictor_key: Mapped[str] = mapped_column(String(160), nullable=False)
    predictor_contract_version: Mapped[str] = mapped_column(String(40), nullable=False)
    artifact_format: Mapped[str] = mapped_column(String(80), nullable=False)
    artifact_payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    artifact_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    feature_schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    feature_schema: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    feature_schema_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    target_property_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    canonical_output_unit: Mapped[str] = mapped_column(String(80), nullable=False)
    uncertainty_method: Mapped[str] = mapped_column(String(120), nullable=False)
    applicability_policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    training_data_descriptor: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    training_data_checksum: Mapped[str | None] = mapped_column(String(64))
    calibration_metrics: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    validation_metrics: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    immutable_metadata: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    model: Mapped[PredictionModel] = relationship(back_populates="versions")
    applicability_domain: Mapped["ModelApplicabilityDomain | None"] = relationship(back_populates="model_version", uselist=False, cascade="all, delete-orphan")


class ModelApplicabilityDomain(Base):
    __tablename__ = "model_applicability_domains"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    model_version_id: Mapped[str] = mapped_column(ForeignKey("prediction_model_versions.id", ondelete="CASCADE"), unique=True, index=True)
    material_families: Mapped[list[str]] = mapped_column(JSONType, default=list)
    required_feature_keys: Mapped[list[str]] = mapped_column(JSONType, default=list)
    numeric_feature_ranges: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    allowed_categorical_values: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    required_component_keys: Mapped[list[str]] = mapped_column(JSONType, default=list)
    target_condition_ranges: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    redacted_input_policy: Mapped[str] = mapped_column(String(40), default="reject")
    domain_distance_method: Mapped[str | None] = mapped_column(String(120))
    domain_distance_config: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    borderline_tolerance: Mapped[float] = mapped_column(Float, default=0.0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    model_version: Mapped[PredictionModelVersion] = relationship(back_populates="applicability_domain")


class PredictionTarget(Base):
    __tablename__ = "prediction_targets"
    __table_args__ = (
        CheckConstraint(
            "(material_id IS NOT NULL AND hypothesis_id IS NULL) OR (material_id IS NULL AND hypothesis_id IS NOT NULL)",
            name="ck_prediction_target_exactly_one_scientific_object",
        ),
        Index("ix_prediction_target_project_property", "project_id", "property_definition_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("replacement_projects.id", ondelete="CASCADE"), nullable=True, index=True)
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True, index=True)
    material_id: Mapped[str | None] = mapped_column(ForeignKey("materials.id"), nullable=True, index=True)
    hypothesis_id: Mapped[str | None] = mapped_column(ForeignKey("candidate_hypotheses.id", ondelete="CASCADE"), nullable=True, index=True)
    property_definition_id: Mapped[str] = mapped_column(ForeignKey("material_property_definitions.id"), index=True)
    requested_conditions: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    condition_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_output_unit: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class PredictionInputSnapshot(Base):
    __tablename__ = "prediction_input_snapshots"
    __table_args__ = (Index("ix_prediction_snapshot_model_feature", "model_version_id", "feature_checksum"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    prediction_target_id: Mapped[str] = mapped_column(ForeignKey("prediction_targets.id", ondelete="CASCADE"), index=True)
    model_version_id: Mapped[str] = mapped_column(ForeignKey("prediction_model_versions.id"), index=True)
    target_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    target_scientific_id: Mapped[str] = mapped_column(String(36), nullable=False)
    feature_schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    normalized_feature_payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    feature_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_entity_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    target_condition_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    missing_features: Mapped[list[str]] = mapped_column(JSONType, default=list)
    redaction_flags: Mapped[list[str]] = mapped_column(JSONType, default=list)
    unit_normalization_version: Mapped[str] = mapped_column(String(40), default="units-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class PredictionRun(Base):
    __tablename__ = "prediction_runs"
    __table_args__ = (
        Index("ix_prediction_run_project_status", "project_id", "status"),
        Index("ix_prediction_run_org_model", "organisation_id", "model_version_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("replacement_projects.id", ondelete="CASCADE"), index=True)
    model_version_id: Mapped[str] = mapped_column(ForeignKey("prediction_model_versions.id"), index=True)
    property_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    configuration_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    target_condition_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_target_count: Mapped[int] = mapped_column(Integer, nullable=False)
    predicted_count: Mapped[int] = mapped_column(Integer, default=0)
    inapplicable_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    run_seed: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    result_checksum: Mapped[str | None] = mapped_column(String(64), index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class PropertyPrediction(Base):
    __tablename__ = "property_predictions"
    __table_args__ = (
        UniqueConstraint("prediction_run_id", "prediction_target_id", name="uq_prediction_run_target"),
        Index("ix_property_prediction_target_status", "prediction_target_id", "status"),
        Index("ix_property_prediction_model_property", "model_version_id", "property_definition_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    prediction_run_id: Mapped[str] = mapped_column(ForeignKey("prediction_runs.id", ondelete="CASCADE"), index=True)
    prediction_target_id: Mapped[str] = mapped_column(ForeignKey("prediction_targets.id", ondelete="CASCADE"), index=True)
    model_version_id: Mapped[str] = mapped_column(ForeignKey("prediction_model_versions.id"), index=True)
    input_snapshot_id: Mapped[str] = mapped_column(ForeignKey("prediction_input_snapshots.id"), index=True)
    property_definition_id: Mapped[str] = mapped_column(ForeignKey("material_property_definitions.id"), index=True)
    applicability_status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    applicability_rationale: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    domain_distance: Mapped[float | None] = mapped_column(Float)
    numeric_point_estimate: Mapped[float | None] = mapped_column(Float)
    output_unit: Mapped[str | None] = mapped_column(String(80))
    canonical_value: Mapped[float | None] = mapped_column(Float)
    canonical_unit: Mapped[str | None] = mapped_column(String(80))
    uncertainty_lower: Mapped[float | None] = mapped_column(Float)
    uncertainty_upper: Mapped[float | None] = mapped_column(Float)
    uncertainty_stddev: Mapped[float | None] = mapped_column(Float)
    uncertainty_method: Mapped[str] = mapped_column(String(120), nullable=False)
    calibrated_coverage_level: Mapped[float | None] = mapped_column(Float)
    warnings: Mapped[list[str]] = mapped_column(JSONType, default=list)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    deterministic_result_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


# Phase 5 — virtual experiment/optimization records are model-based decisions, not physical evidence.
class VirtualExperimentCampaign(Base):
    __tablename__ = "virtual_experiment_campaigns"
    __table_args__ = (
        Index("ix_virtual_campaign_project_status", "project_id", "status"),
        Index("ix_virtual_campaign_org_policy", "organisation_id", "policy_key"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("replacement_projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    replacement_specification_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    search_space_id: Mapped[str] = mapped_column(ForeignKey("candidate_search_spaces.id"), index=True)
    search_space_version: Mapped[int] = mapped_column(Integer, nullable=False)
    search_space_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    policy_version: Mapped[str] = mapped_column(String(60), nullable=False)
    configuration_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    random_seed: Mapped[int] = mapped_column(Integer, default=0)
    max_iterations: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    max_total_new_candidates: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    max_candidates_per_iteration: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    max_parents_per_iteration: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    stop_reason: Mapped[str | None] = mapped_column(String(120))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_checksum: Mapped[str | None] = mapped_column(String(64), index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class CampaignObjective(Base):
    __tablename__ = "campaign_objectives"
    __table_args__ = (
        UniqueConstraint("campaign_id", "sequence", name="uq_campaign_objective_sequence"),
        UniqueConstraint("campaign_id", "property_key", name="uq_campaign_objective_property"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("virtual_experiment_campaigns.id", ondelete="CASCADE"), index=True)
    property_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(30), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    priority: Mapped[int] = mapped_column(Integer, default=1)
    target_value: Mapped[float | None] = mapped_column(Float)
    target_unit: Mapped[str | None] = mapped_column(String(80))
    model_version_id: Mapped[str] = mapped_column(ForeignKey("prediction_model_versions.id"), index=True)
    evaluation_mode: Mapped[str] = mapped_column(String(40), default="model_prediction")
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)


class CampaignConstraintModelPolicy(Base):
    __tablename__ = "campaign_constraint_model_policies"
    __table_args__ = (UniqueConstraint("campaign_id", "constraint_id", name="uq_campaign_constraint_policy"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("virtual_experiment_campaigns.id", ondelete="CASCADE"), index=True)
    constraint_id: Mapped[str] = mapped_column(ForeignKey("constraints.id", ondelete="CASCADE"), index=True)
    model_version_id: Mapped[str | None] = mapped_column(ForeignKey("prediction_model_versions.id"), nullable=True, index=True)
    allowed_value_origin: Mapped[str] = mapped_column(String(60), default="known_evidence_then_prediction")
    unknown_handling: Mapped[str] = mapped_column(String(40), default="retain_uncertain")
    condition_mapping: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)


class CampaignIteration(Base):
    __tablename__ = "campaign_iterations"
    __table_args__ = (
        UniqueConstraint("campaign_id", "iteration_number", name="uq_campaign_iteration_number"),
        Index("ix_campaign_iteration_campaign_status", "campaign_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("virtual_experiment_campaigns.id", ondelete="CASCADE"), index=True)
    iteration_number: Mapped[int] = mapped_column(Integer, nullable=False)
    input_pool_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_selection_checksum: Mapped[str | None] = mapped_column(String(64))
    generation_run_ids: Mapped[list[str]] = mapped_column(JSONType, default=list)
    prediction_run_ids: Mapped[list[str]] = mapped_column(JSONType, default=list)
    evaluated_candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    feasible_count: Mapped[int] = mapped_column(Integer, default=0)
    uncertain_count: Mapped[int] = mapped_column(Integer, default=0)
    infeasible_count: Mapped[int] = mapped_column(Integer, default=0)
    pareto_front_count: Mapped[int] = mapped_column(Integer, default=0)
    pareto_front_checksum: Mapped[str | None] = mapped_column(String(64))
    selected_for_exploration_count: Mapped[int] = mapped_column(Integer, default=0)
    new_candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    decision_checksum: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(30), default="running", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stop_signal: Mapped[bool] = mapped_column(Boolean, default=False)
    stop_reason: Mapped[str | None] = mapped_column(String(120))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)


class VirtualCandidateEvaluation(Base):
    __tablename__ = "virtual_candidate_evaluations"
    __table_args__ = (
        UniqueConstraint("campaign_iteration_id", "candidate_id", name="uq_virtual_evaluation_iteration_candidate"),
        Index("ix_virtual_evaluation_iteration_feasibility", "campaign_iteration_id", "feasibility_class"),
        Index("ix_virtual_evaluation_iteration_pareto", "campaign_iteration_id", "pareto_rank"),
        Index("ix_virtual_eval_checksum", "deterministic_evaluation_checksum"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    campaign_iteration_id: Mapped[str] = mapped_column(ForeignKey("campaign_iterations.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    hypothesis_id: Mapped[str | None] = mapped_column(ForeignKey("candidate_hypotheses.id", ondelete="SET NULL"), nullable=True, index=True)
    feasibility_class: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    hard_pass_count: Mapped[int] = mapped_column(Integer, default=0)
    hard_fail_count: Mapped[int] = mapped_column(Integer, default=0)
    hard_unknown_count: Mapped[int] = mapped_column(Integer, default=0)
    objective_vector: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    objective_intervals: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    objective_origins: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    pareto_rank: Mapped[int | None] = mapped_column(Integer)
    dominance_count: Mapped[int] = mapped_column(Integer, default=0)
    diversity_metric: Mapped[float | None] = mapped_column(Float)
    uncertainty_burden: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    normalized_utility_components: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    acquisition_components: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    selected_as_parent: Mapped[bool] = mapped_column(Boolean, default=False)
    selected_for_next_evaluation: Mapped[bool] = mapped_column(Boolean, default=False)
    disposition: Mapped[str] = mapped_column(String(60), nullable=False, default="evaluated")
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    deterministic_evaluation_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ParetoFrontSnapshot(Base):
    __tablename__ = "pareto_front_snapshots"
    __table_args__ = (UniqueConstraint("campaign_iteration_id", "front_number", name="uq_pareto_iteration_front"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    campaign_iteration_id: Mapped[str] = mapped_column(ForeignKey("campaign_iterations.id", ondelete="CASCADE"), index=True)
    front_number: Mapped[int] = mapped_column(Integer, nullable=False)
    ordered_candidate_ids: Mapped[list[str]] = mapped_column(JSONType, default=list)
    objective_space_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_key: Mapped[str] = mapped_column(String(120), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(60), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class OptimizationDecisionRecord(Base):
    __tablename__ = "optimization_decision_records"
    __table_args__ = (
        UniqueConstraint("campaign_iteration_id", "sequence", name="uq_optimization_decision_sequence"),
        Index("ix_optimization_decision_iteration_type", "campaign_iteration_id", "decision_type"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("virtual_experiment_campaigns.id", ondelete="CASCADE"), index=True)
    campaign_iteration_id: Mapped[str] = mapped_column(ForeignKey("campaign_iterations.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True, index=True)
    hypothesis_id: Mapped[str | None] = mapped_column(ForeignKey("candidate_hypotheses.id", ondelete="SET NULL"), nullable=True, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    decision_type: Mapped[str] = mapped_column(String(80), nullable=False)
    policy_key: Mapped[str] = mapped_column(String(120), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(60), nullable=False)
    input_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


# ---------------------------------------------------------------------------------------------
# Phase 6 — Physics & Simulation Operating System.
#
# A simulation result is a THIRD scientific origin. It is not a MaterialPropertyObservation
# (evidence) and not a PropertyPrediction (statistical model output). Nothing in this section
# writes to either of those tables.
# ---------------------------------------------------------------------------------------------
class ScientificRepresentation(Base):
    """A structured scientific description of exactly one target, adequate (or not) for a method."""
    __tablename__ = "scientific_representations"
    __table_args__ = (
        CheckConstraint(
            "(material_id IS NOT NULL AND hypothesis_id IS NULL) OR (material_id IS NULL AND hypothesis_id IS NOT NULL)",
            name="ck_representation_exactly_one_target",
        ),
        Index("ix_representation_target_type", "representation_type", "status"),
        Index("ix_representation_scope_type", "organisation_id", "representation_type"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str | None] = mapped_column(ForeignKey("organisations.id"), nullable=True, index=True)
    visibility: Mapped[str] = mapped_column(String(20), default="private", index=True)
    material_id: Mapped[str | None] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"), nullable=True, index=True)
    hypothesis_id: Mapped[str | None] = mapped_column(ForeignKey("candidate_hypotheses.id", ondelete="CASCADE"), nullable=True, index=True)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    representation_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    representation_format: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    representation_version: Mapped[str] = mapped_column(String(40), nullable=False, default="1.0")
    content: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    normalized_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    content_bytes: Mapped[int] = mapped_column(Integer, default=0)
    periodicity: Mapped[str | None] = mapped_column(String(40))
    dimensionality: Mapped[int | None] = mapped_column(Integer)
    atom_count: Mapped[int | None] = mapped_column(Integer)
    component_count: Mapped[int | None] = mapped_column(Integer)
    chemical_elements: Mapped[list[str]] = mapped_column(JSONType, default=list)
    validator_key: Mapped[str] = mapped_column(String(120), nullable=False)
    validator_version: Mapped[str] = mapped_column(String(40), nullable=False)
    validation_status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    completeness_status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    validation_messages: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    redaction_flags: Mapped[list[str]] = mapped_column(JSONType, default=list)
    provenance_note: Mapped[str | None] = mapped_column(Text)
    source_record_id: Mapped[str | None] = mapped_column(ForeignKey("source_records.id"), nullable=True)
    evidence_id: Mapped[str | None] = mapped_column(ForeignKey("evidence.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class RegisteredScientificArtifact(Base):
    """Pseudopotentials, force fields and thermodynamic databases: pre-registered, checksummed, approved.

    A simulation never downloads these. Absence of a registered artifact makes a route unavailable.
    """
    __tablename__ = "registered_scientific_artifacts"
    __table_args__ = (
        UniqueConstraint("organisation_id", "key", "version", name="uq_registered_artifact_scope_key_version"),
        Index("ix_registered_artifact_type_status", "artifact_type", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str | None] = mapped_column(ForeignKey("organisations.id"), nullable=True, index=True)
    key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    applies_to_method_families: Mapped[list[str]] = mapped_column(JSONType, default=list)
    applies_to_elements: Mapped[list[str]] = mapped_column(JSONType, default=list)
    applies_to_component_keys: Mapped[list[str]] = mapped_column(JSONType, default=list)
    content_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    content_bytes: Mapped[int] = mapped_column(Integer, default=0)
    storage_reference: Mapped[str | None] = mapped_column(String(200))
    content_available: Mapped[bool] = mapped_column(Boolean, default=False)
    license_name: Mapped[str | None] = mapped_column(String(200))
    license_permits_redistribution: Mapped[bool] = mapped_column(Boolean, default=False)
    source_reference: Mapped[str | None] = mapped_column(Text)
    citation_id: Mapped[str | None] = mapped_column(ForeignKey("citations.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SimulationMethodDefinition(Base):
    """Typed method/purpose registry. Not a free-text field, and never implies universal support."""
    __tablename__ = "simulation_method_definitions"
    __table_args__ = (Index("ix_simulation_method_family_status", "method_family", "status"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    key: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    method_family: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    required_representation_types: Mapped[list[str]] = mapped_column(JSONType, default=list)
    required_parameters: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    optional_parameters: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    output_schema: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    output_property_keys: Mapped[list[str]] = mapped_column(JSONType, default=list)
    output_units: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    convergence_semantics: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    known_limitations: Mapped[list[str]] = mapped_column(JSONType, default=list)
    fidelity: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="approved", index=True)
    definition_version: Mapped[str] = mapped_column(String(40), default="1.0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SimulationProvider(Base):
    """Logical reviewed solver family. Execution safety class is declared here, never by a caller."""
    __tablename__ = "simulation_providers"
    __table_args__ = (
        UniqueConstraint("organisation_id", "key", name="uq_simulation_provider_scope_key"),
        Index("ix_simulation_provider_scope_status", "organisation_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str | None] = mapped_column(ForeignKey("organisations.id"), nullable=True, index=True)
    key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    method_family: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    owner_project: Mapped[str | None] = mapped_column(String(200))
    safety_class: Mapped[str] = mapped_column(String(60), default="reviewed_code_registered")
    approved_execution_mode: Mapped[str] = mapped_column(String(60), default="in_process_fixture")
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    versions: Mapped[list["SimulationProviderVersion"]] = relationship(back_populates="provider", cascade="all, delete-orphan")


class SimulationProviderVersion(Base):
    """Immutable executable/toolchain contract. Never modified in place once a job has used it."""
    __tablename__ = "simulation_provider_versions"
    __table_args__ = (
        UniqueConstraint("provider_id", "version", name="uq_simulation_provider_version"),
        Index("ix_simulation_provider_version_adapter", "adapter_key", "approved_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    provider_id: Mapped[str] = mapped_column(ForeignKey("simulation_providers.id", ondelete="CASCADE"), index=True)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    adapter_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    adapter_contract_version: Mapped[str] = mapped_column(String(40), nullable=False)
    executable_key: Mapped[str | None] = mapped_column(String(120))
    executable_version: Mapped[str | None] = mapped_column(String(120))
    executable_checksum: Mapped[str | None] = mapped_column(String(64))
    container_image: Mapped[str | None] = mapped_column(String(300))
    container_digest: Mapped[str | None] = mapped_column(String(120))
    parser_key: Mapped[str] = mapped_column(String(160), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(40), nullable=False)
    input_builder_key: Mapped[str] = mapped_column(String(160), nullable=False)
    input_builder_version: Mapped[str] = mapped_column(String(40), nullable=False)
    convergence_evaluator_key: Mapped[str] = mapped_column(String(160), nullable=False)
    convergence_evaluator_version: Mapped[str] = mapped_column(String(40), nullable=False)
    supported_method_keys: Mapped[list[str]] = mapped_column(JSONType, default=list)
    supported_material_families: Mapped[list[str]] = mapped_column(JSONType, default=list)
    supported_representation_types: Mapped[list[str]] = mapped_column(JSONType, default=list)
    supported_representation_formats: Mapped[list[str]] = mapped_column(JSONType, default=list)
    supported_property_keys: Mapped[list[str]] = mapped_column(JSONType, default=list)
    required_artifact_types: Mapped[list[str]] = mapped_column(JSONType, default=list)
    artifact_manifest: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    artifact_manifest_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    environment_manifest: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    fidelity: Mapped[str] = mapped_column(String(60), nullable=False)
    deterministic: Mapped[bool] = mapped_column(Boolean, default=True)
    execution_supported: Mapped[bool] = mapped_column(Boolean, default=False)
    maximum_target_size: Mapped[int] = mapped_column(Integer, default=0)
    maximum_wall_time_seconds: Mapped[int] = mapped_column(Integer, default=60)
    resource_class: Mapped[str] = mapped_column(String(60), default="local_small")
    known_limitations: Mapped[list[str]] = mapped_column(JSONType, default=list)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    immutable_metadata: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    provider: Mapped[SimulationProvider] = relationship(back_populates="versions")


class SimulationInputSnapshot(Base):
    """Immutable normalized input. A historical result never depends on a target's current state."""
    __tablename__ = "simulation_input_snapshots"
    __table_args__ = (Index("ix_simulation_snapshot_provider_input", "provider_version_id", "input_checksum"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    target_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    target_scientific_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    target_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    representation_id: Mapped[str] = mapped_column(ForeignKey("scientific_representations.id"), index=True)
    representation_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    method_definition_id: Mapped[str] = mapped_column(ForeignKey("simulation_method_definitions.id"), index=True)
    method_definition_version: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_version_id: Mapped[str] = mapped_column(ForeignKey("simulation_provider_versions.id"), index=True)
    normalized_parameters: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    target_conditions: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    condition_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    input_builder_key: Mapped[str] = mapped_column(String(160), nullable=False)
    input_builder_version: Mapped[str] = mapped_column(String(40), nullable=False)
    artifact_references: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    artifact_manifest_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    unit_normalization_version: Mapped[str] = mapped_column(String(40), default="units-v1")
    input_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    redaction_flags: Mapped[list[str]] = mapped_column(JSONType, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SimulationRoute(Base):
    """Persisted routing decision. Route *previews* are computed and returned without persistence."""
    __tablename__ = "simulation_routes"
    __table_args__ = (Index("ix_simulation_route_target_status", "target_scientific_id", "route_status"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    target_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    target_scientific_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    requested_purpose: Mapped[str] = mapped_column(String(120), nullable=False)
    requested_property_key: Mapped[str | None] = mapped_column(String(120))
    requested_conditions: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    representation_id: Mapped[str | None] = mapped_column(ForeignKey("scientific_representations.id"), nullable=True, index=True)
    method_definition_id: Mapped[str | None] = mapped_column(ForeignKey("simulation_method_definitions.id"), nullable=True)
    provider_version_id: Mapped[str | None] = mapped_column(ForeignKey("simulation_provider_versions.id"), nullable=True, index=True)
    route_status: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    applicability_reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    missing_representation_types: Mapped[list[str]] = mapped_column(JSONType, default=list)
    missing_artifact_types: Mapped[list[str]] = mapped_column(JSONType, default=list)
    fidelity: Mapped[str | None] = mapped_column(String(60))
    estimated_resource_class: Mapped[str | None] = mapped_column(String(60))
    route_policy_version: Mapped[str] = mapped_column(String(40), default="router-v1")
    route_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SimulationWorkflow(Base):
    __tablename__ = "simulation_workflows"
    __table_args__ = (
        Index("ix_simulation_workflow_org_status", "organisation_id", "status"),
        Index("ix_simulation_workflow_target", "target_kind", "target_scientific_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("replacement_projects.id", ondelete="SET NULL"), nullable=True, index=True)
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True, index=True)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("virtual_experiment_campaigns.id", ondelete="SET NULL"), nullable=True, index=True)
    target_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    target_scientific_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    route_id: Mapped[str] = mapped_column(ForeignKey("simulation_routes.id"), index=True)
    input_snapshot_id: Mapped[str] = mapped_column(ForeignKey("simulation_input_snapshots.id"), index=True)
    provider_version_id: Mapped[str] = mapped_column(ForeignKey("simulation_provider_versions.id"), index=True)
    method_definition_id: Mapped[str] = mapped_column(ForeignKey("simulation_method_definitions.id"), index=True)
    workflow_template_key: Mapped[str] = mapped_column(String(160), nullable=False)
    workflow_template_version: Mapped[str] = mapped_column(String(40), nullable=False)
    requested_purpose: Mapped[str] = mapped_column(String(120), nullable=False)
    requested_property_key: Mapped[str | None] = mapped_column(String(120))
    requested_fidelity: Mapped[str] = mapped_column(String(60), nullable=False)
    max_steps: Mapped[int] = mapped_column(Integer, default=1)
    max_wall_time_seconds: Mapped[int] = mapped_column(Integer, default=60)
    status: Mapped[str] = mapped_column(String(30), default="prepared", index=True)
    failure_code: Mapped[str | None] = mapped_column(String(80))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    workflow_checksum: Mapped[str | None] = mapped_column(String(64), index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    steps: Mapped[list["SimulationWorkflowStep"]] = relationship(back_populates="workflow", cascade="all, delete-orphan")


class SimulationWorkflowStep(Base):
    __tablename__ = "simulation_workflow_steps"
    __table_args__ = (
        UniqueConstraint("workflow_id", "sequence", name="uq_simulation_step_sequence"),
        Index("ix_simulation_step_workflow_status", "workflow_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("simulation_workflows.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    step_key: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_version_id: Mapped[str] = mapped_column(ForeignKey("simulation_provider_versions.id"), index=True)
    method_key: Mapped[str] = mapped_column(String(160), nullable=False)
    depends_on_step_ids: Mapped[list[str]] = mapped_column(JSONType, default=list)
    status: Mapped[str] = mapped_column(String(30), default="prepared", index=True)
    input_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    output_checksum: Mapped[str | None] = mapped_column(String(64))
    requires_convergence: Mapped[bool] = mapped_column(Boolean, default=True)
    max_retries: Mapped[int] = mapped_column(Integer, default=0)
    retry_policy_version: Mapped[str] = mapped_column(String(40), default="retry-v1")
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    workflow: Mapped[SimulationWorkflow] = relationship(back_populates="steps")


class SimulationJob(Base):
    """Operational execution attempt. Immutable: a retry appends a new attempt, never overwrites."""
    __tablename__ = "simulation_jobs"
    __table_args__ = (
        UniqueConstraint("step_id", "attempt_number", name="uq_simulation_job_attempt"),
        Index("ix_simulation_job_workflow_status", "workflow_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("simulation_workflows.id", ondelete="CASCADE"), index=True)
    step_id: Mapped[str] = mapped_column(ForeignKey("simulation_workflow_steps.id", ondelete="CASCADE"), index=True)
    provider_version_id: Mapped[str] = mapped_column(ForeignKey("simulation_provider_versions.id"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    workdir_token: Mapped[str] = mapped_column(String(64), nullable=False)
    command_descriptor: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    resource_request: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    compute_backend_key: Mapped[str] = mapped_column(String(60), default="local_bounded_v1")
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    process_exit_code: Mapped[int | None] = mapped_column(Integer)
    failure_code: Mapped[str | None] = mapped_column(String(80))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    elapsed_seconds: Mapped[float | None] = mapped_column(Float)
    stdout_artifact_id: Mapped[str | None] = mapped_column(String(36))
    stderr_artifact_id: Mapped[str | None] = mapped_column(String(36))
    operational_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SimulationArtifact(Base):
    """Immutable checksummed artifact metadata. Absolute filesystem paths are never exposed."""
    __tablename__ = "simulation_artifacts"
    __table_args__ = (
        Index("ix_simulation_artifact_workflow_type", "workflow_id", "artifact_type"),
        Index("ix_simulation_artifact_checksum", "content_checksum"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    workflow_id: Mapped[str | None] = mapped_column(ForeignKey("simulation_workflows.id", ondelete="CASCADE"), nullable=True, index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("simulation_jobs.id", ondelete="CASCADE"), nullable=True, index=True)
    artifact_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    content_role: Mapped[str] = mapped_column(String(80), nullable=False)
    file_name: Mapped[str] = mapped_column(String(200), nullable=False)
    media_type: Mapped[str] = mapped_column(String(120), default="text/plain")
    storage_reference: Mapped[str] = mapped_column(String(200), nullable=False)
    content_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    content_bytes: Mapped[int] = mapped_column(Integer, default=0)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    is_private: Mapped[bool] = mapped_column(Boolean, default=True)
    inline_preview: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SimulationResult(Base):
    """First-class computational result. Operational status and scientific status are separate."""
    __tablename__ = "simulation_results"
    __table_args__ = (
        UniqueConstraint("workflow_id", name="uq_simulation_result_workflow"),
        Index("ix_simulation_result_target_status", "target_scientific_id", "scientific_status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("simulation_workflows.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("simulation_jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    target_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    target_scientific_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    method_definition_id: Mapped[str] = mapped_column(ForeignKey("simulation_method_definitions.id"), index=True)
    provider_version_id: Mapped[str] = mapped_column(ForeignKey("simulation_provider_versions.id"), index=True)
    operational_status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    scientific_status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    convergence_metrics: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    convergence_criteria: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    convergence_evaluator_version: Mapped[str] = mapped_column(String(40), nullable=False)
    parser_key: Mapped[str] = mapped_column(String(160), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(40), nullable=False)
    parsed_quantities: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    warnings: Mapped[list[str]] = mapped_column(JSONType, default=list)
    method_limitations: Mapped[list[str]] = mapped_column(JSONType, default=list)
    output_artifact_checksums: Mapped[list[str]] = mapped_column(JSONType, default=list)
    result_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scientific_origin: Mapped[str] = mapped_column(String(40), default="physics_simulation")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SimulationPropertyEstimate(Base):
    """A simulated quantity mapped onto a property definition. NEVER a MaterialPropertyObservation."""
    __tablename__ = "simulation_property_estimates"
    __table_args__ = (
        UniqueConstraint("simulation_result_id", "property_definition_id", name="uq_simulation_estimate_property"),
        Index("ix_simulation_estimate_property", "property_definition_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    simulation_result_id: Mapped[str] = mapped_column(ForeignKey("simulation_results.id", ondelete="CASCADE"), index=True)
    property_definition_id: Mapped[str] = mapped_column(ForeignKey("material_property_definitions.id"), index=True)
    numeric_value: Mapped[float | None] = mapped_column(Float)
    raw_unit: Mapped[str | None] = mapped_column(String(80))
    canonical_value: Mapped[float | None] = mapped_column(Float)
    canonical_unit: Mapped[str | None] = mapped_column(String(80))
    numerical_tolerance: Mapped[float | None] = mapped_column(Float)
    tolerance_basis: Mapped[str | None] = mapped_column(String(120))
    method_limitations: Mapped[list[str]] = mapped_column(JSONType, default=list)
    target_conditions: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    extractor_key: Mapped[str] = mapped_column(String(160), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(40), nullable=False)
    estimate_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scientific_origin: Mapped[str] = mapped_column(String(40), default="physics_simulation")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class SimulationSelectionPolicyRecord(Base):
    """Explicit, versioned opt-in before any simulated value participates in a comparison."""
    __tablename__ = "simulation_selection_policies"
    __table_args__ = (
        UniqueConstraint("project_id", "property_definition_id", "target_scientific_id", name="uq_simulation_selection_scope"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("replacement_projects.id", ondelete="CASCADE"), index=True)
    property_definition_id: Mapped[str] = mapped_column(ForeignKey("material_property_definitions.id"), index=True)
    target_scientific_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    policy_key: Mapped[str] = mapped_column(String(80), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(40), default="1.0")
    simulation_workflow_id: Mapped[str] = mapped_column(ForeignKey("simulation_workflows.id", ondelete="CASCADE"), index=True)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


# =============================================================================================
# Phase 7 — Industrial Viability Engine
#
# Industrial evidence is a distinct claim class from scientific evidence. A cost figure, a supply
# statistic and a regulatory restriction are all time-bound, place-bound and basis-bound: without
# those qualifiers they are not comparable, so the qualifiers are structural columns rather than
# optional metadata. Nothing here overwrites or reinterprets a MaterialPropertyObservation.
# =============================================================================================
class ManufacturingRoute(Base):
    """A named production route for a material. A route is a claim about how something can be made."""

    __tablename__ = "manufacturing_routes"
    __table_args__ = (
        UniqueConstraint("organisation_id", "key", name="uq_manufacturing_route_scope_key"),
        Index("ix_manufacturing_route_family_status", "process_family", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str | None] = mapped_column(ForeignKey("organisations.id"), index=True)
    visibility: Mapped[str] = mapped_column(String(20), default="private", index=True)
    key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    process_family: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    # Applicability is declared, never inferred from a material's name.
    applies_to_material_families: Mapped[list[str]] = mapped_column(JSONType, default=list)
    applies_to_elements: Mapped[list[str]] = mapped_column(JSONType, default=list)
    required_equipment: Mapped[list[str]] = mapped_column(JSONType, default=list)
    process_temperature_k_min: Mapped[float | None] = mapped_column(Float)
    process_temperature_k_max: Mapped[float | None] = mapped_column(Float)
    process_pressure_pa_min: Mapped[float | None] = mapped_column(Float)
    process_pressure_pa_max: Mapped[float | None] = mapped_column(Float)
    achievable_thickness_m_min: Mapped[float | None] = mapped_column(Float)
    achievable_thickness_m_max: Mapped[float | None] = mapped_column(Float)
    achievable_tolerance_m: Mapped[float | None] = mapped_column(Float)
    surface_finish_ra_m: Mapped[float | None] = mapped_column(Float)
    typical_yield_fraction: Mapped[float | None] = mapped_column(Float)
    throughput_units_per_hour: Mapped[float | None] = mapped_column(Float)
    capex_class: Mapped[str | None] = mapped_column(String(60))
    process_maturity: Mapped[str] = mapped_column(String(60), default="unknown", index=True)
    scale_up_maturity: Mapped[str] = mapped_column(String(60), default="unknown")
    known_limitations: Mapped[list[str]] = mapped_column(JSONType, default=list)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    compatibilities: Mapped[list["MaterialProcessCompatibility"]] = relationship(
        back_populates="route", cascade="all, delete-orphan"
    )


class MaterialProcessCompatibility(Base):
    """Whether a material (or hypothesis) can actually be made by a route, with a stated reason.

    UNKNOWN is a first-class value here: absence of a compatibility record is not incompatibility,
    and incompatibility is never inferred from silence.
    """

    __tablename__ = "material_process_compatibilities"
    __table_args__ = (
        CheckConstraint(
            "(material_id IS NOT NULL AND hypothesis_id IS NULL) OR (material_id IS NULL AND hypothesis_id IS NOT NULL)",
            name="ck_process_compatibility_exactly_one_target",
        ),
        Index(
            "uq_process_compatibility_material", "route_id", "material_id", unique=True,
            postgresql_where=text("material_id IS NOT NULL AND hypothesis_id IS NULL"),
            sqlite_where=text("material_id IS NOT NULL AND hypothesis_id IS NULL"),
        ),
        Index(
            "uq_process_compatibility_hypothesis", "route_id", "hypothesis_id", unique=True,
            postgresql_where=text("hypothesis_id IS NOT NULL AND material_id IS NULL"),
            sqlite_where=text("hypothesis_id IS NOT NULL AND material_id IS NULL"),
        ),
        Index("ix_process_compatibility_state", "compatibility", "route_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str | None] = mapped_column(ForeignKey("organisations.id"), index=True)
    route_id: Mapped[str] = mapped_column(ForeignKey("manufacturing_routes.id", ondelete="CASCADE"), index=True)
    material_id: Mapped[str | None] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"), index=True)
    hypothesis_id: Mapped[str | None] = mapped_column(
        ForeignKey("candidate_hypotheses.id", ondelete="CASCADE"), index=True
    )
    compatibility: Mapped[str] = mapped_column(String(40), default="unknown", index=True)
    rationale: Mapped[str | None] = mapped_column(Text)
    conditions: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    industrial_evidence_id: Mapped[str | None] = mapped_column(
        ForeignKey("industrial_evidence.id", ondelete="SET NULL"), index=True
    )
    as_of_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    route: Mapped[ManufacturingRoute] = relationship(back_populates="compatibilities")


class IndustrialEvidence(Base):
    """One industrial claim, with the qualifiers that make it comparable.

    Cost, supply and regulatory facts are meaningless without currency, basis, geography,
    jurisdiction and an as-of date, so those are columns, not metadata. Two records missing a shared
    basis must never be silently compared.
    """

    __tablename__ = "industrial_evidence"
    __table_args__ = (
        CheckConstraint(
            "(material_id IS NOT NULL AND hypothesis_id IS NULL) OR (material_id IS NULL AND hypothesis_id IS NOT NULL)",
            name="ck_industrial_evidence_exactly_one_target",
        ),
        Index("ix_industrial_evidence_target_metric", "material_id", "category", "metric_key"),
        Index("ix_industrial_evidence_hypothesis_metric", "hypothesis_id", "category", "metric_key"),
        Index("ix_industrial_evidence_asof", "metric_key", "as_of_date"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str | None] = mapped_column(ForeignKey("organisations.id"), index=True)
    visibility: Mapped[str] = mapped_column(String(20), default="private", index=True)
    material_id: Mapped[str | None] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"), index=True)
    hypothesis_id: Mapped[str | None] = mapped_column(
        ForeignKey("candidate_hypotheses.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    metric_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    display_label: Mapped[str] = mapped_column(String(300), nullable=False)

    # Value: numeric, boolean or categorical. Exactly one shape is populated; none is defaulted.
    numeric_value: Mapped[float | None] = mapped_column(Float)
    lower_bound: Mapped[float | None] = mapped_column(Float)
    upper_bound: Mapped[float | None] = mapped_column(Float)
    uncertainty: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(80))
    boolean_value: Mapped[bool | None] = mapped_column(Boolean)
    categorical_value: Mapped[str | None] = mapped_column(String(160))

    # Comparability qualifiers.
    currency: Mapped[str | None] = mapped_column(String(10))
    currency_year: Mapped[int | None] = mapped_column(Integer)
    cost_basis: Mapped[str | None] = mapped_column(String(40))
    quantity_basis_value: Mapped[float | None] = mapped_column(Float)
    quantity_basis_unit: Mapped[str | None] = mapped_column(String(40))
    geography: Mapped[str | None] = mapped_column(String(120), index=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(120), index=True)
    process_context: Mapped[str | None] = mapped_column(String(200))
    manufacturing_route_id: Mapped[str | None] = mapped_column(
        ForeignKey("manufacturing_routes.id", ondelete="SET NULL"), index=True
    )
    conditions: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    as_of_date: Mapped[date | None] = mapped_column(Date, index=True)
    valid_until: Mapped[date | None] = mapped_column(Date)

    # Provenance. Reuses the Phase-1/2 source records rather than a competing provenance system.
    source_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    source_reference: Mapped[str | None] = mapped_column(Text)
    source_record_id: Mapped[str | None] = mapped_column(ForeignKey("source_records.id"), index=True)
    citation_id: Mapped[str | None] = mapped_column(ForeignKey("citations.id"), index=True)
    extraction_method: Mapped[str | None] = mapped_column(String(160))
    confidence: Mapped[float | None] = mapped_column(Float)
    is_estimate: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    scientific_origin: Mapped[str] = mapped_column(String(40), default="industrial_evidence")
    notes: Mapped[str | None] = mapped_column(Text)
    content_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class IndustrialConstraint(Base):
    """An industrial requirement attached to a replacement project."""

    __tablename__ = "industrial_constraints"
    __table_args__ = (
        Index("ix_industrial_constraint_project_category", "project_id", "category"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("replacement_projects.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    constraint_kind: Mapped[str] = mapped_column(String(60), nullable=False)
    metric_key: Mapped[str | None] = mapped_column(String(120), index=True)
    display_label: Mapped[str] = mapped_column(String(300), nullable=False)
    strength: Mapped[str] = mapped_column(String(20), default="hard", index=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    target_value: Mapped[float | None] = mapped_column(Float)
    target_value_upper: Mapped[float | None] = mapped_column(Float)
    target_unit: Mapped[str | None] = mapped_column(String(80))
    currency: Mapped[str | None] = mapped_column(String(10))
    currency_year: Mapped[int | None] = mapped_column(Integer)
    cost_basis: Mapped[str | None] = mapped_column(String(40))
    banned_elements: Mapped[list[str]] = mapped_column(JSONType, default=list)
    allowed_jurisdictions: Mapped[list[str]] = mapped_column(JSONType, default=list)
    required_route_keys: Mapped[list[str]] = mapped_column(JSONType, default=list)
    minimum_maturity: Mapped[str | None] = mapped_column(String(60))
    minimum_supplier_count: Mapped[int | None] = mapped_column(Integer)
    # When evidence is absent, does the constraint fail or stay unknown? Explicit, never assumed.
    treat_missing_evidence_as: Mapped[str] = mapped_column(String(40), default="insufficient_evidence")
    rationale: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class MaturityAssessment(Base):
    """An evidence-backed maturity stage for a material or hypothesis."""

    __tablename__ = "maturity_assessments"
    __table_args__ = (
        CheckConstraint(
            "(material_id IS NOT NULL AND hypothesis_id IS NULL) OR (material_id IS NULL AND hypothesis_id IS NOT NULL)",
            name="ck_maturity_exactly_one_target",
        ),
        Index("ix_maturity_target_stage", "material_id", "stage"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str | None] = mapped_column(ForeignKey("organisations.id"), index=True)
    material_id: Mapped[str | None] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"), index=True)
    hypothesis_id: Mapped[str | None] = mapped_column(
        ForeignKey("candidate_hypotheses.id", ondelete="CASCADE"), index=True
    )
    stage: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    scope: Mapped[str | None] = mapped_column(String(200))
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_evidence_ids: Mapped[list[str]] = mapped_column(JSONType, default=list)
    assessed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    as_of_date: Mapped[date | None] = mapped_column(Date)
    superseded_by_id: Mapped[str | None] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class IndustrialViabilityAssessment(Base):
    """An immutable, reproducible snapshot of one candidate's industrial assessment.

    Historical assessments are never mutated. If evidence changes, a new assessment supersedes the
    old one and the old one remains explainable exactly as it was made.
    """

    __tablename__ = "industrial_viability_assessments"
    __table_args__ = (
        Index("ix_viability_project_target", "project_id", "target_scientific_id"),
        Index("ix_viability_checksum", "assessment_checksum"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("replacement_projects.id", ondelete="CASCADE"), index=True)
    target_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    target_scientific_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("candidates.id", ondelete="SET NULL"), index=True)

    # Per-dimension outcomes. No single opaque score replaces them.
    dimension_states: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    dimension_details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    hard_constraint_failures: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    soft_constraint_results: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    unknown_dimensions: Mapped[list[str]] = mapped_column(JSONType, default=list)
    evidence_coverage: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    missing_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    conflicting_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)

    overall_state: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # A composite score exists only when a methodology is explicitly recorded alongside it.
    composite_score: Mapped[float | None] = mapped_column(Float)
    composite_methodology: Mapped[str | None] = mapped_column(String(120))
    composite_weights: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    composite_is_partial: Mapped[bool] = mapped_column(Boolean, default=True)

    maturity_stage: Mapped[str] = mapped_column(String(60), default="unknown")
    evidence_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    constraint_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    policy_version: Mapped[str] = mapped_column(String(40), default="industrial-viability-v1")
    assessment_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    superseded_by_id: Mapped[str | None] = mapped_column(String(36), index=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


# =============================================================================================
# Phase 8 — Material Functional Decomposition & Replacement Reasoning
#
# The central question: what exactly must be preserved when replacing a material? Chemical
# similarity is not the answer. A property belongs to a material in a STATE, and a replacement must
# preserve a FUNCTION, which a MECHANISM delivers through a PROPERTY, which a STRUCTURAL FEATURE
# enables. Every link in that chain is evidence-backed and separately queryable.
# =============================================================================================
class ProcessingHistory(Base):
    """An ordered, named processing route. Two identical compositions with different histories are
    different states, and properties never propagate between them silently."""

    __tablename__ = "processing_histories"
    __table_args__ = (Index("ix_processing_history_scope_key", "organisation_id", "key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str | None] = mapped_column(ForeignKey("organisations.id"), index=True)
    key: Mapped[str | None] = mapped_column(String(160), index=True)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    history_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    steps: Mapped[list["ProcessingStep"]] = relationship(
        back_populates="history", cascade="all, delete-orphan", order_by="ProcessingStep.sequence"
    )


class ProcessingStep(Base):
    __tablename__ = "processing_steps"
    __table_args__ = (
        UniqueConstraint("history_id", "sequence", name="uq_processing_step_sequence"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    history_id: Mapped[str] = mapped_column(ForeignKey("processing_histories.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    step_kind: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    temperature_k: Mapped[float | None] = mapped_column(Float)
    duration_s: Mapped[float | None] = mapped_column(Float)
    pressure_pa: Mapped[float | None] = mapped_column(Float)
    atmosphere: Mapped[str | None] = mapped_column(String(120))
    cooling_rate_k_per_s: Mapped[float | None] = mapped_column(Float)
    strain_fraction: Mapped[float | None] = mapped_column(Float)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    notes: Mapped[str | None] = mapped_column(Text)

    history: Mapped[ProcessingHistory] = relationship(back_populates="steps")


class MicrostructureDescriptor(Base):
    """Optional microstructural description. Every field is nullable and unknown stays unknown:
    an absent grain size is never rendered or reasoned about as though it were measured."""

    __tablename__ = "microstructure_descriptors"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str | None] = mapped_column(ForeignKey("organisations.id"), index=True)
    display_name: Mapped[str | None] = mapped_column(String(300))
    grain_size_m: Mapped[float | None] = mapped_column(Float)
    grain_size_distribution: Mapped[str | None] = mapped_column(String(120))
    texture: Mapped[str | None] = mapped_column(String(200))
    porosity_fraction: Mapped[float | None] = mapped_column(Float)
    precipitates: Mapped[list[str]] = mapped_column(JSONType, default=list)
    inclusions: Mapped[list[str]] = mapped_column(JSONType, default=list)
    interfaces: Mapped[list[str]] = mapped_column(JSONType, default=list)
    dislocation_density_per_m2: Mapped[float | None] = mapped_column(Float)
    vacancy_concentration: Mapped[float | None] = mapped_column(Float)
    stacking_fault_energy_j_per_m2: Mapped[float | None] = mapped_column(Float)
    defect_notes: Mapped[str | None] = mapped_column(Text)
    descriptor_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class MaterialState(Base):
    """A material in a specific, identified condition.

    'Silicon' is not a state. 'Single-crystal silicon, diamond cubic, Fd-3m, undoped, at 300 K' is.
    Properties reference the state they were measured or computed in, and the reasoning engine
    refuses to carry a property across states it cannot show are compatible.
    """

    __tablename__ = "material_states"
    __table_args__ = (
        CheckConstraint(
            "(material_id IS NOT NULL AND hypothesis_id IS NULL) OR (material_id IS NULL AND hypothesis_id IS NOT NULL)",
            name="ck_material_state_exactly_one_target",
        ),
        Index("ix_material_state_target", "material_id", "hypothesis_id"),
        Index("ix_material_state_identity", "state_checksum"),
        Index("ix_material_state_structure", "structure_identity"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str | None] = mapped_column(ForeignKey("organisations.id"), index=True)
    visibility: Mapped[str] = mapped_column(String(20), default="private", index=True)
    material_id: Mapped[str | None] = mapped_column(ForeignKey("materials.id", ondelete="CASCADE"), index=True)
    hypothesis_id: Mapped[str | None] = mapped_column(
        ForeignKey("candidate_hypotheses.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_reference_state: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # Structure. The representation is the authoritative structural record; the identity hash is
    # derived from it and is deliberately NOT derived from the formula alone.
    representation_id: Mapped[str | None] = mapped_column(
        ForeignKey("scientific_representations.id", ondelete="SET NULL"), index=True
    )
    crystal_system: Mapped[str | None] = mapped_column(String(60))
    space_group_number: Mapped[int | None] = mapped_column(Integer)
    space_group_symbol: Mapped[str | None] = mapped_column(String(40))
    lattice_parameters: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    polymorph: Mapped[str | None] = mapped_column(String(120), index=True)
    phase: Mapped[str | None] = mapped_column(String(120), index=True)
    phase_fraction: Mapped[float | None] = mapped_column(Float)
    structure_identity: Mapped[str | None] = mapped_column(String(64))
    structure_identity_basis: Mapped[str | None] = mapped_column(String(120))
    composition_signature: Mapped[str | None] = mapped_column(String(300), index=True)

    microstructure_id: Mapped[str | None] = mapped_column(
        ForeignKey("microstructure_descriptors.id", ondelete="SET NULL"), index=True
    )
    processing_history_id: Mapped[str | None] = mapped_column(
        ForeignKey("processing_histories.id", ondelete="SET NULL"), index=True
    )

    # Conditions the state is defined at. Absent means unspecified, never "ambient by default".
    temperature_k: Mapped[float | None] = mapped_column(Float)
    pressure_pa: Mapped[float | None] = mapped_column(Float)
    environment: Mapped[str | None] = mapped_column(String(200))
    conditions: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)

    state_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    provenance_note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    composition: Mapped[list["StateCompositionComponent"]] = relationship(
        back_populates="state", cascade="all, delete-orphan"
    )


class StateCompositionComponent(Base):
    """One compositional component of a state, with its role and its stated range.

    The original representation is preserved: a range submitted as 0.1-0.3 stays a range and is
    never collapsed to a midpoint.
    """

    __tablename__ = "state_composition_components"
    __table_args__ = (
        UniqueConstraint("state_id", "element", "role", name="uq_state_component_element_role"),
        Index("ix_state_component_element", "element", "role"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    state_id: Mapped[str] = mapped_column(ForeignKey("material_states.id", ondelete="CASCADE"), index=True)
    element: Mapped[str] = mapped_column(String(8), nullable=False)
    role: Mapped[str] = mapped_column(String(40), default="host", index=True)
    stoichiometry: Mapped[float | None] = mapped_column(Float)
    atomic_fraction: Mapped[float | None] = mapped_column(Float)
    atomic_fraction_min: Mapped[float | None] = mapped_column(Float)
    atomic_fraction_max: Mapped[float | None] = mapped_column(Float)
    concentration_value: Mapped[float | None] = mapped_column(Float)
    concentration_unit: Mapped[str | None] = mapped_column(String(40))
    original_representation: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)

    state: Mapped[MaterialState] = relationship(back_populates="composition")


class Application(Base):
    """An application context. Generic by construction: no domain logic is hardcoded in the engine."""

    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("organisation_id", "key", name="uq_application_scope_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str | None] = mapped_column(ForeignKey("organisations.id"), index=True)
    visibility: Mapped[str] = mapped_column(String(20), default="private")
    key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(120), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    operating_conditions: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    components: Mapped[list["ApplicationComponent"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )


class ApplicationComponent(Base):
    """A physical part of an application that a material occupies."""

    __tablename__ = "application_components"
    __table_args__ = (UniqueConstraint("application_id", "key", name="uq_application_component_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(160), nullable=False)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    operating_conditions: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    application: Mapped[Application] = relationship(back_populates="components")
    roles: Mapped[list["MaterialRole"]] = relationship(
        back_populates="component", cascade="all, delete-orphan"
    )


class MaterialRole(Base):
    """The job a material does in a component. This is what a replacement must preserve."""

    __tablename__ = "material_roles"
    __table_args__ = (UniqueConstraint("component_id", "key", name="uq_material_role_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    component_id: Mapped[str] = mapped_column(ForeignKey("application_components.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(160), nullable=False)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    incumbent_material_id: Mapped[str | None] = mapped_column(ForeignKey("materials.id", ondelete="SET NULL"), index=True)
    incumbent_state_id: Mapped[str | None] = mapped_column(ForeignKey("material_states.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    component: Mapped[ApplicationComponent] = relationship(back_populates="roles")
    functions: Mapped[list["MaterialFunction"]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )


class MaterialFunction(Base):
    """A function the role must deliver — 'withstand electric field', not 'be silicon'."""

    __tablename__ = "material_functions"
    __table_args__ = (UniqueConstraint("role_id", "key", name="uq_material_function_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    role_id: Mapped[str] = mapped_column(ForeignKey("material_roles.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(160), nullable=False)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str] = mapped_column(String(60), default="other", index=True)
    description: Mapped[str | None] = mapped_column(Text)
    criticality: Mapped[int] = mapped_column(Integer, default=1, index=True)
    operating_conditions: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    role: Mapped[MaterialRole] = relationship(back_populates="functions")
    requirements: Mapped[list["FunctionalRequirement"]] = relationship(
        back_populates="function", cascade="all, delete-orphan"
    )


CRITICALITY_FROM_REQUIREMENT_KIND: dict[str, str] = {
    "hard_constraint": "blocking",
    "soft_constraint": "important",
    "objective": "desirable",
    "preference": "desirable",
    "informational": "informational",
}


def _default_criticality(context: Any) -> str:
    """Derive a new requirement's decision-gate criticality from its kind.

    A flat default would silently reclassify hard constraints as merely important, quietly removing
    them from the gating set — exactly the kind of downgrade that must never happen implicitly. This
    matches the deterministic backfill in migration 0012, so a row written by the ORM and a row
    backfilled by the migration always agree.
    """
    parameters = context.get_current_parameters() if context is not None else {}
    kind = str(parameters.get("requirement_kind") or "")
    return CRITICALITY_FROM_REQUIREMENT_KIND.get(kind, "important")


class FunctionalRequirement(Base):
    """A testable requirement derived from a function, bound to a property and its conditions."""

    __tablename__ = "functional_requirements"
    __table_args__ = (
        Index("ix_functional_requirement_property", "property_definition_id", "requirement_kind"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    function_id: Mapped[str] = mapped_column(ForeignKey("material_functions.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(160), nullable=False)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    requirement_kind: Mapped[str] = mapped_column(String(40), default="hard_constraint", index=True)
    direction: Mapped[str] = mapped_column(String(30), nullable=False)
    property_definition_id: Mapped[str | None] = mapped_column(
        ForeignKey("material_property_definitions.id"), index=True
    )
    property_key: Mapped[str | None] = mapped_column(String(120), index=True)
    target_value: Mapped[float | None] = mapped_column(Float)
    target_value_upper: Mapped[float | None] = mapped_column(Float)
    target_unit: Mapped[str | None] = mapped_column(String(80))
    categorical_target: Mapped[str | None] = mapped_column(String(160))
    tolerance: Mapped[float | None] = mapped_column(Float)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    conditions: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    rationale: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    # --- Phase 10 -----------------------------------------------------------------------------
    # `requirement_kind` remains the authoritative input to the Phase-8/9.1 evaluators and is not
    # touched here. `criticality` is an explicit decision-gate classification layered on top of it:
    # a hard gate and an optimization objective are different concepts and are not merged into the
    # existing `weight`. Legacy rows are backfilled deterministically from `requirement_kind` in
    # migration 0012, so no pre-Phase-10 behaviour changes.
    criticality: Mapped[str] = mapped_column(
        String(30), default=_default_criticality, index=True
    )
    requirement_origin: Mapped[str] = mapped_column(String(40), default="user_defined", index=True)
    approval_status: Mapped[str] = mapped_column(String(20), default="accepted", index=True)
    proposed_by: Mapped[str | None] = mapped_column(String(80))
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requirement_version: Mapped[int] = mapped_column(Integer, default=1)

    function: Mapped[MaterialFunction] = relationship(back_populates="requirements")


class StructuralFeature(Base):
    """A structural characteristic that can enable a mechanism (a band structure, a bond network,
    a defect population). Declared and evidence-linked, never inferred from a formula."""

    __tablename__ = "structural_features"
    __table_args__ = (UniqueConstraint("organisation_id", "key", name="uq_structural_feature_scope_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str | None] = mapped_column(ForeignKey("organisations.id"), index=True)
    key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    feature_scale: Mapped[str | None] = mapped_column(String(60))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Mechanism(Base):
    """A physical mechanism through which a structural feature produces a property."""

    __tablename__ = "mechanisms"
    __table_args__ = (UniqueConstraint("organisation_id", "key", name="uq_mechanism_scope_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str | None] = mapped_column(ForeignKey("organisations.id"), index=True)
    key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str | None] = mapped_column(String(60), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ReasoningEdge(Base):
    """One evidence-backed link in the replacement reasoning graph.

    Endpoints are typed (state, feature, mechanism, property, function, requirement). Every edge
    carries provenance, confidence, scope and conditions; a universal causal claim without evidence
    is never created, and the graph is queryable rather than decorative.
    """

    __tablename__ = "reasoning_edges"
    __table_args__ = (
        UniqueConstraint("edge_kind", "from_kind", "from_id", "to_kind", "to_id",
                         name="uq_reasoning_edge_endpoints"),
        Index("ix_reasoning_edge_from", "from_kind", "from_id"),
        Index("ix_reasoning_edge_to", "to_kind", "to_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str | None] = mapped_column(ForeignKey("organisations.id"), index=True)
    edge_kind: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    from_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    from_id: Mapped[str] = mapped_column(String(160), nullable=False)
    to_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    to_id: Mapped[str] = mapped_column(String(160), nullable=False)
    relationship_note: Mapped[str | None] = mapped_column(Text)
    # Scope limits where the link is claimed to hold. An edge with no scope is not a universal law.
    scope: Mapped[str | None] = mapped_column(String(300))
    conditions: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    confidence: Mapped[float | None] = mapped_column(Float)
    evidence_id: Mapped[str | None] = mapped_column(ForeignKey("evidence.id", ondelete="SET NULL"), index=True)
    citation_id: Mapped[str | None] = mapped_column(ForeignKey("citations.id", ondelete="SET NULL"), index=True)
    source_type: Mapped[str] = mapped_column(String(60), default="declared", index=True)
    source_reference: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class CandidateReasoningResult(Base):
    """An immutable, structured explanation of one candidate against one material role.

    The structured result is computed first and is authoritative. Natural-language rendering happens
    afterwards and cannot change any PASS/FAIL/UNKNOWN.
    """

    __tablename__ = "candidate_reasoning_results"
    __table_args__ = (
        Index("ix_candidate_reasoning_scope", "project_id", "role_id", "target_scientific_id"),
        Index("ix_candidate_reasoning_checksum", "reasoning_checksum"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("replacement_projects.id", ondelete="CASCADE"), index=True)
    role_id: Mapped[str] = mapped_column(ForeignKey("material_roles.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("candidates.id", ondelete="SET NULL"), index=True)
    target_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    target_scientific_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    state_id: Mapped[str | None] = mapped_column(ForeignKey("material_states.id", ondelete="SET NULL"), index=True)

    requirement_results: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    function_coverage: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    satisfied_requirements: Mapped[list[str]] = mapped_column(JSONType, default=list)
    failed_requirements: Mapped[list[str]] = mapped_column(JSONType, default=list)
    unknown_requirements: Mapped[list[str]] = mapped_column(JSONType, default=list)
    evidence_gaps: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    origin_breakdown: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    assumptions: Mapped[list[str]] = mapped_column(JSONType, default=list)
    mechanism_paths: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    industrial_assessment_id: Mapped[str | None] = mapped_column(String(36), index=True)
    overall_status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    generation_rationale: Mapped[str | None] = mapped_column(Text)
    reasoning_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(40), default="reasoning-v1")
    superseded_by_id: Mapped[str | None] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


# =============================================================================================
# Phase 9 — Experimental Design & Validation OS
#
# The bridge from computational recommendation to physical evidence. TinkerLab does not own a
# laboratory: it manages plans, protocols, samples, runs and measurements, and ingests results as a
# distinct evidence origin. An experimental measurement never overwrites a prediction or a
# simulation; all three are retained so they can be compared.
# =============================================================================================
class ExperimentProtocol(Base):
    """A named experimental procedure. Content lives in immutable versions, never on this row."""

    __tablename__ = "experiment_protocols"
    __table_args__ = (UniqueConstraint("organisation_id", "key", name="uq_experiment_protocol_scope_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    objective: Mapped[str | None] = mapped_column(Text)
    property_definition_id: Mapped[str | None] = mapped_column(
        ForeignKey("material_property_definitions.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    versions: Mapped[list["ExperimentProtocolVersion"]] = relationship(
        back_populates="protocol", cascade="all, delete-orphan"
    )


class ExperimentProtocolVersion(Base):
    """An immutable protocol version.

    A run snapshots the version it used. Editing a protocol creates a NEW version; it never rewrites
    an existing one, so a historical run always describes what was actually done.
    """

    __tablename__ = "experiment_protocol_versions"
    __table_args__ = (
        UniqueConstraint("protocol_id", "version", name="uq_experiment_protocol_version"),
        Index("ix_protocol_version_checksum", "protocol_checksum"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    protocol_id: Mapped[str] = mapped_column(ForeignKey("experiment_protocols.id", ondelete="CASCADE"), index=True)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    required_equipment: Mapped[list[str]] = mapped_column(JSONType, default=list)
    sample_requirements: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    preparation_steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    controlled_variables: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    independent_variables: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    dependent_variables: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    measurement_procedure: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    calibration_requirements: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    acceptance_criteria: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    safety_notes: Mapped[str | None] = mapped_column(Text)
    replicate_requirement: Mapped[int] = mapped_column(Integer, default=1)
    control_requirement: Mapped[str | None] = mapped_column(String(300))
    protocol_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    is_frozen: Mapped[bool] = mapped_column(Boolean, default=True)
    superseded_by_id: Mapped[str | None] = mapped_column(String(36), index=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    protocol: Mapped[ExperimentProtocol] = relationship(back_populates="versions")


class Instrument(Base):
    """Instrument metadata. Calibration is recorded, never inferred and never fabricated."""

    __tablename__ = "instruments"
    __table_args__ = (UniqueConstraint("organisation_id", "key", name="uq_instrument_scope_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    instrument_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(200))
    model: Mapped[str | None] = mapped_column(String(200))
    asset_reference: Mapped[str | None] = mapped_column(String(160))
    measures_property_keys: Mapped[list[str]] = mapped_column(JSONType, default=list)
    equipment_capabilities: Mapped[list[str]] = mapped_column(JSONType, default=list)
    measurement_unit: Mapped[str | None] = mapped_column(String(80))
    stated_uncertainty: Mapped[float | None] = mapped_column(Float)
    stated_uncertainty_unit: Mapped[str | None] = mapped_column(String(80))
    calibration_status: Mapped[str] = mapped_column(String(40), default="unknown", index=True)
    calibration_date: Mapped[date | None] = mapped_column(Date)
    calibration_due_date: Mapped[date | None] = mapped_column(Date)
    calibration_reference: Mapped[str | None] = mapped_column(String(300))
    integration_kind: Mapped[str] = mapped_column(String(60), default="manual_entry", index=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Sample(Base):
    """A physical specimen. Every measurement must trace to one.

    Lineage is explicit: a subdivided specimen records its parent, so a measurement can always be
    traced back to the material, state and batch it came from.
    """

    __tablename__ = "samples"
    __table_args__ = (
        UniqueConstraint("organisation_id", "sample_code", name="uq_sample_scope_code"),
        Index("ix_sample_target", "material_id", "hypothesis_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    sample_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(300))
    sample_kind: Mapped[str] = mapped_column(String(40), default="unknown", index=True)
    material_id: Mapped[str | None] = mapped_column(ForeignKey("materials.id", ondelete="SET NULL"), index=True)
    hypothesis_id: Mapped[str | None] = mapped_column(
        ForeignKey("candidate_hypotheses.id", ondelete="SET NULL"), index=True
    )
    material_state_id: Mapped[str | None] = mapped_column(
        ForeignKey("material_states.id", ondelete="SET NULL"), index=True
    )
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("candidates.id", ondelete="SET NULL"), index=True)
    parent_sample_id: Mapped[str | None] = mapped_column(ForeignKey("samples.id", ondelete="SET NULL"), index=True)
    batch_reference: Mapped[str | None] = mapped_column(String(160), index=True)
    synthesis_reference: Mapped[str | None] = mapped_column(Text)
    processing_history_id: Mapped[str | None] = mapped_column(
        ForeignKey("processing_histories.id", ondelete="SET NULL"), index=True
    )
    geometry: Mapped[str | None] = mapped_column(String(200))
    dimensions: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    mass_kg: Mapped[float | None] = mapped_column(Float)
    preparation_date: Mapped[date | None] = mapped_column(Date)
    prepared_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    storage_conditions: Mapped[str | None] = mapped_column(String(300))
    provenance_note: Mapped[str | None] = mapped_column(Text)
    provenance_complete: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    provenance_gaps: Mapped[list[str]] = mapped_column(JSONType, default=list)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ExperimentPlan(Base):
    """A designed set of runs. The design kind is one this system actually implements."""

    __tablename__ = "experiment_plans"
    __table_args__ = (Index("ix_experiment_plan_scope", "organisation_id", "status"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("replacement_projects.id", ondelete="SET NULL"), index=True)
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("candidates.id", ondelete="SET NULL"), index=True)
    role_id: Mapped[str | None] = mapped_column(ForeignKey("material_roles.id", ondelete="SET NULL"), index=True)
    requirement_id: Mapped[str | None] = mapped_column(
        ForeignKey("functional_requirements.id", ondelete="SET NULL"), index=True
    )
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    design_kind: Mapped[str] = mapped_column(String(40), default="single_run", index=True)
    protocol_version_id: Mapped[str] = mapped_column(
        ForeignKey("experiment_protocol_versions.id"), nullable=False, index=True
    )
    factors: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    replicate_count: Mapped[int] = mapped_column(Integer, default=1)
    control_plan: Mapped[str | None] = mapped_column(Text)
    planned_run_count: Mapped[int] = mapped_column(Integer, default=1)
    design_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="planned", index=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ExperimentRun(Base):
    """One executed (or planned) experimental run.

    ``protocol_version_id`` pins the exact protocol content used. Editing the protocol later cannot
    change what this run says was done.
    """

    __tablename__ = "experiment_runs"
    __table_args__ = (
        Index("ix_experiment_run_plan_status", "plan_id", "status"),
        Index("ix_experiment_run_sample", "sample_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    plan_id: Mapped[str | None] = mapped_column(ForeignKey("experiment_plans.id", ondelete="SET NULL"), index=True)
    protocol_version_id: Mapped[str] = mapped_column(
        ForeignKey("experiment_protocol_versions.id"), nullable=False, index=True
    )
    protocol_checksum_at_run: Mapped[str] = mapped_column(String(64), nullable=False)
    run_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    sample_id: Mapped[str | None] = mapped_column(ForeignKey("samples.id", ondelete="SET NULL"), index=True)
    instrument_id: Mapped[str | None] = mapped_column(ForeignKey("instruments.id", ondelete="SET NULL"), index=True)
    replicate_index: Mapped[int] = mapped_column(Integer, default=1)
    is_control: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    factor_levels: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    conditions: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    operator_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="planned", index=True)
    deviation_notes: Mapped[str | None] = mapped_column(Text)
    invalidation_reason: Mapped[str | None] = mapped_column(Text)
    integration_kind: Mapped[str] = mapped_column(String(60), default="manual_entry")
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Measurement(Base):
    """A physical measurement produced by a run.

    A measurement without adequate sample provenance is recorded and explicitly marked
    INCOMPLETE_PROVENANCE rather than silently accepted as experimental evidence.
    """

    __tablename__ = "measurements"
    __table_args__ = (
        Index("ix_measurement_property", "property_definition_id", "quality"),
        Index("ix_measurement_run", "run_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("experiment_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    sample_id: Mapped[str | None] = mapped_column(ForeignKey("samples.id", ondelete="SET NULL"), index=True)
    instrument_id: Mapped[str | None] = mapped_column(ForeignKey("instruments.id", ondelete="SET NULL"), index=True)
    property_definition_id: Mapped[str] = mapped_column(
        ForeignKey("material_property_definitions.id"), nullable=False, index=True
    )
    numeric_value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(80))
    canonical_value: Mapped[float | None] = mapped_column(Float)
    canonical_unit: Mapped[str | None] = mapped_column(String(80))
    uncertainty: Mapped[float | None] = mapped_column(Float)
    uncertainty_type: Mapped[str | None] = mapped_column(String(60))
    method: Mapped[str | None] = mapped_column(String(200))
    conditions: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    replicate_index: Mapped[int] = mapped_column(Integer, default=1)
    measured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quality: Mapped[str] = mapped_column(String(40), default="provisional", index=True)
    quality_reasons: Mapped[list[str]] = mapped_column(JSONType, default=list)
    admissibility_codes: Mapped[list[str]] = mapped_column(JSONType, default=list)
    # Raw and processed artifacts stay distinguishable: a derived number is not the raw trace.
    raw_artifact_id: Mapped[str | None] = mapped_column(String(36), index=True)
    processed_artifact_id: Mapped[str | None] = mapped_column(String(36), index=True)
    scientific_origin: Mapped[str] = mapped_column(String(40), default="experimental", index=True)
    measurement_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ExperimentArtifact(Base):
    """Raw or processed data from a run, checksummed and never conflated with each other."""

    __tablename__ = "experiment_artifacts"
    __table_args__ = (Index("ix_experiment_artifact_run_role", "run_id", "content_role"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("experiment_runs.id", ondelete="CASCADE"), index=True)
    measurement_id: Mapped[str | None] = mapped_column(ForeignKey("measurements.id", ondelete="CASCADE"), index=True)
    content_role: Mapped[str] = mapped_column(String(40), nullable=False)
    file_name: Mapped[str] = mapped_column(String(200), nullable=False)
    media_type: Mapped[str] = mapped_column(String(120), default="text/plain")
    storage_reference: Mapped[str] = mapped_column(String(200), nullable=False)
    content_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    content_bytes: Mapped[int] = mapped_column(Integer, default=0)
    derived_from_artifact_id: Mapped[str | None] = mapped_column(String(36), index=True)
    processing_description: Mapped[str | None] = mapped_column(Text)
    is_private: Mapped[bool] = mapped_column(Boolean, default=True)
    inline_preview: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ExperimentRecommendation(Base):
    """A recommended experiment derived from an unresolved requirement.

    Priority is an explainable weighted combination of declared factors. It is deliberately NOT
    called expected value of information: no EVSI/EVI mathematics is implemented.
    """

    __tablename__ = "experiment_recommendations"
    __table_args__ = (Index("ix_experiment_recommendation_scope", "role_id", "target_scientific_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("replacement_projects.id", ondelete="CASCADE"), index=True)
    role_id: Mapped[str | None] = mapped_column(ForeignKey("material_roles.id", ondelete="SET NULL"), index=True)
    requirement_id: Mapped[str | None] = mapped_column(
        ForeignKey("functional_requirements.id", ondelete="SET NULL"), index=True
    )
    target_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    target_scientific_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    property_definition_id: Mapped[str | None] = mapped_column(
        ForeignKey("material_property_definitions.id"), index=True
    )
    unresolved_status: Mapped[str] = mapped_column(String(40), nullable=False)
    why_it_matters: Mapped[str] = mapped_column(Text, nullable=False)
    current_evidence_summary: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    expected_evidence_type: Mapped[str] = mapped_column(String(60), default="experimental")
    proposed_measurement: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_protocol_id: Mapped[str | None] = mapped_column(
        ForeignKey("experiment_protocols.id", ondelete="SET NULL"), index=True
    )
    priority_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    priority_factors: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    priority_methodology: Mapped[str] = mapped_column(String(120), default="explainable_weighted_factors_v1")
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    resolved_by_run_id: Mapped[str | None] = mapped_column(String(36), index=True)
    recommendation_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ValidationAssessment(Base):
    """A candidate's validation state for a role, with the comparison that produced it.

    Prediction, simulation and experiment are compared, never merged. Disagreement is a first-class
    outcome and produces CONTRADICTED rather than a quietly averaged consensus.
    """

    __tablename__ = "validation_assessments"
    __table_args__ = (
        Index("ix_validation_scope", "role_id", "target_scientific_id"),
        Index("ix_validation_checksum", "assessment_checksum"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("replacement_projects.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("candidates.id", ondelete="SET NULL"), index=True)
    role_id: Mapped[str | None] = mapped_column(ForeignKey("material_roles.id", ondelete="SET NULL"), index=True)
    target_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    target_scientific_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    validation_state: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    per_property_comparisons: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    agreements: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    disagreements: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    conflicting_experiments: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    experimentally_supported_requirements: Mapped[list[str]] = mapped_column(JSONType, default=list)
    outstanding_requirements: Mapped[list[str]] = mapped_column(JSONType, default=list)
    measurement_ids: Mapped[list[str]] = mapped_column(JSONType, default=list)
    requirement_outcomes: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    evidence_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(40), default="validation-v1")
    methodology_version: Mapped[str] = mapped_column(String(40), default="experimental-admissibility-v1")
    assessment_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    superseded_by_id: Mapped[str | None] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


# =============================================================================================
# Phase 10 — Closed-Loop Material Replacement Decision OS
#
# Phase 10 adds orchestration and decision provenance. It adds no new evaluator: requirement
# outcomes, state matching, unit conversion, industrial states and experimental admissibility all
# continue to come from the canonical Phase 8/9.1 services. Every conclusion recorded below is
# immutable and versioned — new evidence creates a new conclusion rather than editing an old one.
# =============================================================================================
class DecisionPolicy(Base):
    """A versioned, per-organisation configuration of what "ready to advance" means.

    A semiconductor qualification gate and a packaging-material gate are not the same gate, so the
    policy is data rather than code. A historical assessment keeps the policy version it used; the
    current policy is never retro-applied to an old conclusion.
    """

    __tablename__ = "decision_policies"
    __table_args__ = (
        UniqueConstraint("organisation_id", "key", "version", name="uq_decision_policy_scope_version"),
        Index("ix_decision_policy_active", "organisation_id", "key", "is_active"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Gates that must be satisfied before ADVANCE is possible. Stored explicitly so a reviewer can
    # read the policy that produced a decision without reading the source.
    required_gates: Mapped[list[str]] = mapped_column(JSONType, default=list)
    minimum_evidence_requirements: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    required_experimental_validation: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    industrial_gate_requirements: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    allowed_unresolved_statuses: Mapped[list[str]] = mapped_column(JSONType, default=list)
    ranking_weights: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    sensitivity_bounds: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    auto_reject_on_experimental_contradiction: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    policy_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ReplacementProgram(Base):
    """A replacement study: one application, one incumbent material state, one candidate portfolio.

    The program does not replace `ReplacementProject`; it references one. Existing project contracts
    (constraints, objectives, candidates, generation, prediction, simulation, industrial) keep
    working untouched, and the program adds the application/incumbent/decision layer around them.
    """

    __tablename__ = "replacement_programs"
    __table_args__ = (
        UniqueConstraint("organisation_id", "key", name="uq_replacement_program_scope_key"),
        Index("ix_replacement_program_project", "project_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("replacement_projects.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Application context. The role is the anchor: a replacement must preserve what the incumbent
    # DOES, so every requirement evaluation in Phase 10 runs against this role's decomposition.
    application_id: Mapped[str | None] = mapped_column(ForeignKey("applications.id", ondelete="SET NULL"), index=True)
    application_component_id: Mapped[str | None] = mapped_column(
        ForeignKey("application_components.id", ondelete="SET NULL"), index=True
    )
    role_id: Mapped[str | None] = mapped_column(ForeignKey("material_roles.id", ondelete="SET NULL"), index=True)
    application_name: Mapped[str | None] = mapped_column(String(300))
    application_domain: Mapped[str | None] = mapped_column(String(120), index=True)
    # Domain-specific application context that would otherwise explode into hundreds of columns.
    # Frequently queried fields stay structured above; the long tail lives here.
    application_context: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)

    incumbent_material_id: Mapped[str | None] = mapped_column(ForeignKey("materials.id", ondelete="SET NULL"), index=True)
    incumbent_state_id: Mapped[str | None] = mapped_column(ForeignKey("material_states.id", ondelete="SET NULL"), index=True)

    decision_policy_id: Mapped[str | None] = mapped_column(ForeignKey("decision_policies.id", ondelete="SET NULL"), index=True)
    decision_policy_version: Mapped[str] = mapped_column(String(40), default="decision-policy-v1")

    # Resolved deterministically from evidence. `status_override` records operator intent (PAUSED /
    # ARCHIVED) which is the only thing a human sets directly.
    status: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    status_override: Mapped[str | None] = mapped_column(String(40))
    status_reason_codes: Mapped[list[str]] = mapped_column(JSONType, default=list)

    validation_strategy: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    is_demonstration_data: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    project: Mapped[ReplacementProject] = relationship()
    incumbent_material: Mapped[Material | None] = relationship()


class ScientificAction(Base):
    """One deterministically generated next step, with its dependencies and its provenance.

    Actions are never silently deleted when new evidence arrives: the superseding action records
    which action it replaced, so the reasoning trail survives.
    """

    __tablename__ = "scientific_actions"
    __table_args__ = (
        Index("ix_scientific_action_scope", "program_id", "candidate_id", "status"),
        Index("ix_scientific_action_signature", "program_id", "action_signature"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    program_id: Mapped[str] = mapped_column(ForeignKey("replacement_programs.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    requirement_id: Mapped[str | None] = mapped_column(
        ForeignKey("functional_requirements.id", ondelete="SET NULL"), index=True
    )
    action_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    # Stable identity of "the same recommended step", so recomputation supersedes rather than duplicates.
    action_signature: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="proposed", index=True)
    priority: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    priority_factors: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    decision_value_class: Mapped[str] = mapped_column(String(20), default="low")
    cost_class: Mapped[str] = mapped_column(String(20), default="unknown")
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    resolves_gap_kind: Mapped[str | None] = mapped_column(String(60))
    what_it_could_resolve: Mapped[str | None] = mapped_column(Text)
    depends_on: Mapped[list[str]] = mapped_column(JSONType, default=list)
    supersedes_id: Mapped[str | None] = mapped_column(String(36), index=True)
    superseded_by_id: Mapped[str | None] = mapped_column(String(36), index=True)
    result_reference: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    methodology_version: Mapped[str] = mapped_column(String(60), default="next-action-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EvidenceGapSnapshot(Base):
    """An immutable record of the gap set at one point in time, for auditability of "what changed"."""

    __tablename__ = "evidence_gap_snapshots"
    __table_args__ = (Index("ix_evidence_gap_snapshot_scope", "program_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    program_id: Mapped[str] = mapped_column(ForeignKey("replacement_programs.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    gaps: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    blocking_gap_count: Mapped[int] = mapped_column(Integer, default=0)
    high_value_gap_count: Mapped[int] = mapped_column(Integer, default=0)
    coverage: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    methodology_version: Mapped[str] = mapped_column(String(60), default="evidence-gap-v1")
    gap_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ConvergenceAssessment(Base):
    """How close a program is to a defensible decision. Immutable; never a probability of success."""

    __tablename__ = "convergence_assessments"
    __table_args__ = (
        Index("ix_convergence_scope", "program_id", "created_at"),
        Index("ix_convergence_checksum", "assessment_checksum"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    program_id: Mapped[str] = mapped_column(ForeignKey("replacement_programs.id", ondelete="CASCADE"), index=True)
    convergence_state: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    per_candidate: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    reason_codes: Mapped[list[str]] = mapped_column(JSONType, default=list)
    reasons: Mapped[list[str]] = mapped_column(JSONType, default=list)
    # A presentation-only figure. Explicitly not a likelihood; the underlying metrics are retained.
    presentation_progress_percent: Mapped[float] = mapped_column(Float, default=0.0)
    decision_policy_version: Mapped[str] = mapped_column(String(40), default="decision-policy-v1")
    methodology_version: Mapped[str] = mapped_column(String(60), default="convergence-v1")
    assessment_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    superseded_by_id: Mapped[str | None] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ReplacementRecommendation(Base):
    """An immutable, versioned scientific recommendation. Not a commercial or regulatory approval."""

    __tablename__ = "replacement_recommendations"
    __table_args__ = (
        Index("ix_replacement_recommendation_scope", "program_id", "version"),
        Index("ix_replacement_recommendation_checksum", "recommendation_checksum"),
        UniqueConstraint("program_id", "version", name="uq_replacement_recommendation_version"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    program_id: Mapped[str] = mapped_column(ForeignKey("replacement_programs.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    recommended_candidate_ids: Mapped[list[str]] = mapped_column(JSONType, default=list)
    rejected_candidate_ids: Mapped[list[str]] = mapped_column(JSONType, default=list)
    held_candidate_ids: Mapped[list[str]] = mapped_column(JSONType, default=list)
    incumbent_reference: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    requirement_summary: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    per_candidate: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    blocking_requirements: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    unresolved_requirements: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    conflicting_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    evidence_gaps: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    next_actions: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    ranking: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    pareto: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    sensitivity: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    convergence_state: Mapped[str] = mapped_column(String(40), nullable=False)
    convergence_assessment_id: Mapped[str | None] = mapped_column(String(36), index=True)
    reason_codes: Mapped[list[str]] = mapped_column(JSONType, default=list)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    decision_policy_id: Mapped[str | None] = mapped_column(String(36), index=True)
    decision_policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    methodology_versions: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    assessment_refs: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    qualification_note: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    superseded_by_id: Mapped[str | None] = mapped_column(String(36), index=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class DecisionDelta(Base):
    """Why the recommendation changed, in terms of evidence rather than of score movement."""

    __tablename__ = "decision_deltas"
    __table_args__ = (Index("ix_decision_delta_scope", "program_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    program_id: Mapped[str] = mapped_column(ForeignKey("replacement_programs.id", ondelete="CASCADE"), index=True)
    previous_recommendation_id: Mapped[str | None] = mapped_column(String(36), index=True)
    new_recommendation_id: Mapped[str] = mapped_column(String(36), index=True)
    previous_status: Mapped[str | None] = mapped_column(String(40))
    new_status: Mapped[str] = mapped_column(String(40), nullable=False)
    changed_requirements: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    new_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    invalidated_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    changed_ranking: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    changed_blockers: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    reason_codes: Mapped[list[str]] = mapped_column(JSONType, default=list)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    methodology_version: Mapped[str] = mapped_column(String(60), default="decision-delta-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ReplacementProgramSnapshot(Base):
    """A reproducibility snapshot: enough references to reconstruct exactly how a decision was made."""

    __tablename__ = "replacement_program_snapshots"
    __table_args__ = (
        Index("ix_program_snapshot_scope", "program_id", "created_at"),
        Index("ix_program_snapshot_checksum", "snapshot_checksum"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    program_id: Mapped[str] = mapped_column(ForeignKey("replacement_programs.id", ondelete="CASCADE"), index=True)
    label: Mapped[str | None] = mapped_column(String(200))
    requirements_ref: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    portfolio_ref: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    material_states_ref: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    scientific_evidence_ref: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    industrial_evidence_ref: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    experimental_evidence_ref: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    decision_policy_ref: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    methodology_versions: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    convergence_assessment_id: Mapped[str | None] = mapped_column(String(36), index=True)
    recommendation_id: Mapped[str | None] = mapped_column(String(36), index=True)
    snapshot_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class TechnicalDossier(Base):
    """A generated technical replacement dossier, versioned. Regeneration never overwrites history."""

    __tablename__ = "technical_dossiers"
    __table_args__ = (
        UniqueConstraint("program_id", "version", name="uq_technical_dossier_version"),
        Index("ix_technical_dossier_scope", "program_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    program_id: Mapped[str] = mapped_column(ForeignKey("replacement_programs.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("candidates.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    sections: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    snapshot_id: Mapped[str | None] = mapped_column(String(36), index=True)
    recommendation_id: Mapped[str | None] = mapped_column(String(36), index=True)
    convergence_assessment_id: Mapped[str | None] = mapped_column(String(36), index=True)
    assessment_ids: Mapped[list[str]] = mapped_column(JSONType, default=list)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONType, default=list)
    methodology_versions: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    decision_policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    llm_narrative_used: Mapped[bool] = mapped_column(Boolean, default=False)
    dossier_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ProgramTimelineEvent(Base):
    """Append-only program history. Rows are written once and never updated."""

    __tablename__ = "program_timeline_events"
    __table_args__ = (
        Index("ix_program_timeline_scope", "program_id", "occurred_at"),
        Index("ix_program_timeline_candidate", "program_id", "candidate_id", "occurred_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    organisation_id: Mapped[str] = mapped_column(ForeignKey("organisations.id"), index=True)
    program_id: Mapped[str] = mapped_column(ForeignKey("replacement_programs.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    requirement_id: Mapped[str | None] = mapped_column(String(36), index=True)
    event_kind: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    reference_kind: Mapped[str | None] = mapped_column(String(60))
    reference_id: Mapped[str | None] = mapped_column(String(36), index=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
