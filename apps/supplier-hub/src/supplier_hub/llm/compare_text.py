"""`compare_text`: free-text values worded differently, read by meaning (ARCHITECTURE §8, §13).

The comparators settle what spelling can settle ("nein" = "keine"); what is left is worded
differently, and one Haiku call per round reads all of it before the Opus judge is asked.
A reading the model is unsure of stays with the judge.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from equivalence_core.comparators import ComparisonStatus, DecidedBy, Judgment
from equivalence_core.templates import TemplateDefinition
from equivalence_core.values import TextValue
from llm_client import CallRecord, LLMClient, StructuredRequest, render
from supplier_hub.llm.outputs import TextReadings

PURPOSE = "COMPARE_TEXT"
PROMPT_VERSION = "compare_text_v1"


@dataclass(frozen=True)
class TextComparison:
    # Only decided readings (MATCH or MISMATCH); what the model could not tell is absent.
    judgments: Mapping[str, Judgment]
    records: tuple[CallRecord, ...]


def compare_text(
    llm: LLMClient,
    *,
    template: TemplateDefinition,
    worded: Sequence[Judgment],
    model: str,
) -> TextComparison:
    pairs = [
        {
            "attribute_key": judgment.attribute_key,
            "label": template.attribute(judgment.attribute_key).labels.en,
            "hospital": _text(judgment.hospital.value if judgment.hospital else None),
            "supplier": _text(judgment.supplier.value if judgment.supplier else None),
        }
        for judgment in worded
    ]
    request = StructuredRequest(
        purpose=PURPOSE,
        model=model,
        # Haiku 4.5: no adaptive thinking (ARCHITECTURE §13).
        effort=None,
        prompt_version=PROMPT_VERSION,
        system=render("supplier_hub.llm", f"{PROMPT_VERSION}.j2"),
        user="<data>\n" + json.dumps({"pairs": pairs}, ensure_ascii=False, indent=1) + "\n</data>",
        output_type=TextReadings,
        max_tokens=1024,
    )
    result = llm.parse(request)
    by_key = {judgment.attribute_key: judgment for judgment in worded}
    decided: dict[str, Judgment] = {}
    for reading in result.output.readings if result.output else []:
        base = by_key.get(reading.attribute_key)
        if base is None or reading.status == "UNKNOWN":
            continue
        decided[base.attribute_key] = base.model_copy(
            update={
                "status": ComparisonStatus(reading.status),
                "decided_by": DecidedBy.LLM,
                "rationale": reading.rationale,
            }
        )
    return TextComparison(decided, result.records)


def _text(value: object) -> str:
    return value.value if isinstance(value, TextValue) else ""
