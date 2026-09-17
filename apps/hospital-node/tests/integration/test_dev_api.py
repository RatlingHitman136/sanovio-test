from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine

from hospital_node.core.settings import NodeSettings
from hospital_node.main import create_app
from hospital_node.models import User
from node_fixtures import FakeClock, login


def test_reset_seed_replaces_the_data(
    settings: NodeSettings, engine: Engine, clock: FakeClock, admin: User
) -> None:
    configured = settings.model_copy(
        update={"node_seed_password": SecretStr("correct horse battery")}
    )
    with TestClient(create_app(configured, clock=clock)) as client:
        headers = login(client, admin)
        before = client.get("/api/v1/articles", headers=headers).json()

        response = client.post("/api/v1/dev/reset-seed", json={}, headers=headers)

        assert response.status_code == 200, response.text
        assert response.json() == {"dataset": "demo_ksp", "users": 2, "articles": 10}
        # All sessions ended with the old users.
        assert client.get("/api/v1/articles", headers=headers).status_code == 401
        fresh = client.get("/api/v1/articles", headers=login(client, admin)).json()
    assert {a["article_ref"] for a in fresh}.isdisjoint(a["article_ref"] for a in before)


def test_reset_seed_is_for_admins(client: TestClient, anna: User) -> None:
    response = client.post("/api/v1/dev/reset-seed", json={}, headers=login(client, anna))

    assert response.status_code == 403


def test_reset_seed_without_a_password_is_409(client: TestClient, admin: User) -> None:
    response = client.post("/api/v1/dev/reset-seed", json={}, headers=login(client, admin))

    assert response.status_code == 409
    assert response.json()["code"] == "SEED_PASSWORD_MISSING"


def test_dev_endpoints_do_not_exist_in_prod(
    settings: NodeSettings, engine: Engine, clock: FakeClock, admin: User
) -> None:
    production = settings.model_copy(update={"app_env": "prod"})
    with TestClient(create_app(production, clock=clock)) as client:
        response = client.post("/api/v1/dev/reset-seed", json={}, headers=login(client, admin))

    assert response.status_code == 404
