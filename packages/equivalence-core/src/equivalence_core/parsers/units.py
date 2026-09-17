"""Conversion into a template's canonical unit."""

from functools import cache

import pint

# The physical units the parsers produce or templates declare. Anything else is refused before
# it reaches pint, whose unit-expression parser fails unpredictably on arbitrary text.
_PHYSICAL = frozenset({"ml", "l", "mm", "cm", "m", "µm", "um", "inch", '"', "″"})
_ALIASES = {'"': "inch", "″": "inch"}
_DECIMALS = 6


class UnitError(ValueError):
    """A value cannot be expressed in the requested unit."""


@cache
def _registry() -> pint.UnitRegistry:
    return pint.UnitRegistry()


def to_canonical(value: float, unit: str, canonical_unit: str) -> float:
    if unit == canonical_unit:
        return value
    if unit not in _PHYSICAL or canonical_unit not in _PHYSICAL:
        raise UnitError(f"cannot convert {unit!r} to {canonical_unit!r}")
    try:
        quantity = _registry().Quantity(value, _ALIASES.get(unit, unit))
        converted = quantity.to(_ALIASES.get(canonical_unit, canonical_unit)).magnitude
    except pint.errors.DimensionalityError as exc:
        raise UnitError(f"cannot convert {unit!r} to {canonical_unit!r}") from exc
    # Rounding removes float noise such as 1.5 inch -> 38.099999999999994 mm.
    return round(float(converted), _DECIMALS)
