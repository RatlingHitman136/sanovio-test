from fastapi.testclient import TestClient

from equivalence_core.exchange.keys import jwk_thumbprint
from hub_fixtures import Orgs, login, node_key, register_node_key
from supplier_hub.models.identity import UserRole

TENANT = {
    "code": "ten_ksp",
    "name": "Demo Kantonsspital",
    "supplier_facing_alias": "Hospital H-7F3A",
    "country": "CH",
}


def _operator(client: TestClient, orgs: Orgs) -> dict[str, str]:
    user = orgs.user(orgs.operator(), "ops@sanovio-demo.example", UserRole.OPERATOR)
    return login(client, user)


def test_a_tenant_is_created_and_listed(client: TestClient, orgs: Orgs) -> None:
    headers = _operator(client, orgs)

    created = client.post("/api/v1/admin/tenants", json=TENANT, headers=headers)
    listed = client.get("/api/v1/admin/tenants", headers=headers).json()

    assert created.status_code == 200
    assert created.json()["supplier_facing_alias"] == "Hospital H-7F3A"
    assert [tenant["code"] for tenant in listed] == ["ten_ksp"]


def test_the_same_alias_or_code_is_refused(client: TestClient, orgs: Orgs) -> None:
    headers = _operator(client, orgs)
    client.post("/api/v1/admin/tenants", json=TENANT, headers=headers)

    again = client.post("/api/v1/admin/tenants", json=TENANT, headers=headers)

    assert again.status_code == 409
    assert again.json()["code"] == "TENANT_EXISTS"


def test_a_key_is_registered_with_its_fingerprint(client: TestClient, orgs: Orgs) -> None:
    headers = _operator(client, orgs)
    tenant = client.post("/api/v1/admin/tenants", json=TENANT, headers=headers).json()
    key = node_key()

    registered = register_node_key(client, headers, tenant["id"], key)

    assert registered["kid"] == "ksp-2026-09"
    assert registered["fingerprint"] == jwk_thumbprint(key.jwk())
    assert registered["revoked_at"] is None
    listed = client.get(
        f"/api/v1/admin/tenants/{tenant['id']}/signing-keys", headers=headers
    ).json()
    assert [entry["kid"] for entry in listed] == ["ksp-2026-09"]


def test_a_private_key_is_refused(client: TestClient, orgs: Orgs) -> None:
    headers = _operator(client, orgs)
    tenant = client.post("/api/v1/admin/tenants", json=TENANT, headers=headers).json()
    key = node_key()

    response = client.post(
        f"/api/v1/admin/tenants/{tenant['id']}/signing-keys",
        json={"public_jwk": key.jwk() | {"d": "private-material"}},
        headers=headers,
    )

    assert response.status_code == 422


def test_the_same_kid_cannot_be_registered_twice(client: TestClient, orgs: Orgs) -> None:
    headers = _operator(client, orgs)
    tenant = client.post("/api/v1/admin/tenants", json=TENANT, headers=headers).json()
    key = node_key()
    register_node_key(client, headers, tenant["id"], key)

    response = client.post(
        f"/api/v1/admin/tenants/{tenant['id']}/signing-keys",
        json={"public_jwk": key.jwk()},
        headers=headers,
    )

    assert response.status_code == 409


def test_an_unknown_tenant_is_404(client: TestClient, orgs: Orgs) -> None:
    headers = _operator(client, orgs)

    response = client.get(
        "/api/v1/admin/tenants/00000000-0000-7000-8000-000000000000/signing-keys",
        headers=headers,
    )

    assert response.status_code == 404
