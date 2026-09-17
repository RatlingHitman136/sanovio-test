"""Category templates: which attributes a category has and how each one is compared."""

import re
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from equivalence_core.hashing import sha256_hex

_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
BOOL_SYNONYM_TARGETS = frozenset({"true", "false"})


class TemplateError(ValueError):
    """A template or attribute definition is inconsistent."""


class ValueType(StrEnum):
    NUMBER = "number"
    BOOL = "bool"
    ENUM = "enum"
    TEXT = "text"
    LIST = "list"


class Criticality(StrEnum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class ComparisonRule(StrEnum):
    """Named here so templates are validated now; the comparators themselves live in stage 3."""

    EXACT = "exact"
    TOLERANCE = "tolerance"
    SAME_OR_FINER = "same_or_finer"
    SAME_OR_MORE = "same_or_more"
    INCLUDES = "includes"
    REQUIRED_IF_HOSPITAL = "required_if_hospital"
    SEMANTIC = "semantic"
    INFO_ONLY = "info_only"
    DERIVED = "derived"


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Labels(_Frozen):
    de: str
    en: str


class AttributeDefinition(_Frozen):
    """What an attribute is, independent of any category (the registry entry)."""

    key: str
    type: ValueType
    unit: str | None = None
    options: tuple[str, ...] = ()
    labels: Labels
    # Spelling -> option code (enum) or "true"/"false" (bool).
    synonyms: dict[str, str] = {}
    question_hint: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if not _KEY_PATTERN.match(self.key):
            raise TemplateError(f"invalid attribute key {self.key!r}")
        if (self.type is ValueType.NUMBER) != (self.unit is not None):
            raise TemplateError(f"{self.key}: a unit is required for numbers and only for numbers")
        if (self.type is ValueType.ENUM) != bool(self.options):
            raise TemplateError(f"{self.key}: options are required for enums and only for enums")
        allowed = set(self.options) if self.type is ValueType.ENUM else BOOL_SYNONYM_TARGETS
        if self.synonyms and self.type not in (ValueType.ENUM, ValueType.BOOL):
            raise TemplateError(f"{self.key}: only enum and bool attributes take synonyms")
        if unknown := set(self.synonyms.values()) - allowed:
            raise TemplateError(f"{self.key}: synonyms point to unknown values {sorted(unknown)}")
        return self


class RuleSettings(_Frozen):
    """How one category compares an attribute."""

    criticality: Criticality
    rule: ComparisonRule
    tolerance: float | None = None
    shareable: bool = True

    @model_validator(mode="after")
    def _tolerance_matches_rule(self) -> Self:
        if (self.rule is ComparisonRule.TOLERANCE) != (self.tolerance is not None):
            raise TemplateError("a tolerance is required for the tolerance rule and only for it")
        return self


class TemplateAttribute(RuleSettings):
    """A template's entry for one attribute, before the definition is joined in."""

    key: str


class ResolvedAttribute(AttributeDefinition, RuleSettings):
    """Definition and category settings together, as the node stores and the hub serves them."""


class TemplateDefinition(_Frozen):
    code: str
    keywords: tuple[str, ...] = ()
    # True for the generic fallback: the category has no specific template.
    limited_template: bool = False
    attributes: tuple[ResolvedAttribute, ...]

    @model_validator(mode="after")
    def _unique_keys(self) -> Self:
        keys = [attribute.key for attribute in self.attributes]
        if duplicates := sorted({key for key in keys if keys.count(key) > 1}):
            raise TemplateError(f"{self.code}: duplicate attributes {duplicates}")
        return self

    def attribute(self, key: str) -> ResolvedAttribute:
        for attribute in self.attributes:
            if attribute.key == key:
                return attribute
        raise KeyError(key)

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(attribute.key for attribute in self.attributes)

    @property
    def shareable_keys(self) -> tuple[str, ...]:
        return tuple(attribute.key for attribute in self.attributes if attribute.shareable)

    @property
    def definition_hash(self) -> str:
        return sha256_hex(self)
