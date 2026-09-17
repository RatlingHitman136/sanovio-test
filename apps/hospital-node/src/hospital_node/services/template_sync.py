"""The installed category definitions (N.11): YAML seeds until the hub exists, then the
definitions the client syncs from the hub through `PUT /templates` (D52)."""

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from equivalence_core.templates import (
    TemplateDefinition,
    TemplateError,
    definition_from_json,
    load_seed_templates,
)
from hospital_node.core.settings import NodeSettings
from hospital_node.models import HospitalArticle, InstalledTemplate
from hospital_node.services import projection
from service_kit.errors import Unprocessable

type Templates = Mapping[str, TemplateDefinition]


def installed(session: Session) -> dict[str, TemplateDefinition]:
    return {row.code: definition_from_json(row.definition) for row in rows(session)}


def rows(session: Session) -> list[InstalledTemplate]:
    return list(session.scalars(select(InstalledTemplate).order_by(InstalledTemplate.code)))


def parse(data: Mapping[str, Any]) -> TemplateDefinition:
    try:
        return definition_from_json(data)
    except (ValidationError, TemplateError) as exc:
        raise Unprocessable(f"invalid template definition: {exc}") from exc


def install(
    session: Session,
    data: Mapping[str, Any],
    *,
    user_id: uuid.UUID,
    settings: NodeSettings,
    now: datetime,
    hub_updated_at: datetime | None = None,
) -> InstalledTemplate:
    """Installs the hub's current definition and rebuilds that category's projections in the
    same transaction. No article is re-read: new attributes simply start out unknown (D56)."""
    definition = parse(data)
    row = store(session, definition, user_id=user_id, now=now, hub_updated_at=hub_updated_at or now)
    in_category = session.scalars(
        select(HospitalArticle).where(HospitalArticle.category_code == definition.code)
    )
    for article in in_category:
        projection.rebuild(session, article, definition, settings=settings, now=now)
    return row


def store(
    session: Session,
    definition: TemplateDefinition,
    *,
    user_id: uuid.UUID,
    now: datetime,
    hub_updated_at: datetime,
) -> InstalledTemplate:
    """Replaces the category's current definition. Callers rebuild the category's projections."""
    row = session.scalar(select(InstalledTemplate).where(InstalledTemplate.code == definition.code))
    if row is None:
        row = InstalledTemplate(code=definition.code)
        session.add(row)
    row.definition = definition.model_dump(mode="json")
    row.definition_hash = definition.definition_hash
    row.hub_updated_at = hub_updated_at
    row.installed_by = user_id
    row.installed_at = now
    session.flush()
    return row


def store_seed(session: Session, *, user_id: uuid.UUID, now: datetime) -> None:
    for definition in load_seed_templates().values():
        store(session, definition, user_id=user_id, now=now, hub_updated_at=now)
