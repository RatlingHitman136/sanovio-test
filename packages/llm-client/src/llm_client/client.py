"""The interface every LLM pipeline calls, and the record every call leaves behind."""

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel

type Effort = Literal["low", "medium", "high", "xhigh", "max"]


@dataclass(frozen=True)
class StructuredRequest[T: BaseModel]:
    """One call whose answer must validate as `output_type`.

    `system` is the unchanging prefix (instructions, templates) and is cached; `user` carries the
    data of this call.
    """

    purpose: str
    model: str
    effort: Effort
    prompt_version: str
    system: str
    user: str
    output_type: type[T]
    max_tokens: int = 16000


@dataclass(frozen=True)
class CallRecord:
    """What a service stores in its `llm_calls` table. Never contains credentials."""

    purpose: str
    model: str
    effort: str
    prompt_version: str
    request: dict[str, Any]
    response: dict[str, Any] | None = None
    stop_reason: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    latency_ms: int = 0
    cost_usd: float | None = None
    error: str | None = None


@dataclass(frozen=True)
class LLMResult[T: BaseModel]:
    output: T | None
    # One record per API call, so a repair retry is audited as its own call.
    records: tuple[CallRecord, ...]


class LLMClient(Protocol):
    def parse[T: BaseModel](self, request: StructuredRequest[T]) -> LLMResult[T]:
        """Never raises for model-side failures: `output` is None and the last record says why."""
        ...


def request_log(request: StructuredRequest[Any]) -> dict[str, Any]:
    """The loggable part of a request: prompt text and settings, no client configuration."""
    return {
        "model": request.model,
        "effort": request.effort,
        "max_tokens": request.max_tokens,
        "system": request.system,
        "user": request.user,
        "output_schema": request.output_type.__name__,
    }
