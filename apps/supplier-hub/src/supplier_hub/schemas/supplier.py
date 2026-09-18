import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SupplierQuestionView(BaseModel):
    id: uuid.UUID
    attribute_key: str | None
    text: str
    language: str
    expected_answer: dict[str, Any]
    status: str
    draft: dict[str, Any] | None


class SupplierRequestView(BaseModel):
    """What a supplier may know: its product, the questions, the hospital's alias. Nothing else."""

    assessment_id: uuid.UUID
    hospital: str
    article_no: str
    variant_label: str
    family: str
    status: str
    created_at: datetime
    questions: list[SupplierQuestionView]


class AnswerIn(BaseModel):
    question_id: uuid.UUID
    value: dict[str, Any] | None = None
    comment: str | None = Field(default=None, max_length=4000)
    cannot_provide: bool = False
    applies_to_family: bool = False


class AnswersIn(BaseModel):
    answers: list[AnswerIn]
