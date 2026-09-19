"""Every `/admin` route is for operators only, including routes added later (§17.1)."""

import re
import uuid

import pytest
from fastapi.testclient import TestClient

from supplier_hub.core.settings import HubSettings
from supplier_hub.main import create_app


def _admin_routes() -> list[tuple[str, str]]:
    """Read from the served schema, which lists every mounted route."""
    paths = create_app(HubSettings(_env_file=None)).openapi()["paths"]  # type: ignore[call-arg]
    return sorted(
        (method.upper(), re.sub(r"\{[^}]+\}", str(uuid.UUID(int=1)), path))
        for path, operations in paths.items()
        if path.startswith("/api/v1/admin")
        for method in operations
    )


ROUTES = _admin_routes()


def test_the_walk_sees_the_whole_console() -> None:
    assert len(ROUTES) >= 25


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_a_supplier_is_refused(
    client: TestClient, bd: dict[str, str], method: str, path: str
) -> None:
    assert client.request(method, path, json={}, headers=bd).status_code == 403


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_a_purchaser_is_refused(
    client: TestClient, buyer: dict[str, str], method: str, path: str
) -> None:
    assert client.request(method, path, json={}, headers=buyer).status_code in (401, 403)


@pytest.mark.parametrize(("method", "path"), ROUTES)
def test_an_anonymous_caller_is_refused(client: TestClient, method: str, path: str) -> None:
    assert client.request(method, path, json={}).status_code == 401
