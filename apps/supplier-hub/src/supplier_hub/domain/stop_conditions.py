"""When a round ends the loop, and how (ARCHITECTURE §11, stop conditions 1–4)."""

from dataclasses import dataclass

from equivalence_core.verdict_rules import Verdict, VerdictOutcome
from supplier_hub.models.assessments import AssessmentStatus, ManualReason


@dataclass(frozen=True)
class NextStep:
    status: AssessmentStatus
    manual_reason: ManualReason | None = None


def next_step(
    outcome: VerdictOutcome,
    *,
    round_no: int,
    max_rounds: int,
    input_hash: str,
    previous_input_hash: str | None,
    askable_gaps: int,
) -> NextStep:
    """Checked in the order of §11; the first that applies decides."""
    if outcome.verdict is not Verdict.INSUFFICIENT_DATA:
        return NextStep(AssessmentStatus.PROPOSED_RESOLUTION)
    if round_no >= max_rounds:
        return NextStep(AssessmentStatus.NEEDS_MANUAL_DECISION, ManualReason.ROUND_CAP)
    if previous_input_hash is not None and previous_input_hash == input_hash:
        # Nothing about either side or the template changed, so another round would repeat.
        return NextStep(AssessmentStatus.NEEDS_MANUAL_DECISION, ManualReason.NO_PROGRESS)
    all_unavailable = set(outcome.blocking_gaps) <= set(outcome.unavailable_gaps)
    if all_unavailable or askable_gaps == 0:
        # Nobody can be asked anything useful: every gap is "cannot provide" or withheld.
        return NextStep(AssessmentStatus.NEEDS_MANUAL_DECISION, ManualReason.BLOCKING_UNAVAILABLE)
    return NextStep(AssessmentStatus.NEEDS_QUESTION_REVIEW)
