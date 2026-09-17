"""Numbers as written in German catalogs and article names."""

import re

_UNICODE_FRACTIONS = {
    "½": 0.5,
    "¼": 0.25,
    "¾": 0.75,
    "⅛": 0.125,
    "⅜": 0.375,
    "⅝": 0.625,
    "⅞": 0.875,
}
_FRACTION_CHARS = "".join(_UNICODE_FRACTIONS)

# A dot followed by exactly three digits is a thousands separator ("1.200");
# a comma is the decimal separator ("0,8"); a trailing fraction adds to the whole part ("1 ½").
NUMBER_PATTERN = (
    r"(?:"
    r"(?:\d{1,3}(?:\.\d{3})+(?!\d)|\d+(?:[.,]\d+)?)"
    rf"(?:\s*(?:[{_FRACTION_CHARS}]|\d+/\d+))?"
    rf"|[{_FRACTION_CHARS}]"
    r")"
)
_NUMBER = re.compile(NUMBER_PATTERN)
_THOUSANDS = re.compile(r"^\d{1,3}(?:\.\d{3})+$")
_TRAILING_FRACTION = re.compile(rf"^(.*?)\s*([{_FRACTION_CHARS}]|\d+/\d+)$")


def parse_number(text: str) -> float:
    token = text.strip()
    if not _NUMBER.fullmatch(token):
        raise ValueError(f"not a number: {text!r}")
    whole, fraction = token, 0.0
    if trailing := _TRAILING_FRACTION.match(token):
        whole, fraction = trailing.group(1), _fraction(trailing.group(2))
    if not whole:
        return fraction
    if _THOUSANDS.match(whole):
        whole = whole.replace(".", "")
    return float(whole.replace(",", ".")) + fraction


def _fraction(token: str) -> float:
    if token in _UNICODE_FRACTIONS:
        return _UNICODE_FRACTIONS[token]
    numerator, denominator = token.split("/")
    return int(numerator) / int(denominator)
