"""The hub's queue (§12): once per dedupe key, one claimant, retries, then giving up."""

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from hub_fixtures import FakeClock
from service_kit.db import make_session_factory
from supplier_hub.jobs import queue
from supplier_hub.jobs.worker import run_pending
from supplier_hub.models import Job
from supplier_hub.models.jobs import JobKind, JobStatus

type Factory = sessionmaker[Session]


@pytest.fixture
def factory(engine: Engine) -> Factory:
    return make_session_factory(engine)


def _enqueue(
    factory: Factory, clock: FakeClock, kind: JobKind = JobKind.ASSESS, key: str | None = None
) -> Job | None:
    with factory.begin() as session:
        return queue.enqueue(session, kind, {"n": 1}, now=clock(), dedupe_key=key)


def test_a_dedupe_key_schedules_the_work_once(factory: Factory, clock: FakeClock) -> None:
    first = _enqueue(factory, clock, key="assess:asm_1:1")
    second = _enqueue(factory, clock, key="assess:asm_1:1")

    assert first is not None and second is None
    with factory() as session:
        assert len(session.scalars(select(Job)).all()) == 1


def test_jobs_run_and_chain(factory: Factory, clock: FakeClock) -> None:
    ran: list[str] = []

    def assess(session: Session, payload: Mapping[str, Any], now: datetime) -> None:
        ran.append("assess")
        queue.enqueue(session, JobKind.REBUILD_PROJECTION, {}, now=now)

    def rebuild(session: Session, payload: Mapping[str, Any], now: datetime) -> None:
        ran.append("rebuild")

    _enqueue(factory, clock)
    count = run_pending(
        factory, {JobKind.ASSESS: assess, JobKind.REBUILD_PROJECTION: rebuild}, clock=clock
    )

    assert (count, ran) == (2, ["assess", "rebuild"])
    with factory() as session:
        assert {job.status for job in session.scalars(select(Job))} == {JobStatus.SUCCEEDED}


def test_a_claimed_job_cannot_be_claimed_again(factory: Factory, clock: FakeClock) -> None:
    _enqueue(factory, clock)

    with factory.begin() as session:
        first = queue.claim(session, now=clock(), worker_id="a")
    with factory.begin() as session:
        second = queue.claim(session, now=clock(), worker_id="b")

    assert first is not None and first.locked_by == "a"
    assert second is None


def test_a_failing_job_retries_with_growing_delay_then_gives_up(
    factory: Factory, clock: FakeClock
) -> None:
    given_up: list[str] = []

    def broken(session: Session, payload: Mapping[str, Any], now: datetime) -> None:
        raise RuntimeError("judge unavailable")

    def give_up(session: Session, job: Job, now: datetime) -> None:
        given_up.append(job.kind)

    _enqueue(factory, clock)
    handlers = {JobKind.ASSESS: broken}

    assert run_pending(factory, handlers, clock=clock, on_give_up=give_up) == 1
    with factory() as session:
        job = session.scalars(select(Job)).one()
        assert (job.status, job.attempts) == (JobStatus.QUEUED, 1)
        first_delay = job.run_after - clock()

    # Not ready yet: nothing runs until the delay has passed.
    assert run_pending(factory, handlers, clock=clock, on_give_up=give_up) == 0

    for _ in range(2):
        clock.advance(minutes=5)
        run_pending(factory, handlers, clock=clock, on_give_up=give_up)

    with factory() as session:
        job = session.scalars(select(Job)).one()
        assert job.status == JobStatus.FAILED
        assert job.attempts == 3
        assert job.last_error == "RuntimeError: judge unavailable"
    assert given_up == ["ASSESS"]
    assert first_delay == timedelta(seconds=10)


def test_stuck_jobs_are_requeued(factory: Factory, clock: FakeClock) -> None:
    _enqueue(factory, clock)
    with factory.begin() as session:
        queue.claim(session, now=clock(), worker_id="dead")

    clock.advance(minutes=11)
    with factory.begin() as session:
        assert queue.requeue_stuck(session, now=clock()) == 1

    with factory() as session:
        assert session.scalars(select(Job)).one().status == JobStatus.QUEUED
