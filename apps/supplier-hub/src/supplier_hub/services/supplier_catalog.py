"""A supplier's own catalog: values per family and per variant, and changing them (§9).

An edit is a supplier fact like an answer (`SUPPLIER_ANSWER`, above catalog data), at family
scope for every variant or at variant scope as an override. Withdrawing one of its own facts
brings back what was there before. Open assessments see the change in their next round.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from equivalence_core.facts import ResolvedRecord, SupplierSource, resolve_supplier
from equivalence_core.templates import TemplateDefinition
from equivalence_core.validation import InvalidValue, validate_value
from equivalence_core.values import TypedValue
from service_kit.errors import NotFound, Unprocessable
from supplier_hub.models import ItemFact, ProductFamily, ProductVariant, User
from supplier_hub.services import attribute_registry, catalog, projection, templates

# What a supplier said itself, and so may take back; catalog readings stay.
OWN_SOURCES = frozenset({SupplierSource.SUPPLIER_ANSWER, SupplierSource.UNAVAILABLE})


@dataclass(frozen=True)
class FamilyView:
    family: ProductFamily
    template: TemplateDefinition
    # The family's own values, before any variant overrides them.
    family_record: ResolvedRecord
    variants: list[tuple[ProductVariant, ResolvedRecord]]


def family_view(session: Session, user: User, family_id: uuid.UUID) -> FamilyView:
    family = _own_family(session, user, family_id)
    template = _template(session, family)
    family_record = resolve_supplier(
        projection.core_facts(catalog.family_facts(session, family.id)), template
    )
    variants = [
        (variant, projection.resolve(session, variant, template))
        for variant in sorted(family.variants, key=lambda v: v.article_no)
        if variant.is_active
    ]
    return FamilyView(family, template, family_record, variants)


def set_value(
    session: Session,
    user: User,
    *,
    family_id: uuid.UUID | None,
    variant_id: uuid.UUID | None,
    key: str,
    value: TypedValue | None,
    unavailable: bool,
    now: datetime,
) -> ItemFact:
    """Exactly one of family and variant; a value, or "not available" (`unavailable`)."""
    if (family_id is None) == (variant_id is None):
        raise Unprocessable("name either a family or a variant")
    if unavailable == (value is not None):
        raise Unprocessable("send either a value or unavailable=true")
    if variant_id is not None:
        variant = _own_variant(session, user, variant_id)
        family = variant.family
    else:
        assert family_id is not None
        family = _own_family(session, user, family_id)
    template = _template(session, family)
    checked = None if value is None else _checked(session, template, key, value)
    fact = catalog.add_fact(
        session,
        key=key,
        value=checked,
        raw=None,
        now=now,
        family_id=family_id,
        variant_id=variant_id,
        source=SupplierSource.UNAVAILABLE if unavailable else SupplierSource.SUPPLIER_ANSWER,
        created_by=user.id,
    )
    projection.rebuild_family(session, family, template, now=now)
    return fact


def withdraw(session: Session, user: User, fact_id: uuid.UUID, *, now: datetime) -> None:
    """Takes back one of the supplier's own statements; catalog data cannot be withdrawn."""
    fact = session.get(ItemFact, fact_id)
    family = _family_of(session, fact) if fact is not None else None
    if fact is None or family is None or family.supplier_id != user.org_id or not fact.is_active:
        raise NotFound("fact not found")
    if fact.source not in OWN_SOURCES:
        raise Unprocessable("only values the supplier gave itself can be withdrawn")
    fact.withdrawn_at = now
    fact.withdrawn_by = user.id
    session.flush()
    projection.rebuild_family(session, family, _template(session, family), now=now)


def own_facts(session: Session, family: ProductFamily) -> list[ItemFact]:
    """The supplier's own current statements for the family and each of its variants."""
    facts = list(catalog.family_facts(session, family.id))
    for variant in family.variants:
        facts += [fact for fact in catalog.facts_for(session, variant) if fact.variant_id]
    return [fact for fact in facts if fact.source in OWN_SOURCES]


def _checked(
    session: Session, template: TemplateDefinition, key: str, value: TypedValue
) -> TypedValue:
    definition = attribute_registry.definition_for(session, template, key)
    if definition is None:
        raise Unprocessable(f"{key!r} is not an attribute of {template.code}")
    try:
        return validate_value(definition, value)
    except InvalidValue as exc:
        raise Unprocessable(str(exc)) from exc


def _template(session: Session, family: ProductFamily) -> TemplateDefinition:
    return templates.definition(session, family.category_code or "")


def _own_family(session: Session, user: User, family_id: uuid.UUID) -> ProductFamily:
    family = session.get(ProductFamily, family_id)
    # Another supplier's family does not exist, as far as this supplier can tell.
    if family is None or family.supplier_id != user.org_id:
        raise NotFound("family not found")
    return family


def _own_variant(session: Session, user: User, variant_id: uuid.UUID) -> ProductVariant:
    variant = session.get(ProductVariant, variant_id)
    if variant is None or variant.supplier_id != user.org_id:
        raise NotFound("variant not found")
    return variant


def _family_of(session: Session, fact: ItemFact) -> ProductFamily | None:
    if fact.family_id is not None:
        return session.get(ProductFamily, fact.family_id)
    variant = session.get(ProductVariant, fact.variant_id)
    return variant.family if variant is not None else None
