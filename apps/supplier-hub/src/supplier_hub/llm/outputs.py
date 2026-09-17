"""Structured output of `normalize_item` (ARCHITECTURE §13)."""

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
