"""Turns a model's plain JSON value into the typed value its attribute asks for.

The model is only ever asked for `true`, `12.5`, `"LUER_LOCK"` or a list; the attribute
definition decides the shape, and `validate_value` then checks it like any other input.
"""

from equivalence_core.templates import AttributeDefinition, ValueType
from equivalence_core.validation import InvalidValue, validate_value
from equivalence_core.values import (
    AttributeValue,
    BoolValue,
    EnumValue,
    ListValue,
    NumberValue,
    TextValue,
)

type PlainValue = bool | float | str | list[str]


def typed_value(
    definition: AttributeDefinition, raw: PlainValue | None, unit: str | None = None
) -> AttributeValue | None:
    """The checked value, or None when the plain value cannot mean anything for this attribute."""
    shaped = _shape(definition, raw, unit)
    if shaped is None:
        return None
    try:
        return validate_value(definition, shaped)
    except InvalidValue:
        return None


def _shape(
    definition: AttributeDefinition, raw: PlainValue | None, unit: str | None
) -> AttributeValue | None:
    match definition.type:
        case ValueType.NUMBER if isinstance(raw, int | float) and not isinstance(raw, bool):
            return NumberValue(value=raw, unit=unit or definition.unit or "")
        case ValueType.BOOL if isinstance(raw, bool):
            return BoolValue(value=raw)
        case ValueType.ENUM if isinstance(raw, str):
            return EnumValue(value=raw)
        case ValueType.TEXT if isinstance(raw, str) and raw.strip():
            return TextValue(value=raw.strip())
        case ValueType.LIST if isinstance(raw, list):
            return ListValue(value=tuple(raw))
    return None
