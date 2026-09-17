"""The Anthropic adapter (ARCHITECTURE §13).

Adaptive thinking with an effort level, structured outputs through `messages.parse`, the stable
system prefix cached, and no sampling parameters (Opus 5 and Sonnet 5 reject them). The stop
reason is checked before the output is read, and an answer that fails validation gets exactly
one repair attempt.
"""

import time
from dataclasses import dataclass
from typing import Any

import anthropic
from pydantic import BaseModel, SecretStr, ValidationError

from llm_client.client import CallRecord, LLMResult, StructuredRequest, request_log
from llm_client.pricing import cost_usd

_REPAIR_NOTE = (
    "\n\nYour previous answer did not match the required schema ({error}). "
    "Answer again, following the schema exactly."
)


@dataclass(frozen=True)
class _Tokens:
    input: int = 0
    output: int = 0
    cache_write: int = 0
    cache_read: int = 0


_NO_TOKENS = _Tokens()


class AnthropicClient:
    def __init__(self, api_key: SecretStr, *, sdk: anthropic.Anthropic | None = None) -> None:
        # The SDK can be injected so tests run against a mocked transport.
        self._sdk = sdk or anthropic.Anthropic(api_key=api_key.get_secret_value())

    def parse[T: BaseModel](self, request: StructuredRequest[T]) -> LLMResult[T]:
        output, first = self._attempt(request, request.user)
        if output is not None or first.stop_reason != "end_turn":
            return LLMResult(output=output, records=(first,))
        repaired_user = request.user + _REPAIR_NOTE.format(error=first.error)
        output, second = self._attempt(request, repaired_user)
        return LLMResult(output=output, records=(first, second))

    def _attempt[T: BaseModel](
        self, request: StructuredRequest[T], user: str
    ) -> tuple[T | None, CallRecord]:
        log = request_log(request) | {"user": user}
        started = time.monotonic()
        try:
            message = self._sdk.messages.parse(
                model=request.model,
                max_tokens=request.max_tokens,
                thinking={"type": "adaptive"},
                output_config={"effort": request.effort},
                system=[
                    {
                        "type": "text",
                        "text": request.system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user}],
                output_format=request.output_type,
            )
        except ValidationError as exc:
            return None, self._record(request, log, started, error=f"invalid output: {exc}")
        except anthropic.APIError as exc:
            # The SDK's message names the failure without echoing credentials.
            return None, self._record(
                request, log, started, stop_reason="api_error", error=type(exc).__name__
            )

        usage = message.usage
        tokens = _Tokens(
            input=usage.input_tokens,
            output=usage.output_tokens,
            cache_write=usage.cache_creation_input_tokens or 0,
            cache_read=usage.cache_read_input_tokens or 0,
        )
        stop_reason = message.stop_reason or "unknown"
        if stop_reason != "end_turn":
            return None, self._record(
                request, log, started, stop_reason=stop_reason, error=stop_reason, tokens=tokens
            )
        output = message.parsed_output
        if output is None:
            return None, self._record(
                request, log, started, stop_reason=stop_reason, error="no output", tokens=tokens
            )
        response = output.model_dump(mode="json")
        return output, self._record(
            request, log, started, stop_reason=stop_reason, response=response, tokens=tokens
        )

    @staticmethod
    def _record(
        request: StructuredRequest[Any],
        log: dict[str, Any],
        started: float,
        *,
        stop_reason: str = "end_turn",
        response: dict[str, Any] | None = None,
        error: str | None = None,
        tokens: _Tokens = _NO_TOKENS,
    ) -> CallRecord:
        return CallRecord(
            purpose=request.purpose,
            model=request.model,
            effort=request.effort,
            prompt_version=request.prompt_version,
            request=log,
            response=response,
            stop_reason=stop_reason,
            input_tokens=tokens.input,
            output_tokens=tokens.output,
            cache_read_tokens=tokens.cache_read,
            cache_write_tokens=tokens.cache_write,
            latency_ms=round((time.monotonic() - started) * 1000),
            cost_usd=cost_usd(
                request.model,
                input_tokens=tokens.input,
                output_tokens=tokens.output,
                cache_write_tokens=tokens.cache_write,
                cache_read_tokens=tokens.cache_read,
            ),
            error=error,
        )
