"""The design's own product pairs (ARCHITECTURE §21) run through the comparison, before any
hub exists: requirement + catalog facts → judgments → verdict."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from equivalence_core.comparators import ComparisonStatus, compare, keys_needing_judgement
from equivalence_core.exchange.requirement import AttributeOrigin, ProductHints, RequirementPayload
from equivalence_core.facts import (
    IdentifierEntry,
    ResolvedRecord,
    Scope,
    SupplierFact,
    resolve_supplier,
)
from equivalence_core.identifier_evidence import IdentifierEvidence, identifier_evidence
from equivalence_core.identifiers import IdentifierScheme
from equivalence_core.ids import new_article_ref
from equivalence_core.templates import TemplateDefinition, load_seed_templates
from equivalence_core.templates.model import ValueType
from equivalence_core.values import (
    AttributeValue,
    BoolValue,
    EnumValue,
    ListValue,
    NumberValue,
    TextValue,
)
from equivalence_core.verdict_rules import Verdict, VerdictReason, decide

PAIRS = yaml.safe_load((Path(__file__).parent / "fixtures" / "comparison_pairs.yaml").read_text())
NOW = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def templates() -> dict[str, TemplateDefinition]:
    return load_seed_templates()


def _typed(template: TemplateDefinition, key: str, raw: Any) -> AttributeValue:
    attribute = template.attribute(key)
    match attribute.type:
        case ValueType.NUMBER:
            return NumberValue(value=float(raw), unit=attribute.unit or "")
        case ValueType.BOOL:
            return BoolValue(value=bool(raw))
        case ValueType.ENUM:
            return EnumValue(value=str(raw))
        case ValueType.LIST:
            return ListValue(value=tuple(raw))
    return TextValue(value=str(raw))


def _requirement(name: str, templates: dict[str, TemplateDefinition]) -> RequirementPayload:
    entry = PAIRS["hospital"][name]
    template = templates[entry["template"]]
    attributes = {
        key: _typed(template, key, item["value"]) for key, item in entry["attributes"].items()
    }
    unavailable = tuple(entry.get("unavailable", ()))
    withheld = tuple(entry.get("withheld", ()))
    known = set(attributes) | set(unavailable) | set(withheld)
    return RequirementPayload(
        article_ref=new_article_ref(),
        template_code=template.code,
        attributes=attributes,
        attribute_origin={
            key: AttributeOrigin(entry["attributes"][key]["origin"]) for key in attributes
        },
        unknown_attributes=tuple(key for key in template.keys if key not in known),
        unavailable_attributes=unavailable,
        withheld_attributes=withheld,
    )


def _supplier(name: str, templates: dict[str, TemplateDefinition]) -> ResolvedRecord:
    entry = PAIRS["supplier"][name]
    template = templates[entry["template"]]
    facts = [
        SupplierFact(
            id=f"fct_{name}_{key}",
            attribute_key=key,
            value=_typed(template, key, item["value"]),
            source=item.get("source", "CATALOG"),
            scope=Scope(item["scope"]),
            created_at=NOW,
        )
        for key, item in entry["facts"].items()
    ]
    facts += [
        SupplierFact(
            id=f"fct_{name}_{key}_unavailable",
            attribute_key=key,
            value=None,
            source="UNAVAILABLE",
            scope=Scope.VARIANT,
            created_at=NOW,
        )
        for key in entry.get("unavailable", ())
    ]
    return resolve_supplier(facts, template)


def _identifiers(name: str) -> list[IdentifierEntry]:
    return [
        IdentifierEntry(
            scheme=IdentifierScheme(item["scheme"]),
            value=item["value"],
            checksum_valid=item.get("checksum_valid"),
            fact_id=f"fct_{name}_{item['scheme'].lower()}",
        )
        for item in PAIRS["supplier"][name].get("identifiers", ())
    ]


def test_scenario_1_round_1_asks_for_what_bd_has_not_published(
    templates: dict[str, TemplateDefinition],
) -> None:
    requirement = _requirement("art_03_linked", templates)
    supplier = _supplier("plastipak_round_1", templates)

    judgments = compare(requirement, supplier, templates["syringe_single_use"])
    outcome = decide(judgments)

    assert outcome.verdict is Verdict.INSUFFICIENT_DATA
    assert outcome.reason is VerdictReason.MISSING_DATA
    assert outcome.blocking_gaps == ("mdr_class", "dehp_free", "iso_7886_1_compliant")
    assert all(
        judgment.askable and judgment.missing == "SUPPLIER"
        for judgment in judgments
        if judgment.attribute_key in outcome.blocking_gaps
    )
    assert keys_needing_judgement(judgments) == ()


def test_scenario_1_round_2_ends_with_deviations(
    templates: dict[str, TemplateDefinition],
) -> None:
    requirement = _requirement("art_03_linked", templates)
    supplier = _supplier("plastipak_round_2", templates)

    outcome = decide(compare(requirement, supplier, templates["syringe_single_use"]))

    assert outcome.verdict is Verdict.EQUIVALENT_WITH_DEVIATIONS
    # 3-part against 2-part is a major deviation; a finer graduation is acceptable.
    assert outcome.mismatches == ("design",)
    assert outcome.deviations == ("graduation_step_ml",)
    assert outcome.blocking_gaps == ()


def test_scenario_2_emerald_stops_on_the_connector(
    templates: dict[str, TemplateDefinition],
) -> None:
    requirement = _requirement("art_03_linked", templates)
    supplier = _supplier("emerald", templates)

    judgments = compare(requirement, supplier, templates["syringe_single_use"])
    outcome = decide(judgments)

    assert outcome.verdict is Verdict.NOT_EQUIVALENT
    assert outcome.reason is VerdictReason.CRITICAL_MISMATCH
    assert "connector" in outcome.mismatches
    # An early stop: nothing is asked although plenty is still unknown.
    assert outcome.blocking_gaps


def test_scenario_3_microlance_leaves_only_an_unavailable_gap(
    templates: dict[str, TemplateDefinition],
) -> None:
    requirement = _requirement("art_06", templates)
    supplier = _supplier("microlance", templates)

    judgments = {
        judgment.attribute_key: judgment
        for judgment in compare(requirement, supplier, templates["hypodermic_needle"])
    }
    outcome = decide(tuple(judgments.values()))

    assert outcome.verdict is Verdict.INSUFFICIENT_DATA
    assert outcome.mismatches == ("wall_type",)
    # Every blocking gap is one the supplier already said it cannot provide, which is what
    # sends the assessment to a manual decision (§11, stop condition 4).
    assert outcome.blocking_gaps == outcome.unavailable_gaps == ("inner_diameter_mm",)
    assert judgments["inner_diameter_mm"].status is ComparisonStatus.UNAVAILABLE
    # Gauge and length agree; the outer diameter is only a cross-check.
    assert judgments["gauge"].status is ComparisonStatus.MATCH
    assert judgments["outer_diameter_mm"].status is ComparisonStatus.INFO


def test_scenario_4_a_valid_identifier_match_short_circuits_the_round(
    templates: dict[str, TemplateDefinition],
) -> None:
    requirement = _requirement("art_03_thin", templates)
    hints = ProductHints(brand="B. Braun", manufacturer_article_no="9154010", gtin="04040456781234")

    evidence = identifier_evidence(hints, _identifiers("injekt"), "B. Braun")
    outcome = decide(
        compare(requirement, _supplier("injekt", templates), templates["syringe_single_use"]),
        evidence,
    )

    assert evidence is IdentifierEvidence.SAME_TRADE_ITEM
    assert outcome.verdict is Verdict.EQUIVALENT
    assert outcome.reason is VerdictReason.SAME_TRADE_ITEM
    # No comparator result reaches the verdict, and no judge call is needed (D51).
    assert outcome.blocking_gaps == () and outcome.mismatches == ()


def test_the_same_pair_without_hints_is_compared_normally(
    templates: dict[str, TemplateDefinition],
) -> None:
    requirement = _requirement("art_03_linked", templates)

    evidence = identifier_evidence(None, _identifiers("injekt"), "B. Braun")
    outcome = decide(
        compare(requirement, _supplier("injekt", templates), templates["syringe_single_use"]),
        evidence,
    )

    assert evidence is IdentifierEvidence.NO_INFORMATION
    # The hospital's own current product: every value came from it, so everything matches.
    assert outcome.verdict is Verdict.EQUIVALENT
    assert outcome.reason is VerdictReason.ALL_MATCH
