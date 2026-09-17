import json

from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from equivalence_core.exchange.assertion import ASSERTION_TYP
from equivalence_core.exchange.jws import verify
from equivalence_core.exchange.keys import load_private_key
from hospital_node.core.settings import NodeSettings
from hospital_node.main import create_app
from hospital_node.models import User
from node_fixtures import FakeClock, article, login


def test_a_requirement_is_returned_and_logged(
    client: TestClient, anna: User, admin: User, session: Session
) -> None:
    headers = login(client, anna)
    syringe = article(session, "3")

    response = client.post(
        f"/api/v1/articles/{syringe.id}/requirement",
        json={"answered_question_ids": ["q_9"]},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["requirement"]["template_code"] == "syringe_single_use"
    assert body["requirement"]["answered_question_ids"] == ["q_9"]
    assert body["requirement"]["article_ref"] == syringe.article_ref
    assert "name" not in json.dumps(body["requirement"])

    log = client.get("/api/v1/egress", headers=login(client, admin)).json()
    (entry,) = log["entries"]
    assert entry["id"] == body["egress_id"]
    assert entry["kind"] == "REQUIREMENT"
    assert entry["user"] == "Anna Meier"
    assert entry["content"] == body["requirement"]
    assert log["issued_per_user"] == {"Anna Meier": 1}


def test_an_assertion_is_signed_and_only_its_claims_are_logged(
    client: TestClient, anna: User, admin: User, settings: NodeSettings, clock: FakeClock
) -> None:
    response = client.post("/api/v1/hub-assertions", headers=login(client, anna))

    assert response.status_code == 200
    token = response.json()["assertion"]
    public = load_private_key(settings.node_signing_key_file).public_key()
    claims = verify(
        token,
        typ=ASSERTION_TYP,
        audience="sanovio-hub",
        key_lookup=lambda issuer, kid: public,
        now=clock(),
    )

    (entry,) = client.get("/api/v1/egress", headers=login(client, admin)).json()["entries"]
    assert entry["kind"] == "ASSERTION"
    assert entry["jti"] == claims["jti"]
    assert entry["article_id"] is None
    assert token not in json.dumps(entry)
    assert entry["content"]["sub"] == anna.hub_subject_id


def test_over_the_limit_the_node_answers_429(
    settings: NodeSettings,
    engine: Engine,
    clock: FakeClock,
    anna: User,
    admin: User,
    session: Session,
) -> None:
    limited = settings.model_copy(update={"requirement_rate_limit_per_hour": 3})
    syringe_id = article(session, "3").id

    with TestClient(create_app(limited, clock=clock)) as client:
        headers = login(client, anna)
        url = f"/api/v1/articles/{syringe_id}/requirement"
        codes = [client.post(url, json={}, headers=headers).status_code for _ in range(4)]
        refused = client.post(url, json={}, headers=headers)
        log = client.get("/api/v1/egress", headers=login(client, admin)).json()

    assert codes == [200, 200, 200, 429]
    assert refused.status_code == 429
    assert int(refused.headers["Retry-After"]) > 0
    alerts = [e["alert"] for e in log["entries"] if e["alert"]]
    assert alerts.count("RATE_EXCEEDED") == 2
    assert alerts.count("RATE_80_PERCENT") == 1
    assert log["issued_per_user"] == {"Anna Meier": 3}


def test_egress_is_for_admins_only(client: TestClient, anna: User) -> None:
    assert client.get("/api/v1/egress", headers=login(client, anna)).status_code == 403


def test_requirements_need_the_purchaser_role(
    client: TestClient, admin: User, session: Session
) -> None:
    response = client.post(
        f"/api/v1/articles/{article(session, '3').id}/requirement",
        json={},
        headers=login(client, admin),
    )

    assert response.status_code == 403
