"""The search projection (H.11): one row per variant, family facts merged underneath."""

from datetime import datetime

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from equivalence_core.facts import Scope, SupplierFact, SupplierSource, resolve_supplier
from equivalence_core.templates import TemplateDefinition
from equivalence_core.values import TypedValue
from supplier_hub.models import ItemSearchProjection, ProductFamily, ProductVariant
from supplier_hub.services import catalog

_VALUE = TypeAdapter[TypedValue](TypedValue)


def rebuild_family(
    session: Session, family: ProductFamily, template: TemplateDefinition, *, now: datetime
) -> None:
    for variant in family.variants:
        rebuild(session, variant, template, now=now)


def rebuild(
    session: Session, variant: ProductVariant, template: TemplateDefinition, *, now: datetime
) -> ItemSearchProjection:
    record = resolve_supplier(_core_facts(session, variant), template)
    row = session.scalar(
        select(ItemSearchProjection).where(ItemSearchProjection.variant_id == variant.id)
    )
    if row is None:
        row = ItemSearchProjection(variant_id=variant.id)
        session.add(row)
    family = variant.family
    row.supplier_id = variant.supplier_id
    row.category_code = family.category_code
    row.display_name = f"{variant.label} ({variant.article_no})"
    row.attributes = {
        key: resolved.value.model_dump(mode="json") for key, resolved in record.attributes.items()
    }
    row.attribute_fact_ids = {key: resolved.fact_id for key, resolved in record.attributes.items()}
    row.unknown_attributes = list(record.unknown_attributes)
    row.additional_attributes = {}
    row.identifiers = [entry.model_dump(mode="json") for entry in record.identifiers]
    row.search_text = " ".join(
        part
        for part in (family.manufacturer, family.brand_name, family.name, variant.label)
        if part
    )
    row.record_hash = record.record_hash()
    row.updated_at = now
    session.flush()
    return row


def _core_facts(session: Session, variant: ProductVariant) -> list[SupplierFact]:
    return [
        SupplierFact(
            id=str(fact.id),
            attribute_key=fact.attribute_key,
            value=None if fact.value is None else _VALUE.validate_python(fact.value),
            source=SupplierSource(fact.source),
            scope=Scope.VARIANT if fact.variant_id is not None else Scope.FAMILY,
            created_at=fact.created_at,
        )
        for fact in catalog.facts_for(session, variant)
    ]
