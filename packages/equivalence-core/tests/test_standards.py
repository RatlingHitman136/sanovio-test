import pytest

from equivalence_core.parsers.standards import canonical_standard


@pytest.mark.parametrize(
    ("written", "canonical"),
    [
        ("ISO 7864", "ISO 7864"),
        ("DIN EN ISO 7864", "ISO 7864"),
        ("DIN EN ISO 7886-1:2018", "ISO 7886-1"),
        ("EN ISO 80369-7:2021", "ISO 80369-7"),
        ("din en iso 7864:2016+A1:2019", "ISO 7864"),
        ("ÖNORM EN 455-1", "EN 455-1"),
        ("EN 1041", "EN 1041"),
        ("ISO 7886-1", "ISO 7886-1"),
    ],
)
def test_adoptions_and_editions_are_the_same_standard(written: str, canonical: str) -> None:
    assert canonical_standard(written) == canonical


def test_different_parts_stay_different() -> None:
    assert canonical_standard("ISO 7886-1") != canonical_standard("ISO 7886-2")
