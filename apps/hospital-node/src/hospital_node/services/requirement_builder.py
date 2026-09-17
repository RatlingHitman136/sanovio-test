"""The allowlist: builds the only hospital data that leaves the node (ARCHITECTURE §16).

The builder reads the projection, never the article row, so names, internal ids, prices,
quantities, raw data, quotes and user ids are out of reach. Product hints are a separate
function and only called when the hospital enables them (D47).
"""

from collections.abc import Collection, Sequence
from typing import Any

from equivalence_core.exchange.requirement import AttributeOrigin, ProductHints, RequirementPayload
from equivalence_core.identifiers import IdentifierScheme
from equivalence_core.templates import TemplateDefinition
from hospital_node.models import ArticleProjection
from hospital_node.services.facts import typed_value

MAX_TEXT_LENGTH = 60


def build_requirement(
    projection: ArticleProjection,
    *,
    article_ref: str,
    template: TemplateDefinition,
    deny: Collection[str],
    hints: ProductHints | None,
    answered_question_ids: Sequence[str] = (),
) -> RequirementPayload:
    attributes: dict[str, Any] = {}
    unknown: list[str] = []
    unavailable: list[str] = []
    withheld: list[str] = []
    for key in template.shareable_keys:
        stored = projection.attributes.get(key)
        if key in deny:
            withheld.append(key)
        elif key in projection.unavailable_attributes:
            unavailable.append(key)
        elif stored is not None and _short_enough(stored):
            attributes[key] = typed_value(stored)
        else:
            unknown.append(key)
    return RequirementPayload(
        article_ref=article_ref,
        template_code=template.code,
        attributes=attributes,
        attribute_origin={
            key: AttributeOrigin(projection.attribute_origin[key]) for key in attributes
        },
        unknown_attributes=tuple(unknown),
        unavailable_attributes=tuple(unavailable),
        withheld_attributes=tuple(withheld),
        answered_question_ids=tuple(answered_question_ids),
        product_hints=hints,
        limited_template=template.limited_template,
    )


def product_hints(brand: str | None, identifiers: Sequence[dict[str, Any]]) -> ProductHints | None:
    """Brand, manufacturer article number and a GTIN whose check digit is valid; nothing else."""
    gtin = next(
        (
            entry["value"]
            for entry in identifiers
            if entry["scheme"] == IdentifierScheme.GTIN and entry["checksum_valid"] is True
        ),
        None,
    )
    reference = next(
        (
            entry["value"]
            for entry in identifiers
            if entry["scheme"] == IdentifierScheme.MANUFACTURER_REF
        ),
        None,
    )
    if brand is None and gtin is None and reference is None:
        return None
    return ProductHints(brand=brand, manufacturer_article_no=reference, gtin=gtin)


def _short_enough(stored: dict[str, Any]) -> bool:
    # Free text can carry anything, so only short values leave; longer ones are sent as unknown.
    match stored["type"]:
        case "text":
            return len(stored["value"]) <= MAX_TEXT_LENGTH
        case "list":
            return all(len(item) <= MAX_TEXT_LENGTH for item in stored["value"])
    return True
