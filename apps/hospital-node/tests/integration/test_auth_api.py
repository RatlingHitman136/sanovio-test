from fastapi.testclient import TestClient

from node_fixtures import PASSWORD, Users, login


def test_login_me_logout(client: TestClient, users: Users) -> None:
    anna = users.add("anna")
    headers = login(client, anna)

    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json() == {
        "email": "anna@demo-ksp.example",
        "display_name": "Anna",
        "role": "PURCHASER",
        "hub_subject_id": anna.hub_subject_id,
    }

    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    after = client.get("/api/v1/auth/me", headers=headers)
    assert after.status_code == 401
    assert after.headers["WWW-Authenticate"] == "Bearer"


def test_wrong_password_is_401(client: TestClient, users: Users) -> None:
    users.add("anna")

    response = client.post(
        "/api/v1/auth/login", json={"email": "anna@demo-ksp.example", "password": PASSWORD + "x"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "invalid email or password"}


def test_requests_without_a_token_are_401(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401
