import json
from typing import Any

import anthropic
import httpx2
import pytest
from pydantic import BaseModel, SecretStr

from llm_client import AnthropicClient, StructuredRequest

API_KEY = "sk-ant-test-not-a-real-key"


class Answer(BaseModel):
    colour: str


def _message(text: str, stop_reason: str = "end_turn") -> dict[str, Any]:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 200,
            "cache_creation_input_tokens": 500,
            "cache_read_input_tokens": 0,
        },
    }


class Recorder:
    def __init__(self, *responses: dict[str, Any]) -> None:
        self.responses = list(responses)
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return httpx2.Response(200, json=self.responses.pop(0))

    def body(self, index: int) -> dict[str, Any]:
        parsed: dict[str, Any] = json.loads(self.requests[index].content)
        return parsed


def _client(recorder: Recorder) -> AnthropicClient:
    sdk = anthropic.Anthropic(
        api_key=API_KEY,
        http_client=httpx2.Client(transport=httpx2.MockTransport(recorder)),
        max_retries=0,
    )
    return AnthropicClient(SecretStr(API_KEY), sdk=sdk)


def _request() -> StructuredRequest[Answer]:
    return StructuredRequest(
        purpose="TEST",
        model="claude-sonnet-5",
        effort="medium",
        prompt_version="test_v1",
        system="You name colours.",
        user="Sky?",
        output_type=Answer,
    )


def test_request_uses_adaptive_thinking_effort_cache_and_no_sampling() -> None:
    recorder = Recorder(_message('{"colour": "blue"}'))

    result = _client(recorder).parse(_request())

    assert result.output == Answer(colour="blue")
    body = recorder.body(0)
    assert body["thinking"] == {"type": "adaptive"}
    assert body["output_config"]["effort"] == "medium"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "temperature" not in body
    assert "top_p" not in body


def test_record_has_usage_and_cost_but_never_the_key() -> None:
    recorder = Recorder(_message('{"colour": "blue"}'))

    (record,) = _client(recorder).parse(_request()).records

    assert (record.input_tokens, record.output_tokens) == (1000, 200)
    assert record.cache_write_tokens == 500
    # 1000 × $2 + 200 × $10 + 500 × $2.50 per million tokens
    assert record.cost_usd == pytest.approx(0.00525)
    assert record.response == {"colour": "blue"}
    assert API_KEY not in json.dumps(record.request)


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_a_non_final_stop_reason_yields_no_output_and_no_retry(stop_reason: str) -> None:
    recorder = Recorder(_message('{"colour": "blue"}', stop_reason=stop_reason))

    result = _client(recorder).parse(_request())

    assert result.output is None
    assert [r.error for r in result.records] == [stop_reason]
    assert len(recorder.requests) == 1


def test_invalid_output_is_repaired_once() -> None:
    recorder = Recorder(_message('{"hue": "blue"}'), _message('{"colour": "blue"}'))

    result = _client(recorder).parse(_request())

    assert result.output == Answer(colour="blue")
    assert len(result.records) == 2
    assert result.records[0].error is not None
    assert "did not match the required schema" in recorder.body(1)["messages"][0]["content"]


def test_a_second_invalid_output_gives_up() -> None:
    recorder = Recorder(_message('{"hue": "blue"}'), _message("not json"))

    result = _client(recorder).parse(_request())

    assert result.output is None
    assert len(recorder.requests) == 2


def test_an_api_error_is_recorded_not_raised() -> None:
    def fail(request: httpx2.Request) -> httpx2.Response:
        error = {"type": "authentication_error", "message": "bad key"}
        return httpx2.Response(401, json={"type": "error", "error": error})

    sdk = anthropic.Anthropic(
        api_key=API_KEY,
        http_client=httpx2.Client(transport=httpx2.MockTransport(fail)),
        max_retries=0,
    )

    result = AnthropicClient(SecretStr(API_KEY), sdk=sdk).parse(_request())

    assert result.output is None
    assert result.records[0].error == "AuthenticationError"
    assert result.records[0].cost_usd == 0.0
