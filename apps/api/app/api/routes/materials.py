from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.deps import scope_organisation
from app.db.session import get_db
from app.models.entities import (
    Evidence,
    Material,
    MaterialComponent,
    MaterialIdentifier,
    MaterialProcessState,
    MaterialPropertyDefinition,
    MaterialPropertyObservation,
    ObservationConditionSet,
    ReplacementProject,
)
from app.schemas.materials import (
    EvidenceCreate,
    EvidenceOut,
    MaterialComponentCreate,
    MaterialComponentOut,
    MaterialCreate,
    MaterialDetail,
    MaterialIdentifierCreate,
    MaterialIdentifierOut,
    MaterialProcessStateCreate,
    MaterialProcessStateOut,
    MaterialSummary,
    ObservationCreate,
    ObservationOut,
    PropertyDefinitionOut,
)
from app.services.conditions import validate_condition_values
from app.services.identity import normalize_identifier
from app.services.units import UnitError, validate_property_unit

router = APIRouter(prefix="/materials", tags=["materials"])


def _visible(query, organisation_id: str | None):
    if organisation_id:
        return query.filter(or_(Material.visibility == "public", Material.owner_organisation_id == organisation_id))
    return query.filter(Material.visibility == "public")


def _get_visible_material(db: Session, material_id: str, organisation_id: str | None) -> Material:
    query = db.query(Material).filter(Material.id == material_id)
    material: Material | None = _visible(query, organisation_id).one_or_none()
    if not material:
        raise HTTPException(404, "Material not found")
    return material


@router.get("", response_model=list[MaterialSummary])
def list_materials(
    q: str | None = Query(default=None), family: str | None = Query(default=None), conflict_only: bool = False,
    organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db),
):
    query = _visible(db.query(Material), organisation_id)
    if q:
        query = query.filter(or_(Material.display_name.ilike(f"%{q}%"), Material.canonical_name.ilike(f"%{q}%")))
    if family:
        query = query.filter(Material.material_family == family)
    # conflict_only is intentionally handled in the dedicated conflict endpoint to avoid N+1 scans here.
    if conflict_only:
        query = query.filter(Material.id == "__use_conflict_endpoint__")
    return query.order_by(Material.display_name).limit(200).all()


@router.post("", response_model=MaterialSummary, status_code=201)
def create_material(payload: MaterialCreate, db: Session = Depends(get_db)):
    values = payload.model_dump(mode="json")
    material = Material(**values, is_seed_data=False)
    db.add(material)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Material canonical_name already exists") from exc
    db.refresh(material)
    return material


@router.get("/{material_id}", response_model=MaterialDetail)
def get_material(material_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    material = (
        _visible(
            db.query(Material).options(
                selectinload(Material.identifiers), selectinload(Material.components), selectinload(Material.process_states),
                selectinload(Material.observations).selectinload(MaterialPropertyObservation.property_definition),
                selectinload(Material.observations).selectinload(MaterialPropertyObservation.condition_set),
                selectinload(Material.observations).selectinload(MaterialPropertyObservation.evidence).selectinload(Evidence.provider),
                selectinload(Material.observations).selectinload(MaterialPropertyObservation.evidence).selectinload(Evidence.source_record),
                selectinload(Material.observations).selectinload(MaterialPropertyObservation.evidence).selectinload(Evidence.citation),
            ), organisation_id
        )
        .filter(Material.id == material_id).one_or_none()
    )
    if not material:
        raise HTTPException(404, "Material not found")
    return material


@router.get("/{material_id}/projects")
def material_usage(material_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    _get_visible_material(db, material_id, organisation_id)
    # Replacement projects are organisation-owned. Without an explicit organisation
    # scope we intentionally expose no project metadata, even for public materials.
    if organisation_id is None:
        return []
    rows = (
        db.query(ReplacementProject)
        .filter(
            ReplacementProject.baseline_material_id == material_id,
            ReplacementProject.organisation_id == organisation_id,
        )
        .all()
    )
    return [{"id": p.id, "name": p.name, "status": p.status} for p in rows]


@router.get("/{material_id}/identifiers", response_model=list[MaterialIdentifierOut])
def identifiers(material_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    _get_visible_material(db, material_id, organisation_id)
    query = db.query(MaterialIdentifier).filter(MaterialIdentifier.material_id == material_id)
    if organisation_id:
        query = query.filter(or_(MaterialIdentifier.visibility == "public", MaterialIdentifier.organisation_id == organisation_id))
    else:
        query = query.filter(MaterialIdentifier.visibility == "public")
    return query.order_by(MaterialIdentifier.is_primary.desc(), MaterialIdentifier.namespace).all()


@router.post("/{material_id}/identifiers", response_model=MaterialIdentifierOut, status_code=201)
def add_identifier(material_id: str, payload: MaterialIdentifierCreate, db: Session = Depends(get_db)):
    material = db.get(Material, material_id)
    if not material:
        raise HTTPException(404, "Material not found")
    if payload.visibility.value == "private" and material.visibility == "public":
        raise HTTPException(422, "Private identifiers cannot be attached to a public material in Phase 2")
    normalized = normalize_identifier(payload.namespace, payload.value)
    existing_query = db.query(MaterialIdentifier).filter_by(namespace=payload.namespace, normalized_value=normalized)
    if payload.organisation_id is None:
        existing_query = existing_query.filter(MaterialIdentifier.organisation_id.is_(None))
    else:
        existing_query = existing_query.filter(MaterialIdentifier.organisation_id == payload.organisation_id)
    if existing_query.first(): raise HTTPException(409, "Identifier already exists in this namespace/scope")
    ident = MaterialIdentifier(material_id=material_id, normalized_value=normalized, **payload.model_dump(mode="json"))
    db.add(ident)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback(); raise HTTPException(409, "Identifier already exists in this namespace/scope") from exc
    db.refresh(ident); return ident


@router.get("/{material_id}/composition", response_model=list[MaterialComponentOut])
def composition(material_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    _get_visible_material(db, material_id, organisation_id)
    return db.query(MaterialComponent).filter_by(material_id=material_id).order_by(MaterialComponent.sequence).all()


@router.post("/{material_id}/composition", response_model=MaterialComponentOut, status_code=201)
def add_component(material_id: str, payload: MaterialComponentCreate, db: Session = Depends(get_db)):
    if not db.get(Material, material_id): raise HTTPException(404, "Material not found")
    values = payload.model_dump(mode="json"); values["amount_basis"] = str(payload.amount_basis.value)
    component = MaterialComponent(material_id=material_id, **values)
    db.add(component); db.commit(); db.refresh(component); return component


@router.get("/{material_id}/process-state", response_model=list[MaterialProcessStateOut])
def process_state(material_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    _get_visible_material(db, material_id, organisation_id)
    return db.query(MaterialProcessState).filter_by(material_id=material_id).order_by(MaterialProcessState.sequence).all()


@router.post("/{material_id}/process-state", response_model=MaterialProcessStateOut, status_code=201)
def add_process_state(material_id: str, payload: MaterialProcessStateCreate, db: Session = Depends(get_db)):
    if not db.get(Material, material_id): raise HTTPException(404, "Material not found")
    state = MaterialProcessState(material_id=material_id, **payload.model_dump(mode="json"))
    db.add(state); db.commit(); db.refresh(state); return state


@router.get("/{material_id}/observations", response_model=list[ObservationOut])
def observations(material_id: str, organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    _get_visible_material(db, material_id, organisation_id)
    return (
        db.query(MaterialPropertyObservation).options(
            selectinload(MaterialPropertyObservation.property_definition), selectinload(MaterialPropertyObservation.condition_set),
            selectinload(MaterialPropertyObservation.evidence).selectinload(Evidence.provider),
            selectinload(MaterialPropertyObservation.evidence).selectinload(Evidence.source_record),
            selectinload(MaterialPropertyObservation.evidence).selectinload(Evidence.citation),
        ).filter_by(material_id=material_id).order_by(MaterialPropertyObservation.created_at.desc()).all()
    )


@router.post("/{material_id}/observations", response_model=ObservationOut, status_code=201)
def add_observation(material_id: str, payload: ObservationCreate, db: Session = Depends(get_db)):
    material = db.get(Material, material_id)
    if not material: raise HTTPException(404, "Material not found")
    definition = db.query(MaterialPropertyDefinition).filter_by(key=payload.property_key).one_or_none()
    if not definition: raise HTTPException(422, f"Unknown property {payload.property_key}")
    evidence = db.get(Evidence, payload.evidence_id)
    if not evidence: raise HTTPException(422, "Evidence not found")
    if evidence.visibility == "private" and material.visibility == "public":
        raise HTTPException(422, "Private evidence cannot be attached to a public material")
    if payload.value_type == "boolean":
        if definition.quantity_type != "boolean": raise HTTPException(422, f"Property {payload.property_key} is not boolean")
    else:
        if definition.quantity_type == "boolean": raise HTTPException(422, f"Property {payload.property_key} requires a boolean observation")
        try:
            validate_property_unit(payload.property_key, payload.unit or "", definition.canonical_unit or "")
        except UnitError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not definition.allow_negative and payload.numeric_value is not None and payload.numeric_value < 0:
            raise HTTPException(422, f"Negative values are not allowed for {payload.property_key}")
    condition = None
    if payload.condition_set:
        try: validate_condition_values(payload.condition_set)
        except UnitError as exc: raise HTTPException(422, str(exc)) from exc
        condition = ObservationConditionSet(**payload.condition_set.model_dump(exclude={"metadata"}), metadata_json=payload.condition_set.metadata)
        db.add(condition); db.flush()
    observation = MaterialPropertyObservation(
        material_id=material_id, property_definition_id=definition.id, value_type=payload.value_type,
        numeric_value=payload.numeric_value, boolean_value=payload.boolean_value, unit=payload.unit,
        evidence_id=payload.evidence_id, conditions=payload.conditions, condition_set_id=condition.id if condition else None,
        uncertainty=payload.uncertainty, uncertainty_type=payload.uncertainty_type,
        uncertainty_lower=payload.uncertainty_lower, uncertainty_upper=payload.uncertainty_upper,
        uncertainty_stddev=payload.uncertainty_stddev, confidence=payload.confidence, method=payload.method,
        source_record_id=payload.source_record_id,
    )
    db.add(observation); db.commit(); db.refresh(observation)
    observation.property_definition = definition; observation.evidence = evidence; observation.condition_set = condition
    return observation


property_router = APIRouter(tags=["properties"])

@property_router.get("/property-definitions", response_model=list[PropertyDefinitionOut])
def property_definitions(db: Session = Depends(get_db)):
    return db.query(MaterialPropertyDefinition).order_by(MaterialPropertyDefinition.display_name).all()


evidence_router = APIRouter(tags=["evidence"])

@evidence_router.get("/evidence", response_model=list[EvidenceOut])
def list_evidence(organisation_id: str | None = Depends(scope_organisation), db: Session = Depends(get_db)):
    query = db.query(Evidence)
    if organisation_id: query = query.filter(or_(Evidence.visibility == "public", Evidence.organisation_id == organisation_id))
    else: query = query.filter(Evidence.visibility == "public")
    return query.order_by(Evidence.created_at.desc()).limit(200).all()

@evidence_router.post("/evidence", response_model=EvidenceOut, status_code=201)
def create_evidence(payload: EvidenceCreate, db: Session = Depends(get_db)):
    values = payload.model_dump(mode="json"); metadata = values.pop("metadata")
    evidence = Evidence(**values, metadata_json=metadata)
    db.add(evidence); db.commit(); db.refresh(evidence); return evidence
