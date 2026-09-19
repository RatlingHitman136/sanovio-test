"""Structured output of `normalize_item` (ARCHITECTURE §13)."""

from typing import Literal

from pydantic import BaseModel, Field


class ProposedFact(BaseModel):
    """The attribute key fixes the value type, so the model returns a plain JSON value."""

    attribute_key: str
    value: bool | float | str | list[str]
    unit: str | None = Field(description="Unit of a numeric value as written, else null.")
    quote: str = Field(description="The exact words of the product text that state this value.")
    confidence: float = Field(ge=0, le=1)


class NormalizedItem(BaseModel):
    index: int = Field(description="The number of the product in the input list.")
    category_code: str | None = Field(description="Best matching category code, or null.")
    facts: list[ProposedFact]


class NormalizeItems(BaseModel):
    items: list[NormalizedItem]


# --- judge -----------------------------------------------------------------------------


class AttributeJudgmentOut(BaseModel):
    attribute_key: str
    status: Literal["MATCH", "ACCEPTABLE_DEVIATION", "MISMATCH", "UNKNOWN"]
    confidence: float = Field(ge=0, le=1)
    rationale: str
    cited_fact_ids: list[str] = Field(description="Supplier fact ids the judgment rests on.")


class QuestionDraft(BaseModel):
    attribute_key: str
    addressee: Literal["SUPPLIER", "PURCHASER"]
    text: str = Field(description="One short question, in the addressee's language.")
    language: str = Field(description="Two-letter language code of `text`.")


class JudgeOutput(BaseModel):
    judgments: list[AttributeJudgmentOut]
    verdict: Literal[
        "EQUIVALENT", "EQUIVALENT_WITH_DEVIATIONS", "NOT_EQUIVALENT", "INSUFFICIENT_DATA"
    ]
    confidence: float = Field(ge=0, le=1)
    rationale: str
    questions: list[QuestionDraft]
    extra_concerns: list[str] = Field(
        description="At most three German supplier questions about something the template does "
        "not cover but a clinician would check; empty when nothing stands out."
    )


# --- extract_answer --------------------------------------------------------------------


class ExtractedAnswer(BaseModel):
    status: Literal["VALUE", "UNCLEAR"]
    value: bool | float | str | list[str] | None
    unit: str | None
    quote: str | None = Field(description="The words of the answer the value comes from.")


# --- propose_attribute -----------------------------------------------------------------


class Labels(BaseModel):
    de: str
    en: str


class AttributeProposalOut(BaseModel):
    result: Literal["EXISTING", "NEW", "IDENTIFIER"]
    key: str = Field(description="An existing key, an identifier key, or a new snake_case key.")
    value_type: Literal["number", "bool", "enum", "text", "list"] | None
    unit: str | None
    options: list[str] | None
    labels: Labels | None
    rationale: str


# --- simulate_supplier (dev only) ------------------------------------------------------


class SimulatedAnswer(BaseModel):
    question_id: str
    value: bool | float | str | list[str] | None
    unit: str | None
    comment: str | None
    cannot_provide: bool
    applies_to_family: bool


class SimulatedAnswers(BaseModel):
    answers: list[SimulatedAnswer]


# --- compare_text ----------------------------------------------------------------------


class TextReading(BaseModel):
    attribute_key: str
    status: Literal["MATCH", "MISMATCH", "UNKNOWN"]
    rationale: str = Field(description="One short sentence on why.")


class TextReadings(BaseModel):
    readings: list[TextReading]
