from fastapi.testclient import TestClient

from hospital_node.core.settings import NodeSettings
from hospital_node.main import create_app


def test_health_reports_service_and_version(settings: NodeSettings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "hospital-node"
    assert body["version"]
