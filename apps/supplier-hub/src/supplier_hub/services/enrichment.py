"""Supplier answers become supplier facts, then the next round runs (§9, §12 hub chains).

A typed answer is a fact at once; a free-text comment goes through `extract_answer`, and an
UNCLEAR one leaves the gap open for the next round. "Cannot provide" is a fact too — the one
that lets the loop stop instead of asking again (§11 stop condition 4).
"""

import uuid
from collections.abc import Mapping, Sequence
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
    answers = _submitted(session, payload["answer_ids"])
    # Every model call happens before the first write: on SQLite a pending write holds the
    # one write lock for as long as the model takes, and every request would wait for it.
    readings = {
        answer.id: _read(session, answer, key, template, llm, settings) for answer, key in answers
    }
    known = _known_keys(session, assessment, template, answers, readings)
    fact_ids: list[str] = []
    for answer, key in answers:
        value, source, quote = _fact_for(session, answer, readings[answer.id], assessment, now)
        if source is None or (source is SupplierSource.UNAVAILABLE and key in known):
            continue
        scope = (
            {"family_id": variant.family_id}
            if answer.applies_to_family
            else {"variant_id": variant.id}
        )
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


def _known_keys(
    session: Session,
    assessment: Assessment,
    template: TemplateDefinition,
    answers: Sequence[tuple[Answer, str]],
    readings: Mapping[uuid.UUID, extraction.Extracted | None],
) -> set[str]:
    """Attributes the supplier side has a value for, already or in this batch. A "cannot
    provide" never replaces one (§9): it may answer a narrower question about the same
    attribute, e.g. one standard among the several the supplier did list."""
    known = set(projection.resolve(session, assessment.variant, template).attributes)
    for answer, key in answers:
        reading = readings[answer.id]
        if answer.value is not None or (reading is not None and reading.value is not None):
            known.add(key)
    return known


def _submitted(session: Session, answer_ids: Sequence[Any]) -> list[tuple[Answer, str]]:
    """The submitted answers whose question names an attribute or identifier."""
    found = []
    for answer_id in answer_ids:
        answer = session.get(Answer, uuid.UUID(str(answer_id)))
        if answer is not None and not answer.is_draft and answer.question.attribute_key:
            found.append((answer, answer.question.attribute_key))
    return found


def _read(
    session: Session,
    answer: Answer,
    key: str,
    template: TemplateDefinition,
    llm: LLMClient | None,
    settings: HubSettings,
) -> extraction.Extracted | None:
    """`extract_answer` for a comment-only answer; None when there is nothing to read."""
    if answer.cannot_provide or answer.value is not None or not answer.comment or llm is None:
        return None
    definition = attribute_registry.definition_for(session, template, key)
    if definition is None:
        return None
    return extraction.extract_answer(
        llm,
        question=answer.question.text,
        definition=definition,
        comment=answer.comment,
        model=settings.extract_answer_model,
    )


def _fact_for(
    session: Session,
    answer: Answer,
    extracted: extraction.Extracted | None,
    assessment: Assessment,
    now: datetime,
) -> tuple[TypedValue | None, SupplierSource | None, str | None]:
    if answer.cannot_provide:
        return None, SupplierSource.UNAVAILABLE, None
    if answer.value is not None:
        return _VALUE.validate_python(answer.value), SupplierSource.SUPPLIER_ANSWER, None
    if extracted is None:
        answer.extraction_status = ExtractionStatus.UNCLEAR
        return None, None, None
    for record in extracted.records:
        llm_calls.record_call(session, record, now=now, assessment_id=assessment.id)
    if extracted.value is None:
        answer.extraction_status = ExtractionStatus.UNCLEAR
        return None, None, None
    answer.extraction_status = ExtractionStatus.EXTRACTED
    return extracted.value, SupplierSource.SUPPLIER_ANSWER, extracted.quote
