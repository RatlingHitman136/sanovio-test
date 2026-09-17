import pytest
from pydantic import TypeAdapter, ValidationError

from equivalence_core.identifiers import IdentifierScheme
from equivalence_core.values import (
    AttributeValue,
    BoolValue,
    IdentifierValue,
    ListValue,
    NumberValue,
    TypedValue,
)

typed = TypeAdapter(TypedValue)
attribute = TypeAdapter(AttributeValue)


@pytest.mark.parametrize(
    "value",
    [
        NumberValue(value=10, unit="ml"),
        BoolValue(value=True),
        ListValue(value=("DIN_EN_ISO_7886_1",)),
        IdentifierValue(scheme=IdentifierScheme.GTIN, value="04040456781234", checksum_valid=True),
    ],
)
def test_values_round_trip_through_json(value: TypedValue) -> None:
    assert typed.validate_json(typed.dump_json(value)) == value


def test_shape_follows_the_data_model() -> None:
    assert typed.validate_python({"type": "enum", "value": "LUER_LOCK"}).model_dump() == {
        "type": "enum",
        "value": "LUER_LOCK",
    }


def test_unknown_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        typed.validate_python({"type": "date", "value": "2026-09-17"})


def test_extra_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        typed.validate_python({"type": "bool", "value": True, "quote": "steril"})


def test_attribute_values_cannot_hold_identifiers() -> None:
    with pytest.raises(ValidationError):
        attribute.validate_python(
            {"type": "identifier", "scheme": "GTIN", "value": "1", "checksum_valid": None}
        )
