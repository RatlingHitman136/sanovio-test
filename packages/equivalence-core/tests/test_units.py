import pytest

from equivalence_core.parsers.units import UnitError, to_canonical


@pytest.mark.parametrize(
    ("value", "unit", "canonical", "expected"),
    [
        (10, "ml", "ml", 10),
        (1.5, '"', "mm", 38.1),  # inch mark, rounded free of float noise
        (6, "cm", "mm", 60),
        (5, "m", "mm", 5000),
        (0.005, "mm", "µm", 5),
        (1, "l", "ml", 1000),
        (21, "G", "G", 21),
    ],
)
def test_conversion_into_the_canonical_unit(
    value: float, unit: str, canonical: str, expected: float
) -> None:
    assert to_canonical(value, unit, canonical) == expected


@pytest.mark.parametrize(
    ("unit", "canonical"),
    [("ml", "mm"), ("G", "mm"), ("mm", "G"), ("furlongs-ish", "mm")],
)
def test_impossible_conversions_raise(unit: str, canonical: str) -> None:
    with pytest.raises(UnitError):
        to_canonical(1, unit, canonical)
