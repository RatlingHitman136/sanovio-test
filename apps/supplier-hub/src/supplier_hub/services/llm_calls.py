"""Stores every LLM call the hub makes (H.19); the key is never part of the record."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from llm_client import CallRecord
from supplier_hub.models import LlmCall


def record_call(session: Session, record: CallRecord, *, now: datetime) -> uuid.UUID:
    row = LlmCall(
        purpose=record.purpose,
        model=record.model,
        effort=record.effort,
        prompt_version=record.prompt_version,
        request=record.request,
        response=record.response,
        stop_reason=record.stop_reason,
        input_tokens=record.input_tokens,
        output_tokens=record.output_tokens,
        cache_read_tokens=record.cache_read_tokens,
        cache_write_tokens=record.cache_write_tokens,
        latency_ms=record.latency_ms,
        cost_usd=None if record.cost_usd is None else Decimal(str(record.cost_usd)),
        error=record.error,
        created_at=now,
    )
    session.add(row)
    session.flush()
    return row.id
