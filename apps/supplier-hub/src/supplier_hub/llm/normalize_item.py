"""`normalize_item`: reads a supplier's own product text into facts (ARCHITECTURE §13).

Catalog text is published by the supplier, so unlike the node's article names it is not
hospital data. Every proposed fact is still checked here before anyone sees it.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from equivalence_core.templates import (
    GENERIC_CODE,
    AttributeDefinition,
    TemplateDefinition,
    ValueType,
)
from equivalence_core.validation import InvalidValue, validate_value
from equivalence_core.values import (
    AttributeValue,
    BoolValue,
    EnumValue,
    ListValue,
    NumberValue,
    TextValue,
)
from llm_client import CallRecord, Effort, LLMClient, StructuredRequest, render
from supplier_hub.llm.outputs import NormalizedItem, NormalizeItems, ProposedFact

PURPOSE = "NORMALIZE_ITEM"
PROMPT_VERSION = "normalize_item_v1"


@dataclass(frozen=True)
class CheckedFact:
    attribute_key: str
    value: AttributeValue
    quote: str
    confidence: float


@dataclass(frozen=True)
class ItemReading:
    category_code: str | None
    facts: tuple[CheckedFact, ...]


@dataclass(frozen=True)
class BatchResult:
    readings: Sequence[ItemReading] | None
    records: tuple[CallRecord, ...]


@dataclass(frozen=True)
class ItemText:
    """What one family says about itself, as printed."""

    name: str
    text: str


def normalize_items(
    llm: LLMClient,
    items: Sequence[ItemText],
    templates: Mapping[str, TemplateDefinition],
    *,
    model: str,
    effort: Effort,
) -> BatchResult:
    ordered = [templates[code] for code in sorted(templates)]
    request = StructuredRequest(
        purpose=PURPOSE,
        model=model,
        effort=effort,
        prompt_version=PROMPT_VERSION,
        system=render(
            "supplier_hub.llm",
            f"{PROMPT_VERSION}.j2",
            templates=ordered,
            generic_code=GENERIC_CODE,
        ),
        user=_user_message(items),
        output_type=NormalizeItems,
    )
    result = llm.parse(request)
    if result.output is None:
        return BatchResult(readings=None, records=result.records)
    by_index = {item.index: item for item in result.output.items}
    readings = [_check(by_index.get(index), item, templates) for index, item in enumerate(items)]
    return BatchResult(readings=readings, records=result.records)


def _user_message(items: Sequence[ItemText]) -> str:
    numbered = [
        {"index": index, "name": item.name, "text": item.text} for index, item in enumerate(items)
    ]
    return (
        "Normalize each product in the data block. Return one entry per index.\n"
        f"<products>\n{json.dumps(numbered, ensure_ascii=False, indent=1)}\n</products>"
    )


def _check(
    item: NormalizedItem | None,
    source: ItemText,
    templates: Mapping[str, TemplateDefinition],
) -> ItemReading:
    template = templates.get(item.category_code or "") if item else None
    if item is None or template is None:
        return ItemReading(category_code=None, facts=())
    haystack = f"{source.name} {source.text}".casefold()
    facts: dict[str, CheckedFact] = {}
    for proposed in item.facts:
        key = proposed.attribute_key
        if key not in template.keys or key in facts:
            continue
        if not proposed.quote.strip() or proposed.quote.casefold() not in haystack:
            continue
        definition = template.attribute(key)
        typed = _typed(definition, proposed)
        if typed is None:
            continue
        try:
            value = validate_value(definition, typed)
        except InvalidValue:
            continue
        facts[key] = CheckedFact(key, value, proposed.quote, proposed.confidence)
    return ItemReading(category_code=template.code, facts=tuple(facts.values()))


def _typed(definition: AttributeDefinition, proposed: ProposedFact) -> AttributeValue | None:
    """The plain JSON value in the shape the definition asks for, or None if it cannot be."""
    raw = proposed.value
    match definition.type:
        case ValueType.NUMBER if isinstance(raw, int | float) and not isinstance(raw, bool):
            return NumberValue(value=raw, unit=proposed.unit or definition.unit or "")
        case ValueType.BOOL if isinstance(raw, bool):
            return BoolValue(value=raw)
        case ValueType.ENUM if isinstance(raw, str):
            return EnumValue(value=raw)
        case ValueType.TEXT if isinstance(raw, str) and raw.strip():
            return TextValue(value=raw.strip())
        case ValueType.LIST if isinstance(raw, list):
            return ListValue(value=tuple(raw))
    return None
