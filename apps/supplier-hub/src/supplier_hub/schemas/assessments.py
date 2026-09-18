import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from equivalence_core.exchange.requirement import RequirementPayload


class AssessmentCreate(BaseModel):
    requirement: RequirementPayload
    variant_id: uuid.UUID


class AssessmentSummary(BaseModel):
    """One row of a list; the client joins the article name from the node by `article_ref`."""

    id: uuid.UUID
    article_ref: str
    variant_id: uuid.UUID
    article_no: str
    variant_label: str
    supplier: str
    status: str
    current_round: int
    proposed_verdict: str | None
    final_verdict: str | None
    version: int
    created_by_subject_id: str
    assigned_to_subject_id: str | None
    created_at: datetime


class RoundView(BaseModel):
    round_no: int
    identifier_evidence: str
    rule_verdict: str
    llm_verdict: str | None
    disagreement: bool
    rationale: str | None
    outcome_status: str
    attribute_judgments: list[dict[str, Any]]


class QuestionView(BaseModel):
    id: uuid.UUID
    addressee: str
    attribute_key: str | None
    text: str
    language: str
    expected_answer: dict[str, Any]
    rationale: str | None
    origin: str
    status: str
    answer: dict[str, Any] | None = None


class EventView(BaseModel):
    type: str
    from_status: str | None
    to_status: str | None
    actor: str | None
    data: dict[str, Any]
    created_at: datetime


class AssessmentDetail(AssessmentSummary):
    template_code: str
    manual_reason: str | None
    resolution_kind: str | None
    resolution_note: str | None
    resolved_by_subject_id: str | None
    rounds: list[RoundView]
    questions: list[QuestionView]
    events: list[EventView]


class AssigneeUpdate(BaseModel):
    subject_id: str = Field(max_length=40)


class QuestionEdit(BaseModel):
    version: int
    text: str | None = Field(default=None, min_length=1, max_length=2000)
    withdraw: bool = False


class QuestionAdd(BaseModel):
    version: int
    addressee: str = Field(pattern="^(SUPPLIER|PURCHASER)$")
    attribute_key: str | None = None
    text: str = Field(min_length=1, max_length=2000)


class VersionOnly(BaseModel):
    version: int


class RequirementUpdate(BaseModel):
    requirement: RequirementPayload
    version: int


class Resolve(BaseModel):
    version: int
    verdict: str = Field(
        pattern="^(EQUIVALENT|EQUIVALENT_WITH_DEVIATIONS|NOT_EQUIVALENT|UNDETERMINED)$"
    )
    note: str | None = Field(default=None, max_length=4000)
