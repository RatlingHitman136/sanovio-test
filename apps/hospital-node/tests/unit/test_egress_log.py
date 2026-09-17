from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from hospital_node.models import EgressLog, User
from hospital_node.models.exchange import EgressAlert, EgressKind
from hospital_node.models.users import Role
from hospital_node.services import egress_log
from hospital_node.services.egress_log import Limits
from hospital_node.services.errors import RateLimited
from hospital_node.services.seed import SeedReport
from node_fixtures import FakeClock, user

LIMITS = Limits(per_hour=5, daily_alert=8)


@pytest.fixture
def anna_user(session: Session, seeded: SeedReport) -> User:
    return user(session, Role.PURCHASER)


def _issue(session: Session, who: User, clock: FakeClock, limits: Limits = LIMITS) -> EgressLog:
    return egress_log.issue(
        session,
        kind=EgressKind.REQUIREMENT,
        user=who,
        content={"template_code": "syringe_single_use"},
        limits=limits,
        now=clock(),
    )


def test_each_issued_object_is_recorded_once(
    session: Session, anna_user: User, clock: FakeClock
) -> None:
    row = _issue(session, anna_user, clock)

    assert row.content_sha256 is not None and len(row.content_sha256) == 64
    assert row.issued
    assert len(session.scalars(select(EgressLog)).all()) == 1


def test_the_alert_fires_at_eighty_percent(
    session: Session, anna_user: User, clock: FakeClock
) -> None:
    alerts = []
    for _ in range(5):
        alerts.append(_issue(session, anna_user, clock).alert)
        clock.advance(minutes=1)

    # 80% of 5 is 4, so the fourth issued object carries the alert.
    assert alerts == [None, None, None, EgressAlert.RATE_80_PERCENT, None]


def test_over_the_limit_refuses_and_records_the_attempt(
    session: Session, anna_user: User, clock: FakeClock
) -> None:
    for _ in range(5):
        _issue(session, anna_user, clock)
        clock.advance(minutes=5)

    with pytest.raises(RateLimited) as refused:
        _issue(session, anna_user, clock)

    # The five were issued at 0, 5, 10, 15 and 20 minutes; at 25 the oldest leaves in 35.
    assert refused.value.retry_after_s == 35 * 60
    refusal = session.scalars(select(EgressLog).order_by(EgressLog.created_at.desc())).first()
    assert refusal is not None
    assert refusal.alert == EgressAlert.RATE_EXCEEDED
    assert refusal.content is None
    assert not refusal.issued


def test_the_window_slides(session: Session, anna_user: User, clock: FakeClock) -> None:
    for _ in range(5):
        _issue(session, anna_user, clock)
    clock.advance(hours=1, seconds=1)

    assert _issue(session, anna_user, clock).issued


def test_refused_attempts_do_not_count_towards_the_limit(
    session: Session, anna_user: User, clock: FakeClock
) -> None:
    for _ in range(5):
        _issue(session, anna_user, clock)
    for _ in range(3):
        with pytest.raises(RateLimited):
            _issue(session, anna_user, clock)
    clock.advance(hours=2)

    assert _issue(session, anna_user, clock).alert is None


def test_the_daily_alert_fires_once(session: Session, anna_user: User, clock: FakeClock) -> None:
    generous = Limits(per_hour=100, daily_alert=3)
    alerts = []
    for _ in range(4):
        alerts.append(_issue(session, anna_user, clock, generous).alert)
        clock.advance(minutes=30)

    assert alerts == [None, None, EgressAlert.UNUSUAL_DAILY_VOLUME, None]


def test_limits_are_separate_per_kind(session: Session, anna_user: User, clock: FakeClock) -> None:
    for _ in range(5):
        _issue(session, anna_user, clock)

    assertion = egress_log.issue(
        session,
        kind=EgressKind.ASSERTION,
        user=anna_user,
        content={"iss": "ten_ksp"},
        limits=LIMITS,
        now=clock(),
    )

    assert assertion.issued


def test_history_filters(session: Session, anna_user: User, clock: FakeClock) -> None:
    first = _issue(session, anna_user, clock)
    clock.advance(hours=2)
    second = _issue(session, anna_user, clock)

    recent = egress_log.history(session, since=first.created_at + timedelta(minutes=1))

    assert [row.id for row in recent] == [second.id]
    assert len(egress_log.history(session, user_id=anna_user.id)) == 2
