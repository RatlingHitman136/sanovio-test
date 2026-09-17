from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from hub_fixtures import PASSWORD, Orgs, login
from supplier_hub.models.identity import UserRole


def test_supplier_login_me_logout(client: TestClient, orgs: Orgs) -> None:
    user = orgs.user(orgs.supplier(), "catalog@bd-demo.example", UserRole.SUPPLIER)
    headers = login(client, user)

    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json() == {
        "kind": "user",
        "display_name": "Catalog",
        "organization": "BD",
        "role": "SUPPLIER",
        "subject_id": None,
    }

    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_a_wrong_password_and_an_unknown_email_look_the_same(
    client: TestClient, orgs: Orgs
) -> None:
    orgs.user(orgs.supplier(), "catalog@bd-demo.example", UserRole.SUPPLIER)

    wrong = client.post(
        "/api/v1/auth/login",
        json={"email": "catalog@bd-demo.example", "password": PASSWORD + "!"},
    )
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "nobody@bd-demo.example", "password": PASSWORD}
    )

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_an_inactive_user_cannot_log_in(client: TestClient, orgs: Orgs, session: Session) -> None:
    user = orgs.user(orgs.supplier(), "catalog@bd-demo.example", UserRole.SUPPLIER)
    user.is_active = False
    session.commit()

    response = client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})

    assert response.status_code == 401


def test_admin_endpoints_are_operator_only(client: TestClient, orgs: Orgs) -> None:
    supplier_user = orgs.user(orgs.supplier(), "catalog@bd-demo.example", UserRole.SUPPLIER)

    response = client.get("/api/v1/admin/tenants", headers=login(client, supplier_user))

    assert response.status_code == 403
    assert client.get("/api/v1/admin/tenants").status_code == 401
