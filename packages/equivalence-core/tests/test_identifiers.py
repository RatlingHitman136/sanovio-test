from typing import Any

from equivalence_core.identifiers import (
    IdentifierScheme,
    checksum_valid,
    data_quality_issues,
    gs1_check_digit_valid,
    normalize_identifier,
)
from equivalence_core.quality import DataQualityIssue


def _codes(article: dict[str, Any]) -> dict[IdentifierScheme, str]:
    return {
        IdentifierScheme.GTIN: normalize_identifier(article["gtin"]),
        IdentifierScheme.EAN: normalize_identifier(article["ean"]),
    }


def test_excel_apostrophe_and_spaces_are_removed() -> None:
    assert normalize_identifier(" '0404 0456781234 ") == "04040456781234"


def test_valid_gtins_in_the_sample(sample_articles: list[dict[str, Any]]) -> None:
    valid = [
        a["id"] for a in sample_articles if gs1_check_digit_valid(_codes(a)[IdentifierScheme.GTIN])
    ]
    assert valid == [3, 8, 9]


def test_valid_eans_in_the_sample(sample_articles: list[dict[str, Any]]) -> None:
    valid = [
        a["id"] for a in sample_articles if gs1_check_digit_valid(_codes(a)[IdentifierScheme.EAN])
    ]
    assert valid == [10]


def test_gtin_ean_mismatches_in_the_sample(sample_articles: list[dict[str, Any]]) -> None:
    matching = [
        a["id"]
        for a in sample_articles
        if DataQualityIssue.GTIN_EAN_MISMATCH not in data_quality_issues(_codes(a))
    ]
    assert matching == [4]


def test_issues_for_the_syringe_article(sample_articles: list[dict[str, Any]]) -> None:
    syringe = next(a for a in sample_articles if a["id"] == 3)
    assert data_quality_issues(_codes(syringe)) == [
        DataQualityIssue.EAN_CHECKSUM_INVALID,
        DataQualityIssue.GTIN_EAN_MISMATCH,
    ]


def test_malformed_codes_are_invalid() -> None:
    assert not gs1_check_digit_valid("4040456781")  # wrong length
    assert not gs1_check_digit_valid("040404567812a4")
    assert not gs1_check_digit_valid("٠٤٠٤٠٤٥٦٧٨١٢٣٤")  # non-ASCII digits


def test_schemes_without_check_digit_report_none() -> None:
    assert checksum_valid(IdentifierScheme.MANUFACTURER_REF, "9154010") is None
    assert checksum_valid(IdentifierScheme.GTIN, "04040456781234") is True
