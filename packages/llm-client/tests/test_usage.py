from typing import Any

from pydantic import BaseModel

from llm_client import CallRecord, FakeLLM, RecordingLLM, StructuredRequest, summarize


class Answer(BaseModel):
    text: str


def _request(model: str) -> StructuredRequest[Answer]:
    return StructuredRequest(
        purpose="P",
        model=model,
        effort=None,
        prompt_version="v1",
        system="s",
        user="u",
        output_type=Answer,
    )


def test_every_call_is_recorded_and_passed_through() -> None:
    recording = RecordingLLM(FakeLLM({"P": lambda request: Answer(text="ok")}))

    result = recording.parse(_request("claude-haiku-4-5"))

    assert result.output == Answer(text="ok")
    assert [record.model for record in recording.records] == ["claude-haiku-4-5"]


def test_usage_is_summed_per_model() -> None:
    def record(model: str, cost: float | None, latency: int) -> CallRecord:
        request: dict[str, Any] = {}
        return CallRecord(
            purpose="P",
            model=model,
            effort=None,
            prompt_version="v1",
            request=request,
            input_tokens=100,
            output_tokens=10,
            latency_ms=latency,
            cost_usd=cost,
        )

    usage = summarize(
        [record("opus", 0.5, 1000), record("opus", 0.25, 3000), record("haiku", None, 200)]
    )

    assert [(u.model, u.calls, u.cost_usd, u.mean_latency_ms) for u in usage] == [
        ("haiku", 1, 0.0, 200.0),
        ("opus", 2, 0.75, 2000.0),
    ]
    assert usage[1].input_tokens == 200
