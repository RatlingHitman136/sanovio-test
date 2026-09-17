from equivalence_core.parsers.gauge import (
    gauge_diameter_consistent,
    gauge_for_outer_diameter,
    outer_diameter_for_gauge,
)


def test_21_gauge_is_0_8_mm() -> None:
    assert outer_diameter_for_gauge(21) == 0.8
    assert gauge_for_outer_diameter(0.8) == 21
    assert gauge_for_outer_diameter(0.80) == 21


def test_unknown_sizes_give_nothing() -> None:
    assert outer_diameter_for_gauge(40) is None
    assert outer_diameter_for_gauge(21.5) is None
    assert gauge_for_outer_diameter(0.75) is None


def test_neighbouring_gauges_are_not_confused() -> None:
    assert gauge_for_outer_diameter(0.36) == 28
    assert gauge_for_outer_diameter(0.33) == 29


def test_consistency_check() -> None:
    assert gauge_diameter_consistent(21, 0.8)
    assert not gauge_diameter_consistent(21, 0.9)
