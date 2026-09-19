"""What a run of LLM calls cost, per model: for evals and reports, never for billing."""

from collections.abc import Iterable
from dataclasses import dataclass, field

from pydantic import BaseModel

from llm_client.client import CallRecord, LLMClient, LLMResult, StructuredRequest


@dataclass
class RecordingLLM:
    """Passes every call through and keeps its call records."""

    inner: LLMClient
    records: list[CallRecord] = field(default_factory=list)

    def parse[T: BaseModel](self, request: StructuredRequest[T]) -> LLMResult[T]:
        result = self.inner.parse(request)
        self.records.extend(result.records)
        return result


@dataclass(frozen=True)
class ModelUsage:
    model: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    mean_latency_ms: float


def summarize(records: Iterable[CallRecord]) -> list[ModelUsage]:
    by_model: dict[str, list[CallRecord]] = {}
    for record in records:
        by_model.setdefault(record.model, []).append(record)
    return [
        ModelUsage(
            model=model,
            calls=len(calls),
            input_tokens=sum(c.input_tokens for c in calls),
            output_tokens=sum(c.output_tokens for c in calls),
            cost_usd=round(sum(c.cost_usd or 0.0 for c in calls), 6),
            mean_latency_ms=round(sum(c.latency_ms for c in calls) / len(calls), 1),
        )
        for model, calls in sorted(by_model.items())
    ]
