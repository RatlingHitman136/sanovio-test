"""Keeping the hub running: jobs, LLM spend and assessment counts. Never an assessment's
content, a requirement or an LLM prompt or response (§17.1, D58)."""

import uuid

from fastapi import APIRouter, Query

from supplier_hub.api.deps import Context, DbSession, Operator
from supplier_hub.models import Job
from supplier_hub.models.audit import AuditAction
from supplier_hub.models.jobs import JobKind, JobStatus
from supplier_hub.schemas.admin import (
    AssessmentCountsView,
    FailedCallView,
    JobView,
    UsageView,
)
from supplier_hub.services import operations, operator_audit

router = APIRouter()


@router.get("/jobs")
def list_jobs(
    session: DbSession, status: JobStatus | None = None, kind: JobKind | None = None
) -> list[JobView]:
    return [job_view(job) for job in operations.jobs(session, status=status, kind=kind)]


@router.post("/jobs/{job_id}/retry")
def retry_job(
    job_id: uuid.UUID, context: Context, session: DbSession, operator: Operator
) -> JobView:
    job = operations.retry(session, job_id, now=context.clock())
    operator_audit.record(
        session,
        operator,
        AuditAction.JOB_RETRIED,
        target_type="job",
        target_id=job.id,
        now=context.clock(),
        data={"kind": job.kind},
    )
    return job_view(job)


@router.get("/llm-usage")
def llm_usage(
    context: Context, session: DbSession, days: int = Query(default=7, ge=1, le=90)
) -> list[UsageView]:
    rows = operations.llm_usage(session, days=days, now=context.clock())
    return [UsageView.model_validate(row, from_attributes=True) for row in rows]


@router.get("/llm-usage/failures")
def llm_failures(session: DbSession) -> list[FailedCallView]:
    rows = operations.llm_failures(session)
    return [FailedCallView.model_validate(row, from_attributes=True) for row in rows]


@router.get("/stats/assessments")
def assessment_counts(session: DbSession) -> list[AssessmentCountsView]:
    rows = operations.assessment_counts(session)
    return [AssessmentCountsView.model_validate(row, from_attributes=True) for row in rows]


def job_view(job: Job) -> JobView:
    return JobView(
        id=job.id,
        kind=job.kind,
        status=job.status,
        payload=job.payload,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        run_after=job.run_after,
        finished_at=job.finished_at,
        last_error=job.last_error and operations.error_kind(job.last_error),
        retryable=job.status == JobStatus.FAILED and job.kind not in operations.ASSESSMENT_JOBS,
    )
