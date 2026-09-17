from fastapi.testclient import TestClient

from equivalence_core.templates import load_seed_templates
from hospital_node.models import User
from node_fixtures import login


def test_installed_templates_are_listed(client: TestClient, anna: User) -> None:
    body = client.get("/api/v1/templates", headers=login(client, anna)).json()

    assert [t["code"] for t in body] == [
        "generic_consumable",
        "hypodermic_needle",
        "syringe_single_use",
    ]
    seeds = load_seed_templates()
    assert body[2]["definition_hash"] == seeds["syringe_single_use"].definition_hash


def test_a_hub_definition_can_be_installed(client: TestClient, anna: User) -> None:
    headers = login(client, anna)
    definition = load_seed_templates()["syringe_single_use"].model_dump(mode="json")
    definition["attributes"] = [a for a in definition["attributes"] if a["key"] != "design"]

    response = client.put(
        "/api/v1/templates",
        json={"definition": definition, "updated_at": "2026-09-18T08:10:00Z"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["updated_at"] == "2026-09-18T08:10:00Z"
    (syringe,) = client.get("/api/v1/articles?q=Einmalspritze", headers=headers).json()
    detail = client.get(f"/api/v1/articles/{syringe['id']}", headers=headers).json()
    assert "design" not in detail["unknown_attributes"]


def test_an_invalid_definition_is_422(client: TestClient, anna: User) -> None:
    response = client.put(
        "/api/v1/templates", json={"definition": {"code": "x"}}, headers=login(client, anna)
    )

    assert response.status_code == 422
    assert "invalid template definition" in response.json()["detail"]
