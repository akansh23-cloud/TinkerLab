import pytest

from app.services.units import UnitError, convert, validate_property_unit


def test_pressure_conversion():
    assert convert(1, "MPa", "Pa") == pytest.approx(1_000_000)


def test_density_conversion():
    assert convert(1.35, "g/cm^3", "kg/m^3") == pytest.approx(1350)


def test_temperature_affine_conversion():
    assert convert(0, "degC", "K") == pytest.approx(273.15)
    assert convert(373.15, "K", "degC") == pytest.approx(100)


def test_incompatible_units_rejected():
    with pytest.raises(UnitError):
        convert(5, "MPa", "kg/m^3")


def test_property_dimension_rejected():
    with pytest.raises(UnitError):
        validate_property_unit("density", "MPa", "kg/m^3")
