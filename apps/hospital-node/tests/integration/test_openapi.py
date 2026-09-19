import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from hospital_node.core.settings import NodeSettings
from hospital_node.main import create_app
from hospital_node.openapi import spec


def test_every_operation_is_tagged_and_documents_its_refusals(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()

    operations = [
        (path, method, operation)
        for path, methods in spec["paths"].items()
        for method, operation in methods.items()
    ]
    assert len(operations) > 15
    for path, method, operation in operations:
        assert operation.get("tags"), (method, path)
        assert {"401", "403", "404", "409"} <= set(operation["responses"]), (method, path)
    assert "code" in spec["components"]["schemas"]["ErrorBody"]["properties"]


def test_the_committed_spec_is_current() -> None:
    """The purchaser app's client is generated from openapi/node.json: `make openapi`."""
    committed = Path(__file__).parents[4] / "openapi" / "node.json"

    assert json.loads(committed.read_text(encoding="utf-8")) == spec(), "run `make openapi`"


def test_the_purchaser_app_learns_the_hub_address_without_signing_in(
    settings: NodeSettings, engine: Any
) -> None:
    configured = settings.model_copy(update={"hub_url": "https://hub.sanovio.example"})
    with TestClient(create_app(configured)) as client:
        response = client.get("/api/v1/client-config")

    assert response.json() == {"hub_url": "https://hub.sanovio.example"}


def test_the_node_serves_the_built_purchaser_app(
    settings: NodeSettings, engine: Any, tmp_path: Path
) -> None:
    (tmp_path / "ui").mkdir()
    (tmp_path / "ui" / "index.html").write_text("<html>purchaser</html>")
    configured = settings.model_copy(
        update={"purchaser_ui_dir": tmp_path / "ui", "hub_url": "https://hub.example"}
    )
    with TestClient(create_app(configured)) as client:
        page = client.get("/articles/42")
        api = client.get("/api/v1/health")

    assert page.text == "<html>purchaser</html>"
    assert "connect-src 'self' https://hub.example" in page.headers["Content-Security-Policy"]
    assert api.json()["status"] == "ok"
