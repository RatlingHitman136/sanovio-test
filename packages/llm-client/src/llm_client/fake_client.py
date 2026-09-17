"""Deterministic stand-in for the Anthropic adapter, used in tests and offline runs."""

from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel

from llm_client.client import CallRecord, LLMResult, StructuredRequest, request_log

type Responder = Callable[[StructuredRequest[Any]], BaseModel]


class FakeLLM:
    """Answers each purpose with its responder and remembers every request, so tests can count
    calls and inspect exactly what would have been sent."""

    def __init__(self, responders: Mapping[str, Responder]) -> None:
        self._responders = dict(responders)
        self.calls: list[StructuredRequest[Any]] = []

    def parse[T: BaseModel](self, request: StructuredRequest[T]) -> LLMResult[T]:
        self.calls.append(request)
        output = request.output_type.model_validate(
            self._responders[request.purpose](request).model_dump()
        )
        record = CallRecord(
            purpose=request.purpose,
            model=request.model,
            effort=request.effort,
            prompt_version=request.prompt_version,
            request=request_log(request),
            response=output.model_dump(mode="json"),
            stop_reason="end_turn",
            cost_usd=0.0,
        )
        return LLMResult(output=output, records=(record,))
