"""Typed attribute values, stored identically in facts, projections and requirements."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from equivalence_core.identifiers import IdentifierScheme


class _Value(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NumberValue(_Value):
    type: Literal["number"] = "number"
    value: float
    unit: str


class BoolValue(_Value):
    type: Literal["bool"] = "bool"
    value: bool


class EnumValue(_Value):
    type: Literal["enum"] = "enum"
    value: str


class TextValue(_Value):
    type: Literal["text"] = "text"
    value: str


class ListValue(_Value):
    type: Literal["list"] = "list"
    value: tuple[str, ...]


class IdentifierValue(_Value):
    type: Literal["identifier"] = "identifier"
    scheme: IdentifierScheme
    value: str
    checksum_valid: bool | None


# Comparable values only: a requirement uses this union, so it has no place for identifiers.
type AttributeValue = Annotated[
    NumberValue | BoolValue | EnumValue | TextValue | ListValue, Field(discriminator="type")
]

type TypedValue = Annotated[
    NumberValue | BoolValue | EnumValue | TextValue | ListValue | IdentifierValue,
    Field(discriminator="type"),
]
