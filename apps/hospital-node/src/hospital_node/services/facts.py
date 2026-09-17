"""The single write path for article facts (ARCHITECTURE §9: add, never overwrite)."""

import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy.orm import Session

from equivalence_core.facts import HospitalFact, HospitalSource
from equivalence_core.identifiers import NODE_SCHEMES, IdentifierScheme
from equivalence_core.values import TypedValue
from hospital_node.models import ArticleFact, HospitalArticle

# Identifier facts use the scheme's registry key as attribute key (data-model N.4 note).
IDENTIFIER_KEYS: dict[str, IdentifierScheme] = {scheme.lower(): scheme for scheme in NODE_SCHEMES}

_ANSWERS = frozenset({HospitalSource.PURCHASER_ANSWER, HospitalSource.UNAVAILABLE})
_VALUE = TypeAdapter[TypedValue](TypedValue)


def active_facts(article: HospitalArticle) -> list[ArticleFact]:
    return [fact for fact in article.facts if fact.is_active]


def add_fact(
    session: Session,
    article: HospitalArticle,
    *,
    key: str,
    value: TypedValue | None,
    source: HospitalSource,
    now: datetime,
    **provenance: Any,
) -> ArticleFact:
    """Adds a fact and supersedes the active one it replaces: same key, same kind of source.

    Answers ("cannot provide" included) replace answers, master data replaces master data.
    Facts of other sources stay; precedence decides between them when resolving.
    """
    fact = ArticleFact(
        id=uuid.uuid7(),
        attribute_key=key,
        value=None if value is None else value.model_dump(mode="json"),
        source=source,
        created_at=now,
        **provenance,
    )
    replaced = [
        previous
        for previous in active_facts(article)
        if previous.attribute_key == key and _family(previous.source) == _family(source)
    ]
    article.facts.append(fact)
    # The new row must exist before older rows can point at it.
    session.flush()
    for previous in replaced:
        previous.superseded_by_id = fact.id
    session.flush()
    return fact


def retract(facts: Iterable[ArticleFact], *, now: datetime) -> None:
    """Withdraws facts that no newer fact replaces (a re-run that no longer finds a value,
    or an undone current product)."""
    for fact in facts:
        fact.retracted_at = now


def of_source(facts: Iterable[ArticleFact], *sources: HospitalSource) -> list[ArticleFact]:
    return [fact for fact in facts if fact.source in sources]


def to_core(facts: Sequence[ArticleFact]) -> list[HospitalFact]:
    """Active facts in the core resolver's shape."""
    return [
        HospitalFact(
            id=str(fact.id),
            attribute_key=fact.attribute_key,
            value=None if fact.value is None else typed_value(fact.value),
            source=HospitalSource(fact.source),
            created_at=fact.created_at,
        )
        for fact in facts
        if fact.is_active
    ]


def typed_value(stored: dict[str, Any]) -> TypedValue:
    return _VALUE.validate_python(stored)


def _family(source: str) -> str:
    return "ANSWER" if source in _ANSWERS else source
