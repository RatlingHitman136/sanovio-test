"""Category templates: one current definition per category, served to nodes (H.21, D52)."""

import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from equivalence_core.templates import (
    ResolvedAttribute,
    RuleSettings,
    TemplateDefinition,
    load_seed_templates,
)
from service_kit.errors import Conflict, NotFound
from supplier_hub.models import CategoryTemplate
from supplier_hub.services import attribute_registry


def seed_templates(session: Session, *, now: datetime) -> dict[str, TemplateDefinition]:
    """Loads the core YAML into the registry; afterwards the registry is authoritative."""
    seeded = load_seed_templates()
    attribute_registry.seed_definitions(session, seeded, now=now)
    for definition in seeded.values():
        _store(session, definition, now=now, change_note="Seed")
    session.flush()
    return seeded


def rows(session: Session) -> Sequence[CategoryTemplate]:
    return session.scalars(select(CategoryTemplate).order_by(CategoryTemplate.code)).all()


def row_for(session: Session, code: str) -> CategoryTemplate:
    row = session.scalar(select(CategoryTemplate).where(CategoryTemplate.code == code))
    if row is None:
        raise NotFound(f"no template for category {code!r}")
    return row


def definition(session: Session, code: str) -> TemplateDefinition:
    """The current definition, rebuilt from the registry so a curated change shows at once."""
    return _definition_of(session, row_for(session, code))


def definitions(session: Session) -> dict[str, TemplateDefinition]:
    return {row.code: _definition_of(session, row) for row in rows(session)}


def add_attribute(
    session: Session,
    code: str,
    key: str,
    settings: RuleSettings,
    *,
    now: datetime,
    change_note: str,
    updated_by: uuid.UUID,
) -> TemplateDefinition:
    """Curation: an approved attribute joins the category (D52: a new hash, no version bump)."""
    row = row_for(session, code)
    if any(entry["key"] == key for entry in row.attributes):
        raise Conflict("ATTRIBUTE_IN_TEMPLATE", f"{key!r} is already part of {code}")
    row.attributes = [*row.attributes, {"key": key, **settings.model_dump(mode="json")}]
    updated = _definition_of(session, row)
    row.definition_hash = updated.definition_hash
    row.change_note = change_note
    row.updated_by = updated_by
    row.updated_at = now
    session.flush()
    return updated


def _definition_of(session: Session, row: CategoryTemplate) -> TemplateDefinition:
    entries = {entry["key"]: entry for entry in row.attributes}
    known = {
        found.key: found for found in attribute_registry.definitions(session, keys=list(entries))
    }
    attributes = tuple(
        ResolvedAttribute(
            **attribute_registry.as_core_attribute(known[key]).model_dump(),
            **_rule_settings(entry),
        )
        for key, entry in entries.items()
        if key in known
    )
    return TemplateDefinition(
        code=row.code,
        keywords=tuple(row.keywords),
        limited_template=row.limited_template,
        attributes=attributes,
    )


def _rule_settings(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Only how a category compares the attribute; the definition itself lives in the registry."""
    return {name: entry[name] for name in RuleSettings.model_fields if name in entry}


def _store(
    session: Session,
    definition: TemplateDefinition,
    *,
    now: datetime,
    change_note: str,
) -> CategoryTemplate:
    row = session.scalar(select(CategoryTemplate).where(CategoryTemplate.code == definition.code))
    if row is None:
        row = CategoryTemplate(code=definition.code, created_at=now)
        session.add(row)
    # The parent's attributes are already merged in, so a served definition needs no lookup.
    row.parent_code = None
    row.keywords = list(definition.keywords)
    row.limited_template = definition.limited_template
    row.attributes = [
        {"key": attribute.key, **_rule_settings(attribute.model_dump())}
        for attribute in definition.attributes
    ]
    row.definition_hash = definition.definition_hash
    row.change_note = change_note
    row.updated_at = now
    session.flush()
    return row
