import pytest

from equivalence_core.identifiers import IdentifierScheme
from equivalence_core.templates import TemplateDefinition, load_seed_templates
from equivalence_core.validation import InvalidValue, validate_value
from equivalence_core.values import (
    BoolValue,
    EnumValue,
    IdentifierValue,
    NumberValue,
    TextValue,
)


@pytest.fixture(scope="module")
def needle() -> TemplateDefinition:
    return load_seed_templates()["hypodermic_needle"]


@pytest.fixture(scope="module")
def syringe() -> TemplateDefinition:
    return load_seed_templates()["syringe_single_use"]


def test_enum_spellings_become_codes(syringe: TemplateDefinition) -> None:
    connector = syringe.attribute("connector")

    assert validate_value(connector, EnumValue(value="Luer-Lock")) == EnumValue(value="LUER_LOCK")
    assert validate_value(connector, EnumValue(value="LUER")) == EnumValue(value="LUER")


def test_enum_case_differences_are_accepted(syringe: TemplateDefinition) -> None:
    mdr_class = syringe.attribute("mdr_class")

    assert validate_value(mdr_class, EnumValue(value="IIa")) == EnumValue(value="IIA")


def test_unknown_enum_value_is_rejected(syringe: TemplateDefinition) -> None:
    with pytest.raises(InvalidValue, match="connector"):
        validate_value(syringe.attribute("connector"), EnumValue(value="bayonet"))


def test_numbers_are_converted_to_the_canonical_unit(needle: TemplateDefinition) -> None:
    length = needle.attribute("length_mm")

    assert validate_value(length, NumberValue(value=4, unit="cm")) == NumberValue(
        value=40, unit="mm"
    )


def test_an_incompatible_unit_is_rejected(needle: TemplateDefinition) -> None:
    with pytest.raises(InvalidValue, match="cannot be read as mm"):
        validate_value(needle.attribute("length_mm"), NumberValue(value=4, unit="ml"))


def test_a_wrong_type_is_rejected(syringe: TemplateDefinition) -> None:
    with pytest.raises(InvalidValue, match="expects a bool"):
        validate_value(syringe.attribute("sterile"), TextValue(value="yes"))


def test_identifiers_are_never_attribute_values(syringe: TemplateDefinition) -> None:
    gtin = IdentifierValue(
        scheme=IdentifierScheme.GTIN, value="04040456781234", checksum_valid=True
    )

    with pytest.raises(InvalidValue, match="identifiers"):
        validate_value(syringe.attribute("sterile"), gtin)


def test_other_types_pass_unchanged(syringe: TemplateDefinition) -> None:
    assert validate_value(syringe.attribute("sterile"), BoolValue(value=True)) == BoolValue(
        value=True
    )
