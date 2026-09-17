import httpx
import pytest

from demo_client.node import NodeClient, NodeError

TOKEN = "node-token"


def _node(handler: object) -> NodeClient:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    return NodeClient(httpx.Client(transport=transport), "http://node")


def test_login_stores_the_token_and_sends_it() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/login"):
            return httpx.Response(
                200, json={"access_token": TOKEN, "expires_at": "2026-09-17T17:00:00Z"}
            )
        return httpx.Response(200, json={"display_name": "Anna Meier"})

    node = _node(handle)
    node.login("anna@demo-ksp.example", "pw")
    assert node.me()["display_name"] == "Anna Meier"

    assert "Authorization" not in seen[0].headers
    assert seen[1].headers["Authorization"] == f"Bearer {TOKEN}"
    assert seen[1].url.path == "/api/v1/auth/me"


def test_requirement_posts_to_the_article() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/articles/art-1/requirement"
        return httpx.Response(200, json={"requirement": {"template_code": "x"}, "egress_id": "e"})

    assert _node(handle).requirement("art-1")["egress_id"] == "e"


def test_the_rate_limit_status_is_returned_not_raised() -> None:
    node = _node(lambda request: httpx.Response(429, json={"detail": "too many"}))

    assert node.requirement_status("art-1") == 429
    with pytest.raises(NodeError, match="429"):
        node.requirement("art-1")
