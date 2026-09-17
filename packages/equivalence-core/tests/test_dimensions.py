from equivalence_core.parsers.dimensions import Quantity, find_measurements


def test_pair_with_one_unit_applies_it_to_both_sides() -> None:
    (measurement,) = find_measurements("Kanüle Sterican 0,8 × 40 mm")

    assert measurement.quantities == (Quantity(0.8, "mm"), Quantity(40, "mm"))
    assert measurement.quote == "0,8 × 40 mm"


def test_pair_with_two_units() -> None:
    (measurement,) = find_measurements("0,80 mm x 40 mm")

    assert measurement.quantities == (Quantity(0.8, "mm"), Quantity(40, "mm"))


def test_gauge_and_inch_length() -> None:
    (measurement,) = find_measurements('21 G x 1 ½"')

    assert measurement.quantities == (Quantity(21, "G"), Quantity(1.5, '"'))


def test_several_single_quantities_in_order() -> None:
    measurements = find_measurements("10 ml, nutzbar bis 12 ml")

    assert [m.quantities for m in measurements] == [(Quantity(10, "ml"),), (Quantity(12, "ml"),)]
    assert [m.quote for m in measurements] == ["10 ml", "12 ml"]


def test_units_are_not_read_inside_words() -> None:
    assert find_measurements("Wundpflaster 6 cm × 5 m")[0].quantities == (
        Quantity(6, "cm"),
        Quantity(5, "m"),
    )
    assert find_measurements("Set 12 Mullkompressen") == []
    assert find_measurements("25 x 100 Stück") == []  # packaging, not a size
