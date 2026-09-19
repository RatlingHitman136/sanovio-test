"""What the node and hub clients share: bearer auth, JSON calls and one typed error."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx


class ApiError(RuntimeError):
    """A service refused a call; `status` lets callers react to 401, 409 or 429."""

    def __init__(self, method: str, path: str, status: int, body: str) -> None:
        super().__init__(f"{method} {path} -> {status} {body}")
        self.status = status
        self.body = body


@dataclass
class ApiClient:
    """The HTTP client is injected: a real one, a MockTransport, or a FastAPI TestClient."""

    http: httpx.Client
    base_url: str
    token: str | None = None
    # Called once on a 401 before the request is retried; the hub session sets it (§19).
    reauthenticate: Callable[[], object] | None = None

    def login(self, email: str, password: str) -> str:
        credentials = {"email": email, "password": password}
        body = self._json("POST", "/auth/login", retry=False, json=credentials)
        self.token = str(body["access_token"])
        return self.token

    def me(self) -> dict[str, Any]:
        return self._json("GET", "/auth/me")

    def _json(self, method: str, path: str, *, retry: bool = True, **kwargs: Any) -> dict[str, Any]:
        body: dict[str, Any] = self._call(method, path, retry=retry, **kwargs)
        return body

    def _list(self, method: str, path: str, **kwargs: Any) -> list[dict[str, Any]]:
        body: list[dict[str, Any]] = self._call(method, path, **kwargs)
        return body

    def _call(self, method: str, path: str, *, retry: bool = True, **kwargs: Any) -> Any:
        """`retry=False` for the authentication calls themselves, which must never recurse."""
        response = self._request(method, path, **kwargs)
        if response.status_code == 401 and retry and self.reauthenticate is not None:
            self.reauthenticate()
            response = self._request(method, path, **kwargs)
        if response.is_error:
            raise ApiError(method, path, response.status_code, response.text)
        return response.json()

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        return self.http.request(method, f"{self.base_url}/api/v1{path}", headers=headers, **kwargs)
