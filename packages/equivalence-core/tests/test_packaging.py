import pytest

from equivalence_core.parsers.packaging import Packaging, parse_packaging


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("12 x 100 Stück", Packaging(units_per_order_unit=100, order_units_per_shipping_unit=12)),
        ("25 x 100 Stück", Packaging(units_per_order_unit=100, order_units_per_shipping_unit=25)),
        ("40 × 100", Packaging(units_per_order_unit=100, order_units_per_shipping_unit=40)),
        ("100 / 1.200", Packaging(units_per_order_unit=100, order_units_per_shipping_unit=12)),
        ("100 / 400", Packaging(units_per_order_unit=100, order_units_per_shipping_unit=4)),
    ],
)
def test_catalog_packaging(text: str, expected: Packaging) -> None:
    assert parse_packaging(text) == expected


@pytest.mark.parametrize("text", ["100 / 250", "Karton", "12 x 100 ml"])
def test_unreadable_packaging_gives_nothing(text: str) -> None:
    assert parse_packaging(text) is None
