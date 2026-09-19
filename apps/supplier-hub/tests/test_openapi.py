import json
from pathlib import Path

from fastapi.testclient import TestClient

from supplier_hub.openapi import spec


def test_every_operation_is_tagged_and_documents_its_refusals(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()

    operations = [
        (path, method, operation)
        for path, methods in spec["paths"].items()
        for method, operation in methods.items()
    ]
    assert len(operations) > 30
    for path, method, operation in operations:
        assert operation.get("tags"), (method, path)
        assert {"401", "403", "404", "409"} <= set(operation["responses"]), (method, path)
    assert "code" in spec["components"]["schemas"]["ErrorBody"]["properties"]


def test_the_committed_spec_is_current() -> None:
    """Both apps' hub client is generated from openapi/hub.json: `make openapi`."""
    committed = Path(__file__).parents[3] / "openapi" / "hub.json"

    assert json.loads(committed.read_text(encoding="utf-8")) == spec(), "run `make openapi`"
