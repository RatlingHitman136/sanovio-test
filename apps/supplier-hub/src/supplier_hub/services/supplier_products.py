"""A supplier's product lines and articles: adding, editing and retiring them (§9, D59).

What a supplier enters is stored in the shape of a printed catalog entry and read by the same
parsers, so a family entered here and one loaded from a PDF behave alike. The text a parser
cannot read is left to `normalize_item`, queued as for a changed catalog.
"""

import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from equivalence_core.identifiers import IdentifierScheme, checksum_valid, normalize_identifier
from equivalence_core.templates import TemplateDefinition
from service_kit.errors import Conflict, NotFound, Unprocessable
from supplier_hub.jobs import queue
from supplier_hub.models import Organization, ProductFamily, ProductVariant, User
from supplier_hub.models.catalog import CategorySource
from supplier_hub.models.jobs import JobKind
from supplier_hub.services import catalog, projection, supplier_catalog, templates


@dataclass(frozen=True)
class FamilyText:
    """What a family says about itself; `normalize_item` reads it (§8.1)."""

    name: str
    manufacturer: str
    brand_name: str | None = None
    product_type: str | None = None
    description: str | None = None
    properties_text: str | None = None


@dataclass(frozen=True)
class VariantRow:
    """One article as a size-table row; the size text is read by the core parsers."""

    article_no: str
    label: str
    size_text: str | None = None
    order_unit: str | None = None
    units_per_order_unit: int | None = None
    order_units_per_shipping_unit: int | None = None
    gtin: str | None = None
    pzn: str | None = None


def create_family(
    session: Session, user: User, text: FamilyText, category_code: str, *, now: datetime
) -> ProductFamily:
    template = _template(session, category_code)
    supplier = session.get(Organization, user.org_id)
    assert supplier is not None
    family = catalog.store_family(
        session,
        supplier,
        asdict(text) | {"category_code": category_code},
        template,
        now=now,
        created_by=user.id,
    )
    _chosen_category(family, user, now=now)
    _read_later(session, family, now=now)
    projection.rebuild_family(session, family, template, now=now)
    return family


def edit_family(
    session: Session,
    user: User,
    family_id: uuid.UUID,
    *,
    text: FamilyText | None,
    category_code: str | None,
    now: datetime,
) -> ProductFamily:
    """A changed text replaces what the old one said; a changed category re-projects the family.
    Open assessments keep judging with their own template, so nothing breaks mid-loop."""
    family = supplier_catalog.own_family(session, user, family_id)
    if category_code is not None and category_code != family.category_code:
        _template(session, category_code)
        family.category_code = category_code
        family.raw = family.raw | {"category_code": category_code}
        _chosen_category(family, user, now=now)
    if text is not None and _changes(family, text):
        for name, value in asdict(text).items():
            setattr(family, name, value)
        family.raw = family.raw | asdict(text)
        family.content_hash = catalog.family_content_hash(family.raw)
        catalog.retire_family_readings(session, family, user.id, now=now)
        catalog.read_family_text(
            session, family, supplier_catalog.family_template(session, family), now=now
        )
        _read_later(session, family, now=now)
    family.updated_at = now
    projection.rebuild_family(
        session, family, supplier_catalog.family_template(session, family), now=now
    )
    return family


def add_variant(
    session: Session, user: User, family_id: uuid.UUID, row: VariantRow, *, now: datetime
) -> ProductVariant:
    family = supplier_catalog.own_family(session, user, family_id)
    taken = select(ProductVariant.id).where(
        ProductVariant.supplier_id == family.supplier_id,
        ProductVariant.article_no == row.article_no,
    )
    if session.scalar(taken) is not None:
        raise Conflict(
            "ARTICLE_NO_TAKEN", f"article {row.article_no} exists already; reactivate it instead"
        )
    template = supplier_catalog.family_template(session, family)
    variant = catalog.add_variant(
        session, family, _printed(row), template, now=now, created_by=user.id
    )
    projection.rebuild_family(session, family, template, now=now)
    return variant


def set_variant_active(
    session: Session, user: User, variant_id: uuid.UUID, *, active: bool, now: datetime
) -> ProductVariant:
    """Retiring takes an article out of search and new assessments; open ones keep it."""
    variant = supplier_catalog.own_variant(session, user, variant_id)
    variant.is_active = active
    variant.updated_at = now
    session.flush()
    return variant


def _template(session: Session, category_code: str) -> TemplateDefinition:
    try:
        return templates.definition(session, category_code)
    except NotFound as exc:
        raise Unprocessable(f"unknown category {category_code!r}") from exc


def _chosen_category(family: ProductFamily, user: User, *, now: datetime) -> None:
    # The supplier's choice beats any suggestion the reading makes (§9).
    family.category_source = CategorySource.SUPPLIER
    family.category_set_by = user.id
    family.category_set_at = now


def _changes(family: ProductFamily, text: FamilyText) -> bool:
    return any(getattr(family, name) != value for name, value in asdict(text).items())


def _read_later(session: Session, family: ProductFamily, *, now: datetime) -> None:
    """The same job and dedupe key a changed catalog gets when an assessment needs it."""
    queue.enqueue(
        session,
        JobKind.NORMALIZE_ITEM,
        {"family_id": str(family.id)},
        now=now,
        dedupe_key=f"normalize:{family.id}:{family.content_hash}",
    )


def _printed(row: VariantRow) -> Mapping[str, Any]:
    """The row as a catalog prints it, so `variant_facts` reads it column by column."""
    gtin = normalize_identifier(row.gtin) if row.gtin else None
    if gtin is not None and not checksum_valid(IdentifierScheme.GTIN, gtin):
        raise Unprocessable(f"GTIN {row.gtin} has a wrong check digit")
    cells = {"Art.-Nr.": row.article_no, "Größe": row.size_text, "GTIN": gtin, "PZN": row.pzn}
    return {
        "article_no": row.article_no,
        "label": row.label,
        "order_unit": row.order_unit,
        "units_per_order_unit": row.units_per_order_unit,
        "order_units_per_shipping_unit": row.order_units_per_shipping_unit,
        "source_row": {column: value for column, value in cells.items() if value},
    }
