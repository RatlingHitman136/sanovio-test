import pytest

from equivalence_core.exchange.requirement import ProductHints
from equivalence_core.facts import IdentifierEntry
from equivalence_core.identifier_evidence import IdentifierEvidence, identifier_evidence
from equivalence_core.identifiers import IdentifierScheme

# Both check-digit valid (see test_identifiers).
OURS = "04040456781234"
THEIRS = "04012345678901"


def _supplier(
    scheme: IdentifierScheme, value: str, checksum_valid: bool | None = True
) -> list[IdentifierEntry]:
    return [
        IdentifierEntry(scheme=scheme, value=value, checksum_valid=checksum_valid, fact_id="fct_1")
    ]


def test_the_same_valid_gtin_means_the_same_trade_item() -> None:
    evidence = identifier_evidence(ProductHints(gtin=OURS), _supplier(IdentifierScheme.GTIN, OURS))

    assert evidence is IdentifierEvidence.SAME_TRADE_ITEM


def test_a_supplier_gtin_that_fails_its_check_digit_proves_nothing() -> None:
    evidence = identifier_evidence(
        ProductHints(gtin=OURS), _supplier(IdentifierScheme.GTIN, OURS, checksum_valid=False)
    )

    assert evidence is IdentifierEvidence.NO_INFORMATION


def test_different_gtins_are_never_a_mismatch_only_no_information() -> None:
    evidence = identifier_evidence(
        ProductHints(gtin=OURS), _supplier(IdentifierScheme.GTIN, THEIRS)
    )

    assert evidence is IdentifierEvidence.NO_INFORMATION


def test_without_product_hints_there_is_no_hospital_side() -> None:
    assert (
        identifier_evidence(None, _supplier(IdentifierScheme.GTIN, OURS))
        is IdentifierEvidence.NO_INFORMATION
    )


@pytest.mark.parametrize("manufacturer", ["B. Braun", "B.Braun", "b braun"])
def test_article_number_plus_manufacturer_means_the_same_trade_item(manufacturer: str) -> None:
    hints = ProductHints(brand="B. Braun", manufacturer_article_no="4606728V")

    evidence = identifier_evidence(
        hints, _supplier(IdentifierScheme.SUPPLIER_ARTICLE_NO, "4606728 V", None), manufacturer
    )

    assert evidence is IdentifierEvidence.SAME_TRADE_ITEM


def test_the_same_article_number_from_another_manufacturer_proves_nothing() -> None:
    hints = ProductHints(brand="B. Braun", manufacturer_article_no="4606728V")

    evidence = identifier_evidence(
        hints, _supplier(IdentifierScheme.SUPPLIER_ARTICLE_NO, "4606728V", None), "BD"
    )

    assert evidence is IdentifierEvidence.NO_INFORMATION


def test_an_article_number_without_a_known_manufacturer_proves_nothing() -> None:
    hints = ProductHints(brand="B. Braun", manufacturer_article_no="4606728V")

    evidence = identifier_evidence(
        hints, _supplier(IdentifierScheme.SUPPLIER_ARTICLE_NO, "4606728V", None), None
    )

    assert evidence is IdentifierEvidence.NO_INFORMATION


def test_hints_without_identifiers_prove_nothing() -> None:
    evidence = identifier_evidence(ProductHints(brand="B. Braun"), [])

    assert evidence is IdentifierEvidence.NO_INFORMATION


def test_a_gtin_of_another_scheme_does_not_count() -> None:
    evidence = identifier_evidence(
        ProductHints(gtin=OURS), _supplier(IdentifierScheme.PZN, OURS, None)
    )

    assert evidence is IdentifierEvidence.NO_INFORMATION
