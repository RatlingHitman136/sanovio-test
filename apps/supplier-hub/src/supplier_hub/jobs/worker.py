"""Runs queued jobs: inline for tests and dev, or on a background thread in the app (§12)."""

import logging
import threading
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from service_kit.clock import Clock
from supplier_hub.jobs import queue
from supplier_hub.models import Job
from supplier_hub.models.jobs import JobKind

log = logging.getLogger(__name__)

type Handler = Callable[[Session, Mapping[str, Any], datetime], None]
# Called when a job gives up for good, e.g. to move its assessment to FAILED.
type GiveUp = Callable[[Session, Job, datetime], None]


def run_one(
    session_factory: sessionmaker[Session],
    handlers: Mapping[JobKind, Handler],
    *,
    clock: Clock,
    worker_id: str,
    on_give_up: GiveUp | None = None,
) -> bool:
    """Claims and runs one ready job; False when there was nothing to do."""
    with session_factory.begin() as session:
        job = queue.claim(session, now=clock(), worker_id=worker_id)
        if job is None:
            return False
        job_id, kind, payload = job.id, JobKind(job.kind), dict(job.payload)

    try:
        # The handler's work and the job's success commit together.
        with session_factory.begin() as session:
            handlers[kind](session, payload, clock())
            done = session.get(Job, job_id)
            assert done is not None
            queue.finish(done, now=clock())
    except Exception as exc:  # noqa: BLE001 — every failure is recorded, whatever it is
        log.exception("job %s (%s) failed", job_id, kind)
        with session_factory.begin() as session:
            failed = session.get(Job, job_id)
            assert failed is not None
            if queue.fail(failed, f"{type(exc).__name__}: {exc}", now=clock()) and on_give_up:
                on_give_up(session, failed, clock())
    return True


def run_pending(
    session_factory: sessionmaker[Session],
    handlers: Mapping[JobKind, Handler],
    *,
    clock: Clock,
    on_give_up: GiveUp | None = None,
    limit: int = 100,
) -> int:
    """Runs every ready job, including the ones those jobs enqueue; returns how many ran."""
    ran = 0
    while ran < limit and run_one(
        session_factory, handlers, clock=clock, worker_id="inline", on_give_up=on_give_up
    ):
        ran += 1
    return ran


class Worker:
    """A polling thread for a single-process deployment; Postgres setups run it separately."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        handlers: Mapping[JobKind, Handler],
        *,
        clock: Clock,
        on_give_up: GiveUp | None = None,
        poll_seconds: float = 1.0,
    ) -> None:
        self._session_factory = session_factory
        self._handlers = handlers
        self._clock = clock
        self._on_give_up = on_give_up
        self._poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="hub-worker", daemon=True)
        self._id = f"worker-{uuid.uuid4().hex[:8]}"

    def start(self) -> None:
        with self._session_factory.begin() as session:
            queue.requeue_stuck(session, now=self._clock())
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                busy = run_one(
                    self._session_factory,
                    self._handlers,
                    clock=self._clock,
                    worker_id=self._id,
                    on_give_up=self._on_give_up,
                )
            except Exception:  # noqa: BLE001 — the loop must survive a broken database moment
                log.exception("worker loop error")
                busy = False
            if not busy:
                self._stop.wait(self._poll_seconds)
