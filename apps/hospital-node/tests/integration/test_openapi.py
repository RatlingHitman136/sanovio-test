from fastapi.testclient import TestClient


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
