"""Typed calls to the supplier hub. The HTTP client is injected so tests can fake the network."""

from dataclasses import dataclass
from typing import Any

import httpx

from demo_client.node import NodeError


@dataclass
class HubClient:
    http: httpx.Client
    base_url: str
    token: str | None = None

    def login(self, email: str, password: str) -> str:
        body = self._json("POST", "/auth/login", json={"email": email, "password": password})
        self.token = str(body["access_token"])
        return self.token

    def exchange(self, assertion: str) -> dict[str, Any]:
        """A node assertion becomes a hub token; the client holds both at once (§17)."""
        body = self._json("POST", "/auth/token-exchange", json={"assertion": assertion})
        self.token = str(body["access_token"])
        return body

    def me(self) -> dict[str, Any]:
        return self._json("GET", "/auth/me")

    def templates(self) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = self._call("GET", "/templates")
        return found

    def search(self, requirement: dict[str, Any], **options: Any) -> dict[str, Any]:
        return self._json("POST", "/search", json={"requirement": requirement, **options})

    def variant_attributes(self, variant_id: str) -> dict[str, Any]:
        return self._json("GET", f"/catalog/variants/{variant_id}/attributes")

    def _json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        body: dict[str, Any] = self._call(method, path, **kwargs)
        return body

    def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        response = self.http.request(
            method, f"{self.base_url}/api/v1{path}", headers=headers, **kwargs
        )
        if response.is_error:
            raise NodeError(f"{method} {path} -> {response.status_code} {response.text}")
        return response.json()
