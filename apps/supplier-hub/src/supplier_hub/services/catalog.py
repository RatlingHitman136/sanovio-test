"""Catalogs as printed: families, their size tables, and the facts the core parsers read (§8.1).

A variant's row is kept exactly as it appears in the PDF, and every value is read from it with
the same parsers the node uses on article names, so both sides speak one language.
"""

import uuid
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from equivalence_core.facts import SupplierSource
from equivalence_core.hashing import sha256_hex
from equivalence_core.identifiers import IdentifierScheme, checksum_valid, normalize_identifier
from equivalence_core.parsers import extract_attributes, parse_number
from equivalence_core.parsers.synonyms import normalize_code
from equivalence_core.parsers.units import UnitError, to_canonical
from equivalence_core.templates import TemplateDefinition
from equivalence_core.values import (
    EnumValue,
    IdentifierValue,
    NumberValue,
    TextValue,
    TypedValue,
)
from service_kit.errors import NotFound
from supplier_hub.models import ItemFact, Organization, ProductFamily, ProductVariant

# Printed column names → how the value is read. German catalogs, as scanned from the PDFs.
# Free-text columns are read in this order, not in the row's: a catalog that prints both
# "21 G x 1 ½ \"" and "0,80 mm x 40 mm" means 40 mm, not the 38.1 mm the inch figure converts to.
_FREE_TEXT_COLUMNS = ("AD x Länge (mm)", "Volumen", "Größe", "Gauge x Länge (inch)")
_MEASUREMENT_COLUMNS = {
    "ø ID": ("inner_diameter_mm", "mm"),
    "Außendurchmesser (mm)": ("outer_diameter_mm", "mm"),
    "Länge (mm)": ("length_mm", "mm"),
    "Graduierung": ("graduation_step_ml", "ml"),
}
_CODE_COLUMNS = {
    "Ansatz": "cone_position",
    "Konus": "cone_position",
    "Wandstärke": "wall_type",
    "Schliff": "bevel",
}
_TEXT_COLUMNS = {"Farbcode": "colour_code"}
_IDENTIFIER_COLUMNS = {
    "Produkt-Nr.": IdentifierScheme.SUPPLIER_ARTICLE_NO,
    "Art.-Nr.": IdentifierScheme.SUPPLIER_ARTICLE_NO,
    "PZN": IdentifierScheme.PZN,
    "HiMiV": IdentifierScheme.HIMIV,
}


def supplier_by_code(session: Session, code: str) -> Organization:
    supplier = session.scalar(select(Organization).where(Organization.code == code))
    if supplier is None:
        raise NotFound(f"no supplier {code!r}")
    return supplier


def ingest_family(
    session: Session,
    supplier: Organization,
    data: Mapping[str, Any],
    template: TemplateDefinition,
    *,
    now: datetime,
) -> ProductFamily:
    """Stores a family with its variants and every fact the printed text already states."""
    family = ProductFamily(
        supplier_id=supplier.id,
        manufacturer=data["manufacturer"],
        brand_name=data.get("brand_name"),
        name=data["name"],
        product_type=data.get("product_type"),
        category_code=data.get("category_code"),
        category_source=None,
        description=data.get("description"),
        properties_text=data.get("properties_text"),
        source_document=data.get("source_document"),
        source_page=data.get("source_page"),
        content_hash=sha256_hex(dict(data) | {"variants": None}),
        raw=dict(data),
    )
    session.add(family)
    session.flush()

    for value, raw in _family_values(data, template):
        add_fact(session, family_id=family.id, key=value[0], value=value[1], raw=raw, now=now)
    for row in data.get("variants", ()):
        _ingest_variant(session, supplier, family, row, template, now=now)
    session.flush()
    return family


def _ingest_variant(
    session: Session,
    supplier: Organization,
    family: ProductFamily,
    row: Mapping[str, Any],
    template: TemplateDefinition,
    *,
    now: datetime,
) -> ProductVariant:
    variant = ProductVariant(
        family_id=family.id,
        supplier_id=supplier.id,
        article_no=row["article_no"],
        label=row["label"],
        order_unit=row.get("order_unit"),
        units_per_order_unit=row.get("units_per_order_unit"),
        order_units_per_shipping_unit=row.get("order_units_per_shipping_unit"),
        source_row=dict(row["source_row"]),
        source_page=row.get("source_page", family.source_page),
        content_hash=sha256_hex(dict(row)),
    )
    session.add(variant)
    session.flush()
    for key, value, raw in variant_facts(variant, template):
        add_fact(session, variant_id=variant.id, key=key, value=value, raw=raw, now=now)
    return variant


def variant_facts(
    variant: ProductVariant, template: TemplateDefinition
) -> list[tuple[str, TypedValue, str]]:
    """Everything the printed row states, read column by column."""
    found: dict[str, tuple[str, TypedValue, str]] = {}

    def remember(key: str, value: TypedValue, raw: str) -> None:
        found.setdefault(key, (key, value, raw))

    for column, printed in _ordered(variant.source_row):
        text = str(printed).strip()
        if not text:
            continue
        if column in _IDENTIFIER_COLUMNS:
            scheme = _IDENTIFIER_COLUMNS[column]
            cleaned = normalize_identifier(text)
            remember(
                scheme.lower(),
                IdentifierValue(
                    scheme=scheme, value=cleaned, checksum_valid=checksum_valid(scheme, cleaned)
                ),
                text,
            )
        elif column in _MEASUREMENT_COLUMNS:
            key, unit = _MEASUREMENT_COLUMNS[column]
            number = _number(text, unit, key, template)
            if number is not None:
                remember(key, number, text)
        elif column in _CODE_COLUMNS:
            key = _CODE_COLUMNS[column]
            if key in template.keys:
                code = normalize_code(template.attribute(key), text)
                if code is not None:
                    remember(key, EnumValue(value=code), text)
        elif column in _TEXT_COLUMNS:
            key = _TEXT_COLUMNS[column]
            if key in template.keys:
                remember(key, TextValue(value=text), text)
        elif column in _FREE_TEXT_COLUMNS:
            for extraction in extract_attributes(text, template).extractions:
                remember(extraction.attribute_key, extraction.value, extraction.quote)

    if variant.units_per_order_unit is not None and "units_per_order_unit" in template.keys:
        remember(
            "units_per_order_unit",
            NumberValue(value=variant.units_per_order_unit, unit="pcs"),
            str(variant.units_per_order_unit),
        )
    return list(found.values())


def _ordered(row: Mapping[str, Any]) -> list[tuple[str, Any]]:
    """Columns in reading order: everything explicit first, then free text by precedence."""
    explicit = [(name, value) for name, value in row.items() if name not in _FREE_TEXT_COLUMNS]
    free_text = [(name, row[name]) for name in _FREE_TEXT_COLUMNS if name in row]
    return explicit + free_text


def _family_values(
    data: Mapping[str, Any], template: TemplateDefinition
) -> Iterable[tuple[tuple[str, TypedValue], str]]:
    """What the family's own headline text states; the rest is left to `normalize_item`."""
    text = " · ".join(
        part
        for part in (
            data["name"],
            data.get("product_type"),
            data.get("connector_label"),
            data.get("description"),
        )
        if part
    )
    for extraction in extract_attributes(text, template).extractions:
        yield (extraction.attribute_key, extraction.value), extraction.quote


def add_fact(
    session: Session,
    *,
    key: str,
    value: TypedValue | None,
    raw: str | None,
    now: datetime,
    family_id: uuid.UUID | None = None,
    variant_id: uuid.UUID | None = None,
    source: SupplierSource = SupplierSource.CATALOG,
    **provenance: Any,
) -> ItemFact:
    """The single write path for supplier facts; existing values of the same scope give way."""
    fact = ItemFact(
        id=uuid.uuid7(),
        family_id=family_id,
        variant_id=variant_id,
        attribute_key=key,
        value=None if value is None else value.model_dump(mode="json"),
        raw_value=raw,
        source=source,
        created_at=now,
        **provenance,
    )
    replaced = [
        previous
        for previous in _facts_of(session, family_id=family_id, variant_id=variant_id)
        if previous.attribute_key == key and previous.source == source
    ]
    session.add(fact)
    session.flush()
    for previous in replaced:
        previous.superseded_by_id = fact.id
    session.flush()
    return fact


def facts_for(session: Session, variant: ProductVariant) -> Sequence[ItemFact]:
    """The variant's own facts and its family's, all still current."""
    return [
        *_facts_of(session, variant_id=variant.id),
        *_facts_of(session, family_id=variant.family_id),
    ]


def family_facts(session: Session, family_id: uuid.UUID) -> list[ItemFact]:
    """The family's current facts, whatever their source."""
    return _facts_of(session, family_id=family_id)


def _facts_of(
    session: Session,
    *,
    family_id: uuid.UUID | None = None,
    variant_id: uuid.UUID | None = None,
) -> list[ItemFact]:
    query = select(ItemFact).where(ItemFact.superseded_by_id.is_(None))
    query = (
        query.where(ItemFact.variant_id == variant_id)
        if variant_id is not None
        else query.where(ItemFact.family_id == family_id)
    )
    return list(session.scalars(query))


def _number(text: str, unit: str, key: str, template: TemplateDefinition) -> NumberValue | None:
    if key not in template.keys:
        return None
    attribute = template.attribute(key)
    digits = "".join(character for character in text if character.isdigit() or character in ",.")
    try:
        value = parse_number(digits)
        canonical = to_canonical(value, unit, attribute.unit or unit)
    except ValueError, UnitError:
        return None
    return NumberValue(value=canonical, unit=attribute.unit or unit)
