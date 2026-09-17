"""Identifiers as asymmetric evidence, never as a comparison (D51).

A check-digit-valid identifier that matches on both sides means the same trade item, which is
stronger than any attribute comparison. A difference means nothing at all: equivalent products
from different manufacturers always have different identifiers. So this can only ever say
"same item" or "no information" — never a mismatch, an unknown or a question.
"""

import re
from collections.abc import Sequence
from enum import StrEnum

from equivalence_core.exchange.requirement import ProductHints
from equivalence_core.facts import IdentifierEntry
from equivalence_core.identifiers import IdentifierScheme

_NOISE = re.compile(r"[^0-9a-z]+")


class IdentifierEvidence(StrEnum):
    SAME_TRADE_ITEM = "SAME_TRADE_ITEM"
    NO_INFORMATION = "NO_INFORMATION"


def identifier_evidence(
    hints: ProductHints | None,
    supplier_identifiers: Sequence[IdentifierEntry],
    supplier_manufacturer: str | None = None,
) -> IdentifierEvidence:
    """The hospital side exists only when the hospital sends product hints (D47); without them
    the same check runs in the client, and nothing about it reaches the hub."""
    if hints is None:
        return IdentifierEvidence.NO_INFORMATION
    if _gtin_matches(hints, supplier_identifiers) or _article_number_matches(
        hints, supplier_identifiers, supplier_manufacturer
    ):
        return IdentifierEvidence.SAME_TRADE_ITEM
    return IdentifierEvidence.NO_INFORMATION


def _gtin_matches(hints: ProductHints, supplier: Sequence[IdentifierEntry]) -> bool:
    # A hint's GTIN is check-digit valid by construction (RequirementPayload refuses others);
    # the supplier's must be valid too, or it proves nothing.
    if hints.gtin is None:
        return False
    return any(
        entry.scheme is IdentifierScheme.GTIN
        and entry.checksum_valid is True
        and entry.value == hints.gtin
        for entry in supplier
    )


def _article_number_matches(
    hints: ProductHints, supplier: Sequence[IdentifierEntry], manufacturer: str | None
) -> bool:
    """An article number is only unique within its manufacturer, so both must agree."""
    if hints.manufacturer_article_no is None or hints.brand is None or manufacturer is None:
        return False
    if _plain(hints.brand) != _plain(manufacturer):
        return False
    wanted = _plain(hints.manufacturer_article_no)
    return any(
        entry.scheme is IdentifierScheme.SUPPLIER_ARTICLE_NO and _plain(entry.value) == wanted
        for entry in supplier
    )


def _plain(text: str) -> str:
    """ "B. Braun" and "B.Braun" are the same manufacturer; "4606728 V" the same article number."""
    return _NOISE.sub("", text.casefold())
