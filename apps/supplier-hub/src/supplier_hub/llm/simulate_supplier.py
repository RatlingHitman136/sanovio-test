"""`simulate_supplier` (development only): answers supplier questions from a synthetic
datasheet, so the loop can be demonstrated without a real supplier (§13, §21)."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from llm_client import CallRecord, LLMClient, StructuredRequest, render
from supplier_hub.llm.outputs import SimulatedAnswer, SimulatedAnswers

PURPOSE = "SIMULATE_SUPPLIER"
PROMPT_VERSION = "simulate_supplier_v1"


@dataclass(frozen=True)
class Simulation:
    answers: tuple[SimulatedAnswer, ...]
    records: tuple[CallRecord, ...]


def simulate_supplier(
    llm: LLMClient,
    *,
    questions: Sequence[Mapping[str, Any]],
    datasheet: Mapping[str, Any],
    model: str,
) -> Simulation:
    data = {"questions": list(questions), "datasheet": dict(datasheet)}
    request = StructuredRequest(
        purpose=PURPOSE,
        model=model,
        effort=None,
        prompt_version=PROMPT_VERSION,
        system=render("supplier_hub.llm", f"{PROMPT_VERSION}.j2"),
        user="<data>\n" + json.dumps(data, ensure_ascii=False, indent=1) + "\n</data>",
        output_type=SimulatedAnswers,
        max_tokens=4096,
    )
    result = llm.parse(request)
    asked = {str(question["question_id"]) for question in questions}
    answers = (
        ()
        if result.output is None
        else tuple(answer for answer in result.output.answers if answer.question_id in asked)
    )
    return Simulation(answers, result.records)
