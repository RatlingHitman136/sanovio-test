"""The supplier's side of the loop: its open requests, drafts, and one submission (§14, §19 step 9).

A supplier sees its own product and the questions about it, the hospital only by its alias,
and never the requirement: what the hospital asked for is not the supplier's business (§8.6).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from equivalence_core.identifiers import IdentifierScheme, checksum_valid, normalize_identifier
from equivalence_core.validation import InvalidValue, validate_value
from equivalence_core.values import IdentifierValue, TypedValue
from service_kit.errors import NotFound, Unprocessable
from supplier_hub.domain import state_machine
from supplier_hub.jobs import queue
from supplier_hub.models import Answer, Assessment, Question, User
from supplier_hub.models.assessments import (
    Addressee,
    AssessmentStatus,
    ExtractionStatus,
    QuestionStatus,
)
from supplier_hub.models.events import EventType
from supplier_hub.models.jobs import JobKind
from supplier_hub.services import attribute_registry, templates

_VALUE = TypeAdapter[TypedValue](TypedValue)


@dataclass(frozen=True)
class DraftAnswer:
    question_id: uuid.UUID
    value: dict[str, Any] | None
    comment: str | None
    cannot_provide: bool
    applies_to_family: bool


def requests(session: Session, user: User) -> Sequence[Assessment]:
    """Assessments waiting on this supplier's answers."""
    query = select(Assessment).where(
        Assessment.supplier_id == user.org_id,
        Assessment.status == AssessmentStatus.AWAITING_ANSWERS,
    )
    return session.scalars(query.order_by(Assessment.created_at)).all()


def request_for(session: Session, user: User, assessment_id: uuid.UUID) -> Assessment:
    assessment = session.get(Assessment, assessment_id)
    if assessment is None or assessment.supplier_id != user.org_id:
        raise NotFound("request not found")
    return assessment


def supplier_questions(assessment: Assessment) -> list[Question]:
    return [
        q
        for q in assessment.questions
        if q.addressee == Addressee.SUPPLIER
        and q.status != QuestionStatus.DRAFT
        and q.status != QuestionStatus.WITHDRAWN
    ]


def hospital_name(assessment: Assessment) -> str:
    tenant = assessment.tenant
    if tenant.disclose_name_to_suppliers:
        return tenant.name
    return tenant.supplier_facing_alias or "Hospital"


def save_drafts(
    session: Session,
    user: User,
    assessment: Assessment,
    drafts: Sequence[DraftAnswer],
) -> list[Answer]:
    if assessment.status != AssessmentStatus.AWAITING_ANSWERS:
        raise Unprocessable("this request is not waiting for answers")
    questions = {q.id: q for q in supplier_questions(assessment) if q.status == QuestionStatus.SENT}
    saved = []
    for draft in drafts:
        question = questions.get(draft.question_id)
        if question is None:
            raise NotFound(f"question {draft.question_id} is not open")
        value = _checked_value(session, assessment, question, draft.value)
        answer = question.answer or Answer(question_id=question.id, answered_by=user.id)
        answer.answered_by = user.id
        answer.value = None if value is None else value.model_dump(mode="json")
        answer.comment = (draft.comment or "").strip() or None
        answer.cannot_provide = draft.cannot_provide
        answer.applies_to_family = draft.applies_to_family
        answer.is_draft = True
        if question.answer is None:
            session.add(answer)
            question.answer = answer
        saved.append(answer)
    session.flush()
    return saved


def submit(session: Session, user: User, assessment: Assessment, *, now: datetime) -> list[Answer]:
    """All or nothing: a half-answered batch would start a round that asks the same again."""
    if assessment.status != AssessmentStatus.AWAITING_ANSWERS:
        raise Unprocessable("this request is not waiting for answers")
    open_questions = [q for q in supplier_questions(assessment) if q.status == QuestionStatus.SENT]
    missing = [
        str(q.id)
        for q in open_questions
        if q.answer is None
        or (q.answer.value is None and not q.answer.comment and not q.answer.cannot_provide)
    ]
    if missing:
        raise Unprocessable(f"unanswered questions: {', '.join(missing)}")

    answers = []
    for question in open_questions:
        answer = question.answer
        assert answer is not None
        answer.is_draft = False
        answer.submitted_at = now
        answer.extraction_status = (
            ExtractionStatus.PENDING
            if answer.value is None and answer.comment and not answer.cannot_provide
            else ExtractionStatus.NOT_NEEDED
        )
        question.status = (
            QuestionStatus.UNAVAILABLE if answer.cannot_provide else QuestionStatus.ANSWERED
        )
        answers.append(answer)
    session.flush()
    state_machine.transition(
        session,
        assessment,
        AssessmentStatus.ASSESSING,
        now=now,
        event=EventType.ANSWERS_SUBMITTED,
        actor_user_id=user.id,
        data={"answer_ids": [str(a.id) for a in answers]},
    )
    queue.enqueue(
        session,
        JobKind.EXTRACT_ANSWERS,
        {"assessment_id": str(assessment.id), "answer_ids": [str(a.id) for a in answers]},
        now=now,
        dedupe_key=f"extract:{assessment.id}:{assessment.current_round}",
    )
    return answers


def _checked_value(
    session: Session, assessment: Assessment, question: Question, raw: dict[str, Any] | None
) -> TypedValue | None:
    """A typed answer is validated like any other input, identifiers by their check digit."""
    if raw is None:
        return None
    try:
        value = _VALUE.validate_python(raw)
    except ValidationError as exc:
        raise Unprocessable(f"not a typed value for {question.attribute_key}") from exc
    if isinstance(value, IdentifierValue):
        scheme = IdentifierScheme(value.scheme)
        if scheme.lower() != question.attribute_key:
            raise Unprocessable(f"expected an identifier of scheme {question.attribute_key}")
        cleaned = normalize_identifier(value.value)
        return IdentifierValue(
            scheme=scheme, value=cleaned, checksum_valid=checksum_valid(scheme, cleaned)
        )
    template = templates.definition(session, assessment.template_code)
    definition = attribute_registry.definition_for(session, template, question.attribute_key or "")
    if definition is None:
        raise Unprocessable(f"{question.attribute_key} takes no attribute value here")
    try:
        return validate_value(definition, value)
    except InvalidValue as exc:
        raise Unprocessable(str(exc)) from exc
