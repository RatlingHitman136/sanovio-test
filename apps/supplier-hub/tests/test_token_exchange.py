"""The only door hospital staff come through (ARCHITECTURE §17)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from equivalence_core.exchange.assertion import ASSERTION_TYP
from hub_fixtures import FakeClock, NodeKey, Orgs, login, node_key, register_node_key
from supplier_hub.models import ApiToken, HospitalPrincipal
from supplier_hub.models.identity import UserRole

SUBJECT = "sub_7QF2M4XK9P3TZC8W1N6R"
TENANT = {
    "code": "ten_ksp",
    "name": "Demo Kantonsspital",
    "supplier_facing_alias": "Hospital H-7F3A",
}


@pytest.fixture
def operator(client: TestClient, orgs: Orgs) -> dict[str, str]:
    return login(client, orgs.user(orgs.operator(), "ops@sanovio-demo.example", UserRole.OPERATOR))


@pytest.fixture
def tenant(client: TestClient, operator: dict[str, str]) -> dict[str, Any]:
    created = client.post("/api/v1/admin/tenants", json=TENANT, headers=operator)
    assert created.status_code == 200, created.text
    body: dict[str, Any] = created.json()
    return body


@pytest.fixture
def key(client: TestClient, operator: dict[str, str], tenant: dict[str, Any]) -> NodeKey:
    registered = node_key()
    register_node_key(client, operator, tenant["id"], registered)
    return registered


def _exchange(client: TestClient, assertion: str) -> Any:
    return client.post("/api/v1/auth/token-exchange", json={"assertion": assertion})


def test_a_node_assertion_becomes_a_hub_token(
    client: TestClient, key: NodeKey, clock: FakeClock, session: Session
) -> None:
    response = _exchange(client, key.assertion(clock()))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tenant_alias"] == "Hospital H-7F3A"
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert me == {
        "kind": "purchaser",
        "display_name": SUBJECT,
        "organization": "Hospital H-7F3A",
        "role": None,
        "subject_id": SUBJECT,
    }
    principal = session.scalar(select(HospitalPrincipal))
    assert principal is not None and principal.subject_id == SUBJECT


def test_the_token_lives_thirty_minutes(client: TestClient, key: NodeKey, clock: FakeClock) -> None:
    body = _exchange(client, key.assertion(clock())).json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}

    clock.advance(minutes=29)
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    clock.advance(minutes=2)
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_an_assertion_is_single_use(client: TestClient, key: NodeKey, clock: FakeClock) -> None:
    assertion = key.assertion(clock(), jti="asr_01J9A")

    first = _exchange(client, assertion)
    replay = _exchange(client, assertion)

    assert first.status_code == 200
    assert replay.status_code == 401


def test_every_refusal_says_the_same_thing(
    client: TestClient, key: NodeKey, clock: FakeClock
) -> None:
    refused = _exchange(client, key.assertion(clock(), audience="somewhere-else"))

    assert refused.status_code == 401
    assert refused.json() == {"detail": "the assertion was not accepted"}
    assert refused.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "broken",
    [
        pytest.param({"audience": "another-hub"}, id="wrong audience"),
        pytest.param({"typ": "jwt"}, id="wrong typ"),
        pytest.param({"scope": "operator"}, id="wrong scope"),
        pytest.param({"lifetime_s": 3600}, id="too long"),
        pytest.param({"issuer": "ten_spital2"}, id="another tenant"),
        pytest.param({"issuer": "nobody"}, id="unknown tenant"),
    ],
)
def test_assertions_that_do_not_hold_up(
    client: TestClient, key: NodeKey, clock: FakeClock, broken: dict[str, Any]
) -> None:
    assert _exchange(client, key.assertion(clock(), **broken)).status_code == 401


def test_an_expired_or_future_assertion_is_refused(
    client: TestClient, key: NodeKey, clock: FakeClock
) -> None:
    expired = key.assertion(clock())
    clock.advance(minutes=6)
    assert _exchange(client, expired).status_code == 401

    from_the_future = key.assertion(clock(), lifetime_s=300)
    clock.advance(minutes=-10)
    assert _exchange(client, from_the_future).status_code == 401


def test_a_key_of_another_tenant_is_not_accepted(
    client: TestClient, operator: dict[str, str], tenant: dict[str, Any], clock: FakeClock
) -> None:
    other = client.post(
        "/api/v1/admin/tenants",
        json={
            "code": "ten_spital2",
            "name": "Demo Spital Zwei",
            "supplier_facing_alias": "Hospital H-2C91",
        },
        headers=operator,
    ).json()
    theirs = node_key(tenant_code="ten_spital2", kid="sp2-2026-09")
    register_node_key(client, operator, other["id"], theirs)

    # Their key, but our tenant in `iss`: the kid must belong to the issuer that claims it.
    assert _exchange(client, theirs.assertion(clock(), issuer="ten_ksp")).status_code == 401


def test_an_unregistered_key_is_refused(
    client: TestClient, tenant: dict[str, Any], clock: FakeClock
) -> None:
    stranger = node_key()

    assert _exchange(client, stranger.assertion(clock())).status_code == 401


def test_revoking_a_key_ends_the_sessions_it_created(
    client: TestClient,
    operator: dict[str, str],
    tenant: dict[str, Any],
    key: NodeKey,
    clock: FakeClock,
) -> None:
    body = _exchange(client, key.assertion(clock())).json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

    revoked = client.post(
        f"/api/v1/admin/tenants/{tenant['id']}/signing-keys/{key.kid}/revoke", headers=operator
    )

    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert _exchange(client, key.assertion(clock())).status_code == 401


def test_an_inactive_tenant_and_a_blocked_principal_are_refused(
    client: TestClient, key: NodeKey, clock: FakeClock, session: Session
) -> None:
    assert _exchange(client, key.assertion(clock())).status_code == 200
    principal = session.scalar(select(HospitalPrincipal))
    assert principal is not None
    principal.is_blocked = True
    session.commit()

    assert _exchange(client, key.assertion(clock())).status_code == 401

    principal.is_blocked = False
    principal.tenant.is_active = False
    session.commit()
    assert _exchange(client, key.assertion(clock())).status_code == 401


def test_a_purchaser_token_is_not_a_user_token(
    client: TestClient, key: NodeKey, clock: FakeClock
) -> None:
    body = _exchange(client, key.assertion(clock())).json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}

    # Operator endpoints need a hub login, which a purchaser never has.
    assert client.get("/api/v1/admin/tenants", headers=headers).status_code == 401


def test_the_token_records_which_key_signed_it(
    client: TestClient, key: NodeKey, clock: FakeClock, session: Session
) -> None:
    _exchange(client, key.assertion(clock(), jti="asr_recorded"))

    token = session.scalar(select(ApiToken).where(ApiToken.principal_id.is_not(None)))
    assert token is not None
    assert (token.kid, token.assertion_jti) == (key.kid, "asr_recorded")
    assert token.user_id is None


def test_the_typ_must_be_the_assertion_type(
    client: TestClient, key: NodeKey, clock: FakeClock
) -> None:
    assert ASSERTION_TYP == "assertion+jwt"
    assert _exchange(client, key.assertion(clock(), typ="at+jwt")).status_code == 401
