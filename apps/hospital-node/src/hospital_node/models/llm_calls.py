"""N.10 llm_calls: every normalize_article call, the hospital's audit of names sent out."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import Numeric
from sqlalchemy.orm import Mapped, mapped_column

from hospital_node.core.db import Base, one_of


class LlmPurpose(StrEnum):
    NORMALIZE_ARTICLE = "NORMALIZE_ARTICLE"


class LlmCall(Base):
    __tablename__ = "llm_calls"
    __table_args__ = (one_of("purpose", LlmPurpose),)

    purpose: Mapped[str]
    model: Mapped[str]
    effort: Mapped[str | None]
    prompt_version: Mapped[str]
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
