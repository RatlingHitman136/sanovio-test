"""Which code runs for which job kind (§12 hub chains)."""

import uuid
from collections.abc import Mapping
from datetime import datetime
from functools import partial
from typing import Any

from sqlalchemy.orm import Session

from llm_client import LLMClient
from supplier_hub.core.settings import HubSettings
from supplier_hub.jobs.worker import Handler
from supplier_hub.models import ProductFamily
from supplier_hub.models.jobs import JobKind
from supplier_hub.services import (
    assess,
    attribute_proposals,
    enrichment,
    normalization,
    projection,
    templates,
)


def build(*, llm: LLMClient | None, settings: HubSettings) -> dict[JobKind, Handler]:
    return {
        JobKind.ASSESS: partial(assess.run_round, llm=llm, settings=settings),
        JobKind.NORMALIZE_ITEM: partial(_normalize_family, llm=llm, settings=settings),
        JobKind.REBUILD_PROJECTION: _rebuild_family,
        JobKind.EXTRACT_ANSWERS: partial(enrichment.extract_answers, llm=llm, settings=settings),
        JobKind.PROPOSE_ATTRIBUTE: partial(
            attribute_proposals.run_proposal, llm=llm, settings=settings
        ),
    }


def _normalize_family(
    session: Session,
    payload: Mapping[str, Any],
    now: datetime,
    *,
    llm: LLMClient | None,
    settings: HubSettings,
) -> None:
    family = session.get(ProductFamily, uuid.UUID(str(payload["family_id"])))
    if family is not None:
        normalization.normalize(session, [family], llm=llm, settings=settings, now=now)


def _rebuild_family(session: Session, payload: Mapping[str, Any], now: datetime) -> None:
    family = session.get(ProductFamily, uuid.UUID(str(payload["family_id"])))
    if family is not None:
        template = templates.definition(session, family.category_code or "")
        projection.rebuild_family(session, family, template, now=now)
