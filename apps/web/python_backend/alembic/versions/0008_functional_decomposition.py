"""Phase 8 functional decomposition and replacement reasoning

Revision ID: 0008_phase8
Revises: 0007_phase7
Create Date: 2026-08-13

Forward-only. Migrations 0001-0007 are NOT edited.

This migration was produced by autogenerate and then filtered: 121 statements that autogenerate
proposed against Phase 1-7 tables (62 alter_column, 27 drop_index, 26 create_index, 6
drop_constraint) were discarded. They reflected pre-existing schema drift, and applying them here
would have silently altered earlier phases' schema under the guise of adding Phase 8.

Downgrade removes only Phase-8 tables. No observation, prediction, simulation, campaign or
industrial record is created, altered or deleted by either direction.
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0008_phase8"
down_revision = "0007_phase7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('applications',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('organisation_id', sa.String(length=36), nullable=True),
    sa.Column('visibility', sa.String(length=20), nullable=False),
    sa.Column('key', sa.String(length=160), nullable=False),
    sa.Column('display_name', sa.String(length=300), nullable=False),
    sa.Column('domain', sa.String(length=120), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('operating_conditions', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organisation_id', 'key', name='uq_application_scope_key')
    )
    op.create_index(op.f('ix_applications_domain'), 'applications', ['domain'], unique=False)
    op.create_index(op.f('ix_applications_key'), 'applications', ['key'], unique=False)
    op.create_index(op.f('ix_applications_organisation_id'), 'applications', ['organisation_id'], unique=False)
    op.create_index(op.f('ix_applications_status'), 'applications', ['status'], unique=False)
    op.create_table('mechanisms',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('organisation_id', sa.String(length=36), nullable=True),
    sa.Column('key', sa.String(length=160), nullable=False),
    sa.Column('display_name', sa.String(length=300), nullable=False),
    sa.Column('category', sa.String(length=60), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organisation_id', 'key', name='uq_mechanism_scope_key')
    )
    op.create_index(op.f('ix_mechanisms_category'), 'mechanisms', ['category'], unique=False)
    op.create_index(op.f('ix_mechanisms_key'), 'mechanisms', ['key'], unique=False)
    op.create_index(op.f('ix_mechanisms_organisation_id'), 'mechanisms', ['organisation_id'], unique=False)
    op.create_table('microstructure_descriptors',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('organisation_id', sa.String(length=36), nullable=True),
    sa.Column('display_name', sa.String(length=300), nullable=True),
    sa.Column('grain_size_m', sa.Float(), nullable=True),
    sa.Column('grain_size_distribution', sa.String(length=120), nullable=True),
    sa.Column('texture', sa.String(length=200), nullable=True),
    sa.Column('porosity_fraction', sa.Float(), nullable=True),
    sa.Column('precipitates', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('inclusions', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('interfaces', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('dislocation_density_per_m2', sa.Float(), nullable=True),
    sa.Column('vacancy_concentration', sa.Float(), nullable=True),
    sa.Column('stacking_fault_energy_j_per_m2', sa.Float(), nullable=True),
    sa.Column('defect_notes', sa.Text(), nullable=True),
    sa.Column('descriptor_checksum', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_microstructure_descriptors_descriptor_checksum'), 'microstructure_descriptors', ['descriptor_checksum'], unique=False)
    op.create_index(op.f('ix_microstructure_descriptors_organisation_id'), 'microstructure_descriptors', ['organisation_id'], unique=False)
    op.create_table('processing_histories',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('organisation_id', sa.String(length=36), nullable=True),
    sa.Column('key', sa.String(length=160), nullable=True),
    sa.Column('display_name', sa.String(length=300), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('history_checksum', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_processing_histories_history_checksum'), 'processing_histories', ['history_checksum'], unique=False)
    op.create_index(op.f('ix_processing_histories_key'), 'processing_histories', ['key'], unique=False)
    op.create_index(op.f('ix_processing_histories_organisation_id'), 'processing_histories', ['organisation_id'], unique=False)
    op.create_index('ix_processing_history_scope_key', 'processing_histories', ['organisation_id', 'key'], unique=False)
    op.create_table('structural_features',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('organisation_id', sa.String(length=36), nullable=True),
    sa.Column('key', sa.String(length=160), nullable=False),
    sa.Column('display_name', sa.String(length=300), nullable=False),
    sa.Column('feature_scale', sa.String(length=60), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('organisation_id', 'key', name='uq_structural_feature_scope_key')
    )
    op.create_index(op.f('ix_structural_features_key'), 'structural_features', ['key'], unique=False)
    op.create_index(op.f('ix_structural_features_organisation_id'), 'structural_features', ['organisation_id'], unique=False)
    op.create_table('application_components',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('application_id', sa.String(length=36), nullable=False),
    sa.Column('key', sa.String(length=160), nullable=False),
    sa.Column('display_name', sa.String(length=300), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('operating_conditions', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('application_id', 'key', name='uq_application_component_key')
    )
    op.create_index(op.f('ix_application_components_application_id'), 'application_components', ['application_id'], unique=False)
    op.create_table('processing_steps',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('history_id', sa.String(length=36), nullable=False),
    sa.Column('sequence', sa.Integer(), nullable=False),
    sa.Column('step_kind', sa.String(length=60), nullable=False),
    sa.Column('display_name', sa.String(length=300), nullable=False),
    sa.Column('temperature_k', sa.Float(), nullable=True),
    sa.Column('duration_s', sa.Float(), nullable=True),
    sa.Column('pressure_pa', sa.Float(), nullable=True),
    sa.Column('atmosphere', sa.String(length=120), nullable=True),
    sa.Column('cooling_rate_k_per_s', sa.Float(), nullable=True),
    sa.Column('strain_fraction', sa.Float(), nullable=True),
    sa.Column('parameters', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['history_id'], ['processing_histories.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('history_id', 'sequence', name='uq_processing_step_sequence')
    )
    op.create_index(op.f('ix_processing_steps_history_id'), 'processing_steps', ['history_id'], unique=False)
    op.create_index(op.f('ix_processing_steps_step_kind'), 'processing_steps', ['step_kind'], unique=False)
    op.create_table('reasoning_edges',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('organisation_id', sa.String(length=36), nullable=True),
    sa.Column('edge_kind', sa.String(length=60), nullable=False),
    sa.Column('from_kind', sa.String(length=40), nullable=False),
    sa.Column('from_id', sa.String(length=160), nullable=False),
    sa.Column('to_kind', sa.String(length=40), nullable=False),
    sa.Column('to_id', sa.String(length=160), nullable=False),
    sa.Column('relationship_note', sa.Text(), nullable=True),
    sa.Column('scope', sa.String(length=300), nullable=True),
    sa.Column('conditions', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('evidence_id', sa.String(length=36), nullable=True),
    sa.Column('citation_id', sa.String(length=36), nullable=True),
    sa.Column('source_type', sa.String(length=60), nullable=False),
    sa.Column('source_reference', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['citation_id'], ['citations.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['evidence_id'], ['evidence.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('edge_kind', 'from_kind', 'from_id', 'to_kind', 'to_id', name='uq_reasoning_edge_endpoints')
    )
    op.create_index('ix_reasoning_edge_from', 'reasoning_edges', ['from_kind', 'from_id'], unique=False)
    op.create_index('ix_reasoning_edge_to', 'reasoning_edges', ['to_kind', 'to_id'], unique=False)
    op.create_index(op.f('ix_reasoning_edges_citation_id'), 'reasoning_edges', ['citation_id'], unique=False)
    op.create_index(op.f('ix_reasoning_edges_edge_kind'), 'reasoning_edges', ['edge_kind'], unique=False)
    op.create_index(op.f('ix_reasoning_edges_evidence_id'), 'reasoning_edges', ['evidence_id'], unique=False)
    op.create_index(op.f('ix_reasoning_edges_organisation_id'), 'reasoning_edges', ['organisation_id'], unique=False)
    op.create_index(op.f('ix_reasoning_edges_source_type'), 'reasoning_edges', ['source_type'], unique=False)
    op.create_index(op.f('ix_reasoning_edges_status'), 'reasoning_edges', ['status'], unique=False)
    op.create_table('material_states',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('organisation_id', sa.String(length=36), nullable=True),
    sa.Column('visibility', sa.String(length=20), nullable=False),
    sa.Column('material_id', sa.String(length=36), nullable=True),
    sa.Column('hypothesis_id', sa.String(length=36), nullable=True),
    sa.Column('label', sa.String(length=300), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_reference_state', sa.Boolean(), nullable=False),
    sa.Column('representation_id', sa.String(length=36), nullable=True),
    sa.Column('crystal_system', sa.String(length=60), nullable=True),
    sa.Column('space_group_number', sa.Integer(), nullable=True),
    sa.Column('space_group_symbol', sa.String(length=40), nullable=True),
    sa.Column('lattice_parameters', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('polymorph', sa.String(length=120), nullable=True),
    sa.Column('phase', sa.String(length=120), nullable=True),
    sa.Column('phase_fraction', sa.Float(), nullable=True),
    sa.Column('structure_identity', sa.String(length=64), nullable=True),
    sa.Column('structure_identity_basis', sa.String(length=120), nullable=True),
    sa.Column('composition_signature', sa.String(length=300), nullable=True),
    sa.Column('microstructure_id', sa.String(length=36), nullable=True),
    sa.Column('processing_history_id', sa.String(length=36), nullable=True),
    sa.Column('temperature_k', sa.Float(), nullable=True),
    sa.Column('pressure_pa', sa.Float(), nullable=True),
    sa.Column('environment', sa.String(length=200), nullable=True),
    sa.Column('conditions', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('state_checksum', sa.String(length=64), nullable=False),
    sa.Column('provenance_note', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=30), nullable=False),
    sa.Column('metadata', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('(material_id IS NOT NULL AND hypothesis_id IS NULL) OR (material_id IS NULL AND hypothesis_id IS NOT NULL)', name='ck_material_state_exactly_one_target'),
    sa.ForeignKeyConstraint(['hypothesis_id'], ['candidate_hypotheses.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['material_id'], ['materials.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['microstructure_id'], ['microstructure_descriptors.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], ),
    sa.ForeignKeyConstraint(['processing_history_id'], ['processing_histories.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['representation_id'], ['scientific_representations.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_material_state_identity', 'material_states', ['state_checksum'], unique=False)
    op.create_index('ix_material_state_structure', 'material_states', ['structure_identity'], unique=False)
    op.create_index('ix_material_state_target', 'material_states', ['material_id', 'hypothesis_id'], unique=False)
    op.create_index(op.f('ix_material_states_composition_signature'), 'material_states', ['composition_signature'], unique=False)
    op.create_index(op.f('ix_material_states_hypothesis_id'), 'material_states', ['hypothesis_id'], unique=False)
    op.create_index(op.f('ix_material_states_is_reference_state'), 'material_states', ['is_reference_state'], unique=False)
    op.create_index(op.f('ix_material_states_material_id'), 'material_states', ['material_id'], unique=False)
    op.create_index(op.f('ix_material_states_microstructure_id'), 'material_states', ['microstructure_id'], unique=False)
    op.create_index(op.f('ix_material_states_organisation_id'), 'material_states', ['organisation_id'], unique=False)
    op.create_index(op.f('ix_material_states_phase'), 'material_states', ['phase'], unique=False)
    op.create_index(op.f('ix_material_states_polymorph'), 'material_states', ['polymorph'], unique=False)
    op.create_index(op.f('ix_material_states_processing_history_id'), 'material_states', ['processing_history_id'], unique=False)
    op.create_index(op.f('ix_material_states_representation_id'), 'material_states', ['representation_id'], unique=False)
    op.create_index(op.f('ix_material_states_status'), 'material_states', ['status'], unique=False)
    op.create_index(op.f('ix_material_states_visibility'), 'material_states', ['visibility'], unique=False)
    op.create_table('material_roles',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('component_id', sa.String(length=36), nullable=False),
    sa.Column('key', sa.String(length=160), nullable=False),
    sa.Column('display_name', sa.String(length=300), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('incumbent_material_id', sa.String(length=36), nullable=True),
    sa.Column('incumbent_state_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['component_id'], ['application_components.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['incumbent_material_id'], ['materials.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['incumbent_state_id'], ['material_states.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('component_id', 'key', name='uq_material_role_key')
    )
    op.create_index(op.f('ix_material_roles_component_id'), 'material_roles', ['component_id'], unique=False)
    op.create_index(op.f('ix_material_roles_incumbent_material_id'), 'material_roles', ['incumbent_material_id'], unique=False)
    op.create_index(op.f('ix_material_roles_incumbent_state_id'), 'material_roles', ['incumbent_state_id'], unique=False)
    op.create_table('state_composition_components',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('state_id', sa.String(length=36), nullable=False),
    sa.Column('element', sa.String(length=8), nullable=False),
    sa.Column('role', sa.String(length=40), nullable=False),
    sa.Column('stoichiometry', sa.Float(), nullable=True),
    sa.Column('atomic_fraction', sa.Float(), nullable=True),
    sa.Column('atomic_fraction_min', sa.Float(), nullable=True),
    sa.Column('atomic_fraction_max', sa.Float(), nullable=True),
    sa.Column('concentration_value', sa.Float(), nullable=True),
    sa.Column('concentration_unit', sa.String(length=40), nullable=True),
    sa.Column('original_representation', sa.String(length=200), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['state_id'], ['material_states.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('state_id', 'element', 'role', name='uq_state_component_element_role')
    )
    op.create_index('ix_state_component_element', 'state_composition_components', ['element', 'role'], unique=False)
    op.create_index(op.f('ix_state_composition_components_role'), 'state_composition_components', ['role'], unique=False)
    op.create_index(op.f('ix_state_composition_components_state_id'), 'state_composition_components', ['state_id'], unique=False)
    op.create_table('candidate_reasoning_results',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('organisation_id', sa.String(length=36), nullable=False),
    sa.Column('project_id', sa.String(length=36), nullable=True),
    sa.Column('role_id', sa.String(length=36), nullable=False),
    sa.Column('candidate_id', sa.String(length=36), nullable=True),
    sa.Column('target_kind', sa.String(length=30), nullable=False),
    sa.Column('target_scientific_id', sa.String(length=36), nullable=False),
    sa.Column('state_id', sa.String(length=36), nullable=True),
    sa.Column('requirement_results', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('function_coverage', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('satisfied_requirements', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('failed_requirements', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('unknown_requirements', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('evidence_gaps', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('origin_breakdown', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('assumptions', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('mechanism_paths', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('industrial_assessment_id', sa.String(length=36), nullable=True),
    sa.Column('overall_status', sa.String(length=40), nullable=False),
    sa.Column('generation_rationale', sa.Text(), nullable=True),
    sa.Column('reasoning_checksum', sa.String(length=64), nullable=False),
    sa.Column('policy_version', sa.String(length=40), nullable=False),
    sa.Column('superseded_by_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['replacement_projects.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['role_id'], ['material_roles.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['state_id'], ['material_states.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_candidate_reasoning_checksum', 'candidate_reasoning_results', ['reasoning_checksum'], unique=False)
    op.create_index(op.f('ix_candidate_reasoning_results_candidate_id'), 'candidate_reasoning_results', ['candidate_id'], unique=False)
    op.create_index(op.f('ix_candidate_reasoning_results_industrial_assessment_id'), 'candidate_reasoning_results', ['industrial_assessment_id'], unique=False)
    op.create_index(op.f('ix_candidate_reasoning_results_organisation_id'), 'candidate_reasoning_results', ['organisation_id'], unique=False)
    op.create_index(op.f('ix_candidate_reasoning_results_overall_status'), 'candidate_reasoning_results', ['overall_status'], unique=False)
    op.create_index(op.f('ix_candidate_reasoning_results_project_id'), 'candidate_reasoning_results', ['project_id'], unique=False)
    op.create_index(op.f('ix_candidate_reasoning_results_role_id'), 'candidate_reasoning_results', ['role_id'], unique=False)
    op.create_index(op.f('ix_candidate_reasoning_results_state_id'), 'candidate_reasoning_results', ['state_id'], unique=False)
    op.create_index(op.f('ix_candidate_reasoning_results_superseded_by_id'), 'candidate_reasoning_results', ['superseded_by_id'], unique=False)
    op.create_index(op.f('ix_candidate_reasoning_results_target_scientific_id'), 'candidate_reasoning_results', ['target_scientific_id'], unique=False)
    op.create_index('ix_candidate_reasoning_scope', 'candidate_reasoning_results', ['project_id', 'role_id', 'target_scientific_id'], unique=False)
    op.create_table('material_functions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('role_id', sa.String(length=36), nullable=False),
    sa.Column('key', sa.String(length=160), nullable=False),
    sa.Column('display_name', sa.String(length=300), nullable=False),
    sa.Column('category', sa.String(length=60), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('criticality', sa.Integer(), nullable=False),
    sa.Column('operating_conditions', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['role_id'], ['material_roles.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('role_id', 'key', name='uq_material_function_key')
    )
    op.create_index(op.f('ix_material_functions_category'), 'material_functions', ['category'], unique=False)
    op.create_index(op.f('ix_material_functions_criticality'), 'material_functions', ['criticality'], unique=False)
    op.create_index(op.f('ix_material_functions_role_id'), 'material_functions', ['role_id'], unique=False)
    op.create_table('functional_requirements',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('function_id', sa.String(length=36), nullable=False),
    sa.Column('key', sa.String(length=160), nullable=False),
    sa.Column('display_name', sa.String(length=300), nullable=False),
    sa.Column('requirement_kind', sa.String(length=40), nullable=False),
    sa.Column('direction', sa.String(length=30), nullable=False),
    sa.Column('property_definition_id', sa.String(length=36), nullable=True),
    sa.Column('property_key', sa.String(length=120), nullable=True),
    sa.Column('target_value', sa.Float(), nullable=True),
    sa.Column('target_value_upper', sa.Float(), nullable=True),
    sa.Column('target_unit', sa.String(length=80), nullable=True),
    sa.Column('categorical_target', sa.String(length=160), nullable=True),
    sa.Column('tolerance', sa.Float(), nullable=True),
    sa.Column('weight', sa.Float(), nullable=False),
    sa.Column('conditions', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('rationale', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['function_id'], ['material_functions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['property_definition_id'], ['material_property_definitions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_functional_requirement_property', 'functional_requirements', ['property_definition_id', 'requirement_kind'], unique=False)
    op.create_index(op.f('ix_functional_requirements_function_id'), 'functional_requirements', ['function_id'], unique=False)
    op.create_index(op.f('ix_functional_requirements_property_definition_id'), 'functional_requirements', ['property_definition_id'], unique=False)
    op.create_index(op.f('ix_functional_requirements_property_key'), 'functional_requirements', ['property_key'], unique=False)
    op.create_index(op.f('ix_functional_requirements_requirement_kind'), 'functional_requirements', ['requirement_kind'], unique=False)


def downgrade():
    op.drop_table('candidate_reasoning_results')
    op.drop_table('reasoning_edges')
    op.drop_table('functional_requirements')
    op.drop_table('material_functions')
    op.drop_table('material_roles')
    op.drop_table('application_components')
    op.drop_table('applications')
    op.drop_table('state_composition_components')
    op.drop_table('material_states')
    op.drop_table('microstructure_descriptors')
    op.drop_table('processing_steps')
    op.drop_table('processing_histories')
    op.drop_table('mechanisms')
    op.drop_table('structural_features')
