import pytest
from pydantic import ValidationError

from app.schemas.projects import ConstraintCreate


def test_between_requires_ordered_bounds():
    with pytest.raises(ValidationError):
        ConstraintCreate(property_key="density", comparator="between", target_value=5, target_value_upper=2, target_unit="kg/m^3")


def test_boolean_rejects_numeric_shape():
    with pytest.raises(ValidationError):
        ConstraintCreate(property_key="equipment", comparator="boolean", target_boolean=True, target_value=1, target_unit="1")
