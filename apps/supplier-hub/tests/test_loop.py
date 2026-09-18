"""The whole loop through the API (§19): scenario 1 to a proposal, scenario 3 to a manual
decision. The purchaser, the supplier and the job queue take turns exactly as in production."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from hub_fixtures import (
    ART_03_LINKED,
    fetch,
    login,
    open_assessment,
    requirement,
    run_jobs,
    send_questions,
    supplier_answers,
)
from supplier_hub.models import Answer, ItemFact, User

# CSV #6 after the current product was marked, but still without the wall type (§21, scenario 3).
ART_06: dict[str, Any] = {
    "mdr_class": {"type": "enum", "value": "IIA"},
    "sterile": {"type": "bool", "value": True},
    "single_use": {"type": "bool", "value": True},
    "latex_free": {"type": "bool", "value": True},
    "dehp_free": {"type": "bool", "value": True},
    "standards": {"type": "list", "value": ["ISO 7864"]},
    "gauge": {"type": "number", "value": 21, "unit": "G"},
    "outer_diameter_mm": {"type": "number", "value": 0.8, "unit": "mm"},
    "length_mm": {"type": "number", "value": 40, "unit": "mm"},
    "bevel": {"type": "enum", "value": "LONG"},
    "purpose": {"type": "enum", "value": "INJECTION"},
    "filter_um": {"type": "number", "value": 0, "unit": "µm"},
    "safety_mechanism": {"type": "bool", "value": False},
    "connector": {"type": "enum", "value": "LUER_LOCK"},
    "iso_7864_compliant": {"type": "bool", "value": True},
}


def _open(
    client: TestClient,
    headers: dict[str, str],
    session: Session,
    article_no: str,
    attributes: dict[str, Any],
    template: str,
) -> Any:
    created = open_assessment(
        client, headers, session, article_no, attributes, template_code=template
    )
    run_jobs(client)
    return fetch(client, headers, created["id"])


def _answer_purchaser_questions(
    client: TestClient,
    headers: dict[str, str],
    detail: Any,
    attributes: dict[str, Any],
    answers: dict[str, Any],
    template: str,
) -> Any:
    """What the client does: answer at the node, then forward the node's new requirement."""
    asked = {
        q["attribute_key"]: q["id"]
        for q in detail["questions"]
        if q["addressee"] == "PURCHASER" and q["status"] == "DRAFT"
    }
    for key, question_id in asked.items():
        if key not in answers:
            # Nothing to add from the hospital's side: the purchaser withdraws the question.
            client.patch(
                f"/api/v1/assessments/{detail['id']}/questions/{question_id}",
                json={
                    "version": fetch(client, headers, detail["id"])["version"],
                    "withdraw": True,
                },
                headers=headers,
            ).raise_for_status()
    answered = [asked[key] for key in answers if key in asked]
    if answered:
        new = requirement(
            attributes | answers, template_code=template, answered_question_ids=answered
        )
        response = client.post(
            f"/api/v1/assessments/{detail['id']}/requirements",
            json={"requirement": new, "version": fetch(client, headers, detail["id"])["version"]},
            headers=headers,
        )
        assert response.status_code == 200, response.text
    return fetch(client, headers, detail["id"])


def test_scenario_1_plastipak_from_questions_to_a_proposal(
    client: TestClient, buyer: dict[str, str], bd: dict[str, str], session: Session
) -> None:
    template = "syringe_single_use"
    round_one = _open(client, buyer, session, "300912", ART_03_LINKED, template)
    assert round_one["status"] == "NEEDS_QUESTION_REVIEW"

    # The purchaser: no special scale on their current product either.
    reviewed = _answer_purchaser_questions(
        client,
        buyer,
        round_one,
        ART_03_LINKED,
        {"special_scale": {"type": "text", "value": "keine"}},
        template,
    )
    assert reviewed["status"] == "NEEDS_QUESTION_REVIEW"
    assert send_questions(client, buyer, round_one["id"])["status"] == "AWAITING_ANSWERS"

    # BD sees its product, the questions and an alias — nothing about the hospital's article.
    inbox = client.get("/api/v1/supplier/requests", headers=bd).json()
    assert [r["hospital"] for r in inbox] == ["Hospital H-7F3A"]
    raw = client.get(f"/api/v1/supplier/requests/{round_one['id']}", headers=bd).text
    for secret in ("Kantonsspital", "ar_5MZQ4K7T2V9C", "TWO_PART", "ten_ksp", "requirement"):
        assert secret not in raw

    typed = {key: ART_03_LINKED[key] for key in ART_03_LINKED} | {
        "special_scale": {"type": "text", "value": "keine"},
    }
    supplier_answers(
        client,
        bd,
        round_one["id"],
        typed,
        comments={"dehp_free": "Zylinder und Stopfen enthalten kein DEHP."},
    )
    run_jobs(client)
    final = fetch(client, buyer, round_one["id"])

    assert final["status"] == "PROPOSED_RESOLUTION"
    assert final["proposed_verdict"] == "EQUIVALENT_WITH_DEVIATIONS"
    second = final["rounds"][-1]
    statuses = {j["attribute_key"]: j["status"] for j in second["attribute_judgments"]}
    assert statuses["design"] == "MISMATCH"
    assert statuses["graduation_step_ml"] == "ACCEPTABLE_DEVIATION"
    assert statuses["mdr_class"] == statuses["dehp_free"] == "MATCH"
    assert [e["type"] for e in final["events"]].count("ROUND_COMPLETED") == 2

    # The answers became family facts that remember where they came from.
    mdr = session.scalar(select(ItemFact).where(ItemFact.attribute_key == "mdr_class"))
    assert mdr is not None
    assert (mdr.source, mdr.family_id is not None, mdr.answer_id is not None) == (
        "SUPPLIER_ANSWER",
        True,
        True,
    )
    dehp = session.scalar(
        select(Answer).where(Answer.comment == "Zylinder und Stopfen enthalten kein DEHP.")
    )
    assert dehp is not None and dehp.extraction_status == "EXTRACTED"


def test_scenario_3_microlance_ends_in_a_manual_decision(
    client: TestClient, buyer: dict[str, str], bd: dict[str, str], session: Session
) -> None:
    template = "hypodermic_needle"
    round_one = _open(client, buyer, session, "304432", ART_06, template)
    purchaser_keys = {
        q["attribute_key"] for q in round_one["questions"] if q["addressee"] == "PURCHASER"
    }
    assert "wall_type" in purchaser_keys

    # The purchaser answers the wall type at the node: regular.
    _answer_purchaser_questions(
        client,
        buyer,
        round_one,
        ART_06,
        {"wall_type": {"type": "enum", "value": "REGULAR"}},
        template,
    )
    send_questions(client, buyer, round_one["id"])

    typed = dict(ART_06)
    supplier_answers(client, bd, round_one["id"], typed, cannot_provide=("inner_diameter_mm",))
    run_jobs(client)
    final = fetch(client, buyer, round_one["id"])

    assert final["status"] == "NEEDS_MANUAL_DECISION"
    assert final["manual_reason"] == "BLOCKING_UNAVAILABLE"
    last = {j["attribute_key"]: j for j in final["rounds"][-1]["attribute_judgments"]}
    assert last["wall_type"]["status"] == "MISMATCH"  # thin against regular
    assert last["inner_diameter_mm"]["status"] == "UNAVAILABLE"


def test_sending_is_refused_while_the_purchaser_owes_answers(
    client: TestClient, buyer: dict[str, str], session: Session
) -> None:
    round_one = _open(client, buyer, session, "304432", ART_06, "hypodermic_needle")

    response = client.post(
        f"/api/v1/assessments/{round_one['id']}/send-questions",
        json={"version": round_one["version"]},
        headers=buyer,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "OPEN_PURCHASER_QUESTIONS"


def test_a_half_answered_batch_is_refused(
    client: TestClient, buyer: dict[str, str], bd: dict[str, str], session: Session
) -> None:
    round_one = _open(client, buyer, session, "300912", ART_03_LINKED, "syringe_single_use")
    _answer_purchaser_questions(
        client,
        buyer,
        round_one,
        ART_03_LINKED,
        {"special_scale": {"type": "text", "value": "keine"}},
        "syringe_single_use",
    )
    send_questions(client, buyer, round_one["id"])

    response = client.post(f"/api/v1/supplier/requests/{round_one['id']}/submit", headers=bd)

    assert response.status_code == 422
    assert "unanswered questions" in response.json()["detail"]


def test_a_stale_version_is_refused(
    client: TestClient, buyer: dict[str, str], session: Session
) -> None:
    round_one = _open(client, buyer, session, "300912", ART_03_LINKED, "syringe_single_use")

    response = client.post(
        f"/api/v1/assessments/{round_one['id']}/send-questions",
        json={"version": round_one["version"] - 1},
        headers=buyer,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "VERSION_CONFLICT"


def test_another_supplier_cannot_see_the_request(
    client: TestClient, buyer: dict[str, str], session: Session
) -> None:
    round_one = _open(client, buyer, session, "300912", ART_03_LINKED, "syringe_single_use")
    braun = session.scalar(select(User).where(User.email == "katalog@bbraun-demo.example"))
    assert braun is not None

    response = client.get(
        f"/api/v1/supplier/requests/{round_one['id']}", headers=login(client, braun)
    )

    assert response.status_code == 404
