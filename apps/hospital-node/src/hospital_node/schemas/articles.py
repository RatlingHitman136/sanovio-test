import uuid
from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel, Field, model_validator

from equivalence_core.facts import HospitalSource
from equivalence_core.identifiers import IdentifierScheme
from equivalence_core.values import AttributeValue, TypedValue
from hospital_node.models import HospitalArticle
from hospital_node.models.articles import CategorySource, FactMethod


class ArticleSummary(BaseModel):
    id: uuid.UUID
    internal_id: str
    article_ref: str
    name: str
    brand: str | None
    category_code: str | None
    category_source: CategorySource | None
    data_quality_issues: list[str]


class AttributeView(BaseModel):
    key: str
    value: AttributeValue
    source: HospitalSource
    method: FactMethod | None
    quote: str | None = Field(description="The text the value was read from, if any.")
    fact_id: uuid.UUID


class IdentifierView(BaseModel):
    scheme: IdentifierScheme
    value: str
    checksum_valid: bool | None


class ReferenceView(BaseModel):
    variant_id: str
    label: str | None
    linked_at: datetime | None


class ArticleDetail(ArticleSummary):
    """Everything the purchaser sees at the node; only the requirement ever leaves."""

    annual_quantity: int | None
    order_unit: str | None
    base_units_per_order_unit: int | None
    base_unit: str | None
    target_net_price: str | None
    currency: str | None
    category_set_at: datetime | None
    attributes: list[AttributeView]
    unknown_attributes: list[str]
    unavailable_attributes: list[str]
    identifiers: list[IdentifierView]
    reference: ReferenceView | None
    requirement_hash: str | None


class CategoryUpdate(BaseModel):
    category_code: str


class FactUpdate(BaseModel):
    """A correction or answer. Identifiers use the identifier shape; the node computes
    `checksum_valid` itself."""

    value: TypedValue | None = None
    cannot_provide: bool = False
    hub_question_id: str | None = None

    @model_validator(mode="after")
    def _value_or_cannot_provide(self) -> Self:
        if (self.value is None) != self.cannot_provide:
            raise ValueError("send either a value or cannot_provide=true")
        return self


def summary_fields(article: HospitalArticle) -> dict[str, Any]:
    return {field: getattr(article, field) for field in ArticleSummary.model_fields}
