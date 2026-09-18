"""Typed calls to the supplier hub. The HTTP client is injected so tests can fake the network."""

import time
from collections.abc import Callable
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

    def open_assessment(self, requirement: dict[str, Any], variant_id: str) -> dict[str, Any]:
        body = {"requirement": requirement, "variant_id": variant_id}
        return self._json("POST", "/assessments", json=body)

    def assessment(self, assessment_id: str) -> dict[str, Any]:
        return self._json("GET", f"/assessments/{assessment_id}")

    def settled(
        self,
        assessment_id: str,
        *,
        sleep: Callable[[float], None] = time.sleep,
        attempts: int = 120,
        interval_s: float = 0.5,
    ) -> dict[str, Any]:
        """Polls until the hub's worker has finished the round (§19 step 7)."""
        for _ in range(attempts):
            current = self.assessment(assessment_id)
            if current["status"] != "ASSESSING":
                return current
            sleep(interval_s)
        raise NodeError(f"assessment {assessment_id} is still ASSESSING; is the worker running?")

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

    def simulate_supplier(self, assessment_id: str) -> dict[str, Any]:
        """Development only, and only for an operator (§21)."""
        return self._json("POST", f"/dev/assessments/{assessment_id}/simulate-supplier")

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
