from fastapi import FastAPI
from fastapi.testclient import TestClient

from service_kit.errors import Conflict, RateLimited, Unauthorized
from service_kit.http_errors import install_error_handlers


def _client() -> TestClient:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/conflict")
    def conflict() -> None:
        raise Conflict("ASSESSMENT_OPEN", "already open", {"assessment_id": "asm_1"})

    @app.get("/limited")
    def limited() -> None:
        raise RateLimited("too many", retry_after_s=42)

    @app.get("/unauthorized")
    def unauthorized() -> None:
        raise Unauthorized("no")

    return TestClient(app)


def test_a_conflict_carries_its_code_and_recovery_details() -> None:
    response = _client().get("/conflict")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "already open",
        "code": "ASSESSMENT_OPEN",
        "assessment_id": "asm_1",
    }


def test_a_rate_limit_says_when_to_retry() -> None:
    response = _client().get("/limited")

    assert (response.status_code, response.headers["Retry-After"]) == (429, "42")


def test_unauthorized_asks_for_a_bearer_token() -> None:
    response = _client().get("/unauthorized")

    assert (response.status_code, response.headers["WWW-Authenticate"]) == (401, "Bearer")
