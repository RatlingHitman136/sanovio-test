"""H.7, H.8, H.10, H.11: supplier catalogs, their facts and the search projection."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    and_,
    column,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from equivalence_core.facts import SupplierSource
from service_kit.db import one_of
from supplier_hub.core.db import Base
from supplier_hub.models.organizations import Organization


class CategorySource(StrEnum):
    LLM_SUGGESTED = "LLM_SUGGESTED"
    SUPPLIER = "SUPPLIER"


class ProductFamily(Base):
    """A product line as printed in the catalog; its text is what `normalize_item` reads."""

    __tablename__ = "product_families"
    __table_args__ = (one_of("category_source", CategorySource),)

    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    manufacturer: Mapped[str]
    brand_name: Mapped[str | None]
    name: Mapped[str]
    product_type: Mapped[str | None]
    category_code: Mapped[str | None]
    category_source: Mapped[str | None]
    category_set_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    category_set_at: Mapped[datetime | None]
    description: Mapped[str | None]
    properties_text: Mapped[str | None]
    source_document: Mapped[str | None]
    source_page: Mapped[int | None]
    content_hash: Mapped[str] = mapped_column(String(64))
    normalized_hash: Mapped[str | None] = mapped_column(String(64))
    raw: Mapped[dict[str, Any]]
    # NULL: loaded from a printed catalog; else the supplier user who entered it (D59).
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime]

    supplier: Mapped[Organization] = relationship()
    variants: Mapped[list[ProductVariant]] = relationship(back_populates="family")


class ProductVariant(Base):
    """One orderable article of a family, as printed in its size table."""

    __tablename__ = "product_variants"
    __table_args__ = (UniqueConstraint("supplier_id", "article_no"),)

    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product_families.id"))
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    article_no: Mapped[str]
    label: Mapped[str]
    order_unit: Mapped[str | None]
    units_per_order_unit: Mapped[int | None]
    order_units_per_shipping_unit: Mapped[int | None]
    source_row: Mapped[dict[str, Any]]
    source_page: Mapped[int | None]
    # A retired article leaves search and new assessments; open ones keep it (§9).
    is_active: Mapped[bool] = mapped_column(default=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime]

    family: Mapped[ProductFamily] = relationship(back_populates="variants")
    supplier: Mapped[Organization] = relationship()


# A fact counts until a newer one supersedes it or its supplier withdraws it.
_ACTIVE = and_(column("superseded_by_id").is_(None), column("withdrawn_at").is_(None))


class ItemFact(Base):
    """H.10: a supplier fact, scoped to a family or to a single variant. Only ever added."""

    __tablename__ = "item_facts"
    __table_args__ = (
        one_of("source", SupplierSource),
        CheckConstraint("(family_id IS NULL) <> (variant_id IS NULL)", name="one_scope"),
        Index(
            "ix_item_facts_variant_active",
            "variant_id",
            "attribute_key",
            sqlite_where=_ACTIVE,
            postgresql_where=_ACTIVE,
        ),
        Index(
            "ix_item_facts_family_active",
            "family_id",
            "attribute_key",
            sqlite_where=_ACTIVE,
            postgresql_where=_ACTIVE,
        ),
    )

    family_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("product_families.id"))
    variant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("product_variants.id"))
    attribute_key: Mapped[str]
    # NULL only for UNAVAILABLE ("cannot provide").
    value: Mapped[dict[str, Any] | None]
    raw_value: Mapped[str | None]
    source: Mapped[str]
    evidence_quote: Mapped[str | None]
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    # The supplier answer this fact was read from (§9: every fact keeps its provenance).
    answer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("answers.id"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime]
    llm_call_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("llm_calls.id"))
    model_id: Mapped[str | None]
    prompt_version: Mapped[str | None]
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("item_facts.id"))
    # A supplier took its own value back; the catalog or family value shows again (§9).
    withdrawn_at: Mapped[datetime | None]
    withdrawn_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    @property
    def is_active(self) -> bool:
        return self.superseded_by_id is None and self.withdrawn_at is None


class ItemSearchProjection(Base):
    """H.11: one row per variant, family facts merged underneath its own (derived)."""

    __tablename__ = "item_search_projection"

    variant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product_variants.id"), unique=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    category_code: Mapped[str | None]
    display_name: Mapped[str]
    attributes: Mapped[dict[str, Any]]
    attribute_fact_ids: Mapped[dict[str, Any]]
    unknown_attributes: Mapped[list[Any]]
    # Values of PROVISIONAL attributes: shown, never filtered, never judged (§7.2).
    additional_attributes: Mapped[dict[str, Any]]
    identifiers: Mapped[list[Any]]
    search_text: Mapped[str]
    record_hash: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[datetime]

    variant: Mapped[ProductVariant] = relationship()
