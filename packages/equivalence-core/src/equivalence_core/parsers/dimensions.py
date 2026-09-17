"""Sizes in free text: single quantities and "a × b unit" pairs, each with its source text."""

import re
from dataclasses import dataclass

from equivalence_core.parsers.numbers import NUMBER_PATTERN, parse_number

# Longest alternatives first so "mm" is never read as "m".
_UNIT = r'(?P<{name}>ml|mm|cm|µm|um|m|l|G|"|″)(?![A-Za-zÄÖÜäöüß])'
_PAIR = re.compile(
    rf"(?P<first>{NUMBER_PATTERN})\s*(?:{_UNIT.format(name='first_unit')})?"
    rf"\s*[x×X]\s*"
    rf"(?P<second>{NUMBER_PATTERN})\s*{_UNIT.format(name='second_unit')}"
)
_SINGLE = re.compile(rf"(?<![\d,.])(?P<number>{NUMBER_PATTERN})\s*{_UNIT.format(name='unit')}")


@dataclass(frozen=True)
class Quantity:
    value: float
    unit: str


@dataclass(frozen=True)
class Measurement:
    """One quantity, or the two sides of a pair, with the exact text they were read from."""

    quantities: tuple[Quantity, ...]
    quote: str
    start: int


def find_measurements(text: str) -> list[Measurement]:
    found: list[Measurement] = []
    taken: list[range] = []
    for match in _PAIR.finditer(text):
        second_unit = match["second_unit"]
        # "0,8 × 40 mm": the first number takes the unit of the second.
        first_unit = match["first_unit"] or second_unit
        found.append(
            Measurement(
                quantities=(
                    Quantity(parse_number(match["first"]), first_unit),
                    Quantity(parse_number(match["second"]), second_unit),
                ),
                quote=match.group(0).strip(),
                start=match.start(),
            )
        )
        taken.append(range(match.start(), match.end()))
    for match in _SINGLE.finditer(text):
        if any(match.start() in span for span in taken):
            continue
        found.append(
            Measurement(
                quantities=(Quantity(parse_number(match["number"]), match["unit"]),),
                quote=match.group(0).strip(),
                start=match.start(),
            )
        )
    return sorted(found, key=lambda measurement: measurement.start)
