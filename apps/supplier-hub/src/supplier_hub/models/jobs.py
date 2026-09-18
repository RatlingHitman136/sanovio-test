"""H.18 jobs: the hub's queue (the node has none, D53)."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column

from service_kit.db import one_of
from supplier_hub.core.db import Base


class JobKind(StrEnum):
    NORMALIZE_ITEM = "NORMALIZE_ITEM"
    ASSESS = "ASSESS"
    EXTRACT_ANSWERS = "EXTRACT_ANSWERS"
    PROPOSE_ATTRIBUTE = "PROPOSE_ATTRIBUTE"
    REBUILD_PROJECTION = "REBUILD_PROJECTION"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        one_of("kind", JobKind),
        one_of("status", JobStatus),
        Index("ix_jobs_ready", "status", "run_after"),
    )

    kind: Mapped[str]
    # Ids only: a job is re-read from the database when it runs.
    payload: Mapped[dict[str, Any]]
    dedupe_key: Mapped[str | None] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(default=JobStatus.QUEUED)
    attempts: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=3)
    run_after: Mapped[datetime]
    locked_at: Mapped[datetime | None]
    locked_by: Mapped[str | None]
    last_error: Mapped[str | None]
    finished_at: Mapped[datetime | None]
