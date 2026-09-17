"""H.19 llm_calls: every call the hub makes on our own Anthropic account (append-only)."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import Numeric
from sqlalchemy.orm import Mapped, mapped_column

from service_kit.db import one_of
from supplier_hub.core.db import Base


class LlmPurpose(StrEnum):
    NORMALIZE_ITEM = "NORMALIZE_ITEM"
    JUDGE = "JUDGE"
    EXTRACT_ANSWER = "EXTRACT_ANSWER"
    PROPOSE_ATTRIBUTE = "PROPOSE_ATTRIBUTE"
    SIMULATE_SUPPLIER = "SIMULATE_SUPPLIER"


class LlmCall(Base):
    __tablename__ = "llm_calls"
    __table_args__ = (one_of("purpose", LlmPurpose),)

    purpose: Mapped[str]
    model: Mapped[str]
    effort: Mapped[str | None]
    prompt_version: Mapped[str]
    # The foreign key to `assessments` arrives with that table in stage 5.
    assessment_id: Mapped[uuid.UUID | None]
    request: Mapped[dict[str, Any]]
    response: Mapped[dict[str, Any] | None]
    stop_reason: Mapped[str | None]
    input_tokens: Mapped[int]
    output_tokens: Mapped[int]
    cache_read_tokens: Mapped[int]
    cache_write_tokens: Mapped[int]
    latency_ms: Mapped[int]
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    error: Mapped[str | None]
    created_at: Mapped[datetime]
