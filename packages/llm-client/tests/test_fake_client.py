from pydantic import BaseModel

from llm_client import FakeLLM, StructuredRequest


class Answer(BaseModel):
    colour: str


def _request(user: str) -> StructuredRequest[Answer]:
    return StructuredRequest(
        purpose="COLOUR",
        model="claude-sonnet-5",
        effort="medium",
        prompt_version="v1",
        system="s",
        user=user,
        output_type=Answer,
    )


def test_fake_answers_by_purpose_and_records_calls() -> None:
    fake = FakeLLM({"COLOUR": lambda request: Answer(colour=request.user.upper())})

    result = fake.parse(_request("red"))

    assert result.output == Answer(colour="RED")
    assert [call.user for call in fake.calls] == ["red"]
    assert result.records[0].request["user"] == "red"
