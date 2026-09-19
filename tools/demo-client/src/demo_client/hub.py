"""Typed calls to the supplier hub. The HTTP client is injected so tests can fake the network."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from demo_client.api import ApiClient


class NotSettled(RuntimeError):
    """The round never finished: usually no worker is running at the hub."""


@dataclass
class HubClient(ApiClient):
    # How the client waits for the hub's worker; in-process tests drain the queue instead.
    sleep: Callable[[float], None] = time.sleep

    def exchange(self, assertion: str) -> dict[str, Any]:
        """A node assertion becomes a hub token; the client holds both at once (§17)."""
        body = self._json(
            "POST", "/auth/token-exchange", retry=False, json={"assertion": assertion}
        )
        self.token = str(body["access_token"])
        return body

    def templates(self) -> list[dict[str, Any]]:
        return self._list("GET", "/templates")

    def search(self, requirement: dict[str, Any], **options: Any) -> dict[str, Any]:
        return self._json("POST", "/search", json={"requirement": requirement, **options})

    def catalog_variants(self, text: str) -> list[dict[str, Any]]:
        return self._list("GET", "/catalog/variants", params={"q": text})

    def variant_attributes(self, variant_id: str) -> dict[str, Any]:
        return self._json("GET", f"/catalog/variants/{variant_id}/attributes")

    def open_assessment(self, requirement: dict[str, Any], variant_id: str) -> dict[str, Any]:
        body = {"requirement": requirement, "variant_id": variant_id}
        return self._json("POST", "/assessments", json=body)

    def assessments(self) -> list[dict[str, Any]]:
        return self._list("GET", "/assessments")

    def assessment(self, assessment_id: str) -> dict[str, Any]:
        return self._json("GET", f"/assessments/{assessment_id}")

    def settled(
        self, assessment_id: str, *, attempts: int = 120, interval_s: float = 0.5
    ) -> dict[str, Any]:
        """Polls until the hub's worker has finished the round (§19 step 7)."""
        for _ in range(attempts):
            current = self.assessment(assessment_id)
            if current["status"] != "ASSESSING":
                return current
            self.sleep(interval_s)
        raise NotSettled(f"assessment {assessment_id} is still ASSESSING; is the worker running?")

    def assign(self, assessment_id: str, subject_id: str) -> dict[str, Any]:
        body = {"subject_id": subject_id}
        return self._json("PUT", f"/assessments/{assessment_id}/assignee", json=body)

    def add_question(self, assessment_id: str, text: str, version: int) -> dict[str, Any]:
        """A free question to the supplier; the hub proposes its attribute (§7.2)."""
        body = {"version": version, "addressee": "SUPPLIER", "attribute_key": None, "text": text}
        return self._json("POST", f"/assessments/{assessment_id}/questions", json=body)

    def add_requirement(
        self, assessment_id: str, requirement: dict[str, Any], version: int
    ) -> dict[str, Any]:
        body = {"requirement": requirement, "version": version}
        return self._json("POST", f"/assessments/{assessment_id}/requirements", json=body)

    def withdraw_question(self, assessment_id: str, question_id: str, version: int) -> None:
        body = {"version": version, "withdraw": True}
        self._call("PATCH", f"/assessments/{assessment_id}/questions/{question_id}", json=body)

    def send_questions(self, assessment_id: str, version: int) -> dict[str, Any]:
        body = {"version": version}
        return self._json("POST", f"/assessments/{assessment_id}/send-questions", json=body)

    def resolve(
        self, assessment_id: str, verdict: str, version: int, note: str | None = None
    ) -> dict[str, Any]:
        body = {"verdict": verdict, "version": version, "note": note}
        return self._json("POST", f"/assessments/{assessment_id}/resolve", json=body)

    def tenants(self) -> list[dict[str, Any]]:
        return self._list("GET", "/admin/tenants")

    def register_key(self, tenant_id: str, public_jwk: dict[str, Any]) -> dict[str, Any]:
        """Returns the fingerprint to confirm with the hospital out of band (§17)."""
        body = {"public_jwk": public_jwk}
        return self._json("POST", f"/admin/tenants/{tenant_id}/signing-keys", json=body)

    def revoke_key(self, tenant_id: str, kid: str) -> dict[str, Any]:
        """Also ends every hub session exchanged with that key (§17)."""
        return self._json("POST", f"/admin/tenants/{tenant_id}/signing-keys/{kid}/revoke")

    def cancel(self, assessment_id: str, version: int) -> dict[str, Any]:
        body = {"version": version}
        return self._json("POST", f"/assessments/{assessment_id}/cancel", json=body)

    def proposals(self, status: str | None = None) -> list[dict[str, Any]]:
        params = {} if status is None else {"status": status}
        return self._list("GET", "/admin/attribute-proposals", params=params)

    def approve_proposal(self, proposal_id: str, criticality: str, rule: str) -> dict[str, Any]:
        body = {"criticality": criticality, "rule": rule}
        return self._json("POST", f"/admin/attribute-proposals/{proposal_id}/approve", json=body)

    def simulate_supplier(self, assessment_id: str) -> dict[str, Any]:
        """Development only, and only for an operator (§21)."""
        return self._json("POST", f"/dev/assessments/{assessment_id}/simulate-supplier")
