"""Supplier answers become supplier facts, then the next round runs (§9, §12 hub chains).

A typed answer is a fact at once; a free-text comment goes through `extract_answer`, and an
UNCLEAR one leaves the gap open for the next round. "Cannot provide" is a fact too — the one
that lets the loop stop instead of asking again (§11 stop condition 4).
"""

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy.orm import Session

from equivalence_core.facts import SupplierSource
from equivalence_core.templates import TemplateDefinition
from equivalence_core.values import TypedValue
from llm_client import LLMClient
from supplier_hub.core.settings import HubSettings
from supplier_hub.domain import state_machine
from supplier_hub.llm import extract_answer as extraction
from supplier_hub.models import Answer, Assessment
from supplier_hub.models.assessments import ExtractionStatus
from supplier_hub.models.events import EventType
from supplier_hub.services import assessment as assessments
from supplier_hub.services import attribute_registry, catalog, llm_calls, projection, templates

_VALUE = TypeAdapter[TypedValue](TypedValue)


def extract_answers(
    session: Session,
    payload: Mapping[str, Any],
    now: datetime,
    *,
    llm: LLMClient | None,
    settings: HubSettings,
) -> None:
    """The EXTRACT_ANSWERS job: facts, the projection rebuilt, then the next ASSESS."""
    assessment = session.get(Assessment, uuid.UUID(str(payload["assessment_id"])))
    if assessment is None:
        return
    template = templates.definition(session, assessment.template_code)
    variant = assessment.variant
    fact_ids: list[str] = []
    for answer_id in payload["answer_ids"]:
        answer = session.get(Answer, uuid.UUID(str(answer_id)))
        if answer is None or answer.is_draft:
            continue
        question = answer.question
        key = question.attribute_key
        if key is None:
            continue
        scope = (
            {"family_id": variant.family_id}
            if answer.applies_to_family
            else {"variant_id": variant.id}
        )
        value, source, quote = _fact_for(
            answer, key, template, llm, settings, session, assessment, now
        )
        if source is None:
            continue
        fact = catalog.add_fact(
            session,
            key=key,
            value=value,
            raw=answer.comment or (None if value is None else str(answer.value)),
            now=now,
            source=source,
            evidence_quote=quote,
            answer_id=answer.id,
            created_by=answer.answered_by,
            **scope,
        )
        fact_ids.append(str(fact.id))

    projection.rebuild_family(session, variant.family, template, now=now)
    state_machine.record(
        session, assessment, EventType.FACTS_ADDED, now=now, data={"fact_ids": fact_ids}
    )
    assessments.schedule_round(session, assessment, now=now)


def _fact_for(
    answer: Answer,
    key: str,
    template: TemplateDefinition,
    llm: LLMClient | None,
    settings: HubSettings,
    session: Session,
    assessment: Assessment,
    now: datetime,
) -> tuple[TypedValue | None, SupplierSource | None, str | None]:
    if answer.cannot_provide:
        return None, SupplierSource.UNAVAILABLE, None
    if answer.value is not None:
        return _VALUE.validate_python(answer.value), SupplierSource.SUPPLIER_ANSWER, None
    definition = attribute_registry.definition_for(session, template, key)
    if not answer.comment or llm is None or definition is None:
        answer.extraction_status = ExtractionStatus.UNCLEAR
        return None, None, None
    extracted = extraction.extract_answer(
        llm,
        question=answer.question.text,
        definition=definition,
        comment=answer.comment,
        model=settings.extract_answer_model,
    )
    for record in extracted.records:
        llm_calls.record_call(session, record, now=now, assessment_id=assessment.id)
    if extracted.value is None:
        answer.extraction_status = ExtractionStatus.UNCLEAR
        return None, None, None
    answer.extraction_status = ExtractionStatus.EXTRACTED
    return extracted.value, SupplierSource.SUPPLIER_ANSWER, extracted.quote
