"""Supplier comments read into typed values by `extract_answer` (Haiku 4.5), or UNCLEAR."""

from dataclasses import dataclass, field
from typing import Any

from equivalence_core.templates import AttributeDefinition, load_seed_templates
from llm_client import LLMClient, ModelUsage, RecordingLLM, summarize
from supplier_hub.core.settings import HubSettings
from supplier_hub.evals import load
from supplier_hub.llm.extract_answer import extract_answer
from supplier_hub.llm.values import typed_value


@dataclass(frozen=True)
class AnswerResult:
    attribute_key: str
    comment: str
    expected: Any
    found: Any

    @property
    def ok(self) -> bool:
        return bool(self.found == self.expected)


@dataclass
class AnswerScore:
    answers: list[AnswerResult]
    usage: list[ModelUsage] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return sum(a.ok for a in self.answers) / len(self.answers)


def run(*, llm: LLMClient, settings: HubSettings) -> AnswerScore:
    recording = RecordingLLM(llm)
    results = []
    for case in load("golden_extraction.jsonl"):
        definition = _definition(case["attribute_key"])
        extracted = extract_answer(
            recording,
            question=case["question"],
            definition=definition,
            comment=case["comment"],
            model=settings.extract_answer_model,
        )
        expected = case["expected"]
        results.append(
            AnswerResult(
                attribute_key=case["attribute_key"],
                comment=case["comment"],
                expected=None if expected is None else _dump(typed_value(definition, expected)),
                found=None if extracted.value is None else _dump(extracted.value),
            )
        )
    return AnswerScore(results, summarize(recording.records))


def _definition(key: str) -> AttributeDefinition:
    for template in load_seed_templates().values():
        if key in template.keys:
            return template.attribute(key)
    raise KeyError(key)


def _dump(value: Any) -> Any:
    return value.model_dump(mode="json")
