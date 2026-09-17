"""The current product (ARCHITECTURE §8.2): values of a hub variant, reported by the client,
fill the article's unknowns. The link is stored only at the node; the hub never learns it."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from sqlalchemy.orm import Session

from equivalence_core.facts import HospitalSource, resolve_hospital
from equivalence_core.templates import TemplateDefinition
from equivalence_core.validation import InvalidValue, validate_value
from equivalence_core.values import AttributeValue, IdentifierValue, TypedValue
from hospital_node.core.settings import NodeSettings
from hospital_node.models import ArticleFact, HospitalArticle, User
from hospital_node.models.articles import ReferenceSource
from hospital_node.services import projection
from hospital_node.services.facts import (
    IDENTIFIER_KEYS,
    active_facts,
    add_fact,
    of_source,
    retract,
    to_core,
)
from service_kit.errors import Unprocessable

_ANSWERS = frozenset({HospitalSource.PURCHASER_ANSWER, HospitalSource.UNAVAILABLE})


class Choice(StrEnum):
    KEEP_OURS = "KEEP_OURS"
    TAKE_REFERENCE = "TAKE_REFERENCE"


@dataclass(frozen=True)
class Reported:
    """One value of the hub variant as the client passed it on."""

    value: TypedValue
    fact_id: str | None = None


@dataclass(frozen=True)
class Fill:
    value: AttributeValue
    fact_id: str | None


@dataclass(frozen=True)
class ValueConflict:
    ours: AttributeValue
    ours_source: HospitalSource
    theirs: AttributeValue
    fact_id: str | None


@dataclass
class Preview:
    fills: dict[str, Fill] = field(default_factory=dict)
    conflicts: dict[str, ValueConflict] = field(default_factory=dict)
    # Purchaser answers (and "cannot provide") always win; they are never offered as conflicts.
    kept_purchaser: list[str] = field(default_factory=list)
    # The supplier's identifiers name the supplier's trade item, so they are never copied.
    identifiers: dict[str, TypedValue] = field(default_factory=dict)
    ignored: list[str] = field(default_factory=list)


def preview(
    article: HospitalArticle, template: TemplateDefinition, reported: Mapping[str, Reported]
) -> Preview:
    # Compare with the article as it would be without its current product.
    without_reference = [
        fact for fact in to_core(article.facts) if fact.source != HospitalSource.REFERENCE_ITEM
    ]
    current = resolve_hospital(without_reference, template)
    result = Preview()
    for key, item in sorted(reported.items()):
        if key in IDENTIFIER_KEYS or isinstance(item.value, IdentifierValue):
            result.identifiers[key] = item.value
            continue
        if key not in template.keys:
            result.ignored.append(key)
            continue
        try:
            theirs = validate_value(template.attribute(key), item.value)
        except InvalidValue:
            result.ignored.append(key)
            continue
        ours = current.attributes.get(key)
        if key in current.unavailable_attributes or (ours and ours.source in _ANSWERS):
            result.kept_purchaser.append(key)
        elif ours is None:
            result.fills[key] = Fill(theirs, item.fact_id)
        elif ours.value != theirs:
            result.conflicts[key] = ValueConflict(
                ours.value, HospitalSource(ours.source), theirs, item.fact_id
            )
    return result


def link(
    session: Session,
    article: HospitalArticle,
    template: TemplateDefinition,
    *,
    variant_id: str,
    label: str | None,
    reported: Mapping[str, Reported],
    choices: Mapping[str, Choice],
    user: User,
    settings: NodeSettings,
    now: datetime,
) -> Preview:
    """Makes the variant the article's current product, replacing any previous one."""
    plan = preview(article, template, reported)
    if unresolved := sorted(set(plan.conflicts) - set(choices)):
        raise Unprocessable(f"choose KEEP_OURS or TAKE_REFERENCE for: {', '.join(unresolved)}")
    retract(_reference_facts(article), now=now)
    accepted = dict(plan.fills)
    for key, conflict in plan.conflicts.items():
        # Keeping ours writes nothing: a reference fact would outrank master and extracted values.
        if choices[key] is Choice.TAKE_REFERENCE:
            accepted[key] = Fill(conflict.theirs, conflict.fact_id)
    for key, fill in accepted.items():
        add_fact(
            session,
            article,
            key=key,
            value=fill.value,
            source=HospitalSource.REFERENCE_ITEM,
            now=now,
            hub_variant_id=variant_id,
            hub_fact_id=fill.fact_id,
            created_by=user.id,
        )
    article.reference_hub_variant_id = variant_id
    article.reference_label = label
    article.reference_source = ReferenceSource.CLIENT_REPORTED
    article.reference_linked_by = user.id
    article.reference_linked_at = now
    projection.rebuild(session, article, template, settings=settings, now=now)
    return plan


def unlink(
    session: Session,
    article: HospitalArticle,
    template: TemplateDefinition,
    *,
    settings: NodeSettings,
    now: datetime,
) -> None:
    retract(_reference_facts(article), now=now)
    article.reference_hub_variant_id = None
    article.reference_label = None
    article.reference_source = None
    article.reference_linked_by = None
    article.reference_linked_at = None
    projection.rebuild(session, article, template, settings=settings, now=now)


def _reference_facts(article: HospitalArticle) -> list[ArticleFact]:
    return of_source(active_facts(article), HospitalSource.REFERENCE_ITEM)
