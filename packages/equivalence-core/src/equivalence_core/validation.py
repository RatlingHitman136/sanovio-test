"""Checks a typed value against its attribute definition before it becomes a fact.

Used for every value that does not come from the core parsers: purchaser answers, LLM output,
reference values reported by the client and, later, supplier answers.
"""

from equivalence_core.parsers.synonyms import normalize_code
from equivalence_core.parsers.units import UnitError, to_canonical
from equivalence_core.templates.model import AttributeDefinition
from equivalence_core.values import (
    AttributeValue,
    EnumValue,
    IdentifierValue,
    NumberValue,
    TypedValue,
)


class InvalidValue(ValueError):
    """The value does not fit the attribute; the message is safe to show to the user."""


def validate_value(definition: AttributeDefinition, value: TypedValue) -> AttributeValue:
    """The value in its stored form: enum spellings become codes, numbers the canonical unit."""
    if isinstance(value, IdentifierValue):
        raise InvalidValue(f"{definition.key}: identifiers are not attribute values")
    if value.type != definition.type.value:
        raise InvalidValue(f"{definition.key} expects a {definition.type} value, not {value.type}")
    if isinstance(value, EnumValue):
        code = normalize_code(definition, value.value)
        if code is None:
            raise InvalidValue(
                f"{definition.key}: {value.value!r} is not one of {definition.options}"
            )
        return EnumValue(value=code)
    if isinstance(value, NumberValue):
        # A number attribute always has a unit (enforced by AttributeDefinition).
        unit = definition.unit or ""
        try:
            return NumberValue(value=to_canonical(value.value, value.unit, unit), unit=unit)
        except UnitError as exc:
            raise InvalidValue(
                f"{definition.key}: {value.unit!r} cannot be read as {unit}"
            ) from exc
    return value
