"""N.3 hospital_articles, N.5 article_facts and N.6 article_projection."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import ForeignKey, Index, Numeric, String, and_, column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from equivalence_core.facts import HospitalSource
from hospital_node.core.db import Base
from service_kit.db import one_of


class CategorySource(StrEnum):
    RULES = "RULES"
    LLM_SUGGESTED = "LLM_SUGGESTED"
    PURCHASER = "PURCHASER"


class FactMethod(StrEnum):
    RULES = "RULES"
    LLM = "LLM"


class ReferenceSource(StrEnum):
    # Values supplied by the client from the hub catalog, unsigned (D37).
    CLIENT_REPORTED = "CLIENT_REPORTED"


class HospitalArticle(Base):
    __tablename__ = "hospital_articles"
    __table_args__ = (
        one_of("category_source", CategorySource),
        one_of("reference_source", ReferenceSource),
    )

    internal_id: Mapped[str] = mapped_column(unique=True)
    article_ref: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    brand: Mapped[str | None]
    annual_quantity: Mapped[int | None]
    order_unit: Mapped[str | None]
    base_units_per_order_unit: Mapped[int | None]
    base_unit: Mapped[str | None]
    target_net_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    currency: Mapped[str | None] = mapped_column(String(3))

    category_code: Mapped[str | None]
    category_source: Mapped[str | None]
    category_set_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    category_set_at: Mapped[datetime | None]

    reference_hub_variant_id: Mapped[str | None]
    reference_label: Mapped[str | None]
    reference_source: Mapped[str | None]
    reference_linked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reference_linked_at: Mapped[datetime | None]

    content_hash: Mapped[str] = mapped_column(String(64))
    normalized_hash: Mapped[str | None] = mapped_column(String(64))
    data_quality_issues: Mapped[list[Any]] = mapped_column(default=list)
    raw: Mapped[dict[str, Any]]

    facts: Mapped[list[ArticleFact]] = relationship(
        back_populates="article", order_by="ArticleFact.id"
    )
    projection: Mapped[ArticleProjection | None] = relationship(back_populates="article")


_ACTIVE = and_(column("superseded_by_id").is_(None), column("retracted_at").is_(None))


class ArticleFact(Base):
    """Only ever added; `superseded_by_id` and `retracted_at` are the only columns updated."""

    __tablename__ = "article_facts"
    __table_args__ = (
        one_of("source", HospitalSource),
        one_of("method", FactMethod),
        Index(
            "ix_article_facts_active",
            "article_id",
            "attribute_key",
            sqlite_where=_ACTIVE,
            postgresql_where=_ACTIVE,
        ),
    )

    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hospital_articles.id"))
    attribute_key: Mapped[str]
    # NULL only for UNAVAILABLE.
    value: Mapped[dict[str, Any] | None]
    raw_value: Mapped[str | None]
    source: Mapped[str]
    method: Mapped[str | None]
    evidence_quote: Mapped[str | None]
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    hub_variant_id: Mapped[str | None]
    hub_fact_id: Mapped[str | None]
    hub_question_id: Mapped[str | None]
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime]
    parser_version: Mapped[str | None]
    llm_call_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("llm_calls.id"))
    model_id: Mapped[str | None]
    prompt_version: Mapped[str | None]
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("article_facts.id"))
    # Set when the fact is withdrawn without a replacement (undoing the current product).
    retracted_at: Mapped[datetime | None]

    article: Mapped[HospitalArticle] = relationship(back_populates="facts")

    @property
    def is_active(self) -> bool:
        return self.superseded_by_id is None and self.retracted_at is None


class ArticleProjection(Base):
    """Derived from the facts; rebuilt on every write."""

    __tablename__ = "article_projection"

    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hospital_articles.id"), unique=True)
    category_code: Mapped[str | None]
    definition_hash: Mapped[str] = mapped_column(String(64))
    attributes: Mapped[dict[str, Any]]
    attribute_origin: Mapped[dict[str, Any]]
    identifiers: Mapped[list[Any]]
    attribute_fact_ids: Mapped[dict[str, Any]]
    unknown_attributes: Mapped[list[Any]]
    unavailable_attributes: Mapped[list[Any]]
    record_hash: Mapped[str] = mapped_column(String(64))
    requirement_hash: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[datetime]

    article: Mapped[HospitalArticle] = relationship(back_populates="projection")
