"""The rules of motion (ARCHITECTURE §11): one table of allowed moves, nothing else."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from hub_fixtures import bare_assessment
from service_kit.errors import Conflict
from supplier_hub.domain.state_machine import ALLOWED, check_version, transition
from supplier_hub.models import Event
from supplier_hub.models.assessments import FINAL_STATUSES, AssessmentStatus
from supplier_hub.services.seed import SeedReport

NOW = datetime(2026, 9, 17, 10, 0, tzinfo=UTC)
MOVES = [(start, end) for start, ends in ALLOWED.items() for end in ends]
FORBIDDEN = [
    (start, end)
    for start in AssessmentStatus
    for end in AssessmentStatus
    if end not in ALLOWED[start] and start != end
]


@pytest.mark.parametrize(("start", "end"), MOVES)
def test_every_allowed_move_is_recorded(
    session: Session, seeded: SeedReport, start: AssessmentStatus, end: AssessmentStatus
) -> None:
    assessment = bare_assessment(session, start)

    event = transition(session, assessment, end, now=NOW)

    assert assessment.status == end
    assert assessment.version == 2
    assert (event.from_status, event.to_status) == (start, end)


@pytest.mark.parametrize(("start", "end"), FORBIDDEN)
def test_every_other_move_is_refused(
    session: Session, seeded: SeedReport, start: AssessmentStatus, end: AssessmentStatus
) -> None:
    assessment = bare_assessment(session, start)

    with pytest.raises(Conflict) as refused:
        transition(session, assessment, end, now=NOW)

    assert refused.value.code == "INVALID_TRANSITION"
    assert assessment.status == start
    assert session.scalars(select(Event)).all() == []


def test_final_states_are_final_and_cancel_reaches_everything_else() -> None:
    for status in AssessmentStatus:
        if status in FINAL_STATUSES:
            assert ALLOWED[status] == frozenset()
        else:
            assert AssessmentStatus.CANCELLED in ALLOWED[status]


def test_manual_resolution_is_possible_from_every_state_but_assessing() -> None:
    for status in AssessmentStatus:
        if status in FINAL_STATUSES:
            continue
        can_resolve = AssessmentStatus.RESOLVED in ALLOWED[status]
        assert can_resolve == (status is not AssessmentStatus.ASSESSING), status


def test_a_stale_version_is_a_conflict(session: Session, seeded: SeedReport) -> None:
    assessment = bare_assessment(session)

    check_version(assessment, 1)
    with pytest.raises(Conflict) as stale:
        check_version(assessment, 0)

    assert stale.value.code == "VERSION_CONFLICT"
