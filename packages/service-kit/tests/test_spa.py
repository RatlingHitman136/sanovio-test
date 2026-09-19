from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from service_kit.spa import MissingBuild, mount_spa


def _build(tmp_path: Path) -> Path:
    (tmp_path / "assets").mkdir(parents=True)
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "assets" / "main.js").write_text("console.log(1)")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    (tmp_path.parent / "secret.txt").write_text("outside the build")
    return tmp_path


def _app(directory: Path) -> TestClient:
    app = FastAPI()
    api = APIRouter(prefix="/api/v1")

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api)
    mount_spa(app, directory, connect_to=["http://hub.example"])
    return TestClient(app)


def test_client_routes_get_the_app_and_its_headers(tmp_path: Path) -> None:
    client = _app(_build(tmp_path / "dist"))

    page = client.get("/assessments/0190-some-id")

    assert page.status_code == 200 and page.text == "<html>app</html>"
    policy = page.headers["Content-Security-Policy"]
    assert "connect-src 'self' http://hub.example" in policy
    assert "script-src 'self';" in policy
    assert page.headers["X-Content-Type-Options"] == "nosniff"


def test_files_and_the_api_are_served_as_themselves(tmp_path: Path) -> None:
    client = _app(_build(tmp_path / "dist"))

    assert client.get("/assets/main.js").text == "console.log(1)"
    assert client.get("/favicon.svg").text == "<svg/>"
    assert client.get("/api/v1/health").json() == {"status": "ok"}
    # An unknown API path is a JSON 404, never the app.
    missing = client.get("/api/v1/nothing-here")
    assert missing.status_code == 404 and missing.headers["content-type"] == "application/json"


def test_nothing_outside_the_build_is_served(tmp_path: Path) -> None:
    client = _app(_build(tmp_path / "dist"))

    assert client.get("/../secret.txt").text == "<html>app</html>"
    assert client.get("/%2e%2e/secret.txt").text == "<html>app</html>"


def test_a_missing_build_fails_at_startup(tmp_path: Path) -> None:
    with pytest.raises(MissingBuild, match="make ui-build"):
        mount_spa(FastAPI(), tmp_path)
