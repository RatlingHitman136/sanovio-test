import pytest

from equivalence_core.parsers.wording import NOTHING, canonical_text


@pytest.mark.parametrize(
    "written", ["keine", "Keine.", "nein", " NEIN ", "ohne", "none", "No", "n/a", "–", "-", ""]
)
def test_every_way_of_saying_nothing_is_one_token(written: str) -> None:
    assert canonical_text(written) == NOTHING


@pytest.mark.parametrize(
    ("one", "other"),
    [
        ("Skala 0,2 ml", "skala 0.2 ml"),
        ("Luer-Lock", "luer lock"),
        ("latexfrei!", "Latexfrei"),
    ],
)
def test_spelling_differences_disappear(one: str, other: str) -> None:
    assert canonical_text(one) == canonical_text(other)


def test_different_statements_stay_different() -> None:
    assert canonical_text("keine Skala") != canonical_text("keine")
    assert canonical_text("0,2 ml") != canonical_text("0,5 ml")
