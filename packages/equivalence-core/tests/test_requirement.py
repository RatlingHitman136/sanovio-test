from typing import Any

import pytest
from pydantic import ValidationError

from equivalence_core.exchange.requirement import RequirementPayload


def _payload(**overrides: Any) -> dict[str, Any]:
    return {
        "article_ref": "ar_5MZQ4K7T2V9C",
        "template_code": "syringe_single_use",
        "attributes": {
            "nominal_volume_ml": {"type": "number", "value": 10, "unit": "ml"},
            "connector": {"type": "enum", "value": "LUER_LOCK"},
        },
        "attribute_origin": {"nominal_volume_ml": "EXTRACTED", "connector": "EXTRACTED"},
        "unknown_attributes": ["needle_included", "pump_compatible"],
        **overrides,
    }


def test_the_architecture_example_is_valid() -> None:
    requirement = RequirementPayload.model_validate(_payload())

    assert requirement.requirement_version == 1
    assert requirement.product_hints is None


@pytest.mark.parametrize("field", ["name", "target_net_price", "internal_id", "gtin"])
def test_extra_fields_are_rejected(field: str) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RequirementPayload.model_validate(_payload(**{field: "leak"}))


def test_identifiers_cannot_be_sent_as_attributes() -> None:
    attributes = _payload()["attributes"] | {
        "gtin": {
            "type": "identifier",
            "scheme": "GTIN",
            "value": "04040456781234",
            "checksum_valid": True,
        }
    }
    origin = _payload()["attribute_origin"] | {"gtin": "MASTER"}

    with pytest.raises(ValidationError):
        RequirementPayload.model_validate(_payload(attributes=attributes, attribute_origin=origin))


def test_origins_must_match_the_attributes() -> None:
    with pytest.raises(ValidationError, match="attribute_origin"):
        RequirementPayload.model_validate(_payload(attribute_origin={"connector": "EXTRACTED"}))


def test_an_attribute_cannot_be_both_known_and_unknown() -> None:
    with pytest.raises(ValidationError, match="only one"):
        RequirementPayload.model_validate(_payload(unknown_attributes=["connector"]))


@pytest.mark.parametrize(
    "ref", ["ar_short", "AR_5MZQ4K7T2V9C", "ar_5mzq4k7t2v9c", "art_03", "ar_5MZQ4K7T2V9I"]
)
def test_malformed_article_refs_are_rejected(ref: str) -> None:
    with pytest.raises(ValidationError):
        RequirementPayload.model_validate(_payload(article_ref=ref))


def test_version_other_than_1_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RequirementPayload.model_validate(_payload(requirement_version=2))


def test_product_hints_accept_only_a_valid_gtin() -> None:
    valid = RequirementPayload.model_validate(
        _payload(product_hints={"brand": "B. Braun", "gtin": "04040456781234"})
    )
    assert valid.product_hints is not None

    with pytest.raises(ValidationError, match="check digit"):
        RequirementPayload.model_validate(_payload(product_hints={"gtin": "04040456999887"}))


def test_hash_ignores_key_order_and_bookkeeping_fields() -> None:
    base = RequirementPayload.model_validate(_payload()).requirement_hash()
    reordered = _payload()
    reordered["attributes"] = dict(reversed(reordered["attributes"].items()))
    reordered["unknown_attributes"] = ["pump_compatible", "needle_included"]

    assert RequirementPayload.model_validate(reordered).requirement_hash() == base
    assert (
        RequirementPayload.model_validate(
            _payload(answered_question_ids=["q_9"], article_ref="ar_H8R2WX3N6J4D")
        ).requirement_hash()
        == base
    )


def test_hash_changes_with_content() -> None:
    base = RequirementPayload.model_validate(_payload()).requirement_hash()
    changed = _payload()
    changed["attributes"]["connector"] = {"type": "enum", "value": "LUER"}

    assert RequirementPayload.model_validate(changed).requirement_hash() != base
    assert (
        RequirementPayload.model_validate(
            _payload(product_hints={"brand": "B. Braun"})
        ).requirement_hash()
        != base
    )
