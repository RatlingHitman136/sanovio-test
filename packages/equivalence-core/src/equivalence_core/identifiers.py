"""Product identifiers: fixed schemes per side, GS1 check digits and data-quality flags."""

from collections.abc import Mapping
from enum import StrEnum

from equivalence_core.quality import DataQualityIssue


class IdentifierScheme(StrEnum):
    GTIN = "GTIN"
    EAN = "EAN"
    MANUFACTURER_REF = "MANUFACTURER_REF"
    PHARMACODE = "PHARMACODE"
    SUPPLIER_ARTICLE_NO = "SUPPLIER_ARTICLE_NO"
    PZN = "PZN"
    HIMIV = "HIMIV"


# Fixed lists rather than registry lookups: the node has no copy of the hub registry.
NODE_SCHEMES = frozenset(
    {
        IdentifierScheme.GTIN,
        IdentifierScheme.EAN,
        IdentifierScheme.MANUFACTURER_REF,
        IdentifierScheme.PHARMACODE,
    }
)
HUB_SCHEMES = frozenset(
    {
        IdentifierScheme.GTIN,
        IdentifierScheme.SUPPLIER_ARTICLE_NO,
        IdentifierScheme.PZN,
        IdentifierScheme.HIMIV,
    }
)
_GS1_SCHEMES = frozenset({IdentifierScheme.GTIN, IdentifierScheme.EAN})
_GS1_LENGTHS = frozenset({8, 12, 13, 14})


def normalize_identifier(raw: str) -> str:
    """Remove the apostrophe Excel adds to keep leading zeros, and any spaces."""
    return raw.strip().lstrip("'").replace(" ", "")


def gs1_check_digit_valid(code: str) -> bool:
    if not (code.isascii() and code.isdigit()) or len(code) not in _GS1_LENGTHS:
        return False
    *body, check = (int(digit) for digit in code)
    # Weights alternate 3, 1, … starting from the digit next to the check digit.
    total = sum(digit * (3 if index % 2 == 0 else 1) for index, digit in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def checksum_valid(scheme: IdentifierScheme, value: str) -> bool | None:
    """None for schemes that carry no check digit."""
    return gs1_check_digit_valid(value) if scheme in _GS1_SCHEMES else None


def data_quality_issues(identifiers: Mapping[IdentifierScheme, str]) -> list[DataQualityIssue]:
    """Problems between an article's identifiers; a valid check digit alone proves nothing."""
    gtin = identifiers.get(IdentifierScheme.GTIN)
    ean = identifiers.get(IdentifierScheme.EAN)
    issues = []
    if gtin is not None and not gs1_check_digit_valid(gtin):
        issues.append(DataQualityIssue.GTIN_CHECKSUM_INVALID)
    if ean is not None and not gs1_check_digit_valid(ean):
        issues.append(DataQualityIssue.EAN_CHECKSUM_INVALID)
    # An EAN-13 is the same number as a GTIN-14 without its leading zero.
    if gtin is not None and ean is not None and gtin.zfill(14) != ean.zfill(14):
        issues.append(DataQualityIssue.GTIN_EAN_MISMATCH)
    return issues
