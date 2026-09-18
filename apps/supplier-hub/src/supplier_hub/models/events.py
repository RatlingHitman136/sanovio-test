"""H.17 events: the append-only timeline of an assessment."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from service_kit.db import one_of
from supplier_hub.core.db import Base


class EventType(StrEnum):
    CREATED = "CREATED"
    ROUND_COMPLETED = "ROUND_COMPLETED"
    STATUS_CHANGED = "STATUS_CHANGED"
    REQUIREMENT_RECEIVED = "REQUIREMENT_RECEIVED"
    QUESTION_EDITED = "QUESTION_EDITED"
    QUESTION_ADDED = "QUESTION_ADDED"
    QUESTIONS_SENT = "QUESTIONS_SENT"
    PURCHASER_ANSWERS_RECEIVED = "PURCHASER_ANSWERS_RECEIVED"
    ANSWERS_SUBMITTED = "ANSWERS_SUBMITTED"
    FACTS_ADDED = "FACTS_ADDED"
    ATTRIBUTE_PROPOSED = "ATTRIBUTE_PROPOSED"
    ASSIGNED = "ASSIGNED"
    RESOLVED = "RESOLVED"
    CANCELLED = "CANCELLED"
    JOB_FAILED = "JOB_FAILED"


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        one_of("type", EventType),
        # Both empty means the system acted (a job).
        CheckConstraint("actor_user_id IS NULL OR actor_principal_id IS NULL", name="one_actor"),
    )

    assessment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assessments.id"))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    actor_principal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("hospital_principals.id")
    )
    type: Mapped[str]
    from_status: Mapped[str | None]
    to_status: Mapped[str | None]
    data: Mapped[dict[str, Any]]
    created_at: Mapped[datetime]
