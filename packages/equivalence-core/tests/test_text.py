from typing import Any

from equivalence_core.parsers.text import extract_attributes
from equivalence_core.quality import DataQualityIssue
from equivalence_core.templates import load_seed_templates, suggest_category
from equivalence_core.values import BoolValue, EnumValue, NumberValue

TEMPLATES = load_seed_templates()


def _read(name: str) -> dict[str, tuple[object, str, bool]]:
    reading = extract_attributes(name, TEMPLATES[suggest_category(name, TEMPLATES)])
    return {e.attribute_key: (e.value, e.quote, e.derived) for e in reading.extractions}


def _article(sample: list[dict[str, Any]], article_id: int) -> str:
    return str(next(a["name"] for a in sample if a["id"] == article_id))


def test_syringe_article(sample_articles: list[dict[str, Any]]) -> None:
    assert _read(_article(sample_articles, 3)) == {
        "nominal_volume_ml": (NumberValue(value=10, unit="ml"), "10 ml", False),
        "connector": (EnumValue(value="LUER_LOCK"), "Luer-Lock", False),
        "sterile": (BoolValue(value=True), "steril", False),
    }


def test_needle_article(sample_articles: list[dict[str, Any]]) -> None:
    assert _read(_article(sample_articles, 6)) == {
        "outer_diameter_mm": (NumberValue(value=0.8, unit="mm"), "0,8 × 40 mm", False),
        "length_mm": (NumberValue(value=40, unit="mm"), "0,8 × 40 mm", False),
        "gauge": (NumberValue(value=21, unit="G"), "0,8 × 40 mm", True),
    }


def test_nothing_is_invented_for_the_other_articles(sample_articles: list[dict[str, Any]]) -> None:
    readings = {a["id"]: _read(a["name"]) for a in sample_articles if a["id"] not in (3, 6)}

    # Only "steril" is stated in these names; volumes and sizes have no attribute in the
    # generic template, so they are not read.
    assert {article_id: set(found) for article_id, found in readings.items()} == {
        1: set(),
        2: {"sterile"},
        4: set(),
        5: set(),
        7: set(),
        8: set(),
        9: {"sterile"},
        10: set(),
    }


def test_usable_volume_is_told_apart() -> None:
    found = _read("Einmalspritze 10 ml, nutzbar bis 12 ml")

    assert found["nominal_volume_ml"][0] == NumberValue(value=10, unit="ml")
    assert found["usable_volume_ml"][0] == NumberValue(value=12, unit="ml")


def test_gauge_fills_in_the_diameter() -> None:
    found = _read('Kanüle 21 G x 1 ½"')

    assert found["length_mm"][0] == NumberValue(value=38.1, unit="mm")
    assert found["outer_diameter_mm"] == (NumberValue(value=0.8, unit="mm"), '21 G x 1 ½"', True)


def test_gauge_and_diameter_disagreeing_is_flagged() -> None:
    reading = extract_attributes("Kanüle 21 G 0,9 × 40 mm", TEMPLATES["hypodermic_needle"])

    assert reading.issues == (DataQualityIssue.GAUGE_DIAMETER_MISMATCH,)
    assert reading.value_of("gauge") == NumberValue(value=21, unit="G")


def test_contradicting_phrases_leave_the_attribute_unknown() -> None:
    assert "sterile" not in _read("Einmalspritze steril / unsteril")
