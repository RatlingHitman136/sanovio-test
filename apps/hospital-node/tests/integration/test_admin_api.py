from fastapi.testclient import TestClient

from equivalence_core.exchange.keys import jwk_thumbprint, load_private_key, public_jwk
from hospital_node.core.settings import NodeSettings
from hospital_node.models import User
from node_fixtures import login


def test_signing_key_shows_only_the_public_half(
    client: TestClient, admin: User, settings: NodeSettings
) -> None:
    response = client.get("/api/v1/admin/signing-key", headers=login(client, admin))

    assert response.status_code == 200
    body = response.json()
    expected = public_jwk(load_private_key(settings.node_signing_key_file), "test-kid")
    assert body == {
        "kid": "test-kid",
        "public_jwk": expected,
        "fingerprint": jwk_thumbprint(expected),
    }
    assert "d" not in body["public_jwk"]


def test_purchasers_cannot_read_admin_endpoints(client: TestClient, anna: User) -> None:
    response = client.get("/api/v1/admin/signing-key", headers=login(client, anna))

    assert response.status_code == 403
