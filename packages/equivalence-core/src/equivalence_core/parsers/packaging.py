"""Packaging notations from catalog variant tables."""

import re
from dataclasses import dataclass

from equivalence_core.parsers.numbers import parse_number

_INTEGER = r"\d{1,3}(?:\.\d{3})+(?!\d)|\d+"
# "12 × 100 Stück": 12 order units of 100 pieces each.
_PACKS = re.compile(
    rf"^\s*(?P<packs>{_INTEGER})\s*[x×X]\s*(?P<units>{_INTEGER})\s*(?:Stück|Stk\.?|St\.?|pcs)?\s*$"
)
# "100 / 1.200" (VE / UK): pieces per order unit / pieces per shipping unit.
_PER_UNIT = re.compile(rf"^\s*(?P<units>{_INTEGER})\s*/\s*(?P<shipping>{_INTEGER})\s*$")


@dataclass(frozen=True)
class Packaging:
    units_per_order_unit: int
    order_units_per_shipping_unit: int


def parse_packaging(text: str) -> Packaging | None:
    if match := _PACKS.match(text):
        return Packaging(_int(match["units"]), _int(match["packs"]))
    if match := _PER_UNIT.match(text):
        units, shipping = _int(match["units"]), _int(match["shipping"])
        if units and shipping % units == 0:
            return Packaging(units, shipping // units)
    return None


def _int(token: str) -> int:
    return int(parse_number(token))
