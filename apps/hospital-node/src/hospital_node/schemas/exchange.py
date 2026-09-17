import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from equivalence_core.exchange.requirement import RequirementPayload
from hospital_node.models.exchange import EgressAlert, EgressKind


class RequirementRequest(BaseModel):
    answered_question_ids: tuple[str, ...] = ()


class RequirementResponse(BaseModel):
    """Exactly what the client may pass to the hub, plus the id of its egress record."""

    requirement: RequirementPayload
    egress_id: uuid.UUID


class AssertionResponse(BaseModel):
    assertion: str
    expires_at: datetime


class EgressEntry(BaseModel):
    id: uuid.UUID
    kind: EgressKind
    created_at: datetime
    user: str
    article_id: uuid.UUID | None
    content: dict[str, Any] | None
    content_sha256: str | None
    jti: str | None
    alert: EgressAlert | None


class EgressPage(BaseModel):
    entries: list[EgressEntry]
    # Issued objects per user in the selected range; refused attempts are not counted.
    issued_per_user: dict[str, int]
    alerts: int
