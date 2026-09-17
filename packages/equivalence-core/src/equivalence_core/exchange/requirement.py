"""The requirement: the only hospital data that leaves the node (ARCHITECTURE §16).

It is plain JSON, validated by this model on both sides. There is no field for article names,
prices or identifiers, so the node cannot send them and the hub rejects any that are added.
"""

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from equivalence_core.hashing import sha256_hex
from equivalence_core.identifiers import gs1_check_digit_valid
from equivalence_core.ids import ARTICLE_REF_PATTERN
from equivalence_core.values import AttributeValue


class AttributeOrigin(StrEnum):
    """Where a value came from, coarsely; no fact or variant ids ever leave the node."""

    MASTER = "MASTER"
    EXTRACTED = "EXTRACTED"
    REFERENCE = "REFERENCE"
    PURCHASER = "PURCHASER"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProductHints(_Strict):
    """Sent only when the hospital enables SHARE_PRODUCT_HINTS (D47)."""

    brand: str | None = None
    manufacturer_article_no: str | None = None
    gtin: str | None = None

    @field_validator("gtin")
    @classmethod
    def _valid_gtin_only(cls, gtin: str | None) -> str | None:
        if gtin is not None and not gs1_check_digit_valid(gtin):
            raise ValueError("only a GTIN with a valid check digit may be sent")
        return gtin


class RequirementPayload(_Strict):
    requirement_version: Literal[1] = 1
    article_ref: str = Field(pattern=ARTICLE_REF_PATTERN)
    template_code: str
    attributes: dict[str, AttributeValue]
    attribute_origin: dict[str, AttributeOrigin]
    unknown_attributes: tuple[str, ...] = ()
    unavailable_attributes: tuple[str, ...] = ()
    withheld_attributes: tuple[str, ...] = ()
    answered_question_ids: tuple[str, ...] = ()
    product_hints: ProductHints | None = None
    limited_template: bool = False

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.attribute_origin.keys() != self.attributes.keys():
            raise ValueError("attribute_origin must name exactly the attributes that are sent")
        groups = [
            set(self.attributes),
            set(self.unknown_attributes),
            set(self.unavailable_attributes),
            set(self.withheld_attributes),
        ]
        if sum(len(group) for group in groups) != len(set().union(*groups)):
            raise ValueError("an attribute may appear in only one of the value and status lists")
        return self

    def requirement_hash(self) -> str:
        """The hospital side as judged: re-sending the same content counts as no progress, so
        article_ref, answered question ids and origins are left out."""
        return sha256_hex(
            {
                "template_code": self.template_code,
                "attributes": self.attributes,
                "unknown_attributes": sorted(self.unknown_attributes),
                "unavailable_attributes": sorted(self.unavailable_attributes),
                "withheld_attributes": sorted(self.withheld_attributes),
                "product_hints": self.product_hints,
            }
        )
