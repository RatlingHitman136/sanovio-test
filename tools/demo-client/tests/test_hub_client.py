import httpx
import pytest

from demo_client.hub import HubClient
from demo_client.node import NodeError

TOKEN = "hub-token"


def _hub(handler: object) -> HubClient:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    return HubClient(httpx.Client(transport=transport), "http://hub")


def test_an_exchange_stores_the_hub_token() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("token-exchange"):
            return httpx.Response(
                200,
                json={
                    "access_token": TOKEN,
                    "expires_at": "2026-09-17T09:30:00Z",
                    "tenant_alias": "Hospital H-7F3A",
                },
            )
        return httpx.Response(200, json={"kind": "purchaser"})

    hub = _hub(handle)
    exchanged = hub.exchange("signed.assertion")
    hub.me()

    assert exchanged["tenant_alias"] == "Hospital H-7F3A"
    assert "Authorization" not in seen[0].headers
    assert seen[1].headers["Authorization"] == f"Bearer {TOKEN}"


def test_search_posts_the_requirement_unchanged() -> None:
    requirement = {"template_code": "syringe_single_use", "attributes": {}}

    def handle(request: httpx.Request) -> httpx.Response:
        import json

        assert json.loads(request.content)["requirement"] == requirement
        return httpx.Response(200, json={"candidates": []})

    assert _hub(handle).search(requirement) == {"candidates": []}


def test_a_refusal_is_raised_with_its_status() -> None:
    hub = _hub(lambda request: httpx.Response(401, json={"detail": "nope"}))

    with pytest.raises(NodeError, match="401"):
        hub.exchange("bad")


def test_settled_polls_until_the_round_is_done() -> None:
    statuses = iter(["ASSESSING", "ASSESSING", "NEEDS_QUESTION_REVIEW"])
    naps: list[float] = []

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "a1", "status": next(statuses)})

    settled = _hub(handle).settled("a1", sleep=naps.append, interval_s=0.1)

    assert settled["status"] == "NEEDS_QUESTION_REVIEW"
    assert naps == [0.1, 0.1]


def test_settled_gives_up_when_no_worker_runs() -> None:
    hub = _hub(lambda request: httpx.Response(200, json={"status": "ASSESSING"}))

    with pytest.raises(NodeError, match="worker"):
        hub.settled("a1", sleep=lambda _: None, attempts=3)


def test_state_changes_carry_the_version() -> None:
    import json

    seen: list[tuple[str, str, dict[str, object]]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, json.loads(request.content or b"{}")))
        return httpx.Response(200, json={"status": "AWAITING_ANSWERS"})

    hub = _hub(handle)
    hub.send_questions("a1", 4)
    hub.withdraw_question("a1", "q1", 5)
    hub.resolve("a1", "EQUIVALENT", 6)

    assert seen == [
        ("POST", "/api/v1/assessments/a1/send-questions", {"version": 4}),
        ("PATCH", "/api/v1/assessments/a1/questions/q1", {"version": 5, "withdraw": True}),
        (
            "POST",
            "/api/v1/assessments/a1/resolve",
            {"verdict": "EQUIVALENT", "version": 6, "note": None},
        ),
    ]
