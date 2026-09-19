"""Typed calls to one hospital node. The HTTP client is injected so tests can fake the network."""

from collections.abc import Mapping, Sequence
from typing import Any

from demo_client.api import ApiClient


class NodeClient(ApiClient):
    def articles(self, query: str | None = None) -> list[dict[str, Any]]:
        return self._list("GET", "/articles", params={} if query is None else {"q": query})

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

    def signing_key(self) -> dict[str, Any]:
        """The node's public JWK and fingerprint, for registration at the hub (node admin)."""
        return self._json("GET", "/admin/signing-key")

    def templates(self) -> list[dict[str, Any]]:
        return self._list("GET", "/templates")

    def install_template(self, definition: Mapping[str, Any], updated_at: str) -> dict[str, Any]:
        body = {"definition": dict(definition), "updated_at": updated_at}
        return self._json("PUT", "/templates", json=body)

    def requirement_status(self, article_id: str) -> int:
        """The status code only, for showing the rate limit in action."""
        return self._request("POST", f"/articles/{article_id}/requirement", json={}).status_code
