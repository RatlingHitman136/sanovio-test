"""Ending an assessment, or giving it another chance (ARCHITECTURE §11).

A purchaser confirms or overrides what the rules proposed, or decides manually where the loop
could not; code proposes, a person decides. Every action carries the version it was based on.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from service_kit.errors import Conflict, Unprocessable
from supplier_hub.domain import state_machine
from supplier_hub.models import Assessment, HospitalPrincipal
from supplier_hub.models.assessments import AssessmentStatus, FinalVerdict, ResolutionKind
from supplier_hub.models.events import EventType
from supplier_hub.services import assessment as assessments


def resolve(
    session: Session,
    assessment: Assessment,
    *,
    verdict: FinalVerdict,
    note: str | None,
    version: int,
    actor: HospitalPrincipal,
    now: datetime,
) -> None:
    state_machine.check_version(assessment, version)
    note = (note or "").strip() or None
    if assessment.status == AssessmentStatus.PROPOSED_RESOLUTION:
        if verdict == assessment.proposed_verdict:
            kind = ResolutionKind.CONFIRMED
        elif verdict is FinalVerdict.UNDETERMINED:
            raise Unprocessable("UNDETERMINED is for manual decisions only")
        elif note is None:
            raise Unprocessable("overriding the proposed verdict needs a note")
        else:
            kind = ResolutionKind.OVERRIDDEN
    else:
        kind = ResolutionKind.MANUAL
    assessment.final_verdict = verdict
    assessment.resolution_kind = kind
    assessment.resolution_note = note
    assessment.resolved_by_principal_id = actor.id
    assessment.resolved_at = now
    state_machine.transition(
        session,
        assessment,
        AssessmentStatus.RESOLVED,
        now=now,
        event=EventType.RESOLVED,
        actor_principal_id=actor.id,
        data={"final_verdict": verdict, "resolution_kind": kind, "note": note},
    )


def request_more_info(
    session: Session,
    assessment: Assessment,
    *,
    version: int,
    actor: HospitalPrincipal,
    now: datetime,
) -> None:
    """Not convinced by the proposal: back to question review to ask something more."""
    state_machine.check_version(assessment, version)
    if assessment.status != AssessmentStatus.PROPOSED_RESOLUTION:
        raise Conflict("NOT_PROPOSED", "only a proposed resolution can ask for more information")
    assessment.proposed_verdict = None
    state_machine.transition(
        session,
        assessment,
        AssessmentStatus.NEEDS_QUESTION_REVIEW,
        now=now,
        actor_principal_id=actor.id,
    )


def extra_round(
    session: Session,
    assessment: Assessment,
    *,
    version: int,
    actor: HospitalPrincipal,
    now: datetime,
) -> None:
    """Past the round cap or out of answers: one more round, with questions the purchaser words."""
    state_machine.check_version(assessment, version)
    if assessment.status != AssessmentStatus.NEEDS_MANUAL_DECISION:
        raise Conflict("NOT_MANUAL", "an extra round is for assessments waiting for a decision")
    assessment.max_rounds = max(assessment.max_rounds, assessment.current_round + 1)
    assessment.manual_reason = None
    state_machine.transition(
        session,
        assessment,
        AssessmentStatus.NEEDS_QUESTION_REVIEW,
        now=now,
        actor_principal_id=actor.id,
    )


def retry(
    session: Session,
    assessment: Assessment,
    *,
    version: int,
    actor: HospitalPrincipal,
    now: datetime,
) -> None:
    """A round that failed for good (the LLM was down, say) is run again."""
    state_machine.check_version(assessment, version)
    if assessment.status != AssessmentStatus.FAILED:
        raise Conflict("NOT_FAILED", "only a failed assessment can be retried")
    state_machine.transition(
        session, assessment, AssessmentStatus.ASSESSING, now=now, actor_principal_id=actor.id
    )
    assessments.schedule_round(session, assessment, now=now, reason=f"retry{assessment.version}")


def cancel(
    session: Session,
    assessment: Assessment,
    *,
    version: int,
    actor: HospitalPrincipal,
    now: datetime,
) -> None:
    state_machine.check_version(assessment, version)
    state_machine.transition(
        session,
        assessment,
        AssessmentStatus.CANCELLED,
        now=now,
        event=EventType.CANCELLED,
        actor_principal_id=actor.id,
    )
