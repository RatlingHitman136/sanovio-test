"""When a round ends the loop (ARCHITECTURE §11, stop conditions 1–4)."""

import pytest

from equivalence_core.verdict_rules import Verdict, VerdictOutcome, VerdictReason
from supplier_hub.domain.stop_conditions import next_step
from supplier_hub.models.assessments import AssessmentStatus, ManualReason


def _missing(*gaps: str, unavailable: tuple[str, ...] = ()) -> VerdictOutcome:
    return VerdictOutcome(
        Verdict.INSUFFICIENT_DATA,
        VerdictReason.MISSING_DATA,
        blocking_gaps=gaps,
        unavailable_gaps=unavailable,
    )


def _step(outcome: VerdictOutcome, **overrides: object):  # type: ignore[no-untyped-def]
    arguments: dict[str, object] = {
        "round_no": 1,
        "max_rounds": 3,
        "input_hash": "b" * 64,
        "previous_input_hash": None,
        "askable_gaps": 2,
    }
    return next_step(outcome, **(arguments | overrides))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "verdict",
    [Verdict.EQUIVALENT, Verdict.EQUIVALENT_WITH_DEVIATIONS, Verdict.NOT_EQUIVALENT],
)
def test_a_decisive_verdict_proposes_a_resolution(verdict: Verdict) -> None:
    outcome = VerdictOutcome(verdict, VerdictReason.ALL_MATCH)

    # Even on the last round and without progress: a decision beats every other condition.
    step = _step(outcome, round_no=3, previous_input_hash="b" * 64)

    assert step.status is AssessmentStatus.PROPOSED_RESOLUTION
    assert step.manual_reason is None


def test_missing_data_with_askable_gaps_asks() -> None:
    assert _step(_missing("mdr_class")).status is AssessmentStatus.NEEDS_QUESTION_REVIEW


def test_the_round_cap_stops_the_loop() -> None:
    step = _step(_missing("mdr_class"), round_no=3)

    assert (step.status, step.manual_reason) == (
        AssessmentStatus.NEEDS_MANUAL_DECISION,
        ManualReason.ROUND_CAP,
    )


def test_an_unchanged_input_is_no_progress() -> None:
    step = _step(_missing("mdr_class"), round_no=2, previous_input_hash="b" * 64)

    assert step.manual_reason is ManualReason.NO_PROGRESS


def test_when_every_blocking_gap_is_unavailable_nobody_can_help() -> None:
    step = _step(_missing("inner_diameter_mm", unavailable=("inner_diameter_mm",)), round_no=2)

    assert step.manual_reason is ManualReason.BLOCKING_UNAVAILABLE


def test_one_askable_gap_among_unavailable_ones_still_asks() -> None:
    outcome = _missing("inner_diameter_mm", "mdr_class", unavailable=("inner_diameter_mm",))

    assert _step(outcome, round_no=2).status is AssessmentStatus.NEEDS_QUESTION_REVIEW


def test_gaps_that_may_not_be_asked_stop_the_loop() -> None:
    """Withheld attributes are judged unknown but never asked (§16)."""
    step = _step(_missing("mdr_class"), askable_gaps=0)

    assert step.manual_reason is ManualReason.BLOCKING_UNAVAILABLE
