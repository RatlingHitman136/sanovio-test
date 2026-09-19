import json
from typing import Any

import pytest
from pydantic import ValidationError

from equivalence_core.templates import (
    GENERIC_CODE,
    AttributeDefinition,
    ComparisonRule,
    Criticality,
    TemplateAttribute,
    TemplateDefinition,
    TemplateError,
    definition_from_json,
    load_seed_templates,
    suggest_category,
)

TEMPLATES = load_seed_templates()
SYRINGE = TEMPLATES["syringe_single_use"]
NEEDLE = TEMPLATES["hypodermic_needle"]


def test_the_three_seed_templates_load() -> None:
    assert sorted(TEMPLATES) == [GENERIC_CODE, "hypodermic_needle", "syringe_single_use"]


def test_children_inherit_the_generic_attributes() -> None:
    generic_keys = set(TEMPLATES[GENERIC_CODE].keys)
    assert generic_keys <= set(SYRINGE.keys)
    assert generic_keys <= set(NEEDLE.keys)
    assert SYRINGE.keys[: len(generic_keys)] == TEMPLATES[GENERIC_CODE].keys


def test_only_the_generic_template_is_limited() -> None:
    assert TEMPLATES[GENERIC_CODE].limited_template
    assert not SYRINGE.limited_template


def test_settings_follow_the_architecture() -> None:
    assert SYRINGE.attribute("connector").criticality is Criticality.CRITICAL
    assert SYRINGE.attribute("graduation_step_ml").rule is ComparisonRule.SAME_OR_FINER
    inner = NEEDLE.attribute("inner_diameter_mm")
    assert (inner.rule, inner.tolerance) == (ComparisonRule.TOLERANCE, 0.02)
    assert "units_per_order_unit" not in SYRINGE.shareable_keys
    assert "nominal_volume_ml" in SYRINGE.shareable_keys


def test_hub_json_builds_the_same_definition() -> None:
    served = json.loads(SYRINGE.model_dump_json())

    rebuilt = definition_from_json(served)

    assert rebuilt == SYRINGE
    assert rebuilt.definition_hash == SYRINGE.definition_hash


def test_a_changed_criticality_changes_the_hash() -> None:
    served = json.loads(SYRINGE.model_dump_json())
    served["attributes"][-1]["criticality"] = "critical"

    assert definition_from_json(served).definition_hash != SYRINGE.definition_hash


def _definition(**overrides: Any) -> dict[str, Any]:
    return {
        "key": "connector",
        "type": "enum",
        "options": ["LUER"],
        "labels": {"de": "Ansatz", "en": "Connector"},
        **overrides,
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"type": "date"},  # unknown type
        {"type": "number", "options": []},  # number without unit
        {"type": "text", "options": [], "unit": "mm"},  # unit on a non-number
        {"options": []},  # enum without options
        {"synonyms": {"Luer-Lock": "LUER_LOCK"}},  # synonym to an undeclared option
        {"key": "Connector"},  # key not snake_case
    ],
)
def test_inconsistent_definitions_are_rejected(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        AttributeDefinition.model_validate(_definition(**overrides))


def test_unknown_rule_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TemplateAttribute.model_validate({"key": "x", "criticality": "major", "rule": "fuzzy"})


@pytest.mark.parametrize(
    "entry",
    [
        {"key": "x", "criticality": "major", "rule": "tolerance"},
        {"key": "x", "criticality": "major", "rule": "exact", "tolerance": 0.1},
    ],
)
def test_tolerance_must_match_the_rule(entry: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        TemplateAttribute.model_validate(entry)


@pytest.mark.parametrize(
    ("key", "rule", "extra"),
    [
        ("connector", "tolerance", {"tolerance": 0.1}),  # an enum has no distance
        ("needle_included", "same_or_more", {}),
        ("special_scale", "required_if_hospital", {}),  # text is not a yes/no property
        ("nominal_volume_ml", "includes", {}),
    ],
)
def test_a_rule_must_fit_the_value_type(key: str, rule: str, extra: dict[str, Any]) -> None:
    served = json.loads(SYRINGE.model_dump_json())
    entry = next(a for a in served["attributes"] if a["key"] == key)
    entry.update({"rule": rule, "tolerance": None} | extra)

    with pytest.raises(ValidationError, match="cannot compare"):
        TemplateDefinition.model_validate(served)


def test_duplicate_attributes_are_rejected() -> None:
    served = json.loads(SYRINGE.model_dump_json())
    served["attributes"].append(served["attributes"][0])

    with pytest.raises(ValidationError, match="duplicate"):
        TemplateDefinition.model_validate(served)


def test_template_error_is_a_value_error() -> None:
    assert issubclass(TemplateError, ValueError)


def test_category_suggestions_for_the_sample(sample_articles: list[dict[str, Any]]) -> None:
    for article in sample_articles:
        assert suggest_category(article["name"], TEMPLATES) == article["category"], article["name"]


def test_the_leading_noun_wins() -> None:
    assert suggest_category("Einmalspritze mit Kanüle", TEMPLATES) == "syringe_single_use"
    assert suggest_category("Kanüle für Spritze", TEMPLATES) == "hypodermic_needle"
