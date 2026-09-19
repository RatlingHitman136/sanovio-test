"""The development supplier simulator (§21): operators only, dev only, datasheets never shown."""

import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from hub_fixtures import (
    ART_03_WITH_SCALE,
    FakeClock,
    Orgs,
    fetch,
    login,
    open_assessment,
    purchaser_headers,
    run_jobs,
    send_questions,
)
from llm_client import FakeLLM
from supplier_hub.core.settings import HubSettings
from supplier_hub.llm import extract_answer, judge, normalize_item, propose_attribute
from supplier_hub.llm.fakes import fake_llm
from supplier_hub.llm.simulate_supplier import PURPOSE as SIMULATE
from supplier_hub.main import create_app
from supplier_hub.models import Answer, Question, User
from supplier_hub.models.assessments import ExtractionStatus
from supplier_hub.models.identity import UserRole

PURPOSES = (
    normalize_item.PURPOSE,
    judge.PURPOSE,
    extract_answer.PURPOSE,
    propose_attribute.PURPOSE,
)


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


def test_an_answer_in_words_is_kept_for_extraction(
    settings: HubSettings, clock: FakeClock, orgs: Orgs, session: Session, seeded: Any
) -> None:
    """Found in the real-key run: Haiku wrote "normalwandig" instead of REGULAR, and the
    simulator turned an answered question into "cannot provide"."""
    base = fake_llm()
    seen: list[Any] = []

    def in_words(request: Any) -> Any:
        seen.append(json.loads(request.user.split("<data>")[1].split("</data>")[0]))
        output = base.parse(request).output
        assert output is not None
        for answer in output.answers:
            if answer.value == "IIA":
                answer.value = "Klasse IIa"
        return output

    llm = FakeLLM({purpose: _delegate(base) for purpose in PURPOSES} | {SIMULATE: in_words})
    with TestClient(create_app(settings, clock=clock, llm=llm)) as client:
        buyer = purchaser_headers(client, orgs, clock)
        created = _awaiting(client, buyer, session)
        operator = login(client, _operator_user(session))
        assert _simulate(client, operator, created["id"]).status_code == 200

    mdr = next(q for q in seen[0]["questions"] if q["attribute_key"] == "mdr_class")
    assert "IIA" in mdr["expected_answer"]["options"]
    answer = session.scalar(
        select(Answer).join(Answer.question).where(Question.attribute_key == "mdr_class")
    )
    assert answer is not None
    assert (answer.cannot_provide, answer.comment, answer.value) == (False, "Klasse IIa", None)


def _delegate(base: FakeLLM) -> Any:
    def answer(request: Any) -> Any:
        return base.parse(request).output

    return answer


def _operator_user(session: Session) -> User:
    user = session.scalar(select(User).where(User.role == UserRole.OPERATOR))
    assert user is not None
    return user
