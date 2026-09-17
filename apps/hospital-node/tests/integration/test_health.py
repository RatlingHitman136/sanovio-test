from fastapi.testclient import TestClient


def test_health_reports_service_and_version(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "hospital-node"
    assert body["version"]
