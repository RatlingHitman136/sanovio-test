"""Assessments as the purchaser sees them: create, read, list, assign (§11, §14, §19).

The hospital is always taken from the token, never from the body, and every query is scoped
to it: another hospital's assessment is simply not found.
"""

import re
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from equivalence_core.ids import SUBJECT_ID_PATTERN
from service_kit.errors import Conflict, NotFound, Unprocessable
from supplier_hub.core.settings import HubSettings
from supplier_hub.domain import state_machine
from supplier_hub.jobs import queue
from supplier_hub.models import (
    Assessment,
    HospitalPrincipal,
    Job,
    ProductVariant,
    Requirement,
)
from supplier_hub.models.assessments import (
    FINAL_STATUSES,
    OPEN_QUESTION_STATUSES,
    Addressee,
    AssessmentStatus,
    QuestionStatus,
)
from supplier_hub.models.events import EventType
from supplier_hub.models.jobs import JobKind
from supplier_hub.services import requirement_intake
from supplier_hub.services.requirement_intake import AcceptedRequirement


def create(
    session: Session,
    principal: HospitalPrincipal,
    body: object,
    variant_id: uuid.UUID,
    *,
    settings: HubSettings,
    now: datetime,
) -> Assessment:
    accepted = requirement_intake.accept(session, body)
    variant = session.get(ProductVariant, variant_id)
    if variant is None or not variant.is_active:
        raise NotFound("variant not found")
    if variant.family.category_code != accepted.payload.template_code:
        raise Unprocessable(
            f"the variant is a {variant.family.category_code}, the requirement a "
            f"{accepted.payload.template_code}"
        )
    open_one = session.scalar(
        select(Assessment).where(
            Assessment.hospital_tenant_id == principal.tenant_id,
            Assessment.article_ref == accepted.payload.article_ref,
            Assessment.variant_id == variant.id,
            Assessment.status.not_in([status.value for status in FINAL_STATUSES]),
        )
    )
    if open_one is not None:
        raise Conflict(
            "ASSESSMENT_OPEN",
            "this article is already being assessed against this variant",
            {"assessment_id": str(open_one.id)},
        )

    assessment = Assessment(
        hospital_tenant_id=principal.tenant_id,
        supplier_id=variant.supplier_id,
        article_ref=accepted.payload.article_ref,
        variant_id=variant.id,
        template_code=accepted.payload.template_code,
        status=AssessmentStatus.ASSESSING,
        max_rounds=settings.max_rounds,
        created_by_principal_id=principal.id,
        created_at=now,
    )
    session.add(assessment)
    session.flush()
    requirement = store_requirement(session, assessment, accepted, principal, now=now)
    state_machine.record(
        session,
        assessment,
        EventType.CREATED,
        now=now,
        to_status=AssessmentStatus.ASSESSING,
        actor_principal_id=principal.id,
        data={"variant_id": str(variant.id), "requirement_id": str(requirement.id)},
    )
    family = variant.family
    if family.normalized_hash != family.content_hash:
        # Catalog text changed since it was read: read it again before judging (§12).
        queue.enqueue(
            session,
            JobKind.NORMALIZE_ITEM,
            {"family_id": str(family.id)},
            now=now,
            dedupe_key=f"normalize:{family.id}:{family.content_hash}",
        )
    schedule_round(session, assessment, now=now)
    return assessment


def store_requirement(
    session: Session,
    assessment: Assessment,
    accepted: AcceptedRequirement,
    principal: HospitalPrincipal,
    *,
    now: datetime,
) -> Requirement:
    requirement = Requirement(
        tenant_id=principal.tenant_id,
        assessment_id=assessment.id,
        requirement_version=accepted.payload.requirement_version,
        article_ref=accepted.payload.article_ref,
        template_code=accepted.payload.template_code,
        payload=accepted.payload.model_dump(mode="json"),
        requirement_hash=accepted.requirement_hash,
        answered_question_ids=list(accepted.payload.answered_question_ids),
        received_by_principal_id=principal.id,
        created_at=now,
    )
    session.add(requirement)
    session.flush()
    assessment.current_requirement_id = requirement.id
    return requirement


def add_requirement(
    session: Session,
    assessment: Assessment,
    body: object,
    *,
    version: int,
    actor: HospitalPrincipal,
    now: datetime,
) -> Requirement:
    """The purchaser's answers, travelling the only way hospital data travels: as a new
    requirement built by the node (§11, "purchaser-addressed questions")."""
    state_machine.check_version(assessment, version)
    if assessment.status in FINAL_STATUSES or assessment.status == AssessmentStatus.ASSESSING:
        raise Conflict("NOT_ACCEPTING_REQUIREMENTS", f"the assessment is {assessment.status}")
    accepted = requirement_intake.accept(session, body)
    if (
        accepted.payload.article_ref != assessment.article_ref
        or accepted.payload.template_code != assessment.template_code
    ):
        raise Unprocessable("the requirement is for another article or category")
    requirement = store_requirement(session, assessment, accepted, actor, now=now)

    answered = []
    for question in assessment.questions:
        if str(question.id) not in accepted.payload.answered_question_ids:
            continue
        if question.addressee != Addressee.PURCHASER:
            continue
        unavailable = question.attribute_key in accepted.payload.unavailable_attributes
        question.status = QuestionStatus.UNAVAILABLE if unavailable else QuestionStatus.ANSWERED
        question.answered_in_requirement_id = requirement.id
        answered.append(str(question.id))
    assessment.version += 1
    state_machine.record(
        session,
        assessment,
        EventType.PURCHASER_ANSWERS_RECEIVED,
        now=now,
        actor_principal_id=actor.id,
        data={"requirement_id": str(requirement.id), "question_ids": answered},
    )
    supplier_questions_open = any(
        q.addressee == Addressee.SUPPLIER and q.status in OPEN_QUESTION_STATUSES
        for q in assessment.questions
    )
    if assessment.status == AssessmentStatus.NEEDS_QUESTION_REVIEW and not supplier_questions_open:
        state_machine.transition(
            session, assessment, AssessmentStatus.ASSESSING, now=now, actor_principal_id=actor.id
        )
        schedule_round(session, assessment, now=now)
    return requirement


def schedule_round(
    session: Session, assessment: Assessment, *, now: datetime, reason: str = "round"
) -> Job | None:
    """`reason` separates a retry from the round it retries, so both can be scheduled."""
    round_no = assessment.current_round + 1
    return queue.enqueue(
        session,
        JobKind.ASSESS,
        {"assessment_id": str(assessment.id)},
        now=now,
        dedupe_key=(
            f"assess:{assessment.id}:{round_no}:{assessment.current_requirement_id}:{reason}"
        ),
    )


def get(session: Session, tenant_id: uuid.UUID, assessment_id: uuid.UUID) -> Assessment:
    assessment = session.get(Assessment, assessment_id)
    # Another hospital's assessment does not exist, as far as this caller can tell.
    if assessment is None or assessment.hospital_tenant_id != tenant_id:
        raise NotFound("assessment not found")
    return assessment


def list_for(
    session: Session,
    tenant_id: uuid.UUID,
    *,
    status: str | None = None,
    article_ref: str | None = None,
    assigned_to: uuid.UUID | None = None,
) -> Sequence[Assessment]:
    query = select(Assessment).where(Assessment.hospital_tenant_id == tenant_id)
    if status is not None:
        query = query.where(Assessment.status == status)
    if article_ref is not None:
        query = query.where(Assessment.article_ref == article_ref)
    if assigned_to is not None:
        query = query.where(Assessment.assigned_to_principal_id == assigned_to)
    return session.scalars(query.order_by(Assessment.created_at.desc())).all()


def principal_for_subject(
    session: Session, tenant_id: uuid.UUID, subject_id: str, *, now: datetime
) -> HospitalPrincipal:
    """Upserted: a colleague can be assigned before they have ever used the hub (§11)."""
    if not re.fullmatch(SUBJECT_ID_PATTERN, subject_id):
        raise Unprocessable("not a subject id")
    found = session.scalar(
        select(HospitalPrincipal).where(
            HospitalPrincipal.tenant_id == tenant_id, HospitalPrincipal.subject_id == subject_id
        )
    )
    if found is None:
        found = HospitalPrincipal(
            tenant_id=tenant_id, subject_id=subject_id, first_seen_at=now, last_seen_at=now
        )
        session.add(found)
        session.flush()
    return found


def assign(
    session: Session,
    assessment: Assessment,
    subject_id: str,
    *,
    actor: HospitalPrincipal,
    now: datetime,
) -> None:
    assignee = principal_for_subject(session, assessment.hospital_tenant_id, subject_id, now=now)
    assessment.assigned_to_principal_id = assignee.id
    assessment.version += 1
    state_machine.record(
        session,
        assessment,
        EventType.ASSIGNED,
        now=now,
        actor_principal_id=actor.id,
        data={"assigned_to_subject_id": subject_id},
    )


def give_up(session: Session, job: Job, now: datetime) -> None:
    """A job that failed for good leaves its assessment FAILED, visibly (§11)."""
    assessment_id = job.payload.get("assessment_id")
    if assessment_id is None:
        return
    assessment = session.get(Assessment, uuid.UUID(str(assessment_id)))
    if assessment is None or assessment.status in FINAL_STATUSES:
        return
    data: dict[str, Any] = {"job_id": str(job.id), "kind": job.kind, "error": job.last_error}
    state_machine.record(session, assessment, EventType.JOB_FAILED, now=now, data=data)
    if AssessmentStatus.FAILED in state_machine.ALLOWED[AssessmentStatus(assessment.status)]:
        state_machine.transition(session, assessment, AssessmentStatus.FAILED, now=now, data=data)
