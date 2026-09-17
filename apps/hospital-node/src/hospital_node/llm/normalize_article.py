"""`normalize_article`: one call reads a batch of article names (ARCHITECTURE §13).

Only the names are sent — no brand, id, price or quantity. Every proposed fact is checked here
before anyone sees it: the category must be installed, the attribute must belong to it, the
quote must occur in the name and the value must fit the attribute definition.
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
from hospital_node.llm.outputs import NormalizeBatch, NormalizedArticle, ProposedFact
from llm_client import CallRecord, Effort, LLMClient, StructuredRequest, render

PURPOSE = "NORMALIZE_ARTICLE"
PROMPT_VERSION = "normalize_article_v1"


@dataclass(frozen=True)
class CheckedFact:
    attribute_key: str
    value: AttributeValue
    quote: str
    confidence: float


@dataclass(frozen=True)
class ArticleReading:
    category_code: str | None
    facts: tuple[CheckedFact, ...]


@dataclass(frozen=True)
class BatchResult:
    # None when the call failed; the caller keeps the rules result for these articles.
    readings: Sequence[ArticleReading] | None
    records: tuple[CallRecord, ...]


def normalize_batch(
    llm: LLMClient,
    names: Sequence[str],
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
            "hospital_node.llm",
            f"{PROMPT_VERSION}.j2",
            templates=ordered,
            generic_code=GENERIC_CODE,
        ),
        user=_user_message(names),
        output_type=NormalizeBatch,
    )
    result = llm.parse(request)
    if result.output is None:
        return BatchResult(readings=None, records=result.records)
    by_index = {article.index: article for article in result.output.articles}
    readings = [_check(by_index.get(index), name, templates) for index, name in enumerate(names)]
    return BatchResult(readings=readings, records=result.records)


def _user_message(names: Sequence[str]) -> str:
    numbered = [{"index": index, "name": name} for index, name in enumerate(names)]
    return (
        "Normalize each article in the data block. Return one entry per index.\n"
        f"<articles>\n{json.dumps(numbered, ensure_ascii=False, indent=1)}\n</articles>"
    )


def _check(
    article: NormalizedArticle | None, name: str, templates: Mapping[str, TemplateDefinition]
) -> ArticleReading:
    template = templates.get(article.category_code or "") if article else None
    if article is None or template is None:
        return ArticleReading(category_code=None, facts=())
    facts: dict[str, CheckedFact] = {}
    for proposed in article.facts:
        key = proposed.attribute_key
        if key not in template.keys or key in facts:
            continue
        if not proposed.quote.strip() or proposed.quote.casefold() not in name.casefold():
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
    return ArticleReading(category_code=template.code, facts=tuple(facts.values()))


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
