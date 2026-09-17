"""H.20 and H.21: the attribute registry the hub owns (§7.2, D52)."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from equivalence_core.templates import ValueType
from service_kit.db import one_of
from supplier_hub.core.db import Base


class AttributeKind(StrEnum):
    ATTRIBUTE = "ATTRIBUTE"
    # Identifier definitions can never be part of a category template (D50).
    IDENTIFIER = "IDENTIFIER"


class AttributeStatus(StrEnum):
    PROVISIONAL = "PROVISIONAL"
    APPROVED = "APPROVED"
    DEPRECATED = "DEPRECATED"


class AttributeOrigin(StrEnum):
    SEED = "SEED"
    PROPOSAL = "PROPOSAL"


class AttributeDefinition(Base):
    __tablename__ = "attribute_definitions"
    __table_args__ = (
        one_of("kind", AttributeKind),
        one_of("status", AttributeStatus),
        one_of("origin", AttributeOrigin),
        one_of("value_type", ValueType, name="value_type_known"),
    )

    key: Mapped[str] = mapped_column(unique=True)
    kind: Mapped[str] = mapped_column(default=AttributeKind.ATTRIBUTE)
    value_type: Mapped[str]
    unit: Mapped[str | None]
    options: Mapped[list[Any] | None]
    labels: Mapped[dict[str, Any]]
    synonyms: Mapped[dict[str, Any]]
    question_hint: Mapped[dict[str, Any] | None]
    status: Mapped[str]
    origin: Mapped[str]
    # Set when a proposal created or replaced this definition (stage 5).
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("attribute_definitions.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class CategoryTemplate(Base):
    """One current definition per category; the node syncs a copy of it (D52)."""

    __tablename__ = "category_templates"

    code: Mapped[str] = mapped_column(unique=True)
    parent_code: Mapped[str | None]
    keywords: Mapped[list[Any]]
    limited_template: Mapped[bool] = mapped_column(default=False)
    # [{key, criticality, comparison_rule, tolerance?, shareable}]; keys must be APPROVED.
    attributes: Mapped[list[Any]]
    definition_hash: Mapped[str] = mapped_column(String(64))
    change_note: Mapped[str | None]
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime]
    created_at: Mapped[datetime]
