"""Questions: the purchaser reviews them, then sends them (§11; §19 step 8).

PURCHASER questions are answered at the node and return inside a new requirement; SUPPLIER
questions wait in the supplier's inbox. Sending is refused while the purchaser still owes
answers, so a supplier is never asked about a product whose requirement is still moving.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from equivalence_core.identifiers import HUB_SCHEMES
from service_kit.errors import Conflict, NotFound, Unprocessable
from supplier_hub.domain import state_machine
from supplier_hub.models import Assessment, HospitalPrincipal, Question
from supplier_hub.models.assessments import (
    OPEN_QUESTION_STATUSES,
    Addressee,
    AssessmentStatus,
    QuestionOrigin,
    QuestionStatus,
)
from supplier_hub.models.events import EventType
from supplier_hub.services import assessment as assessments
from supplier_hub.services import attribute_proposals, attribute_registry, templates

# Identifier questions name an identifier definition instead of an attribute (D50).
IDENTIFIER_KEYS = frozenset(scheme.lower() for scheme in HUB_SCHEMES)


def _reviewable(assessment: Assessment, version: int) -> None:
    state_machine.check_version(assessment, version)
    if assessment.status != AssessmentStatus.NEEDS_QUESTION_REVIEW:
        raise Conflict("NOT_IN_REVIEW", "questions can only be changed while in review")


def _question(assessment: Assessment, question_id: uuid.UUID) -> Question:
    for question in assessment.questions:
        if question.id == question_id:
            return question
    raise NotFound("question not found")


def edit(
    session: Session,
    assessment: Assessment,
    question_id: uuid.UUID,
    *,
    text: str | None,
    withdraw: bool,
    version: int,
    actor: HospitalPrincipal,
    now: datetime,
) -> Question:
    _reviewable(assessment, version)
    question = _question(assessment, question_id)
    if question.status != QuestionStatus.DRAFT:
        raise Conflict("QUESTION_NOT_DRAFT", "only draft questions can be changed")
    if withdraw:
        question.status = QuestionStatus.WITHDRAWN
    if text is not None:
        question.text = text
        question.edited_by_purchaser = True
    assessment.version += 1
    state_machine.record(
        session,
        assessment,
        EventType.QUESTION_EDITED,
        now=now,
        actor_principal_id=actor.id,
        data={"question_id": str(question.id), "withdrawn": withdraw},
    )
    return question


def add(
    session: Session,
    assessment: Assessment,
    *,
    addressee: Addressee,
    attribute_key: str | None,
    text: str,
    version: int,
    actor: HospitalPrincipal,
    now: datetime,
) -> Question:
    """A purchaser's own question. Without a key it goes to the supplier and waits for an
    attribute proposal (§7.2); its key and typed shape arrive when the proposal is done."""
    _reviewable(assessment, version)
    template = templates.definition(session, assessment.template_code)
    expected: dict[str, Any] = {"type": "text"}
    if attribute_key is None:
        if addressee != Addressee.SUPPLIER:
            raise Unprocessable("a question without an attribute can only go to the supplier")
    elif attribute_key in IDENTIFIER_KEYS:
        expected = {"type": "identifier", "scheme": attribute_key.upper()}
    elif attribute_key in template.keys:
        expected = attribute_registry.expected_answer(template.attribute(attribute_key))
    else:
        raise Unprocessable(f"{attribute_key!r} is neither in {template.code} nor an identifier")
    question = Question(
        assessment_id=assessment.id,
        addressee=addressee,
        attribute_key=attribute_key,
        text=text,
        language="de",
        expected_answer=expected,
        origin=QuestionOrigin.PURCHASER,
        status=QuestionStatus.DRAFT,
        edited_by_purchaser=True,
        created_at=now,
    )
    session.add(question)
    assessment.questions.append(question)
    assessment.version += 1
    session.flush()
    state_machine.record(
        session,
        assessment,
        EventType.QUESTION_ADDED,
        now=now,
        actor_principal_id=actor.id,
        data={"question_id": str(question.id), "attribute_key": attribute_key},
    )
    if attribute_key is None:
        attribute_proposals.open_for(session, assessment, question, now=now)
    return question


def send(
    session: Session,
    assessment: Assessment,
    *,
    version: int,
    actor: HospitalPrincipal,
    now: datetime,
) -> list[Question]:
    _reviewable(assessment, version)
    open_for_purchaser = [
        q
        for q in assessment.questions
        if q.addressee == Addressee.PURCHASER and q.status in OPEN_QUESTION_STATUSES
    ]
    if open_for_purchaser:
        raise Conflict(
            "OPEN_PURCHASER_QUESTIONS",
            "answer or withdraw the questions addressed to you first",
            {"question_ids": [str(q.id) for q in open_for_purchaser]},
        )
    if attribute_proposals.pending(session, assessment):
        raise Conflict("ATTRIBUTE_PROPOSAL_PENDING", "attribute proposals are still running")
    attribute_proposals.make_provisional(session, assessment, now=now)
    to_send = [
        q
        for q in assessment.questions
        if q.addressee == Addressee.SUPPLIER and q.status == QuestionStatus.DRAFT
    ]
    for question in to_send:
        question.status = QuestionStatus.SENT
        question.sent_at = now
    data = {"question_ids": [str(q.id) for q in to_send]}
    if to_send:
        state_machine.transition(
            session,
            assessment,
            AssessmentStatus.AWAITING_ANSWERS,
            now=now,
            event=EventType.QUESTIONS_SENT,
            actor_principal_id=actor.id,
            data=data,
        )
    else:
        # Nothing for the supplier: the purchaser's answers alone are worth a new round.
        state_machine.transition(
            session,
            assessment,
            AssessmentStatus.ASSESSING,
            now=now,
            event=EventType.QUESTIONS_SENT,
            actor_principal_id=actor.id,
            data=data,
        )
        assessments.schedule_round(session, assessment, now=now)
    return to_send
