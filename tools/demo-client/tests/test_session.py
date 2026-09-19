import json
from typing import Any

import httpx
import pytest

from demo_client.api import ApiError
from demo_client.hub import HubClient
from demo_client.node import NodeClient
from demo_client.session import Session


class FakeServices:
    """Node and hub behind one MockTransport, counting what the session does."""

    def __init__(self, expired_calls: int = 0) -> None:
        self.exchanges = 0
        self.expired_calls = expired_calls
        self.installed: list[dict[str, Any]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        route = (request.url.host, request.method, request.url.path.removeprefix("/api/v1"))
        match route:
            case ("node", "POST", "/auth/login"):
                return httpx.Response(200, json={"access_token": "node-token"})
            case ("node", "POST", "/hub-assertions"):
                return httpx.Response(200, json={"assertion": f"assertion-{self.exchanges}"})
            case ("hub", "POST", "/auth/token-exchange"):
                self.exchanges += 1
                return httpx.Response(200, json={"access_token": f"hub-{self.exchanges}"})
            case ("hub", "GET", "/auth/me"):
                if self.expired_calls:
                    self.expired_calls -= 1
                    return httpx.Response(401, json={"detail": "invalid or expired token"})
                return httpx.Response(200, json={"token": request.headers["Authorization"]})
            case ("hub", "GET", "/templates"):
                return httpx.Response(
                    200,
                    json=[
                        _template("syringe", "2026-09-18T10:00:00Z"),
                        _template("needle", "2026-09-17T09:00:00Z"),
                    ],
                )
            case ("node", "GET", "/templates"):
                return httpx.Response(
                    200,
                    json=[
                        _template("syringe", "2026-09-17T09:00:00Z"),
                        _template("needle", "2026-09-17T09:00:00Z"),
                    ],
                )
            case ("node", "PUT", "/templates"):
                self.installed.append(json.loads(request.content))
                return httpx.Response(200, json={})
        raise AssertionError(f"unexpected {route}")


def _template(code: str, updated_at: str) -> dict[str, Any]:
    return {"code": code, "definition": {"code": code}, "updated_at": updated_at}


def _session(services: FakeServices) -> Session:
    http = httpx.Client(transport=httpx.MockTransport(services.handle))
    return Session(NodeClient(http, "http://node"), HubClient(http, "http://hub"))


def test_an_expired_hub_token_is_exchanged_again_once() -> None:
    services = FakeServices(expired_calls=1)
    session = _session(services)
    session.sign_in("anna@demo-ksp.example", "pw")

    assert session.hub.me() == {"token": "Bearer hub-2"}
    assert services.exchanges == 2


def test_a_second_refusal_is_raised() -> None:
    services = FakeServices(expired_calls=2)
    session = _session(services)
    session.sign_in("anna@demo-ksp.example", "pw")

    with pytest.raises(ApiError) as refused:
        session.hub.me()
    assert refused.value.status == 401
    assert services.exchanges == 2


def test_only_newer_hub_definitions_are_installed() -> None:
    services = FakeServices()
    session = _session(services)
    session.sign_in("anna@demo-ksp.example", "pw")

    assert session.sync_templates() == ["syringe"]
    assert services.installed == [
        {"definition": {"code": "syringe"}, "updated_at": "2026-09-18T10:00:00Z"}
    ]
