from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from hospital_node.models import EgressLog, User


def _user(**overrides: object) -> User:
    fields: dict[str, object] = {
        "email": "anna@example.org",
        "password_hash": "x",
        "role": "PURCHASER",
        "display_name": "Anna",
        "hub_subject_id": "sub_7QF2M4XK9P3TZC8W1N6R",
    }
    return User(**(fields | overrides))


def test_pragmas_are_active(engine: Engine) -> None:
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert connection.execute(text("PRAGMA journal_mode")).scalar() == "wal"


def test_datetimes_come_back_in_utc(session: Session) -> None:
    user = _user()
    session.add(user)
    session.flush()
    zurich = timezone(timedelta(hours=2))
    row = EgressLog(
        kind="ASSERTION",
        user_id=user.id,
        content={"iss": "ten_ksp"},
        content_sha256="0" * 64,
        created_at=datetime(2026, 9, 17, 11, 0, tzinfo=zurich),
    )
    session.add(row)
    session.commit()
    session.expire_all()

    stored = session.get(EgressLog, row.id)

    assert stored is not None
    assert stored.created_at == datetime(2026, 9, 17, 9, 0, tzinfo=UTC)
    assert stored.created_at.tzinfo is UTC


def test_naive_datetimes_are_refused(session: Session) -> None:
    user = _user()
    session.add(user)
    session.flush()
    session.add(
        EgressLog(
            kind="ASSERTION",
            user_id=user.id,
            content={},
            content_sha256="0" * 64,
            created_at=datetime(2026, 9, 17, 9, 0),
        )
    )

    with pytest.raises(StatementError, match="naive"):
        session.flush()


def test_enum_checks_are_enforced(session: Session) -> None:
    session.add(_user(role="SUPPLIER"))

    with pytest.raises(IntegrityError):
        session.flush()


def test_egress_rows_without_content_must_be_refusal_alerts(session: Session) -> None:
    user = _user()
    session.add(user)
    session.flush()
    now = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)
    session.add(
        EgressLog(kind="REQUIREMENT", user_id=user.id, alert="RATE_EXCEEDED", created_at=now)
    )
    session.flush()
    session.add(EgressLog(kind="REQUIREMENT", user_id=user.id, created_at=now))

    with pytest.raises(IntegrityError):
        session.flush()


def test_ids_are_time_ordered_uuid7(session: Session) -> None:
    first, second = _user(), _user(email="b@example.org", hub_subject_id="sub_K2D9V7H4Q1M8X5B3T6YZ")
    session.add_all([first, second])
    session.flush()

    assert first.id.version == 7
    assert first.id < second.id
