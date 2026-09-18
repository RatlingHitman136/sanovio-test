import uuid

from fastapi import APIRouter

from supplier_hub.api.deps import Context, DbSession, Supplier
from supplier_hub.models import Assessment
from supplier_hub.schemas.supplier import (
    AnswersIn,
    SupplierQuestionView,
    SupplierRequestView,
)
from supplier_hub.services import supplier_inbox
from supplier_hub.services.supplier_inbox import DraftAnswer

router = APIRouter(prefix="/supplier", tags=["supplier"])


@router.get("/requests")
def list_requests(session: DbSession, user: Supplier) -> list[SupplierRequestView]:
    return [_view(row) for row in supplier_inbox.requests(session, user)]


@router.get("/requests/{assessment_id}")
def get_request(
    assessment_id: uuid.UUID, session: DbSession, user: Supplier
) -> SupplierRequestView:
    return _view(supplier_inbox.request_for(session, user, assessment_id))


@router.put("/requests/{assessment_id}/answers")
def save_answers(
    assessment_id: uuid.UUID, body: AnswersIn, session: DbSession, user: Supplier
) -> SupplierRequestView:
    """Drafts: nothing is visible to the hospital until the batch is submitted."""
    found = supplier_inbox.request_for(session, user, assessment_id)
    supplier_inbox.save_drafts(
        session,
        user,
        found,
        [
            DraftAnswer(
                question_id=answer.question_id,
                value=answer.value,
                comment=answer.comment,
                cannot_provide=answer.cannot_provide,
                applies_to_family=answer.applies_to_family,
            )
            for answer in body.answers
        ],
    )
    return _view(found)


@router.post("/requests/{assessment_id}/submit")
def submit(
    assessment_id: uuid.UUID, context: Context, session: DbSession, user: Supplier
) -> SupplierRequestView:
    found = supplier_inbox.request_for(session, user, assessment_id)
    supplier_inbox.submit(session, user, found, now=context.clock())
    return _view(found)


def _view(row: Assessment) -> SupplierRequestView:
    return SupplierRequestView(
        assessment_id=row.id,
        hospital=supplier_inbox.hospital_name(row),
        article_no=row.variant.article_no,
        variant_label=row.variant.label,
        family=row.variant.family.name,
        status=row.status,
        created_at=row.created_at,
        questions=[
            SupplierQuestionView(
                id=question.id,
                attribute_key=question.attribute_key,
                text=question.text,
                language=question.language,
                expected_answer=question.expected_answer,
                status=question.status,
                draft=(
                    None
                    if question.answer is None
                    else {
                        "value": question.answer.value,
                        "comment": question.answer.comment,
                        "cannot_provide": question.answer.cannot_provide,
                        "applies_to_family": question.answer.applies_to_family,
                        "submitted": not question.answer.is_draft,
                    }
                ),
            )
            for question in supplier_inbox.supplier_questions(row)
        ],
    )
