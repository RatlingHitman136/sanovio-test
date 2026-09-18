"""The development supplier simulator (§21): operators only, dev only, datasheets never shown."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from hub_fixtures import (
    ART_03_WITH_SCALE,
    FakeClock,
    fetch,
    login,
    open_assessment,
    run_jobs,
    send_questions,
)
from supplier_hub.core.settings import HubSettings
from supplier_hub.main import create_app
from supplier_hub.models import Answer, User
from supplier_hub.models.assessments import ExtractionStatus
from supplier_hub.models.identity import UserRole


@pytest.fixture
def operator(client: TestClient, session: Session, buyer: dict[str, str]) -> dict[str, str]:
    user = session.scalar(select(User).where(User.role == UserRole.OPERATOR))
    assert user is not None
    return login(client, user)


def _awaiting(client: TestClient, buyer: dict[str, str], session: Session) -> Any:
    created = open_assessment(client, buyer, session, "300912", ART_03_WITH_SCALE)
    run_jobs(client)
    assert send_questions(client, buyer, created["id"])["status"] == "AWAITING_ANSWERS"
    return created


def _simulate(client: TestClient, headers: dict[str, str], assessment_id: str) -> Any:
    return client.post(
        f"/api/v1/dev/assessments/{assessment_id}/simulate-supplier", headers=headers
    )


def test_the_simulator_answers_for_bd_and_the_loop_ends_in_a_proposal(
    client: TestClient, buyer: dict[str, str], operator: dict[str, str], session: Session
) -> None:
    created = _awaiting(client, buyer, session)

    response = _simulate(client, operator, created["id"])
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ASSESSING"}
    assert "Zylinder" not in response.text

    run_jobs(client)
    detail = fetch(client, buyer, created["id"])
    assert detail["status"] == "PROPOSED_RESOLUTION"
    assert detail["rounds"][-1]["rule_verdict"] == "EQUIVALENT_WITH_DEVIATIONS"
    # The DEHP answer came as free text and went through extraction.
    statuses = {a.extraction_status for a in session.scalars(select(Answer))}
    assert ExtractionStatus.EXTRACTED in statuses


def test_only_an_operator_may_simulate(
    client: TestClient,
    buyer: dict[str, str],
    bd: dict[str, str],
    session: Session,
) -> None:
    created = _awaiting(client, buyer, session)
    assert _simulate(client, bd, created["id"]).status_code == 403
    assert _simulate(client, buyer, created["id"]).status_code in (401, 403)


def test_nothing_to_simulate_without_sent_questions(
    client: TestClient, buyer: dict[str, str], operator: dict[str, str], session: Session
) -> None:
    created = open_assessment(client, buyer, session, "300912", ART_03_WITH_SCALE)
    run_jobs(client)
    response = _simulate(client, operator, created["id"])
    assert response.status_code == 409
    assert response.json()["code"] == "NOT_AWAITING_ANSWERS"


def test_the_simulator_does_not_exist_outside_dev(
    settings: HubSettings, clock: FakeClock, engine: Engine
) -> None:
    production = settings.model_copy(update={"app_env": "prod"})
    with TestClient(create_app(production, clock=clock)) as client:
        response = _simulate(client, {}, str(uuid.uuid4()))
    assert response.status_code == 404
