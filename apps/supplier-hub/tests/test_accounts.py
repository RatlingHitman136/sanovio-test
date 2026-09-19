"""Hub logins an operator manages, and the purchasers they can stop (§17.1)."""

from typing import Any

from fastapi.testclient import TestClient

ADMIN = "/api/v1/admin"
PASSWORD = "sechs6"


def _org(client: TestClient, operator: dict[str, str], code: str) -> Any:
    orgs = client.get(f"{ADMIN}/organizations", headers=operator).json()
    return next(org for org in orgs if org["code"] == code)


def _create(client: TestClient, operator: dict[str, str], org_id: str, email: str) -> Any:
    return client.post(
        f"{ADMIN}/users",
        json={"org_id": org_id, "email": email, "display_name": "Anna", "password": PASSWORD},
        headers=operator,
    )


def _login(client: TestClient, email: str, password: str = PASSWORD) -> Any:
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _bearer(response: Any) -> dict[str, str]:
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_only_suppliers_and_the_operator_hold_hub_logins(
    client: TestClient, operator: dict[str, str]
) -> None:
    orgs = client.get(f"{ADMIN}/organizations", headers=operator).json()

    assert {org["type"] for org in orgs} == {"SUPPLIER", "OPERATOR"}


def test_a_new_supplier_gets_a_user_who_can_sign_in(
    client: TestClient, operator: dict[str, str]
) -> None:
    supplier = client.post(
        f"{ADMIN}/suppliers", json={"code": "org_terumo", "name": "Terumo"}, headers=operator
    )
    assert supplier.status_code == 200, supplier.text

    created = _create(client, operator, supplier.json()["id"], "Anna@Terumo-Demo.example")

    assert created.status_code == 200, created.text
    assert (created.json()["role"], created.json()["email"]) == (
        "SUPPLIER",
        "anna@terumo-demo.example",
    )
    me = client.get("/api/v1/auth/me", headers=_bearer(_login(client, "anna@terumo-demo.example")))
    assert me.json()["role"] == "SUPPLIER"


def test_a_short_password_or_a_taken_email_is_refused(
    client: TestClient, operator: dict[str, str]
) -> None:
    bd = _org(client, operator, "org_bd")["id"]
    short = client.post(
        f"{ADMIN}/users",
        json={"org_id": bd, "email": "x@bd.example", "display_name": "X", "password": "12345"},
        headers=operator,
    )
    assert short.status_code == 422

    taken = _create(client, operator, bd, "catalog@bd-demo.example")
    assert taken.status_code == 409


def test_a_deactivated_user_is_signed_out_at_once_and_can_come_back(
    client: TestClient, operator: dict[str, str]
) -> None:
    user = _create(client, operator, _org(client, operator, "org_bd")["id"], "b@bd.example").json()
    session = _bearer(_login(client, "b@bd.example"))

    client.post(f"{ADMIN}/users/{user['id']}/deactivate", headers=operator).raise_for_status()

    assert client.get("/api/v1/supplier/requests", headers=session).status_code == 401
    assert _login(client, "b@bd.example").status_code == 401
    client.post(f"{ADMIN}/users/{user['id']}/reactivate", headers=operator).raise_for_status()
    assert _login(client, "b@bd.example").status_code == 200


def test_a_password_reset_ends_every_session(client: TestClient, operator: dict[str, str]) -> None:
    user = _create(client, operator, _org(client, operator, "org_bd")["id"], "c@bd.example").json()
    session = _bearer(_login(client, "c@bd.example"))

    reset = client.post(
        f"{ADMIN}/users/{user['id']}/password", json={"password": "neues-pw"}, headers=operator
    )

    assert reset.status_code == 204
    assert client.get("/api/v1/supplier/requests", headers=session).status_code == 401
    assert _login(client, "c@bd.example").status_code == 401
    assert _login(client, "c@bd.example", "neues-pw").status_code == 200
    # The audit names the user, never the password.
    audit = client.get(
        f"{ADMIN}/audit", params={"action": "PASSWORD_RESET"}, headers=operator
    ).json()
    assert [(row["target_id"], row["data"]) for row in audit] == [("c@bd.example", {})]


def test_an_operator_cannot_deactivate_their_own_account(
    client: TestClient, operator: dict[str, str]
) -> None:
    users = client.get(f"{ADMIN}/users", headers=operator).json()
    own = next(user for user in users if user["email"] == "ops@sanovio-demo.example")

    response = client.post(f"{ADMIN}/users/{own['id']}/deactivate", headers=operator)

    assert response.status_code == 409
    assert response.json()["code"] == "OWN_ACCOUNT"


def test_a_blocked_purchaser_is_stopped_without_touching_the_hospital(
    client: TestClient, operator: dict[str, str], buyer: dict[str, str]
) -> None:
    tenants = client.get(f"{ADMIN}/tenants", headers=operator).json()
    ksp = next(tenant for tenant in tenants if tenant["code"] == "ten_ksp")
    url = f"{ADMIN}/tenants/{ksp['id']}/principals"
    [principal] = client.get(url, headers=operator).json()
    assert principal["subject_id"].startswith("sub_") and not principal["is_blocked"]

    blocked = client.post(f"{url}/{principal['subject_id']}/block", headers=operator)

    assert blocked.status_code == 204
    assert client.get("/api/v1/suppliers", headers=buyer).status_code == 401
    [after] = client.get(url, headers=operator).json()
    assert after["is_blocked"]
    unblocked = client.post(f"{url}/{principal['subject_id']}/unblock", headers=operator)
    assert unblocked.status_code == 204
