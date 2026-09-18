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


class ProposalResult(StrEnum):
    EXISTING = "EXISTING"
    NEW = "NEW"
    IDENTIFIER = "IDENTIFIER"


class ProposalStatus(StrEnum):
    PENDING = "PENDING"
    MATCHED = "MATCHED"
    PROVISIONAL = "PROVISIONAL"
    APPROVED = "APPROVED"
    MERGED = "MERGED"
    REJECTED = "REJECTED"
    # An identifier question: the scheme went to the question, no attribute was created.
    ROUTED = "ROUTED"


class AttributeProposal(Base):
    """H.22: how a question without an attribute found (or became) one (§7.2)."""

    __tablename__ = "attribute_proposals"
    __table_args__ = (
        one_of("result", ProposalResult),
        one_of("status", ProposalStatus),
    )

    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questions.id"), unique=True)
    assessment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assessments.id"))
    category_code: Mapped[str]
    result: Mapped[str | None]
    matched_attribute_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("attribute_definitions.id")
    )
    proposal: Mapped[dict[str, Any] | None]
    attribute_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("attribute_definitions.id"))
    status: Mapped[str] = mapped_column(default=ProposalStatus.PENDING)
    identifier_key: Mapped[str | None]
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None]
    review_note: Mapped[str | None]
    llm_call_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("llm_calls.id"))
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
