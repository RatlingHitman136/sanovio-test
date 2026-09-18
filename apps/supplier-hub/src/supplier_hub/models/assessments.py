"""H.12–H.16: requirements, assessments, their rounds, questions and supplier answers."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import ForeignKey, Index, Numeric, String, UniqueConstraint, column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from equivalence_core.identifier_evidence import IdentifierEvidence
from service_kit.db import one_of
from supplier_hub.core.db import Base
from supplier_hub.models.catalog import ProductVariant
from supplier_hub.models.identity import HospitalPrincipal
from supplier_hub.models.organizations import Organization


class AssessmentStatus(StrEnum):
    ASSESSING = "ASSESSING"
    NEEDS_QUESTION_REVIEW = "NEEDS_QUESTION_REVIEW"
    AWAITING_ANSWERS = "AWAITING_ANSWERS"
    PROPOSED_RESOLUTION = "PROPOSED_RESOLUTION"
    NEEDS_MANUAL_DECISION = "NEEDS_MANUAL_DECISION"
    FAILED = "FAILED"
    RESOLVED = "RESOLVED"
    CANCELLED = "CANCELLED"


FINAL_STATUSES = frozenset({AssessmentStatus.RESOLVED, AssessmentStatus.CANCELLED})


class ProposedVerdict(StrEnum):
    EQUIVALENT = "EQUIVALENT"
    EQUIVALENT_WITH_DEVIATIONS = "EQUIVALENT_WITH_DEVIATIONS"
    NOT_EQUIVALENT = "NOT_EQUIVALENT"


class FinalVerdict(StrEnum):
    EQUIVALENT = "EQUIVALENT"
    EQUIVALENT_WITH_DEVIATIONS = "EQUIVALENT_WITH_DEVIATIONS"
    NOT_EQUIVALENT = "NOT_EQUIVALENT"
    UNDETERMINED = "UNDETERMINED"


class ResolutionKind(StrEnum):
    CONFIRMED = "CONFIRMED"
    OVERRIDDEN = "OVERRIDDEN"
    MANUAL = "MANUAL"


class ManualReason(StrEnum):
    ROUND_CAP = "ROUND_CAP"
    NO_PROGRESS = "NO_PROGRESS"
    BLOCKING_UNAVAILABLE = "BLOCKING_UNAVAILABLE"


class RoundVerdict(StrEnum):
    EQUIVALENT = "EQUIVALENT"
    EQUIVALENT_WITH_DEVIATIONS = "EQUIVALENT_WITH_DEVIATIONS"
    NOT_EQUIVALENT = "NOT_EQUIVALENT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class Addressee(StrEnum):
    SUPPLIER = "SUPPLIER"
    PURCHASER = "PURCHASER"


class QuestionOrigin(StrEnum):
    LLM = "LLM"
    TEMPLATE = "TEMPLATE"
    PURCHASER = "PURCHASER"


class QuestionStatus(StrEnum):
    DRAFT = "DRAFT"
    SENT = "SENT"
    ANSWERED = "ANSWERED"
    UNAVAILABLE = "UNAVAILABLE"
    WITHDRAWN = "WITHDRAWN"


OPEN_QUESTION_STATUSES = frozenset({QuestionStatus.DRAFT, QuestionStatus.SENT})


class ExtractionStatus(StrEnum):
    NOT_NEEDED = "NOT_NEEDED"
    PENDING = "PENDING"
    EXTRACTED = "EXTRACTED"
    UNCLEAR = "UNCLEAR"


class Requirement(Base):
    """H.12: a requirement an assessment judged against (search requirements are never stored)."""

    __tablename__ = "requirements"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    assessment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assessments.id"))
    requirement_version: Mapped[int]
    article_ref: Mapped[str]
    template_code: Mapped[str]
    payload: Mapped[dict[str, Any]]
    requirement_hash: Mapped[str] = mapped_column(String(64))
    answered_question_ids: Mapped[list[Any]]
    received_by_principal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hospital_principals.id")
    )
    created_at: Mapped[datetime]


_OPEN = column("status").not_in([status.value for status in FINAL_STATUSES])


class Assessment(Base):
    """H.13: one hospital article against one supplier variant, owned by the hospital."""

    __tablename__ = "assessments"
    __table_args__ = (
        one_of("status", AssessmentStatus),
        one_of("proposed_verdict", ProposedVerdict),
        one_of("final_verdict", FinalVerdict),
        one_of("resolution_kind", ResolutionKind),
        one_of("manual_reason", ManualReason),
        # One open assessment per (hospital, article, variant); closed ones may repeat.
        Index(
            "ux_assessments_open_pair",
            "hospital_tenant_id",
            "article_ref",
            "variant_id",
            unique=True,
            sqlite_where=_OPEN,
            postgresql_where=_OPEN,
        ),
        Index(
            "ix_assessments_assignee",
            "hospital_tenant_id",
            "assigned_to_principal_id",
            "status",
        ),
    )

    hospital_tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    article_ref: Mapped[str]
    variant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product_variants.id"))
    # Circular with requirements.assessment_id, so it is set after the first requirement.
    current_requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("requirements.id", use_alter=True)
    )
    template_code: Mapped[str]
    status: Mapped[str]
    current_round: Mapped[int] = mapped_column(default=0)
    max_rounds: Mapped[int]
    proposed_verdict: Mapped[str | None]
    final_verdict: Mapped[str | None]
    resolution_kind: Mapped[str | None]
    resolution_note: Mapped[str | None]
    manual_reason: Mapped[str | None]
    version: Mapped[int] = mapped_column(default=1)
    created_by_principal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hospital_principals.id"))
    resolved_by_principal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("hospital_principals.id")
    )
    assigned_to_principal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("hospital_principals.id")
    )
    created_at: Mapped[datetime]
    resolved_at: Mapped[datetime | None]

    tenant: Mapped[Organization] = relationship(foreign_keys=[hospital_tenant_id])
    supplier: Mapped[Organization] = relationship(foreign_keys=[supplier_id])
    variant: Mapped[ProductVariant] = relationship()
    current_requirement: Mapped[Requirement | None] = relationship(
        foreign_keys=[current_requirement_id], post_update=True
    )
    created_by: Mapped[HospitalPrincipal] = relationship(foreign_keys=[created_by_principal_id])
    assigned_to: Mapped[HospitalPrincipal | None] = relationship(
        foreign_keys=[assigned_to_principal_id]
    )
    resolved_by: Mapped[HospitalPrincipal | None] = relationship(
        foreign_keys=[resolved_by_principal_id]
    )
    rounds: Mapped[list[AssessmentRound]] = relationship(
        back_populates="assessment", order_by="AssessmentRound.round_no"
    )
    questions: Mapped[list[Question]] = relationship(
        back_populates="assessment", order_by="Question.id"
    )


class AssessmentRound(Base):
    """H.14: one judgment, append-only and replayable from its snapshot."""

    __tablename__ = "assessment_rounds"
    __table_args__ = (
        UniqueConstraint("assessment_id", "round_no"),
        one_of("identifier_evidence", IdentifierEvidence),
        one_of("rule_verdict", RoundVerdict),
        one_of("llm_verdict", RoundVerdict),
    )

    assessment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assessments.id"))
    round_no: Mapped[int]
    requirement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("requirements.id"))
    supplier_record_hash: Mapped[str] = mapped_column(String(64))
    input_hash: Mapped[str] = mapped_column(String(64))
    input_snapshot: Mapped[dict[str, Any]]
    identifier_evidence: Mapped[str]
    attribute_judgments: Mapped[list[Any]]
    rule_verdict: Mapped[str]
    llm_verdict: Mapped[str | None]
    llm_confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    disagreement: Mapped[bool] = mapped_column(default=False)
    rationale: Mapped[str | None]
    extra_concerns: Mapped[list[Any]]
    outcome_status: Mapped[str]
    definition_hash: Mapped[str] = mapped_column(String(64))
    prompt_version: Mapped[str | None]
    model_id: Mapped[str | None]
    llm_call_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("llm_calls.id"))
    created_at: Mapped[datetime]

    assessment: Mapped[Assessment] = relationship(back_populates="rounds")


class Question(Base):
    """H.15: to the supplier or to the purchaser, never revealing the other side (§8.6)."""

    __tablename__ = "questions"
    __table_args__ = (
        one_of("addressee", Addressee),
        one_of("origin", QuestionOrigin),
        one_of("status", QuestionStatus),
    )

    assessment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assessments.id"))
    round_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assessment_rounds.id"))
    addressee: Mapped[str]
    # NULL while a free question waits for its attribute proposal (§7.2).
    attribute_key: Mapped[str | None]
    text: Mapped[str]
    language: Mapped[str] = mapped_column(String(2))
    expected_answer: Mapped[dict[str, Any]]
    rationale: Mapped[str | None]
    origin: Mapped[str]
    status: Mapped[str]
    edited_by_purchaser: Mapped[bool] = mapped_column(default=False)
    answered_in_requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("requirements.id")
    )
    sent_at: Mapped[datetime | None]
    created_at: Mapped[datetime]

    assessment: Mapped[Assessment] = relationship(back_populates="questions")
    answer: Mapped[Answer | None] = relationship(back_populates="question")


class Answer(Base):
    """H.16: a supplier's answer; purchaser answers travel as requirements instead."""

    __tablename__ = "answers"
    __table_args__ = (one_of("extraction_status", ExtractionStatus),)

    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questions.id"), unique=True)
    answered_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    value: Mapped[dict[str, Any] | None]
    comment: Mapped[str | None]
    cannot_provide: Mapped[bool] = mapped_column(default=False)
    applies_to_family: Mapped[bool] = mapped_column(default=False)
    is_draft: Mapped[bool] = mapped_column(default=True)
    submitted_at: Mapped[datetime | None]
    extraction_status: Mapped[str] = mapped_column(default=ExtractionStatus.NOT_NEEDED)

    question: Mapped[Question] = relationship(back_populates="answer")
