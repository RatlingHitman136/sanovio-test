"""Needle gauge and outer diameter, per ISO 6009."""

# Nominal outer diameter in mm for each gauge.
ISO_6009_OUTER_DIAMETER_MM: dict[int, float] = {
    18: 1.20, 19: 1.10, 20: 0.90, 21: 0.80, 22: 0.70, 23: 0.60, 24: 0.55,
    25: 0.50, 26: 0.45, 27: 0.40, 28: 0.36, 29: 0.33, 30: 0.30,
}  # fmt: skip
# Closest neighbours in the table differ by 0.03 mm, so a match within 0.01 mm is unambiguous.
_DIAMETER_TOLERANCE_MM = 0.01


def outer_diameter_for_gauge(gauge: float) -> float | None:
    return ISO_6009_OUTER_DIAMETER_MM.get(int(gauge)) if float(gauge).is_integer() else None


def gauge_for_outer_diameter(diameter_mm: float) -> int | None:
    for gauge, nominal in ISO_6009_OUTER_DIAMETER_MM.items():
        if abs(nominal - diameter_mm) <= _DIAMETER_TOLERANCE_MM:
            return gauge
    return None


def gauge_diameter_consistent(gauge: float, diameter_mm: float) -> bool:
    nominal = outer_diameter_for_gauge(gauge)
    return nominal is not None and abs(nominal - diameter_mm) <= _DIAMETER_TOLERANCE_MM
