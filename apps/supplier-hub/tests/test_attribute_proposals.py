"""A new attribute from a purchaser's free question, shared before it counts (§7.2; scenario 7)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
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
    supplier_answers,
    variant,
)
from llm_client import FakeLLM
from supplier_hub.core.settings import HubSettings
from supplier_hub.llm import judge, propose_attribute
from supplier_hub.llm.fakes import fake_llm
from supplier_hub.main import create_app
from supplier_hub.models import AttributeDefinition, AttributeProposal, User
from supplier_hub.models.identity import UserRole
from supplier_hub.models.registry import AttributeStatus
from supplier_hub.services.seed import SeedReport

CONCERN = "Ist ein abziehbares Dokumentationsetikett beigelegt?"
LABEL_QUESTION = "Liegt der Packung ein abziehbares Dokumentationsetikett bei?"


@pytest.fixture
def operator(client: TestClient, session: Session, buyer: dict[str, str]) -> dict[str, str]:
    user = session.scalar(select(User).where(User.role == UserRole.OPERATOR))
    assert user is not None
    return login(client, user)


def _in_review(client: TestClient, buyer: dict[str, str], session: Session) -> Any:
    """Plastipak's round 1 with the scale already known at the node: only BD owes answers."""
    created = open_assessment(client, buyer, session, "300912", ART_03_WITH_SCALE)
    run_jobs(client)
    detail = fetch(client, buyer, created["id"])
    assert detail["status"] == "NEEDS_QUESTION_REVIEW"
    assert {q["addressee"] for q in detail["questions"]} == {"SUPPLIER"}
    return detail


def _ask(
    client: TestClient, buyer: dict[str, str], assessment_id: str, text: str, **body: Any
) -> Any:
    return client.post(
        f"/api/v1/assessments/{assessment_id}/questions",
        json={
            "version": fetch(client, buyer, assessment_id)["version"],
            "addressee": "SUPPLIER",
            "attribute_key": None,
            "text": text,
        }
        | body,
        headers=buyer,
    )


def _question(detail: Any, text: str) -> Any:
    return next(q for q in detail["questions"] if q["text"] == text)


def _proposals(client: TestClient, operator: dict[str, str], **params: str) -> Any:
    response = client.get("/api/v1/admin/attribute-proposals", params=params, headers=operator)
    assert response.status_code == 200, response.text
    return response.json()


def _registry_row(session: Session, key: str) -> AttributeDefinition:
    session.expire_all()
    row = session.scalar(select(AttributeDefinition).where(AttributeDefinition.key == key))
    assert row is not None, key
    return row


def test_scenario_7_a_label_question_becomes_a_shared_then_approved_attribute(
    client: TestClient,
    buyer: dict[str, str],
    bd: dict[str, str],
    operator: dict[str, str],
    orgs: Orgs,
    clock: FakeClock,
    session: Session,
) -> None:
    review = _in_review(client, buyer, session)
    assert _ask(client, buyer, review["id"], LABEL_QUESTION).status_code == 200

    # The proposal job has not run yet: the questions wait for it.
    version = fetch(client, buyer, review["id"])["version"]
    early = client.post(
        f"/api/v1/assessments/{review['id']}/send-questions",
        json={"version": version},
        headers=buyer,
    )
    assert early.status_code == 409
    assert early.json()["code"] == "ATTRIBUTE_PROPOSAL_PENDING"

    run_jobs(client)
    [proposal] = _proposals(client, operator)
    assert (proposal["result"], proposal["status"]) == ("NEW", "PENDING")
    assert proposal["proposal"]["key"] == "peel_off_label"

    # Sending makes it provisional and gives the question its key and typed shape.
    assert send_questions(client, buyer, review["id"])["status"] == "AWAITING_ANSWERS"
    asked = _question(fetch(client, buyer, review["id"]), LABEL_QUESTION)
    assert asked["attribute_key"] == "peel_off_label"
    assert asked["expected_answer"] == {"type": "bool"}
    assert _registry_row(session, "peel_off_label").status == AttributeStatus.PROVISIONAL

    # BD answers "yes" for the whole family, along with everything else it was asked.
    typed = ART_03_WITH_SCALE | {"peel_off_label": {"type": "bool", "value": True}}
    supplier_answers(client, bd, review["id"], typed)
    run_jobs(client)
    decided = fetch(client, buyer, review["id"])
    assert decided["status"] == "PROPOSED_RESOLUTION"
    # Information only: the provisional attribute is never judged.
    judged = {j["attribute_key"] for r in decided["rounds"] for j in r["attribute_judgments"]}
    assert "peel_off_label" not in judged

    # Another hospital sees it at once, as information, on a sibling variant of the family.
    other = purchaser_headers(client, orgs, clock, tenant_code="ten_spital2")
    sibling = variant(session, "309628")
    shown = client.get(f"/api/v1/catalog/variants/{sibling.id}/attributes", headers=other).json()
    assert shown["additional_information"]["peel_off_label"]["value"] == {
        "type": "bool",
        "value": True,
    }
    assert "peel_off_label" not in shown["attributes"]

    before = client.get("/api/v1/templates/syringe_single_use", headers=operator).json()
    clock.advance(minutes=5)
    approved = client.post(
        f"/api/v1/admin/attribute-proposals/{proposal['id']}/approve",
        json={"criticality": "major", "rule": "exact"},
        headers=operator,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert _registry_row(session, "peel_off_label").status == AttributeStatus.APPROVED

    # The served definition changes, so every node picks it up at its next sync (D52).
    after = client.get("/api/v1/templates/syringe_single_use", headers=operator).json()
    assert after["definition_hash"] != before["definition_hash"]
    assert after["updated_at"] != before["updated_at"]
    entry = next(a for a in after["definition"]["attributes"] if a["key"] == "peel_off_label")
    assert (entry["criticality"], entry["rule"]) == ("major", "exact")

    # Now it is a real attribute of the variant, no longer additional information.
    shown = client.get(f"/api/v1/catalog/variants/{sibling.id}/attributes", headers=other).json()
    assert shown["attributes"]["peel_off_label"]["value"] == {"type": "bool", "value": True}
    assert shown["additional_information"] == {}


def test_an_identifier_question_is_routed_without_an_attribute(
    client: TestClient, buyer: dict[str, str], operator: dict[str, str], session: Session
) -> None:
    review = _in_review(client, buyer, session)
    text = "Wie lautet die GTIN der Handelseinheit?"
    _ask(client, buyer, review["id"], text).raise_for_status()
    run_jobs(client)

    [proposal] = _proposals(client, operator)
    assert (proposal["result"], proposal["status"]) == ("IDENTIFIER", "ROUTED")
    asked = _question(fetch(client, buyer, review["id"]), text)
    assert asked["attribute_key"] == "gtin"
    assert asked["expected_answer"] == {"type": "identifier", "scheme": "GTIN"}
    assert _registry_row(session, "gtin").status == AttributeStatus.APPROVED


def test_a_question_about_a_known_attribute_takes_its_key(
    client: TestClient, buyer: dict[str, str], operator: dict[str, str], session: Session
) -> None:
    review = _in_review(client, buyer, session)
    label = _registry_row(session, "latex_free").labels["en"]
    text = f"Please confirm: {label}?"
    _ask(client, buyer, review["id"], text).raise_for_status()
    run_jobs(client)

    [proposal] = _proposals(client, operator, status="MATCHED")
    assert proposal["result"] == "EXISTING"
    assert _question(fetch(client, buyer, review["id"]), text)["attribute_key"] == "latex_free"


def test_a_withdrawn_free_question_creates_no_attribute(
    client: TestClient, buyer: dict[str, str], session: Session
) -> None:
    review = _in_review(client, buyer, session)
    _ask(client, buyer, review["id"], LABEL_QUESTION).raise_for_status()
    run_jobs(client)
    asked = _question(fetch(client, buyer, review["id"]), LABEL_QUESTION)
    client.patch(
        f"/api/v1/assessments/{review['id']}/questions/{asked['id']}",
        json={"version": fetch(client, buyer, review["id"])["version"], "withdraw": True},
        headers=buyer,
    ).raise_for_status()

    send_questions(client, buyer, review["id"])
    session.expire_all()
    key = select(AttributeDefinition).where(AttributeDefinition.key == "peel_off_label")
    assert session.scalar(key) is None


def test_a_free_question_goes_to_the_supplier_only(
    client: TestClient, buyer: dict[str, str], session: Session
) -> None:
    review = _in_review(client, buyer, session)
    response = _ask(client, buyer, review["id"], LABEL_QUESTION, addressee="PURCHASER")
    assert response.status_code == 422


def test_only_a_provisional_attribute_can_be_approved(
    client: TestClient, buyer: dict[str, str], operator: dict[str, str], session: Session
) -> None:
    review = _in_review(client, buyer, session)
    _ask(client, buyer, review["id"], LABEL_QUESTION).raise_for_status()
    run_jobs(client)
    [proposal] = _proposals(client, operator)

    response = client.post(
        f"/api/v1/admin/attribute-proposals/{proposal['id']}/approve",
        json={"criticality": "major", "rule": "exact"},
        headers=operator,
    )
    assert response.status_code == 409
    assert response.json()["code"] == "NOT_PROVISIONAL"


def test_purchasers_cannot_curate(
    client: TestClient, buyer: dict[str, str], session: Session
) -> None:
    response = client.get("/api/v1/admin/attribute-proposals", headers=buyer)
    assert response.status_code in (401, 403)


def test_a_judge_concern_becomes_a_supplier_question_with_a_proposal(
    settings: HubSettings, clock: FakeClock, orgs: Orgs, session: Session, seeded: SeedReport
) -> None:
    base = fake_llm()

    def concerned(request: Any) -> Any:
        output = base.parse(request).output
        assert output is not None
        return output.model_copy(update={"extra_concerns": [CONCERN]})

    purposes = (judge.PURPOSE, propose_attribute.PURPOSE)
    llm = FakeLLM(
        {purpose: concerned if purpose == judge.PURPOSE else _via(base) for purpose in purposes}
    )
    with TestClient(create_app(settings, clock=clock, llm=llm)) as client:
        buyer = purchaser_headers(client, orgs, clock)
        created = open_assessment(client, buyer, session, "300912", ART_03_WITH_SCALE)
        run_jobs(client)
        concern = _question(fetch(client, buyer, created["id"]), CONCERN)

    assert (concern["addressee"], concern["origin"]) == ("SUPPLIER", "LLM")
    # The proposal ran with the round's other jobs; the key follows when the questions are sent.
    assert concern["attribute_key"] is None
    [proposal] = session.scalars(select(AttributeProposal)).all()
    assert (proposal.result, proposal.status) == ("NEW", "PENDING")
    assert proposal.proposal is not None and proposal.proposal["key"] == "peel_off_label"


def _via(base: FakeLLM) -> Any:
    def answer(request: Any) -> Any:
        return base.parse(request).output

    return answer
