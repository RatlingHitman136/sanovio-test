"""The search projection (H.11): one row per variant, family facts merged underneath."""

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from equivalence_core.facts import (
    ResolvedRecord,
    Scope,
    SupplierFact,
    SupplierSource,
    resolve_supplier,
)
from equivalence_core.templates import TemplateDefinition
from equivalence_core.values import TypedValue
from supplier_hub.models import ItemFact, ItemSearchProjection, ProductFamily, ProductVariant
from supplier_hub.services import attribute_registry, catalog

_VALUE = TypeAdapter[TypedValue](TypedValue)


def rebuild_family(
    session: Session, family: ProductFamily, template: TemplateDefinition, *, now: datetime
) -> None:
    for variant in family.variants:
        rebuild(session, variant, template, now=now)


def resolve(
    session: Session, variant: ProductVariant, template: TemplateDefinition
) -> ResolvedRecord:
    """The variant's effective record, family facts merged under its own, with fact scopes."""
    return resolve_supplier(_core_facts(session, variant), template)


def rebuild(
    session: Session, variant: ProductVariant, template: TemplateDefinition, *, now: datetime
) -> ItemSearchProjection:
    facts = _core_facts(session, variant)
    record = resolve_supplier(facts, template)
    # Queried before a new row is added, so autoflush never sees it half-filled.
    provisional = attribute_registry.provisional_keys(session)
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
    row.additional_attributes = _additional(facts, provisional)
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


def _additional(facts: list[SupplierFact], keys: set[str]) -> dict[str, Any]:
    """Provisional values: shown as information, never filtered or judged (§7.2 step 5).
    The variant's own answer beats the family's, a newer one an older one."""
    shown: dict[str, Any] = {}
    ordered = sorted(facts, key=lambda f: (f.scope == Scope.VARIANT, f.created_at))
    for fact in ordered:
        if fact.attribute_key in keys and fact.value is not None:
            shown[fact.attribute_key] = {
                "value": fact.value.model_dump(mode="json"),
                "source": fact.source,
                "fact_id": fact.id,
            }
    return shown


def _core_facts(session: Session, variant: ProductVariant) -> list[SupplierFact]:
    return core_facts(catalog.facts_for(session, variant))


def core_facts(facts: Iterable[ItemFact]) -> list[SupplierFact]:
    """Stored facts in the core's shape, for the resolver."""
    return [
        SupplierFact(
            id=str(fact.id),
            attribute_key=fact.attribute_key,
            value=None if fact.value is None else _VALUE.validate_python(fact.value),
            source=SupplierSource(fact.source),
            scope=Scope.VARIANT if fact.variant_id is not None else Scope.FAMILY,
            created_at=fact.created_at,
        )
        for fact in facts
    ]
