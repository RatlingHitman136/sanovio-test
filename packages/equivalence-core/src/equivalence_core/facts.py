"""Facts and the resolver that turns them into a projection's current values.

Facts are only ever added. The resolver drops superseded facts, lets the highest-precedence
source win per attribute (newest first on ties) and keeps identifiers as a set of their own.
"""

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from equivalence_core.hashing import sha256_hex
from equivalence_core.identifiers import IdentifierScheme
from equivalence_core.templates.model import TemplateDefinition
from equivalence_core.values import AttributeValue, IdentifierValue, TypedValue


class HospitalSource(StrEnum):
    HOSPITAL_MASTER = "HOSPITAL_MASTER"
    EXTRACTION = "EXTRACTION"
    REFERENCE_ITEM = "REFERENCE_ITEM"
    PURCHASER_ANSWER = "PURCHASER_ANSWER"
    UNAVAILABLE = "UNAVAILABLE"


class SupplierSource(StrEnum):
    CATALOG = "CATALOG"
    EXTRACTION = "EXTRACTION"
    SUPPLIER_ANSWER = "SUPPLIER_ANSWER"
    UNAVAILABLE = "UNAVAILABLE"


class Scope(StrEnum):
    FAMILY = "FAMILY"
    VARIANT = "VARIANT"


# Lower wins. "Cannot provide" is an answer, so it ranks with answers.
_HOSPITAL_RANK = {
    HospitalSource.PURCHASER_ANSWER: 0,
    HospitalSource.UNAVAILABLE: 0,
    HospitalSource.REFERENCE_ITEM: 1,
    HospitalSource.HOSPITAL_MASTER: 2,
    HospitalSource.EXTRACTION: 3,
}
_SUPPLIER_RANK = {
    SupplierSource.SUPPLIER_ANSWER: 0,
    SupplierSource.UNAVAILABLE: 0,
    SupplierSource.CATALOG: 1,
    SupplierSource.EXTRACTION: 2,
}
_SCOPE_RANK = {Scope.VARIANT: 0, Scope.FAMILY: 1}


class _Fact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    attribute_key: str
    value: TypedValue | None
    created_at: datetime
    superseded_by: str | None = None

    @model_validator(mode="after")
    def _value_unless_unavailable(self) -> Self:
        if (self.value is None) != (getattr(self, "source", None) == "UNAVAILABLE"):
            raise ValueError("a fact has a value unless its source is UNAVAILABLE")
        return self


class HospitalFact(_Fact):
    source: HospitalSource


class SupplierFact(_Fact):
    source: SupplierSource
    scope: Scope


class ResolvedValue(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: AttributeValue
    fact_id: str
    source: str
    # Supplier facts only: whether the winning fact belongs to the variant or to its family.
    scope: Scope | None = None


class IdentifierEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    scheme: IdentifierScheme
    value: str
    checksum_valid: bool | None
    fact_id: str


class ResolvedRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    attributes: dict[str, ResolvedValue]
    unknown_attributes: tuple[str, ...]
    unavailable_attributes: tuple[str, ...]
    identifiers: tuple[IdentifierEntry, ...]

    def record_hash(self) -> str:
        """Changes exactly when a resolved value, an unavailable mark or an identifier changes."""
        return sha256_hex(
            {
                "attributes": {key: resolved.value for key, resolved in self.attributes.items()},
                "unavailable": sorted(self.unavailable_attributes),
                "identifiers": [
                    [entry.scheme, entry.value, entry.checksum_valid] for entry in self.identifiers
                ],
            }
        )


def resolve_hospital(facts: Iterable[HospitalFact], template: TemplateDefinition) -> ResolvedRecord:
    return _resolve(list(facts), template, lambda f: (_HOSPITAL_RANK[f.source], _newest(f)))


def resolve_supplier(facts: Iterable[SupplierFact], template: TemplateDefinition) -> ResolvedRecord:
    """Answers beat catalog data, catalog beats extraction; within each, variant beats family."""
    return _resolve(
        list(facts),
        template,
        lambda f: (_SUPPLIER_RANK[f.source], _SCOPE_RANK[f.scope], _newest(f)),
    )


def _newest(fact: _Fact) -> float:
    return -fact.created_at.timestamp()


def _resolve[F: HospitalFact | SupplierFact](
    facts: Sequence[F],
    template: TemplateDefinition,
    rank: Callable[[F], tuple[float, ...]],
) -> ResolvedRecord:
    live = [fact for fact in facts if fact.superseded_by is None]
    identifiers = sorted(
        (
            IdentifierEntry(
                scheme=fact.value.scheme,
                value=fact.value.value,
                checksum_valid=fact.value.checksum_valid,
                fact_id=fact.id,
            )
            for fact in live
            if isinstance(fact.value, IdentifierValue)
        ),
        key=lambda entry: (entry.scheme, entry.value),
    )
    by_key: dict[str, list[F]] = defaultdict(list)
    for fact in live:
        if not isinstance(fact.value, IdentifierValue) and fact.attribute_key in template.keys:
            by_key[fact.attribute_key].append(fact)

    attributes: dict[str, ResolvedValue] = {}
    unavailable: list[str] = []
    for key in template.keys:
        if not by_key[key]:
            continue
        winner = min(by_key[key], key=rank)
        if winner.value is None:
            unavailable.append(key)
        elif not isinstance(winner.value, IdentifierValue):
            attributes[key] = ResolvedValue(
                value=winner.value,
                fact_id=winner.id,
                source=winner.source,
                scope=getattr(winner, "scope", None),
            )
    resolved = attributes.keys() | set(unavailable)
    return ResolvedRecord(
        attributes=attributes,
        unknown_attributes=tuple(key for key in template.keys if key not in resolved),
        unavailable_attributes=tuple(unavailable),
        identifiers=tuple(identifiers),
    )
