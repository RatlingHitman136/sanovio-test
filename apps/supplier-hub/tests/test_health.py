from fastapi.testclient import TestClient

from supplier_hub.core.settings import HubSettings
from supplier_hub.main import create_app


def test_health_reports_service_and_version() -> None:
    with TestClient(create_app(HubSettings())) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "supplier-hub"
    assert body["version"]
