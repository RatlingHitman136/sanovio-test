"""Structured output of `normalize_article`; quotes are fields because citations cannot be
combined with structured outputs (ARCHITECTURE §13)."""

from pydantic import BaseModel, Field


class ProposedFact(BaseModel):
    """The attribute key fixes the value type, so the model returns a plain JSON value."""

    attribute_key: str
    value: bool | float | str | list[str]
    unit: str | None = Field(description="Unit of a numeric value as written, else null.")
    quote: str = Field(description="The exact words of the article name that state this value.")
    confidence: float = Field(ge=0, le=1)


class NormalizedArticle(BaseModel):
    index: int = Field(description="The number of the article in the input list.")
    category_code: str | None = Field(description="Best matching category code, or null.")
    facts: list[ProposedFact]


class NormalizeBatch(BaseModel):
    articles: list[NormalizedArticle]
