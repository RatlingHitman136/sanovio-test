"""The development stand-in for a supplier (§21): answers the open questions from a synthetic
datasheet, then submits them exactly as a supplier user would.

Mounted only with APP_ENV=dev and only for operators; the datasheets never appear in a
response, so no supplier or purchaser can read them.
"""

import json
import uuid
from datetime import datetime
from functools import cache
from importlib import resources
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from equivalence_core.templates import TemplateDefinition
from llm_client import LLMClient
from service_kit.errors import Conflict
from supplier_hub.core.settings import HubSettings
from supplier_hub.llm.outputs import SimulatedAnswer
from supplier_hub.llm.simulate_supplier import simulate_supplier
from supplier_hub.llm.values import typed_value
from supplier_hub.models import Assessment, User
from supplier_hub.models.assessments import AssessmentStatus, QuestionStatus
from supplier_hub.models.identity import UserRole
from supplier_hub.services import attribute_registry, llm_calls, supplier_inbox, templates
from supplier_hub.services.supplier_inbox import DraftAnswer

_NOT_SPECIFIED = "Nicht spezifiziert."


@cache
def datasheets() -> dict[str, dict[str, Any]]:
    """Family name → attribute entries; synthetic, see the file's `_note`."""
    path = resources.files("supplier_hub") / "seed" / "hidden_datasheets.json"
    raw = path.read_text(encoding="utf-8")
    return {sheet["family"]: sheet["attributes"] for sheet in json.loads(raw)["sheets"]}


def simulate(
    session: Session,
    assessment: Assessment,
    *,
    llm: LLMClient,
    settings: HubSettings,
    now: datetime,
) -> None:
    if assessment.status != AssessmentStatus.AWAITING_ANSWERS:
        raise Conflict("NOT_AWAITING_ANSWERS", "no questions are waiting for the supplier")
    questions = [
        q for q in supplier_inbox.supplier_questions(assessment) if q.status == QuestionStatus.SENT
    ]
    simulation = simulate_supplier(
        llm,
        questions=[
            {"question_id": str(q.id), "attribute_key": q.attribute_key, "text": q.text}
            for q in questions
        ],
        datasheet=datasheets().get(assessment.variant.family.name, {}),
        model=settings.simulate_supplier_model,
    )
    for record in simulation.records:
        llm_calls.record_call(session, record, now=now, assessment_id=assessment.id)
    template = templates.definition(session, assessment.template_code)
    answered = {answer.question_id: answer for answer in simulation.answers}
    drafts = [
        _draft(session, template, q.id, q.attribute_key, answered.get(str(q.id))) for q in questions
    ]
    user = _supplier_user(session, assessment)
    supplier_inbox.save_drafts(session, user, assessment, drafts)
    supplier_inbox.submit(session, user, assessment, now=now)


def _draft(
    session: Session,
    template: TemplateDefinition,
    question_id: uuid.UUID,
    key: str | None,
    answer: SimulatedAnswer | None,
) -> DraftAnswer:
    """A value the definition cannot type is dropped; its comment, if any, still goes in."""
    definition = attribute_registry.definition_for(session, template, key or "")
    value = (
        typed_value(definition, answer.value, answer.unit)
        if answer is not None and definition is not None
        else None
    )
    comment = answer.comment if answer is not None else None
    if answer is None or answer.cannot_provide or (value is None and not comment):
        return DraftAnswer(question_id, None, _NOT_SPECIFIED, True, False)
    return DraftAnswer(
        question_id,
        None if value is None else value.model_dump(mode="json"),
        comment,
        False,
        answer.applies_to_family,
    )


def _supplier_user(session: Session, assessment: Assessment) -> User:
    query = select(User).where(
        User.org_id == assessment.supplier_id, User.role == UserRole.SUPPLIER
    )
    user = session.scalars(query.order_by(User.email)).first()
    if user is None:
        raise Conflict("NO_SUPPLIER_USER", "the supplier has no account to answer with")
    return user
