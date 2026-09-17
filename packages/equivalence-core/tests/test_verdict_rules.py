import pytest

from equivalence_core.comparators import (
    ComparisonStatus,
    DecidedBy,
    HospitalSide,
    Judgment,
    MissingSide,
)
from equivalence_core.exchange.requirement import AttributeOrigin
from equivalence_core.identifier_evidence import IdentifierEvidence
from equivalence_core.templates.model import ComparisonRule, Criticality
from equivalence_core.values import EnumValue
from equivalence_core.verdict_rules import Verdict, VerdictReason, apply_judgments, decide


def _judgment(
    key: str,
    status: ComparisonStatus,
    criticality: Criticality = Criticality.CRITICAL,
    **kwargs: object,
) -> Judgment:
    missing = (
        MissingSide.SUPPLIER
        if status in (ComparisonStatus.UNKNOWN, ComparisonStatus.UNAVAILABLE)
        else None
    )
    return Judgment(
        attribute_key=key,
        criticality=criticality,
        rule=ComparisonRule.EXACT,
        status=status,
        missing=missing,
        **kwargs,  # type: ignore[arg-type]
    )


def test_same_trade_item_wins_over_everything() -> None:
    critical_mismatch = [_judgment("connector", ComparisonStatus.MISMATCH)]

    outcome = decide(critical_mismatch, IdentifierEvidence.SAME_TRADE_ITEM)

    assert outcome.verdict is Verdict.EQUIVALENT
    assert outcome.reason is VerdictReason.SAME_TRADE_ITEM
    assert outcome.mismatches == ()


def test_a_critical_mismatch_stops_the_loop() -> None:
    outcome = decide(
        [
            _judgment("connector", ComparisonStatus.MISMATCH),
            _judgment("mdr_class", ComparisonStatus.UNKNOWN),
        ]
    )

    assert outcome.verdict is Verdict.NOT_EQUIVALENT
    assert outcome.reason is VerdictReason.CRITICAL_MISMATCH
    assert outcome.mismatches == ("connector",)


@pytest.mark.parametrize("criticality", [Criticality.CRITICAL, Criticality.MAJOR])
@pytest.mark.parametrize(
    "status", [ComparisonStatus.UNKNOWN, ComparisonStatus.UNAVAILABLE, ComparisonStatus.NEEDS_JUDGE]
)
def test_a_blocking_gap_means_insufficient_data(
    criticality: Criticality, status: ComparisonStatus
) -> None:
    outcome = decide(
        [_judgment("sterile", ComparisonStatus.MATCH), _judgment("dehp_free", status, criticality)]
    )

    assert outcome.verdict is Verdict.INSUFFICIENT_DATA
    assert outcome.reason is VerdictReason.MISSING_DATA
    assert outcome.blocking_gaps == ("dehp_free",)


def test_unavailable_gaps_are_listed_separately() -> None:
    outcome = decide(
        [
            _judgment("dehp_free", ComparisonStatus.UNAVAILABLE, Criticality.MAJOR),
            _judgment("mdr_class", ComparisonStatus.UNKNOWN),
        ]
    )

    assert outcome.blocking_gaps == ("dehp_free", "mdr_class")
    assert outcome.unavailable_gaps == ("dehp_free",)


def test_a_major_mismatch_is_a_deviation_not_a_stop() -> None:
    outcome = decide(
        [
            _judgment("connector", ComparisonStatus.MATCH),
            _judgment("design", ComparisonStatus.MISMATCH, Criticality.MAJOR),
        ]
    )

    assert outcome.verdict is Verdict.EQUIVALENT_WITH_DEVIATIONS
    assert outcome.reason is VerdictReason.DEVIATIONS
    assert outcome.mismatches == ("design",)


def test_an_accepted_deviation_on_a_major_attribute_still_shows() -> None:
    outcome = decide(
        [
            _judgment("connector", ComparisonStatus.MATCH),
            _judgment(
                "graduation_step_ml", ComparisonStatus.ACCEPTABLE_DEVIATION, Criticality.MAJOR
            ),
        ]
    )

    assert outcome.verdict is Verdict.EQUIVALENT_WITH_DEVIATIONS
    assert outcome.deviations == ("graduation_step_ml",)


def test_minor_gaps_and_minor_mismatches_do_not_block() -> None:
    outcome = decide(
        [
            _judgment("connector", ComparisonStatus.MATCH),
            _judgment("pvc_free", ComparisonStatus.UNKNOWN, Criticality.MINOR),
            _judgment("units_per_order_unit", ComparisonStatus.INFO, Criticality.MINOR),
        ]
    )

    assert outcome.verdict is Verdict.EQUIVALENT
    assert outcome.reason is VerdictReason.ALL_MATCH
    assert outcome.minor_gaps == ("pvc_free",)
    assert outcome.blocking_gaps == ()


def test_everything_matching_is_equivalent() -> None:
    outcome = decide([_judgment("connector", ComparisonStatus.MATCH)])

    assert outcome.verdict is Verdict.EQUIVALENT
    assert outcome.reason is VerdictReason.ALL_MATCH


def test_a_minor_deviation_alone_is_still_a_deviation_verdict() -> None:
    outcome = decide([_judgment("silicone_oil_free", ComparisonStatus.MISMATCH, Criticality.MINOR)])

    assert outcome.verdict is Verdict.EQUIVALENT_WITH_DEVIATIONS


def test_judgments_fill_only_what_the_comparators_left_open() -> None:
    comparator = [
        _judgment("stopper_material", ComparisonStatus.NEEDS_JUDGE, Criticality.MINOR),
        _judgment("connector", ComparisonStatus.MISMATCH),
    ]
    from_llm = {
        "stopper_material": Judgment(
            attribute_key="stopper_material",
            criticality=Criticality.MINOR,
            rule=ComparisonRule.SEMANTIC,
            status=ComparisonStatus.MATCH,
            confidence=0.8,
            rationale="Both describe a latex-free elastomer stopper.",
        ),
        # The comparators already decided this one, so the model's answer is dropped (§8.4).
        "connector": Judgment(
            attribute_key="connector",
            criticality=Criticality.CRITICAL,
            rule=ComparisonRule.EXACT,
            status=ComparisonStatus.MATCH,
        ),
    }

    merged = apply_judgments(comparator, from_llm)

    stopper, connector = merged.judgments
    assert (stopper.status, stopper.decided_by) == (ComparisonStatus.MATCH, DecidedBy.LLM)
    assert stopper.rationale is not None and stopper.confidence == 0.8
    assert (connector.status, connector.decided_by) == (
        ComparisonStatus.MISMATCH,
        DecidedBy.COMPARATOR,
    )
    assert merged.discarded == ("connector",)


def test_the_comparator_context_survives_a_judgment() -> None:
    comparator = [
        _judgment(
            "stopper_material",
            ComparisonStatus.NEEDS_JUDGE,
            Criticality.MINOR,
            hospital=HospitalSide(
                value=EnumValue(value="LATEX_FREE"), origin=AttributeOrigin.PURCHASER
            ),
        )
    ]
    answer = {
        "stopper_material": Judgment(
            attribute_key="stopper_material",
            criticality=Criticality.MINOR,
            rule=ComparisonRule.SEMANTIC,
            status=ComparisonStatus.ACCEPTABLE_DEVIATION,
        )
    }

    (merged,) = apply_judgments(comparator, answer).judgments

    assert merged.status is ComparisonStatus.ACCEPTABLE_DEVIATION
    assert merged.hospital is not None
    assert merged.hospital.origin is AttributeOrigin.PURCHASER
    # The stored row keeps the comparator's own rule and criticality, not the model's.
    assert (merged.rule, merged.criticality) == (ComparisonRule.EXACT, Criticality.MINOR)


def test_an_unjudged_attribute_degrades_to_missing_data() -> None:
    outcome = decide(
        [_judgment("stopper_material", ComparisonStatus.NEEDS_JUDGE, Criticality.MAJOR)]
    )

    assert outcome.verdict is Verdict.INSUFFICIENT_DATA
