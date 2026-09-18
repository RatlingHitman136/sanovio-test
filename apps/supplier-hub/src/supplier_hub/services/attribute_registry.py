"""The attribute registry the hub owns (H.20, §7.2).

The core YAML seeds it once; from then on the registry is the source of truth and the nodes
hold synced copies of the definitions it serves (D52).
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from equivalence_core.identifiers import HUB_SCHEMES, NODE_SCHEMES, IdentifierScheme
from equivalence_core.templates import AttributeDefinition as CoreAttribute
from equivalence_core.templates import TemplateDefinition, ValueType
from service_kit.errors import NotFound
from supplier_hub.models import AttributeDefinition
from supplier_hub.models.registry import AttributeKind, AttributeOrigin, AttributeStatus

# Identifier definitions are registry entries too, but never part of a template (D50).
IDENTIFIER_LABELS = {
    IdentifierScheme.GTIN: ("GTIN (Handelseinheit)", "GTIN (trade item)"),
    IdentifierScheme.EAN: ("EAN", "EAN"),
    IdentifierScheme.MANUFACTURER_REF: ("Hersteller-Artikelnummer", "Manufacturer article no."),
    IdentifierScheme.PHARMACODE: ("Pharmacode", "Pharmacode"),
    IdentifierScheme.SUPPLIER_ARTICLE_NO: ("Lieferanten-Artikelnummer", "Supplier article no."),
    IdentifierScheme.PZN: ("PZN", "PZN"),
    IdentifierScheme.HIMIV: ("HiMiV-Nummer", "HiMiV number"),
}


def seed_definitions(
    session: Session, templates: dict[str, TemplateDefinition], *, now: datetime
) -> int:
    """Every attribute of the seeded templates, plus one entry per identifier scheme."""
    written = 0
    for attribute in _core_attributes(templates):
        written += _upsert(
            session,
            key=attribute.key,
            kind=AttributeKind.ATTRIBUTE,
            value_type=attribute.type,
            unit=attribute.unit,
            options=list(attribute.options) or None,
            labels=attribute.labels.model_dump(),
            synonyms=dict(attribute.synonyms),
            question_hint={"de": attribute.question_hint} if attribute.question_hint else None,
            now=now,
        )
    for scheme in sorted(NODE_SCHEMES | HUB_SCHEMES):
        german, english = IDENTIFIER_LABELS[scheme]
        written += _upsert(
            session,
            key=scheme.lower(),
            kind=AttributeKind.IDENTIFIER,
            value_type=ValueType.TEXT,
            unit=None,
            options=None,
            labels={"de": german, "en": english},
            synonyms={},
            question_hint=None,
            now=now,
        )
    session.flush()
    return written


def definitions(
    session: Session, *, status: str | None = None, keys: Sequence[str] | None = None
) -> Sequence[AttributeDefinition]:
    query = select(AttributeDefinition).order_by(AttributeDefinition.key)
    if status is not None:
        query = query.where(AttributeDefinition.status == status)
    if keys is not None:
        query = query.where(AttributeDefinition.key.in_(keys))
    return session.scalars(query).all()


def by_key(session: Session, key: str) -> AttributeDefinition:
    definition = session.scalar(select(AttributeDefinition).where(AttributeDefinition.key == key))
    if definition is None:
        raise NotFound(f"no attribute definition {key!r}")
    return definition


def definition_for(
    session: Session, template: TemplateDefinition, key: str
) -> CoreAttribute | None:
    """What an answer for `key` must look like: the category's attribute, or a registry
    attribute outside the category (a provisional one from a free question, §7.2)."""
    if key in template.keys:
        return template.attribute(key)
    row = session.scalar(select(AttributeDefinition).where(AttributeDefinition.key == key))
    if row is None or row.kind != AttributeKind.ATTRIBUTE:
        return None
    if row.status == AttributeStatus.DEPRECATED:
        return None
    return as_core_attribute(row)


def expected_answer(definition: CoreAttribute) -> dict[str, Any]:
    """The typed shape a question asks for, so an answer form can offer the right input."""
    expected: dict[str, Any] = {"type": definition.type}
    if definition.unit:
        expected["unit"] = definition.unit
    if definition.options:
        expected["options"] = list(definition.options)
    return expected


def provisional_keys(session: Session) -> set[str]:
    rows = session.scalars(
        select(AttributeDefinition.key).where(
            AttributeDefinition.status == AttributeStatus.PROVISIONAL
        )
    )
    return set(rows)


def as_core_attribute(row: AttributeDefinition) -> CoreAttribute:
    """The registry row in the shape the core (and every node) understands."""
    return CoreAttribute(
        key=row.key,
        type=ValueType(row.value_type),
        unit=row.unit,
        options=tuple(row.options or ()),
        labels=row.labels,
        synonyms=dict(row.synonyms),
        question_hint=(row.question_hint or {}).get("de"),
    )


def _core_attributes(templates: dict[str, TemplateDefinition]) -> list[CoreAttribute]:
    seen: dict[str, CoreAttribute] = {}
    for template in templates.values():
        for attribute in template.attributes:
            fields = CoreAttribute.model_fields
            seen.setdefault(
                attribute.key,
                CoreAttribute(**{name: getattr(attribute, name) for name in fields}),
            )
    return [seen[key] for key in sorted(seen)]


def _upsert(
    session: Session,
    *,
    key: str,
    kind: AttributeKind,
    value_type: str,
    unit: str | None,
    options: list[str] | None,
    labels: dict[str, str],
    synonyms: dict[str, str],
    question_hint: dict[str, str] | None,
    now: datetime,
) -> int:
    row = session.scalar(select(AttributeDefinition).where(AttributeDefinition.key == key))
    if row is None:
        row = AttributeDefinition(key=key, created_at=now)
        session.add(row)
    row.kind = kind
    row.value_type = value_type
    row.unit = unit
    row.options = options
    row.labels = labels
    row.synonyms = synonyms
    row.question_hint = question_hint
    row.status = AttributeStatus.APPROVED
    row.origin = AttributeOrigin.SEED
    row.updated_at = now
    return 1
