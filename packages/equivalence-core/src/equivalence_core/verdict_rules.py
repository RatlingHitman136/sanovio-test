"""From per-attribute judgments to one verdict (ARCHITECTURE §8.5).

Code decides; the model's own verdict is only ever a cross-check, and a purchaser confirms.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from equivalence_core.comparators import ComparisonStatus, DecidedBy, Judgment
from equivalence_core.identifier_evidence import IdentifierEvidence
from equivalence_core.templates.model import Criticality

BLOCKING = frozenset({Criticality.CRITICAL, Criticality.MAJOR})
_GAPS = frozenset(
    {ComparisonStatus.UNKNOWN, ComparisonStatus.UNAVAILABLE, ComparisonStatus.NEEDS_JUDGE}
)


class Verdict(StrEnum):
    EQUIVALENT = "EQUIVALENT"
    EQUIVALENT_WITH_DEVIATIONS = "EQUIVALENT_WITH_DEVIATIONS"
    NOT_EQUIVALENT = "NOT_EQUIVALENT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class VerdictReason(StrEnum):
    SAME_TRADE_ITEM = "SAME_TRADE_ITEM"
    CRITICAL_MISMATCH = "CRITICAL_MISMATCH"
    MISSING_DATA = "MISSING_DATA"
    DEVIATIONS = "DEVIATIONS"
    ALL_MATCH = "ALL_MATCH"


@dataclass(frozen=True)
class VerdictOutcome:
    verdict: Verdict
    reason: VerdictReason
    mismatches: tuple[str, ...] = ()
    deviations: tuple[str, ...] = ()
    # Critical or major attributes nobody knows yet; these are what questions are made of.
    blocking_gaps: tuple[str, ...] = ()
    # Blocking gaps a side already said it cannot provide (§11 stop condition 4).
    unavailable_gaps: tuple[str, ...] = ()
    minor_gaps: tuple[str, ...] = ()


def decide(
    judgments: Sequence[Judgment], evidence: IdentifierEvidence = IdentifierEvidence.NO_INFORMATION
) -> VerdictOutcome:
    """The §8.5 table, checked in order."""
    if evidence is IdentifierEvidence.SAME_TRADE_ITEM:
        # The same trade item needs no comparison at all, and no judge call.
        return VerdictOutcome(Verdict.EQUIVALENT, VerdictReason.SAME_TRADE_ITEM)

    mismatches = _keys(judgments, lambda j: j.status is ComparisonStatus.MISMATCH)
    critical_mismatches = _keys(
        judgments,
        lambda j: j.status is ComparisonStatus.MISMATCH and j.criticality is Criticality.CRITICAL,
    )
    # An attribute the judge never got to is as unknown as one nobody has data for.
    gaps = _keys(judgments, lambda j: j.status in _GAPS and j.criticality in BLOCKING)
    unavailable = _keys(
        judgments,
        lambda j: j.status is ComparisonStatus.UNAVAILABLE and j.criticality in BLOCKING,
    )
    minor_gaps = _keys(judgments, lambda j: j.status in _GAPS and j.criticality not in BLOCKING)
    deviations = _keys(
        judgments,
        lambda j: j.status is ComparisonStatus.ACCEPTABLE_DEVIATION and j.criticality in BLOCKING,
    )
    shared = {
        "mismatches": mismatches,
        "deviations": deviations,
        "blocking_gaps": gaps,
        "unavailable_gaps": unavailable,
        "minor_gaps": minor_gaps,
    }

    if critical_mismatches:
        # Early stop: a critical mismatch cannot be repaired by any answer.
        return VerdictOutcome(Verdict.NOT_EQUIVALENT, VerdictReason.CRITICAL_MISMATCH, **shared)
    if gaps:
        return VerdictOutcome(Verdict.INSUFFICIENT_DATA, VerdictReason.MISSING_DATA, **shared)
    if mismatches or deviations:
        return VerdictOutcome(
            Verdict.EQUIVALENT_WITH_DEVIATIONS, VerdictReason.DEVIATIONS, **shared
        )
    return VerdictOutcome(Verdict.EQUIVALENT, VerdictReason.ALL_MATCH, **shared)


@dataclass(frozen=True)
class MergedJudgments:
    judgments: tuple[Judgment, ...]
    # Judgments the model returned for attributes the comparators had already decided (§8.4).
    discarded: tuple[str, ...]


def apply_judgments(
    judgments: Sequence[Judgment], llm_judgments: Mapping[str, Judgment]
) -> MergedJudgments:
    """Fills in what the comparators left to the judge, and discards the rest."""
    merged = []
    used = set()
    for judgment in judgments:
        answer = llm_judgments.get(judgment.attribute_key)
        if answer is None or judgment.status is not ComparisonStatus.NEEDS_JUDGE:
            merged.append(judgment)
            continue
        used.add(judgment.attribute_key)
        merged.append(
            judgment.model_copy(
                update={
                    "status": answer.status,
                    "decided_by": DecidedBy.LLM,
                    "confidence": answer.confidence,
                    "rationale": answer.rationale,
                }
            )
        )
    return MergedJudgments(tuple(merged), tuple(sorted(set(llm_judgments) - used)))


def _keys(judgments: Sequence[Judgment], matches: Callable[[Judgment], bool]) -> tuple[str, ...]:
    return tuple(j.attribute_key for j in judgments if matches(j))
