"""Candidate search: one requirement in, ranked variants out (ARCHITECTURE §15).

Deterministic and read-only — no LLM call, and nothing about the requirement is stored. Hard
filters come from the critical attributes the hospital actually knows: a known contradiction
excludes a variant, an unknown never does.
"""

import uuid
from collections import Counter
from dataclasses import dataclass, field

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from equivalence_core.comparators import ComparisonStatus, Judgment, compare
from equivalence_core.exchange.requirement import ProductHints, RequirementPayload
from equivalence_core.facts import IdentifierEntry, ResolvedRecord, ResolvedValue
from equivalence_core.identifier_evidence import IdentifierEvidence, identifier_evidence
from equivalence_core.identifiers import IdentifierScheme
from equivalence_core.templates import ComparisonRule, Criticality, TemplateDefinition
from equivalence_core.values import AttributeValue
from supplier_hub.models import ItemSearchProjection, ProductVariant

DEFAULT_LIMIT = 20
MAX_LIMIT = 50
# §15.6: how much each per-attribute result is worth, and how much the attribute itself weighs.
_SCORE = {
    ComparisonStatus.MATCH: 1.0,
    ComparisonStatus.ACCEPTABLE_DEVIATION: 0.7,
    ComparisonStatus.UNKNOWN: 0.3,
    ComparisonStatus.UNAVAILABLE: 0.3,
    ComparisonStatus.NEEDS_JUDGE: 0.3,
    ComparisonStatus.MISMATCH: 0.0,
}
_WEIGHT = {Criticality.CRITICAL: 3, Criticality.MAJOR: 2, Criticality.MINOR: 1}
_HARD_RULES = (ComparisonRule.EXACT, ComparisonRule.TOLERANCE)
_ATTRIBUTE = TypeAdapter[AttributeValue](AttributeValue)


@dataclass(frozen=True)
class SearchSpec:
    category: str
    # A candidate is dropped only when it states something else, never when it says nothing.
    hard_filters: dict[str, AttributeValue]
    soft_criteria: tuple[str, ...]
    hospital_gaps: tuple[str, ...]


@dataclass(frozen=True)
class Candidate:
    variant: ProductVariant
    projection: ItemSearchProjection
    judgments: tuple[Judgment, ...]
    score: float
    coverage: float
    critical_unknowns: int
    identifier_match: str | None


@dataclass(frozen=True)
class SearchResult:
    spec: SearchSpec
    candidates: list[Candidate]
    # How many variants each hard filter removed; an empty list is explained by this (D54).
    excluded_by: dict[str, int] = field(default_factory=dict)


def build_spec(requirement: RequirementPayload, template: TemplateDefinition) -> SearchSpec:
    hard: dict[str, AttributeValue] = {}
    soft: list[str] = []
    for key, value in requirement.attributes.items():
        attribute = template.attribute(key)
        if attribute.criticality is Criticality.CRITICAL and attribute.rule in _HARD_RULES:
            hard[key] = value
        else:
            soft.append(key)
    return SearchSpec(
        category=requirement.template_code,
        hard_filters=hard,
        soft_criteria=tuple(soft),
        # What the purchaser could fill by marking their current product (§15.3).
        hospital_gaps=tuple(
            sorted({*requirement.unknown_attributes, *requirement.withheld_attributes})
        ),
    )


def search(
    session: Session,
    requirement: RequirementPayload,
    template: TemplateDefinition,
    *,
    supplier_id: uuid.UUID | None = None,
    limit: int = DEFAULT_LIMIT,
) -> SearchResult:
    spec = build_spec(requirement, template)
    rows = _category_rows(session, spec.category, supplier_id)
    excluded: Counter[str] = Counter()

    kept = []
    for row in rows:
        blocking = _contradicted(spec, row)
        if blocking:
            excluded[blocking] += 1
            continue
        kept.append(row)

    hints = requirement.product_hints
    candidates = [_candidate(row, requirement, template, hints) for row in kept]
    candidates.sort(
        key=lambda candidate: (
            candidate.identifier_match is None,
            candidate.critical_unknowns,
            -candidate.score,
            -candidate.coverage,
        )
    )
    return SearchResult(
        spec=spec, candidates=candidates[: min(limit, MAX_LIMIT)], excluded_by=dict(excluded)
    )


def _category_rows(
    session: Session, category: str, supplier_id: uuid.UUID | None
) -> list[ItemSearchProjection]:
    query = (
        select(ItemSearchProjection)
        .join(ProductVariant, ProductVariant.id == ItemSearchProjection.variant_id)
        .where(ItemSearchProjection.category_code == category, ProductVariant.is_active.is_(True))
    )
    if supplier_id is not None:
        query = query.where(ItemSearchProjection.supplier_id == supplier_id)
    return list(session.scalars(query))


def _contradicted(spec: SearchSpec, row: ItemSearchProjection) -> str | None:
    """The first hard filter this variant states differently, if any."""
    for key, wanted in spec.hard_filters.items():
        stored = row.attributes.get(key)
        if stored is None:
            continue  # an unknown passes
        if _ATTRIBUTE.validate_python(stored) != wanted:
            return key
    return None


def _candidate(
    row: ItemSearchProjection,
    requirement: RequirementPayload,
    template: TemplateDefinition,
    hints: ProductHints | None,
) -> Candidate:
    judgments = compare(requirement, _record(row, template), template)
    counted = [judgment for judgment in judgments if judgment.status is not ComparisonStatus.INFO]
    total_weight = sum(_WEIGHT[judgment.criticality] for judgment in counted) or 1
    score = sum(_SCORE[judgment.status] * _WEIGHT[judgment.criticality] for judgment in counted)
    known = sum(1 for key in template.keys if key in row.attributes)
    critical_unknowns = sum(
        1
        for judgment in counted
        if judgment.criticality is Criticality.CRITICAL
        and judgment.status
        in (ComparisonStatus.UNKNOWN, ComparisonStatus.UNAVAILABLE, ComparisonStatus.NEEDS_JUDGE)
    )
    return Candidate(
        variant=row.variant,
        projection=row,
        judgments=judgments,
        score=round(score / total_weight, 4),
        coverage=round(known / max(len(template.keys), 1), 4),
        critical_unknowns=critical_unknowns,
        identifier_match=_identifier_match(hints, row),
    )


def _record(row: ItemSearchProjection, template: TemplateDefinition) -> ResolvedRecord:
    """The stored projection in the shape the comparators expect."""
    attributes = {
        key: ResolvedValue(
            value=_ATTRIBUTE.validate_python(value),
            fact_id=str(row.attribute_fact_ids.get(key, "")),
            source="CATALOG",
        )
        for key, value in row.attributes.items()
        if key in template.keys
    }
    return ResolvedRecord(
        attributes=attributes,
        unknown_attributes=tuple(key for key in template.keys if key not in attributes),
        unavailable_attributes=(),
        identifiers=tuple(_identifiers(row)),
    )


def _identifiers(row: ItemSearchProjection) -> list[IdentifierEntry]:
    return [IdentifierEntry.model_validate(entry) for entry in row.identifiers]


def _identifier_match(hints: ProductHints | None, row: ItemSearchProjection) -> str | None:
    """Which hint matched, for ranking and for the purchaser's eyes (D47, D51)."""
    if hints is None:
        return None
    identifiers = _identifiers(row)
    manufacturer = row.variant.family.manufacturer
    if identifier_evidence(hints, identifiers, manufacturer) is IdentifierEvidence.NO_INFORMATION:
        return None
    gtin_matched = any(
        entry.scheme is IdentifierScheme.GTIN
        and entry.checksum_valid is True
        and entry.value == hints.gtin
        for entry in identifiers
    )
    return "GTIN" if gtin_matched else "ARTICLE_NO"
