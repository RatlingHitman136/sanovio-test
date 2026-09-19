"""Category templates: one current definition per category, served to nodes (H.21, D52)."""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from equivalence_core.templates import (
    ResolvedAttribute,
    RuleSettings,
    TemplateDefinition,
    load_seed_templates,
)
from service_kit.errors import Conflict, NotFound, Unprocessable
from supplier_hub.models import CategoryTemplate
from supplier_hub.models.registry import AttributeKind, AttributeStatus
from supplier_hub.services import attribute_registry, projection


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


@dataclass(frozen=True)
class TemplateEdit:
    """One curation step on a category: settings changed, attributes added or removed."""

    set: Mapping[str, RuleSettings] = field(default_factory=dict)
    add: Mapping[str, RuleSettings] = field(default_factory=dict)
    remove: Sequence[str] = ()


def edit(
    session: Session,
    code: str,
    change: TemplateEdit,
    *,
    now: datetime,
    change_note: str,
    updated_by: uuid.UUID,
) -> TemplateDefinition:
    """Only an operator changes how a category compares (§7.2). The definition gets a new hash
    (D52: no version bump), every family of the category is re-projected, and nodes pick the
    change up at their next sync."""
    row = row_for(session, code)
    entries = {entry["key"]: entry for entry in row.attributes}
    _check_edit(session, code, entries, change)
    for key in change.remove:
        del entries[key]
    for key, settings in {**change.set, **change.add}.items():
        entries[key] = {"key": key, **settings.model_dump(mode="json")}
    attributes = list(entries.values())
    if attributes == row.attributes:
        raise Unprocessable("the edit changes nothing")
    try:
        updated = _definition_from(session, row, attributes)
    except ValidationError as exc:
        raise Unprocessable(_first_error(exc)) from exc
    row.attributes = attributes
    row.definition_hash = updated.definition_hash
    row.change_note = change_note
    row.updated_by = updated_by
    row.updated_at = now
    session.flush()
    projection.rebuild_category(session, updated, now=now)
    return updated


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
    """Curation: an approved attribute joins the category."""
    return edit(
        session,
        code,
        TemplateEdit(add={key: settings}),
        now=now,
        change_note=change_note,
        updated_by=updated_by,
    )


def _check_edit(
    session: Session, code: str, entries: Mapping[str, Any], change: TemplateEdit
) -> None:
    if missing := sorted({*change.set, *change.remove} - set(entries)):
        raise Unprocessable(f"not part of {code}: {', '.join(missing)}")
    if present := sorted(set(change.add) & set(entries)):
        raise Conflict("ATTRIBUTE_IN_TEMPLATE", f"already part of {code}: {', '.join(present)}")
    if both := sorted(set(change.remove) & {*change.set, *change.add}):
        raise Unprocessable(f"changed and removed at once: {', '.join(both)}")
    for key in change.add:
        row = attribute_registry.by_key(session, key)
        # Identifiers are evidence, never compared (D50); provisional ones are approved first.
        if row.kind != AttributeKind.ATTRIBUTE or row.status != AttributeStatus.APPROVED:
            raise Unprocessable(f"{key} is not an approved attribute")


def _definition_of(session: Session, row: CategoryTemplate) -> TemplateDefinition:
    return _definition_from(session, row, row.attributes)


def _first_error(exc: ValidationError) -> str:
    return str(exc.errors()[0]["msg"]).removeprefix("Value error, ")


def _definition_from(
    session: Session, row: CategoryTemplate, attributes: Sequence[Mapping[str, Any]]
) -> TemplateDefinition:
    entries = {entry["key"]: entry for entry in attributes}
    known = {
        found.key: found for found in attribute_registry.definitions(session, keys=list(entries))
    }
    resolved = tuple(
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
        attributes=resolved,
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
