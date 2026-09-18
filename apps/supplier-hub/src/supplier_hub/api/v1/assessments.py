import uuid
from collections.abc import Callable

from fastapi import APIRouter, status
from sqlalchemy import select

from supplier_hub.api.deps import Context, CurrentPrincipal, DbSession
from supplier_hub.models import Assessment, Event, HospitalPrincipal
from supplier_hub.models.assessments import Addressee, FinalVerdict
from supplier_hub.schemas.assessments import (
    AssessmentCreate,
    AssessmentDetail,
    AssessmentSummary,
    AssigneeUpdate,
    EventView,
    QuestionAdd,
    QuestionEdit,
    QuestionView,
    RequirementUpdate,
    Resolve,
    RoundView,
    VersionOnly,
)
from supplier_hub.services import assessment as assessments
from supplier_hub.services import questions, resolution

router = APIRouter(prefix="/assessments", tags=["assessments"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def create_assessment(
    body: AssessmentCreate, context: Context, session: DbSession, caller: CurrentPrincipal
) -> AssessmentSummary:
    """Accepted: the first round runs as a job; poll `GET /assessments/{id}` (§19 step 4)."""
    created = assessments.create(
        session,
        caller.principal,
        body.requirement.model_dump(mode="json"),
        body.variant_id,
        settings=context.settings,
        now=context.clock(),
    )
    return summary(created)


@router.get("")
def list_assessments(
    context: Context,
    session: DbSession,
    caller: CurrentPrincipal,
    status: str | None = None,
    article_ref: str | None = None,
    assigned_to: str | None = None,
) -> list[AssessmentSummary]:
    assignee = None
    if assigned_to == "me":
        assignee = caller.principal.id
    elif assigned_to is not None:
        assignee = assessments.principal_for_subject(
            session, caller.tenant.id, assigned_to, now=context.clock()
        ).id
    found = assessments.list_for(
        session, caller.tenant.id, status=status, article_ref=article_ref, assigned_to=assignee
    )
    return [summary(row) for row in found]


@router.get("/{assessment_id}")
def get_assessment(
    assessment_id: uuid.UUID, session: DbSession, caller: CurrentPrincipal
) -> AssessmentDetail:
    return detail(session, assessments.get(session, caller.tenant.id, assessment_id))


@router.put("/{assessment_id}/assignee")
def set_assignee(
    assessment_id: uuid.UUID,
    body: AssigneeUpdate,
    context: Context,
    session: DbSession,
    caller: CurrentPrincipal,
) -> AssessmentSummary:
    found = assessments.get(session, caller.tenant.id, assessment_id)
    assessments.assign(session, found, body.subject_id, actor=caller.principal, now=context.clock())
    return summary(found)


@router.patch("/{assessment_id}/questions/{question_id}")
def edit_question(
    assessment_id: uuid.UUID,
    question_id: uuid.UUID,
    body: QuestionEdit,
    context: Context,
    session: DbSession,
    caller: CurrentPrincipal,
) -> AssessmentDetail:
    found = assessments.get(session, caller.tenant.id, assessment_id)
    questions.edit(
        session,
        found,
        question_id,
        text=body.text,
        withdraw=body.withdraw,
        version=body.version,
        actor=caller.principal,
        now=context.clock(),
    )
    return detail(session, found)


@router.post("/{assessment_id}/questions")
def add_question(
    assessment_id: uuid.UUID,
    body: QuestionAdd,
    context: Context,
    session: DbSession,
    caller: CurrentPrincipal,
) -> AssessmentDetail:
    found = assessments.get(session, caller.tenant.id, assessment_id)
    questions.add(
        session,
        found,
        addressee=Addressee(body.addressee),
        attribute_key=body.attribute_key,
        text=body.text,
        version=body.version,
        actor=caller.principal,
        now=context.clock(),
    )
    return detail(session, found)


@router.post("/{assessment_id}/send-questions")
def send_questions(
    assessment_id: uuid.UUID,
    body: VersionOnly,
    context: Context,
    session: DbSession,
    caller: CurrentPrincipal,
) -> AssessmentSummary:
    found = assessments.get(session, caller.tenant.id, assessment_id)
    questions.send(
        session, found, version=body.version, actor=caller.principal, now=context.clock()
    )
    return summary(found)


@router.post("/{assessment_id}/requirements")
def add_requirement(
    assessment_id: uuid.UUID,
    body: RequirementUpdate,
    context: Context,
    session: DbSession,
    caller: CurrentPrincipal,
) -> AssessmentSummary:
    """The purchaser's answers, as a new requirement built by the node (§11)."""
    found = assessments.get(session, caller.tenant.id, assessment_id)
    assessments.add_requirement(
        session,
        found,
        body.requirement.model_dump(mode="json"),
        version=body.version,
        actor=caller.principal,
        now=context.clock(),
    )
    return summary(found)


@router.post("/{assessment_id}/resolve")
def resolve(
    assessment_id: uuid.UUID,
    body: Resolve,
    context: Context,
    session: DbSession,
    caller: CurrentPrincipal,
) -> AssessmentSummary:
    found = assessments.get(session, caller.tenant.id, assessment_id)
    resolution.resolve(
        session,
        found,
        verdict=FinalVerdict(body.verdict),
        note=body.note,
        version=body.version,
        actor=caller.principal,
        now=context.clock(),
    )
    return summary(found)


def _action(name: str, action: Callable[..., None]) -> None:
    """The version-only actions share one shape: POST {version} → the updated summary."""

    def endpoint(
        assessment_id: uuid.UUID,
        body: VersionOnly,
        context: Context,
        session: DbSession,
        caller: CurrentPrincipal,
    ) -> AssessmentSummary:
        found = assessments.get(session, caller.tenant.id, assessment_id)
        action(session, found, version=body.version, actor=caller.principal, now=context.clock())
        return summary(found)

    router.add_api_route(f"/{{assessment_id}}/{name}", endpoint, methods=["POST"], name=name)


_action("request-more-info", resolution.request_more_info)
_action("extra-round", resolution.extra_round)
_action("retry", resolution.retry)
_action("cancel", resolution.cancel)


def summary(row: Assessment) -> AssessmentSummary:
    return AssessmentSummary(
        id=row.id,
        article_ref=row.article_ref,
        variant_id=row.variant_id,
        article_no=row.variant.article_no,
        variant_label=row.variant.label,
        supplier=row.supplier.name,
        status=row.status,
        current_round=row.current_round,
        proposed_verdict=row.proposed_verdict,
        final_verdict=row.final_verdict,
        version=row.version,
        created_by_subject_id=row.created_by.subject_id,
        assigned_to_subject_id=row.assigned_to.subject_id if row.assigned_to else None,
        created_at=row.created_at,
    )


def detail(session: DbSession, row: Assessment) -> AssessmentDetail:
    events = session.scalars(
        select(Event).where(Event.assessment_id == row.id).order_by(Event.created_at, Event.id)
    ).all()
    subjects = {
        principal.id: principal.subject_id
        for principal in session.scalars(
            select(HospitalPrincipal).where(HospitalPrincipal.tenant_id == row.hospital_tenant_id)
        )
    }
    return AssessmentDetail(
        **summary(row).model_dump(),
        template_code=row.template_code,
        manual_reason=row.manual_reason,
        resolution_kind=row.resolution_kind,
        resolution_note=row.resolution_note,
        resolved_by_subject_id=row.resolved_by.subject_id if row.resolved_by else None,
        rounds=[
            RoundView(
                round_no=r.round_no,
                identifier_evidence=r.identifier_evidence,
                rule_verdict=r.rule_verdict,
                llm_verdict=r.llm_verdict,
                disagreement=r.disagreement,
                rationale=r.rationale,
                outcome_status=r.outcome_status,
                attribute_judgments=r.attribute_judgments,
            )
            for r in row.rounds
        ],
        questions=[
            QuestionView(
                id=q.id,
                addressee=q.addressee,
                attribute_key=q.attribute_key,
                text=q.text,
                language=q.language,
                expected_answer=q.expected_answer,
                rationale=q.rationale,
                origin=q.origin,
                status=q.status,
                answer=(
                    None
                    if q.answer is None or q.answer.is_draft
                    else {
                        "value": q.answer.value,
                        "comment": q.answer.comment,
                        "cannot_provide": q.answer.cannot_provide,
                        "applies_to_family": q.answer.applies_to_family,
                    }
                ),
            )
            for q in row.questions
        ],
        events=[
            EventView(
                type=e.type,
                from_status=e.from_status,
                to_status=e.to_status,
                # A supplier or operator acts as their organization; purchasers as a subject.
                actor=(
                    subjects.get(e.actor_principal_id)
                    if e.actor_principal_id
                    else ("supplier" if e.actor_user_id else None)
                ),
                data=e.data,
                created_at=e.created_at,
            )
            for e in events
        ],
    )
