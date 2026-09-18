"""Typed calls to one hospital node. The HTTP client is injected so tests can fake the network."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import httpx


class NodeError(RuntimeError):
    """The node refused a call; the message carries its status and detail."""


@dataclass
class NodeClient:
    http: httpx.Client
    base_url: str
    token: str | None = None

    def login(self, email: str, password: str) -> str:
        body = self._json("POST", "/auth/login", json={"email": email, "password": password})
        self.token = str(body["access_token"])
        return self.token

    def me(self) -> dict[str, Any]:
        return self._json("GET", "/auth/me")

    def articles(self, query: str | None = None) -> list[dict[str, Any]]:
        path = "/articles" if query is None else f"/articles?q={query}"
        found: list[dict[str, Any]] = self._call("GET", path)
        return found

    def article(self, article_id: str) -> dict[str, Any]:
        return self._json("GET", f"/articles/{article_id}")

    def requirement(
        self, article_id: str, answered_question_ids: Sequence[str] = ()
    ) -> dict[str, Any]:
        body = {"answered_question_ids": list(answered_question_ids)}
        return self._json("POST", f"/articles/{article_id}/requirement", json=body)

    def set_reference(self, article_id: str, variant: Mapping[str, Any]) -> dict[str, Any]:
        """Marks a hub variant as the current product, from its `variant_attributes` (§8.2)."""
        body = {
            "variant_id": variant["variant_id"],
            "label": variant["label"],
            "attributes": variant["attributes"],
        }
        return self._json("PUT", f"/articles/{article_id}/reference", json=body)

    def set_fact(
        self, article_id: str, key: str, value: Mapping[str, Any], hub_question_id: str
    ) -> dict[str, Any]:
        """The purchaser's answer to a hub question, recorded at the node (§19 step 8)."""
        body = {"value": dict(value), "hub_question_id": hub_question_id}
        return self._json("PUT", f"/articles/{article_id}/facts/{key}", json=body)

    def assertion(self) -> dict[str, Any]:
        return self._json("POST", "/hub-assertions")

    def egress(self) -> dict[str, Any]:
        return self._json("GET", "/egress")

    def requirement_status(self, article_id: str) -> int:
        """The status code only, for showing the rate limit in action."""
        return self._request("POST", f"/articles/{article_id}/requirement", json={}).status_code

    def _json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        body: dict[str, Any] = self._call(method, path, **kwargs)
        return body

    def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._request(method, path, **kwargs)
        if response.is_error:
            raise NodeError(f"{method} {path} -> {response.status_code} {response.text}")
        return response.json()

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        return self.http.request(method, f"{self.base_url}/api/v1{path}", headers=headers, **kwargs)
