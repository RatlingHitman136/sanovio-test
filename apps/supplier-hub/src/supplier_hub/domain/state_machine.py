"""Every allowed status move of an assessment, in one table (ARCHITECTURE §11).

A move bumps the optimistic-lock `version` and writes an `events` row, so the timeline is
complete by construction: there is no other way to change a status.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from service_kit.errors import Conflict
from supplier_hub.models import Assessment, Event
from supplier_hub.models.assessments import AssessmentStatus as S
from supplier_hub.models.events import EventType

ALLOWED: dict[S, frozenset[S]] = {
    S.ASSESSING: frozenset(
        {
            S.NEEDS_QUESTION_REVIEW,
            S.PROPOSED_RESOLUTION,
            S.NEEDS_MANUAL_DECISION,
            S.FAILED,
            S.CANCELLED,
        }
    ),
    # Sending questions with none left for the supplier goes straight back to ASSESSING.
    S.NEEDS_QUESTION_REVIEW: frozenset({S.AWAITING_ANSWERS, S.ASSESSING, S.RESOLVED, S.CANCELLED}),
    S.AWAITING_ANSWERS: frozenset({S.ASSESSING, S.RESOLVED, S.CANCELLED}),
    S.PROPOSED_RESOLUTION: frozenset({S.RESOLVED, S.NEEDS_QUESTION_REVIEW, S.CANCELLED}),
    # An extra round reopens question review: the purchaser words what to ask, then sends it.
    S.NEEDS_MANUAL_DECISION: frozenset({S.NEEDS_QUESTION_REVIEW, S.RESOLVED, S.CANCELLED}),
    S.FAILED: frozenset({S.ASSESSING, S.RESOLVED, S.CANCELLED}),
    S.RESOLVED: frozenset(),
    S.CANCELLED: frozenset(),
}


def check_version(assessment: Assessment, version: int) -> None:
    """Two purchasers acting on one assessment: the second one learns, never overwrites."""
    if version != assessment.version:
        raise Conflict(
            "VERSION_CONFLICT",
            f"the assessment changed (now version {assessment.version}); reload and retry",
        )


def transition(
    session: Session,
    assessment: Assessment,
    to: S,
    *,
    now: datetime,
    event: EventType = EventType.STATUS_CHANGED,
    actor_user_id: uuid.UUID | None = None,
    actor_principal_id: uuid.UUID | None = None,
    data: dict[str, Any] | None = None,
) -> Event:
    current = S(assessment.status)
    if to not in ALLOWED[current]:
        raise Conflict("INVALID_TRANSITION", f"an assessment cannot move from {current} to {to}")
    assessment.status = to
    assessment.version += 1
    return record(
        session,
        assessment,
        event,
        now=now,
        from_status=current,
        to_status=to,
        actor_user_id=actor_user_id,
        actor_principal_id=actor_principal_id,
        data=data,
    )


def record(
    session: Session,
    assessment: Assessment,
    event: EventType,
    *,
    now: datetime,
    from_status: str | None = None,
    to_status: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    actor_principal_id: uuid.UUID | None = None,
    data: dict[str, Any] | None = None,
) -> Event:
    """An event that is not a status move (an assignment, questions edited, facts added)."""
    row = Event(
        assessment_id=assessment.id,
        actor_user_id=actor_user_id,
        actor_principal_id=actor_principal_id,
        type=event,
        from_status=from_status,
        to_status=to_status,
        data=data or {},
        created_at=now,
    )
    session.add(row)
    session.flush()
    return row
