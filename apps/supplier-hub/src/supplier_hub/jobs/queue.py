"""Queue operations. Jobs are written in the same transaction as the state change that needs
them, so a crash can never leave an assessment waiting for work nobody will do."""

import logging
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from supplier_hub.models import Job
from supplier_hub.models.jobs import JobKind, JobStatus

log = logging.getLogger(__name__)

# Growing delay between attempts: 10 s, 40 s, 90 s …
_BACKOFF = timedelta(seconds=10)
# A RUNNING job older than this belonged to a worker that died.
STUCK_AFTER = timedelta(minutes=10)


def enqueue(
    session: Session,
    kind: JobKind,
    payload: Mapping[str, Any],
    *,
    now: datetime,
    dedupe_key: str | None = None,
) -> Job | None:
    """None when a job with this dedupe key already exists: the work is already scheduled."""
    if dedupe_key is not None:
        existing = session.scalar(select(Job).where(Job.dedupe_key == dedupe_key))
        if existing is not None:
            return None
    job = Job(kind=kind, payload=dict(payload), dedupe_key=dedupe_key, run_after=now)
    session.add(job)
    session.flush()
    return job


def claim(session: Session, *, now: datetime, worker_id: str) -> Job | None:
    """The oldest ready job, claimed with a conditional UPDATE so two workers never share one."""
    candidates = session.scalars(
        select(Job.id)
        .where(Job.status == JobStatus.QUEUED, Job.run_after <= now)
        .order_by(Job.run_after, Job.id)
        .limit(5)
    ).all()
    for job_id in candidates:
        claimed = session.execute(
            update(Job)
            .where(Job.id == job_id, Job.status == JobStatus.QUEUED)
            .values(status=JobStatus.RUNNING, locked_at=now, locked_by=worker_id)
        )
        if claimed.rowcount == 1:  # type: ignore[attr-defined]
            session.flush()
            job = session.get(Job, job_id)
            if job is not None:
                session.refresh(job)
                job.attempts += 1
                return job
    return None


def finish(job: Job, *, now: datetime) -> None:
    job.status = JobStatus.SUCCEEDED
    job.finished_at = now
    job.last_error = None


def fail(job: Job, error: str, *, now: datetime) -> bool:
    """Retries with a growing delay; returns True once the job has given up for good."""
    job.last_error = error[:2000]
    job.locked_at = None
    job.locked_by = None
    if job.attempts >= job.max_attempts:
        job.status = JobStatus.FAILED
        job.finished_at = now
        return True
    job.status = JobStatus.QUEUED
    job.run_after = now + _BACKOFF * job.attempts**2
    return False


def retry(job: Job, *, now: datetime) -> None:
    """An operator sends a failed job round again, with a fresh set of attempts (§17.1)."""
    job.status = JobStatus.QUEUED
    job.attempts = 0
    job.run_after = now
    job.finished_at = None


def requeue_stuck(session: Session, *, now: datetime) -> int:
    """At startup: jobs a dead worker left RUNNING go back into the queue."""
    stuck = session.execute(
        update(Job)
        .where(Job.status == JobStatus.RUNNING, Job.locked_at < now - STUCK_AFTER)
        .values(status=JobStatus.QUEUED, locked_at=None, locked_by=None, run_after=now)
    )
    count = int(stuck.rowcount or 0)  # type: ignore[attr-defined]
    if count:
        log.warning("requeued %d stuck job(s)", count)
    return count
