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
