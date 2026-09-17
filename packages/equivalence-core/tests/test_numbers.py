import pytest

from equivalence_core.parsers.numbers import parse_number


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("10", 10),
        ("0,8", 0.8),
        ("0,80", 0.8),
        ("0.25", 0.25),
        ("1.200", 1200),  # German thousands separator
        ("12.000.000", 12_000_000),
        ("½", 0.5),
        ("1 ½", 1.5),
        ("1½", 1.5),
        ("1 1/2", 1.5),
        ("1 ⅜", 1.375),
    ],
)
def test_german_notation(text: str, expected: float) -> None:
    assert parse_number(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["", "ml", "1,2,3", "abc10"])
def test_non_numbers_are_rejected(text: str) -> None:
    with pytest.raises(ValueError, match="not a number"):
        parse_number(text)
