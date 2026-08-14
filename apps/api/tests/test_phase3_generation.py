from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.db.seed import seed
from app.models.entities import (
    Candidate,
    CandidateHypothesis,
    CandidateSearchSpace,
    GenerationRun,
    GenerationRunResult,
    Material,
    MaterialComponent,
    MaterialPropertyObservation,
    ReplacementProject,
    SearchSpaceComponentRule,
    SubstitutionRule,
)
from app.services.generation import (
    candidate_fingerprint,
    execute_generation,
    get_search_space,
    search_space_checksum,
    structural_screen,
    validate_search_space,
)


def _context(client):
    context = client.get('/demo-context').json()
    project = next(p for p in client.get('/replacement-projects').json() if p['name'] == 'Demo Polymer Replacement Study')
    return context, project, {'X-Organisation-ID': context['organisation_id']}


def _project(db):
    return db.query(ReplacementProject).options(
        selectinload(ReplacementProject.baseline_material),
        selectinload(ReplacementProject.constraints),
        selectinload(ReplacementProject.objectives),
    ).filter_by(name='Demo Polymer Replacement Study').one()


def test_seeded_phase3_demo_has_bounded_run_and_integrity(db):
    project = _project(db)
    space = db.query(CandidateSearchSpace).filter_by(project_id=project.id, active=True).one()
    run = db.query(GenerationRun).filter_by(project_id=project.id, strategy_key='curated_component_substitution').one()
    assert len(space.checksum) == 64
    assert (run.generated_count, run.accepted_count, run.rejected_count, run.duplicate_count) == (3, 1, 1, 1)
    hypotheses = db.query(CandidateHypothesis).filter_by(project_id=project.id).all()
    assert hypotheses
    assert any(h.structural_validity == 'invalid' for h in hypotheses)
    # Hypotheses are not canonical materials and cannot own Phase-2 material observations.
    material_ids = {m.id for m in db.query(Material).all()}
    assert all(h.id not in material_ids for h in hypotheses)


def test_candidate_exactly_one_target_constraint(db):
    project = _project(db)
    bad = Candidate(project_id=project.id, candidate_kind='known_material', material_id=None, hypothesis_id=None, candidate_source='manual', status='proposed')
    db.add(bad)
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_fingerprint_is_deterministic_and_label_order_independent():
    a = [
        {'component_key':'b','display_name':'ignored label','role':'modifier','amount':20.0,'unit':'%','basis':'weight_percent','locked':False},
        {'component_key':'a','display_name':'another label','role':'matrix','amount':80.0,'unit':'%','basis':'weight_percent','locked':False},
    ]
    b = [
        {'component_key':'a','display_name':'renamed','role':'matrix','amount':80,'unit':'%','basis':'weight_percent','locked':False},
        {'component_key':'b','display_name':'renamed too','role':'modifier','amount':20,'unit':'%','basis':'weight_percent','locked':False},
    ]
    fp1 = candidate_fingerprint('polymer', a, [])
    fp2 = candidate_fingerprint('polymer', b, [])
    assert fp1 == fp2
    b[1]['amount'] = 19.5
    assert candidate_fingerprint('polymer', b, []) != fp1
    assert candidate_fingerprint('polymer', a, [{'parameter_key':'temperature','value':110,'unit':'degC'}]) != fp1


def test_search_space_checksum_stable(db):
    project = _project(db)
    space = get_search_space(db, db.query(CandidateSearchSpace).filter_by(project_id=project.id, active=True).one().id)
    assert search_space_checksum(space) == space.checksum
    before = space.checksum
    # Non-semantic note does not participate in the scientific checksum.
    space.notes = 'editorial note changed'
    assert search_space_checksum(space) == before
    db.rollback()


def test_search_space_validation_and_structural_prohibition(db):
    project = _project(db)
    space = get_search_space(db, db.query(CandidateSearchSpace).filter_by(project_id=project.id, active=True).one().id)
    result = validate_search_space(db, space, 'bounded_composition_variation')
    assert result['valid'] is True
    assert result['estimated_cardinality'] == 3
    reasons = structural_screen(space, [
        {'component_key':'base_resin_a','amount':78,'unit':'%','basis':'weight_percent'},
        {'component_key':'modifier_b','amount':18,'unit':'%','basis':'weight_percent'},
        {'component_key':'reinforcement_c','amount':4,'unit':'%','basis':'weight_percent'},
        {'component_key':'restricted_demo_component','amount':0,'unit':'%','basis':'weight_percent'},
    ], [])
    assert 'prohibited_component_present' in reasons


def test_redacted_baseline_mutation_is_blocked(db):
    org_id = db.query(ReplacementProject).first().organisation_id
    user_id = db.query(ReplacementProject).first().created_by
    redacted_material = db.query(Material).filter_by(canonical_name='demo-polymer-c').one()
    redacted_component = db.query(MaterialComponent).filter_by(material_id=redacted_material.id, is_redacted=True).one()
    project = ReplacementProject(id=str(uuid.uuid4()), organisation_id=org_id, name='Redacted mutation test', baseline_material_id=redacted_material.id, replacement_reasons=['cost'], status='draft', created_by=user_id)
    db.add(project); db.flush()
    space = CandidateSearchSpace(id=str(uuid.uuid4()), project_id=project.id, organisation_id=org_id, version=1, material_family='polymer', amount_basis='weight_percent', candidate_budget=10, maximum_enumeration=50, checksum='pending')
    db.add(space); db.flush()
    db.add(SearchSpaceComponentRule(id=str(uuid.uuid4()), search_space_id=space.id, baseline_component_id=redacted_component.id, component_key='private_component', display_name='Private component', mutable=True, min_amount=1, max_amount=2, step_amount=1, amount_unit='%', amount_basis='weight_percent'))
    db.flush(); space = get_search_space(db, space.id); space.checksum = search_space_checksum(space)
    result = validate_search_space(db, space, 'bounded_composition_variation')
    assert result['valid'] is False
    assert 'REDACTED_BASELINE_COMPONENT' in {i['code'] for i in result['issues']}
    db.rollback()


def test_generation_preview_does_not_persist(client, db):
    context, project, headers = _context(client)
    space = db.query(CandidateSearchSpace).filter_by(project_id=project['id'], active=True).one()
    before_runs = db.query(GenerationRun).count(); before_hypotheses = db.query(CandidateHypothesis).count()
    response = client.post(f"/replacement-projects/{project['id']}/generation-runs/preview", headers=headers, json={
        'search_space_id': space.id, 'strategy_key':'bounded_composition_variation', 'random_seed':77, 'candidate_budget':2, 'configuration':{}
    })
    assert response.status_code == 200, response.text
    body = response.json(); assert body['valid'] is True; assert body['estimated_cardinality'] == 3; assert body['expected_truncation'] is True
    assert db.query(GenerationRun).count() == before_runs
    assert db.query(CandidateHypothesis).count() == before_hypotheses


def test_same_generation_envelope_reproduces_ordered_fingerprints(db):
    project = _project(db); space = get_search_space(db, db.query(CandidateSearchSpace).filter_by(project_id=project.id, active=True).one().id)
    r1 = execute_generation(db, project, space, 'bounded_composition_variation', 99, 2, {'test':'repro'}, project.created_by)
    rows1 = db.query(GenerationRunResult).filter_by(generation_run_id=r1.id).order_by(GenerationRunResult.sequence).all()
    r2 = execute_generation(db, project, space, 'bounded_composition_variation', 99, 2, {'test':'repro'}, project.created_by)
    rows2 = db.query(GenerationRunResult).filter_by(generation_run_id=r2.id).order_by(GenerationRunResult.sequence).all()
    assert [x.candidate_fingerprint for x in rows1] == [x.candidate_fingerprint for x in rows2]
    assert r1.result_checksum == r2.result_checksum
    assert r2.duplicate_count == 2


def test_hypothesis_comparison_is_unknown_not_inherited(client, db):
    context, project, headers = _context(client)
    response = client.get(f"/replacement-projects/{project['id']}/comparison?include_hypotheses=true", headers=headers)
    assert response.status_code == 200
    hypotheses = [x for x in response.json() if x['candidate_kind'] == 'hypothesis']
    assert hypotheses
    for item in hypotheses:
        assert item['completeness'] == 0
        assert item['hard_passed'] == 0 and item['hard_failed'] == 0
        assert {x['status'] for x in item['constraints']} == {'UNKNOWN'}
        assert all(x['selected_observation_id'] is None for x in item['constraints'])
        assert item['evidence_posture'].startswith('UNKNOWN')


def test_hypothesis_has_zero_fabricated_property_observations(db):
    before = db.query(MaterialPropertyObservation).count()
    project = _project(db); space = get_search_space(db, db.query(CandidateSearchSpace).filter_by(project_id=project.id, active=True).one().id)
    execute_generation(db, project, space, 'bounded_process_variation', 5, 2, {}, project.created_by)
    after = db.query(MaterialPropertyObservation).count()
    assert after == before


def test_known_material_retrieval_is_deterministic_and_preserves_unknown(db):
    project = _project(db); space = get_search_space(db, db.query(CandidateSearchSpace).filter_by(project_id=project.id, active=True).one().id)
    r1 = execute_generation(db, project, space, 'known_material_retrieval', 0, 20, {}, project.created_by)
    r2 = execute_generation(db, project, space, 'known_material_retrieval', 999, 20, {}, project.created_by)
    a = db.query(GenerationRunResult).filter_by(generation_run_id=r1.id).order_by(GenerationRunResult.sequence).all()
    b = db.query(GenerationRunResult).filter_by(generation_run_id=r2.id).order_by(GenerationRunResult.sequence).all()
    assert [x.material_id for x in a] == [x.material_id for x in b]
    assert r1.result_checksum == r2.result_checksum
    # Incomplete-evidence material remains retrievable; retrieval does not fabricate its missing observations.
    incomplete = db.query(Material).filter_by(canonical_name='demo-polymer-c').one()
    assert incomplete.id in {x.material_id for x in a}


def test_only_approved_substitution_rules_are_automatic(db):
    project = _project(db); space = get_search_space(db, db.query(CandidateSearchSpace).filter_by(project_id=project.id, active=True).one().id)
    draft = SubstitutionRule(id=str(uuid.uuid4()), organisation_id=project.organisation_id, project_id=project.id, material_family='polymer', source_component_key='modifier_b', replacement_component_key='draft_only_x', replacement_display_name='Draft Only X', reason='Must never be applied automatically while draft.', status='draft', version=1)
    db.add(draft); db.commit()
    run = execute_generation(db, project, space, 'curated_component_substitution', 0, 20, {}, project.created_by)
    results = db.query(GenerationRunResult).filter_by(generation_run_id=run.id).all()
    hypothesis_ids = [x.hypothesis_id for x in results if x.hypothesis_id]
    hypotheses = db.query(CandidateHypothesis).options(selectinload(CandidateHypothesis.components)).filter(CandidateHypothesis.id.in_(hypothesis_ids)).all()
    assert all('draft_only_x' not in {c.component_key for c in h.components} for h in hypotheses)


def test_phase3_routes_require_organisation_scope(client, db):
    _, project, headers = _context(client)
    db.query(CandidateSearchSpace).filter_by(project_id=project['id'], active=True).one()
    assert client.get(f"/replacement-projects/{project['id']}/search-spaces").status_code == 404
    assert client.get(f"/replacement-projects/{project['id']}/search-spaces", headers=headers).status_code == 200
    run = db.query(GenerationRun).filter_by(project_id=project['id']).first()
    assert client.get(f"/generation-runs/{run.id}").status_code == 404
    assert client.get(f"/generation-runs/{run.id}", headers=headers).status_code == 200
    hypothesis = db.query(CandidateHypothesis).filter_by(project_id=project['id']).first()
    assert client.get(f"/replacement-projects/{project['id']}/comparison?include_hypotheses=true").status_code == 404
    assert client.get(f"/candidate-hypotheses/{hypothesis.id}").status_code == 404
    assert client.get(f"/candidate-hypotheses/{hypothesis.id}", headers=headers).status_code == 200


def test_candidate_lab_paginates_known_and_hypothesis(client):
    context, project, headers = _context(client)
    response = client.get(f"/replacement-projects/{project['id']}/candidate-lab?offset=0&limit=2", headers=headers)
    assert response.status_code == 200
    body = response.json(); assert body['total'] >= 6; assert len(body['items']) == 2
    full = client.get(f"/replacement-projects/{project['id']}/candidate-lab?offset=0&limit=100", headers=headers).json()
    assert {'known_material','hypothesis'} <= {x['candidate_kind'] for x in full['items']}
    assert any(x['evidence_posture'].startswith('UNKNOWN') for x in full['items'] if x['candidate_kind']=='hypothesis')


def test_seed_remains_idempotent_with_phase3(db):
    counts_before = {
        'spaces': db.query(CandidateSearchSpace).count(), 'rules': db.query(SubstitutionRule).count(),
        'runs': db.query(GenerationRun).count(), 'hypotheses': db.query(CandidateHypothesis).count(), 'candidates': db.query(Candidate).count(),
    }
    seed(db)
    counts_after = {
        'spaces': db.query(CandidateSearchSpace).count(), 'rules': db.query(SubstitutionRule).count(),
        'runs': db.query(GenerationRun).count(), 'hypotheses': db.query(CandidateHypothesis).count(), 'candidates': db.query(Candidate).count(),
    }
    assert counts_after == counts_before


def test_search_space_api_validate_and_clone_is_versioned(client, db):
    _, project, headers = _context(client)
    spaces = client.get(f"/replacement-projects/{project['id']}/search-spaces", headers=headers).json()
    active = next(x for x in spaces if x['active'])
    validated = client.post(
        f"/replacement-projects/{project['id']}/search-spaces/{active['id']}/validate?strategy_key=bounded_composition_variation",
        headers=headers,
    )
    assert validated.status_code == 200
    assert validated.json()['valid'] is True
    cloned = client.post(f"/replacement-projects/{project['id']}/search-spaces/{active['id']}/clone", headers=headers)
    assert cloned.status_code == 201, cloned.text
    body = cloned.json()
    assert body['version'] == max(x['version'] for x in spaces) + 1
    assert body['active'] is False
    assert body['checksum'] != active['checksum']  # version is part of the auditable search-space checksum
    assert [(x['component_key'],x['min_amount'],x['max_amount']) for x in body['component_rules']] == [(x['component_key'],x['min_amount'],x['max_amount']) for x in active['component_rules']]


def test_substitution_rule_status_requires_scope_and_is_auditable(client, db):
    _, project, headers = _context(client)
    rules = client.get(f"/replacement-projects/{project['id']}/substitution-rules", headers=headers).json()
    rule = next(x for x in rules if x['status'] == 'approved')
    assert client.post(f"/substitution-rules/{rule['id']}/disable").status_code == 404
    disabled = client.post(f"/substitution-rules/{rule['id']}/disable", headers=headers)
    assert disabled.status_code == 200
    assert disabled.json()['status'] == 'disabled'
    assert disabled.json()['version'] == rule['version'] + 1
    approved = client.post(f"/substitution-rules/{rule['id']}/approve", headers=headers)
    assert approved.status_code == 200
    assert approved.json()['status'] == 'approved'


def test_manual_hypothesis_api_uses_unknown_property_posture(client, db):
    context, project, headers = _context(client)
    before_observations = db.query(MaterialPropertyObservation).count()
    response = client.post(f"/replacement-projects/{project['id']}/hypotheses/manual", headers=headers, json={
        'display_label':'Manual integrity hypothesis API', 'material_family':'polymer',
        'components':[
            {'component_key':'base_resin_a','display_name':'Base Resin A','role':'matrix','amount':77.5,'unit':'%','basis':'weight_percent'},
            {'component_key':'modifier_b','display_name':'Modifier B','role':'modifier','amount':18.5,'unit':'%','basis':'weight_percent'},
            {'component_key':'reinforcement_c','display_name':'Reinforcement C','role':'reinforcement','amount':4.0,'unit':'%','basis':'weight_percent','locked':True},
        ], 'process_parameters':[], 'notes':'Synthetic manual Phase-3 hypothesis.'
    })
    assert response.status_code == 201, response.text
    h = response.json()
    assert 'not yet predicted' in h['warning'].lower()
    assert db.query(MaterialPropertyObservation).count() == before_observations
    comparison = client.get(f"/replacement-projects/{project['id']}/comparison?include_hypotheses=true", headers=headers).json()
    item = next(x for x in comparison if x['hypothesis_id'] == h['id'])
    assert item['completeness'] == 0
    assert {c['status'] for c in item['constraints']} == {'UNKNOWN'}


def test_bounded_process_variation_only_uses_configured_values(db):
    project = _project(db)
    space = get_search_space(db, db.query(CandidateSearchSpace).filter_by(project_id=project.id, active=True).one().id)
    run = execute_generation(db, project, space, 'bounded_process_variation', 2026, 3, {'test':'process-bounds'}, project.created_by)
    rows = db.query(GenerationRunResult).filter_by(generation_run_id=run.id).order_by(GenerationRunResult.sequence).all()
    values = []
    for row in rows:
        if not row.hypothesis_id:
            continue
        hypothesis = db.query(CandidateHypothesis).options(selectinload(CandidateHypothesis.process_parameters)).filter_by(id=row.hypothesis_id).one()
        values.extend((p.parameter_key, p.value, p.unit) for p in hypothesis.process_parameters)
    assert values
    assert all(key == 'generic_process_temperature' and unit == 'degC' and value in {100.0,110.0,120.0} for key,value,unit in values)


def test_composition_variation_preserves_locked_component_and_total(db):
    project = _project(db)
    space = get_search_space(db, db.query(CandidateSearchSpace).filter_by(project_id=project.id, active=True).one().id)
    run = execute_generation(db, project, space, 'bounded_composition_variation', 17, 3, {'test':'locked-total'}, project.created_by)
    rows = db.query(GenerationRunResult).filter_by(generation_run_id=run.id).all()
    for row in rows:
        hypothesis = db.query(CandidateHypothesis).options(selectinload(CandidateHypothesis.components)).filter_by(id=row.hypothesis_id).one()
        by_key = {c.component_key:c for c in hypothesis.components}
        assert by_key['reinforcement_c'].amount == 4.0
        assert by_key['reinforcement_c'].locked is True
        assert abs(sum(c.amount or 0 for c in hypothesis.components) - 100.0) <= space.total_tolerance
        assert 16.0 <= by_key['modifier_b'].amount <= 20.0


def test_invalid_hypothesis_cannot_be_accepted_for_screening(client, db):
    _, project, headers = _context(client)
    invalid = db.query(CandidateHypothesis).filter_by(project_id=project['id'], structural_validity='invalid').first()
    assert invalid is not None
    response = client.post(f"/candidate-hypotheses/{invalid.id}/status?status=accepted_for_screening", headers=headers)
    assert response.status_code == 422


def test_generation_preview_budget_is_bounded_by_search_space(client, db):
    _, project, headers = _context(client)
    space = db.query(CandidateSearchSpace).filter_by(project_id=project['id'], active=True).one()
    response = client.post(f"/replacement-projects/{project['id']}/generation-runs/preview", headers=headers, json={
        'search_space_id':space.id, 'strategy_key':'bounded_composition_variation', 'random_seed':1,
        'candidate_budget':1000, 'configuration':{'test':'budget-cap'}
    })
    assert response.status_code == 200
    assert response.json()['candidate_budget'] == space.candidate_budget
