from fastapi.testclient import TestClient

from hospital_node.models.users import Role
from node_fixtures import Users, login


def test_directory_needs_a_login(client: TestClient) -> None:
    assert client.get("/api/v1/users").status_code == 401


def test_directory_lists_names_and_subjects_only(client: TestClient, users: Users) -> None:
    anna = users.add("anna")
    users.add("admin", Role.NODE_ADMIN)
    retired = users.add("bert", active=False)
    headers = login(client, anna)

    active = client.get("/api/v1/users", headers=headers).json()
    everyone = client.get("/api/v1/users?include_inactive=true", headers=headers).json()

    assert [entry["display_name"] for entry in active] == ["Admin", "Anna"]
    assert {entry["hub_subject_id"] for entry in everyone} >= {retired.hub_subject_id}
    assert set(active[0]) == {"display_name", "role", "hub_subject_id", "is_active"}
