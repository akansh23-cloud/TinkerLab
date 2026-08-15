from sqlalchemy.orm import Session

from app.models.entities import MaterialPropertyDefinition
from app.schemas.projects import ConstraintCreate, ObjectiveCreate
from app.services.units import UnitError, validate_property_unit


class DomainValidationError(ValueError):
    pass


def definition_for(db: Session, key: str) -> MaterialPropertyDefinition:
    definition = db.query(MaterialPropertyDefinition).filter_by(key=key).one_or_none()
    if not definition:
        raise DomainValidationError(f"Unknown property: {key}")
    return definition


def validate_constraint(db: Session, payload: ConstraintCreate) -> MaterialPropertyDefinition:
    d = definition_for(db, payload.property_key)
    if payload.comparator.value not in d.allowed_comparators:
        raise DomainValidationError(f"Comparator {payload.comparator.value} is not allowed for {payload.property_key}")
    if payload.comparator.value == "boolean":
        if d.quantity_type != "boolean":
            raise DomainValidationError(f"Property {payload.property_key} is not boolean")
        return d
    if d.quantity_type == "boolean":
        raise DomainValidationError(f"Property {payload.property_key} requires the boolean comparator")
    try:
        validate_property_unit(payload.property_key, payload.target_unit or "", d.canonical_unit or "")
    except UnitError as exc:
        raise DomainValidationError(str(exc)) from exc
    if not d.allow_negative and payload.target_value is not None and payload.target_value < 0:
        raise DomainValidationError(f"Negative target is not allowed for {payload.property_key}")
    return d


def validate_objective(db: Session, payload: ObjectiveCreate) -> MaterialPropertyDefinition:
    d = definition_for(db, payload.property_key)
    if d.quantity_type == "boolean":
        raise DomainValidationError("Boolean properties are not Phase-1 optimization objectives")
    if payload.target_unit:
        try:
            validate_property_unit(payload.property_key, payload.target_unit, d.canonical_unit or "")
        except UnitError as exc:
            raise DomainValidationError(str(exc)) from exc
    return d
