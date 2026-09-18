"""`judge`: the LLM decides only what the comparators could not (ARCHITECTURE §8.4, §13).

What goes in is deliberately thin: the hospital side is the requirement's attribute values —
no `article_ref`, no product hints, no tenant — and the supplier side is its *attribute* facts
with their ids. What comes out is checked: an invented citation turns a judgment into UNKNOWN.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from equivalence_core.comparators import ComparisonStatus, DecidedBy, Judgment
from equivalence_core.exchange.requirement import RequirementPayload
from equivalence_core.templates import TemplateDefinition
from equivalence_core.verdict_rules import Verdict
from llm_client import CallRecord, Effort, LLMClient, StructuredRequest, render
from supplier_hub.llm.outputs import JudgeOutput, QuestionDraft

PURPOSE = "JUDGE"
MAX_EXTRA_CONCERNS = 3
PROMPT_VERSION = "judge_v1"


@dataclass(frozen=True)
class SupplierFactView:
    """One supplier fact as the judge may see it; identifier facts never get here (D51)."""

    fact_id: str
    attribute_key: str
    value: Any
    scope: str | None


@dataclass(frozen=True)
class JudgeResult:
    judgments: dict[str, Judgment]
    verdict: Verdict | None
    confidence: float | None
    rationale: str | None
    questions: tuple[QuestionDraft, ...]
    extra_concerns: tuple[str, ...]
    records: tuple[CallRecord, ...]


def judge(
    llm: LLMClient,
    *,
    template: TemplateDefinition,
    requirement: RequirementPayload,
    comparator_results: Sequence[Judgment],
    supplier_facts: Sequence[SupplierFactView],
    supplier_product: str,
    past_answers: Sequence[Mapping[str, Any]],
    model: str,
    effort: Effort,
) -> JudgeResult:
    to_judge = [j for j in comparator_results if j.status is ComparisonStatus.NEEDS_JUDGE]
    gaps = [
        {"attribute_key": j.attribute_key, "missing": j.missing, "criticality": j.criticality}
        for j in comparator_results
        if j.missing is not None and j.askable
    ]
    data = {
        "supplier_product": supplier_product,
        "hospital_requirement": {
            "attributes": {k: v.model_dump(mode="json") for k, v in requirement.attributes.items()},
            "unknown": list(requirement.unknown_attributes),
            "cannot_provide": list(requirement.unavailable_attributes),
        },
        "supplier_facts": [fact.__dict__ for fact in supplier_facts],
        "decided": [
            {"attribute_key": j.attribute_key, "status": j.status}
            for j in comparator_results
            if j.status not in (ComparisonStatus.NEEDS_JUDGE, ComparisonStatus.INFO)
        ],
        "needs_judgement": [j.attribute_key for j in to_judge],
        "gaps": gaps,
        "past_answers": list(past_answers),
    }
    request = StructuredRequest(
        purpose=PURPOSE,
        model=model,
        effort=effort,
        prompt_version=PROMPT_VERSION,
        system=render("supplier_hub.llm", f"{PROMPT_VERSION}.j2", template=template),
        user="<data>\n" + json.dumps(data, ensure_ascii=False, indent=1) + "\n</data>",
        output_type=JudgeOutput,
    )
    result = llm.parse(request)
    if result.output is None:
        return JudgeResult({}, None, None, None, (), (), result.records)

    known_ids = {fact.fact_id for fact in supplier_facts}
    by_key = {j.attribute_key: j for j in to_judge}
    judgments: dict[str, Judgment] = {}
    for proposed in result.output.judgments:
        base = by_key.get(proposed.attribute_key)
        if base is None:
            continue  # the comparators decided it, or it is not in the template
        cited_ok = bool(proposed.cited_fact_ids) and set(proposed.cited_fact_ids) <= known_ids
        status = ComparisonStatus(proposed.status) if cited_ok else ComparisonStatus.UNKNOWN
        judgments[base.attribute_key] = base.model_copy(
            update={
                "status": status,
                "decided_by": DecidedBy.LLM,
                "confidence": proposed.confidence,
                "rationale": proposed.rationale,
            }
        )
    askable = {gap["attribute_key"] for gap in gaps}
    return JudgeResult(
        judgments=judgments,
        verdict=Verdict(result.output.verdict),
        confidence=result.output.confidence,
        rationale=result.output.rationale,
        questions=tuple(q for q in result.output.questions if q.attribute_key in askable),
        extra_concerns=tuple(c.strip() for c in result.output.extra_concerns if c.strip())[
            :MAX_EXTRA_CONCERNS
        ],
        records=result.records,
    )
