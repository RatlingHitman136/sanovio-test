"""`extract_answer`: a supplier's free-text comment → the value it states, or UNCLEAR (§13).

Haiku-sized work: one question, one attribute definition, one comment. A value that does not
fit the definition is UNCLEAR, and an UNCLEAR answer leaves the gap open for the next round.
"""

import json
from dataclasses import dataclass

from equivalence_core.templates import AttributeDefinition
from equivalence_core.values import AttributeValue
from llm_client import CallRecord, LLMClient, StructuredRequest, render
from supplier_hub.llm.outputs import ExtractedAnswer
from supplier_hub.llm.values import typed_value

PURPOSE = "EXTRACT_ANSWER"
PROMPT_VERSION = "extract_answer_v1"


@dataclass(frozen=True)
class Extracted:
    # None means UNCLEAR.
    value: AttributeValue | None
    quote: str | None
    records: tuple[CallRecord, ...]


def extract_answer(
    llm: LLMClient,
    *,
    question: str,
    definition: AttributeDefinition,
    comment: str,
    model: str,
) -> Extracted:
    data = {
        "question": question,
        "attribute": {
            "key": definition.key,
            "type": definition.type,
            "unit": definition.unit,
            "options": list(definition.options),
            "label": definition.labels.en,
        },
        "answer": comment,
    }
    request = StructuredRequest(
        purpose=PURPOSE,
        model=model,
        # Haiku 4.5: no adaptive thinking (ARCHITECTURE §13).
        effort=None,
        prompt_version=PROMPT_VERSION,
        system=render("supplier_hub.llm", f"{PROMPT_VERSION}.j2"),
        user="<data>\n" + json.dumps(data, ensure_ascii=False, indent=1) + "\n</data>",
        output_type=ExtractedAnswer,
        max_tokens=1024,
    )
    result = llm.parse(request)
    output = result.output
    if output is None or output.status == "UNCLEAR":
        return Extracted(None, None, result.records)
    value = typed_value(definition, output.value, output.unit)
    return Extracted(value, output.quote if value is not None else None, result.records)
