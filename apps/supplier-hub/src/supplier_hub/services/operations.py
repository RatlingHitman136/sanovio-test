"""What an operator needs to keep the hub running: the job queue, LLM spend and how much
assessment work each hospital has, as counts only (§17.1, D58).

Nothing here returns an assessment's content, a requirement or an LLM prompt or response:
those hold hospital data, and operators never see it.
"""

import math
import uuid
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from service_kit.errors import Conflict, NotFound
from supplier_hub.jobs import queue
from supplier_hub.models import Assessment, Job, LlmCall, Organization, ProductFamily
from supplier_hub.models.jobs import JobKind, JobStatus

# These drive an assessment's state; the hospital retries them from the assessment itself,
# so the state machine stays the only way an assessment moves.
ASSESSMENT_JOBS = frozenset({JobKind.ASSESS, JobKind.EXTRACT_ANSWERS})


def jobs(
    session: Session,
    *,
    status: JobStatus | None = None,
    kind: JobKind | None = None,
    limit: int = 200,
) -> Sequence[Job]:
    query = select(Job).order_by(Job.run_after.desc()).limit(limit)
    if status is not None:
        query = query.where(Job.status == status)
    if kind is not None:
        query = query.where(Job.kind == kind)
    return session.scalars(query).all()


def retry(session: Session, job_id: uuid.UUID, *, now: datetime) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise NotFound("job not found")
    if job.kind in ASSESSMENT_JOBS:
        raise Conflict("JOB_BELONGS_TO_ASSESSMENT", "the hospital retries this from its assessment")
    if job.status != JobStatus.FAILED:
        raise Conflict("JOB_NOT_FAILED", "only a failed job can be retried")
    queue.retry(job, now=now)
    session.flush()
    return job


def renormalize(session: Session, family_id: uuid.UUID, *, now: datetime) -> Job:
    """Reads a family's catalog text again; the reading only fills attributes still missing."""
    family = session.get(ProductFamily, family_id)
    if family is None:
        raise NotFound("family not found")
    waiting = session.scalars(
        select(Job).where(
            Job.kind == JobKind.NORMALIZE_ITEM,
            Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        )
    )
    if any(job.payload.get("family_id") == str(family.id) for job in waiting):
        raise Conflict("JOB_PENDING", "this family is already waiting to be read")
    job = queue.enqueue(session, JobKind.NORMALIZE_ITEM, {"family_id": str(family.id)}, now=now)
    assert job is not None  # no dedupe key, so always a new job
    return job


@dataclass(frozen=True)
class UsageRow:
    day: date
    purpose: str
    model: str
    calls: int
    errors: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cost_usd: Decimal
    mean_latency_ms: int
    p95_latency_ms: int


def llm_usage(session: Session, *, days: int, now: datetime) -> list[UsageRow]:
    """Per day, pipeline and model over the last `days` days; only the columns that count."""
    rows = session.execute(
        select(
            LlmCall.created_at,
            LlmCall.purpose,
            LlmCall.model,
            LlmCall.error,
            LlmCall.input_tokens,
            LlmCall.output_tokens,
            LlmCall.cache_read_tokens,
            LlmCall.cost_usd,
            LlmCall.latency_ms,
        ).where(LlmCall.created_at >= now - timedelta(days=days))
    )
    groups: dict[tuple[date, str, str], list[_Call]] = defaultdict(list)
    for row in rows:
        call = _Call(
            failed=row.error is not None,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            cache_read_tokens=row.cache_read_tokens,
            cost_usd=row.cost_usd or Decimal(0),
            latency_ms=row.latency_ms,
        )
        groups[(row.created_at.date(), row.purpose, row.model)].append(call)
    return [
        _usage(day, purpose, model, calls)
        for (day, purpose, model), calls in sorted(groups.items(), reverse=True)
    ]


@dataclass(frozen=True)
class FailedCall:
    id: uuid.UUID
    purpose: str
    model: str
    created_at: datetime
    # Only the kind of failure: the full text can quote model output, and so hospital values.
    error_kind: str


def llm_failures(session: Session, *, limit: int = 50) -> list[FailedCall]:
    rows = session.execute(
        select(LlmCall.id, LlmCall.purpose, LlmCall.model, LlmCall.created_at, LlmCall.error)
        .where(LlmCall.error.is_not(None))
        .order_by(LlmCall.created_at.desc())
        .limit(limit)
    )
    return [
        FailedCall(
            id=row.id,
            purpose=row.purpose,
            model=row.model,
            created_at=row.created_at,
            error_kind=error_kind(row.error),
        )
        for row in rows
    ]


def error_kind(error: str) -> str:
    return error.split(":", 1)[0].strip()[:80]


@dataclass(frozen=True)
class AssessmentCounts:
    tenant_code: str
    by_status: dict[str, int]
    by_verdict: dict[str, int]


def assessment_counts(session: Session) -> list[AssessmentCounts]:
    """How much work each hospital has, and how it ended: counts, never an assessment."""
    statuses = _counted(session, Assessment.status)
    verdicts = _counted(session, Assessment.final_verdict)
    codes = sorted(statuses.keys() | verdicts.keys())
    return [
        AssessmentCounts(code, dict(statuses.get(code, {})), dict(verdicts.get(code, {})))
        for code in codes
    ]


def _counted(
    session: Session, column: InstrumentedAttribute[str] | InstrumentedAttribute[str | None]
) -> dict[str, dict[str, int]]:
    rows = session.execute(
        select(Organization.code, column, func.count())
        .join(Organization, Organization.id == Assessment.hospital_tenant_id)
        .where(column.is_not(None))
        .group_by(Organization.code, column)
    )
    counted: dict[str, dict[str, int]] = defaultdict(dict)
    for code, value, count in rows:
        counted[code][value] = count
    return counted


@dataclass(frozen=True)
class _Call:
    failed: bool
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cost_usd: Decimal
    latency_ms: int


def _usage(day: date, purpose: str, model: str, calls: list[_Call]) -> UsageRow:
    latencies = sorted(call.latency_ms for call in calls)
    return UsageRow(
        day=day,
        purpose=purpose,
        model=model,
        calls=len(calls),
        errors=sum(call.failed for call in calls),
        input_tokens=sum(call.input_tokens for call in calls),
        output_tokens=sum(call.output_tokens for call in calls),
        cache_read_tokens=sum(call.cache_read_tokens for call in calls),
        cost_usd=sum((call.cost_usd for call in calls), Decimal(0)),
        mean_latency_ms=round(sum(latencies) / len(latencies)),
        p95_latency_ms=latencies[math.ceil(0.95 * len(latencies)) - 1],
    )
