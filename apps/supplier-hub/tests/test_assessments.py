"""Creating assessments and their first round (§11, §19; scenarios 2 and 4)."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from hub_fixtures import (
    ART_03_LINKED,
    FakeClock,
    Orgs,
    fetch,
    login,
    open_assessment,
    purchaser_headers,
    requirement,
    run_jobs,
    variant,
)
from service_kit.security import PasswordHasher
from supplier_hub.core.settings import HubSettings
from supplier_hub.llm.fakes import fake_normalizer
from supplier_hub.models import Assessment, LlmCall, User
from supplier_hub.services.seed import SeedReport, seed


def _after_jobs(client: TestClient, headers: dict[str, str], assessment_id: str) -> Any:
    run_jobs(client)
    return fetch(client, headers, assessment_id)


def _judge_calls(session: Session) -> int:
    return len(session.scalars(select(LlmCall).where(LlmCall.purpose == "JUDGE")).all())


def test_a_new_assessment_is_accepted_and_queued(
    client: TestClient, buyer: dict[str, str], session: Session
) -> None:
    created = open_assessment(client, buyer, session, "300912")

    assert created["status"] == "ASSESSING"
    assert (created["article_no"], created["supplier"]) == ("300912", "BD")
    events = client.get(f"/api/v1/assessments/{created['id']}", headers=buyer).json()["events"]
    assert [event["type"] for event in events] == ["CREATED"]


def test_scenario_2_emerald_stops_in_round_one(
    client: TestClient, buyer: dict[str, str], session: Session
) -> None:
    created = open_assessment(client, buyer, session, "307736")

    detail = _after_jobs(client, buyer, created["id"])

    assert detail["status"] == "PROPOSED_RESOLUTION"
    assert detail["proposed_verdict"] == "NOT_EQUIVALENT"
    assert detail["questions"] == []
    (first,) = detail["rounds"]
    assert first["rule_verdict"] == "NOT_EQUIVALENT"
    connector = next(j for j in first["attribute_judgments"] if j["attribute_key"] == "connector")
    assert (connector["status"], connector["decided_by"]) == ("MISMATCH", "COMPARATOR")
    # A critical mismatch decides the round; the judge is not even asked.
    assert _judge_calls(session) == 0


def test_scenario_4_the_same_trade_item_needs_no_judge(
    client: TestClient, buyer: dict[str, str], session: Session
) -> None:
    hints = {"brand": "B. Braun", "manufacturer_article_no": "4606728V"}

    created = open_assessment(client, buyer, session, "4606728V", product_hints=hints)
    detail = _after_jobs(client, buyer, created["id"])

    assert detail["status"] == "PROPOSED_RESOLUTION"
    assert detail["proposed_verdict"] == "EQUIVALENT"
    (first,) = detail["rounds"]
    assert first["identifier_evidence"] == "SAME_TRADE_ITEM"
    assert first["attribute_judgments"] == []
    assert _judge_calls(session) == 0


def test_scenario_1_round_one_asks_bd_for_what_it_has_not_published(
    client: TestClient, buyer: dict[str, str], session: Session
) -> None:
    created = open_assessment(client, buyer, session, "300912")

    detail = _after_jobs(client, buyer, created["id"])

    assert detail["status"] == "NEEDS_QUESTION_REVIEW"
    (first,) = detail["rounds"]
    assert first["rule_verdict"] == "INSUFFICIENT_DATA"
    supplier_questions = {
        q["attribute_key"] for q in detail["questions"] if q["addressee"] == "SUPPLIER"
    }
    assert {"mdr_class", "dehp_free", "iso_7886_1_compliant"} <= supplier_questions
    assert all(q["status"] == "DRAFT" for q in detail["questions"])
    # Supplier-facing wording never names the hospital (§8.6).
    for question in detail["questions"]:
        assert "Kantonsspital" not in question["text"] and "H-7F3A" not in question["text"]
    # The round stores the core's judgment elements unchanged, with the supplier's scopes.
    design = next(j for j in first["attribute_judgments"] if j["attribute_key"] == "design")
    assert design["status"] == "MISMATCH"
    assert design["supplier"]["scope"] == "FAMILY"
    assert _judge_calls(session) == 1


def test_the_same_pair_cannot_be_opened_twice(
    client: TestClient, buyer: dict[str, str], session: Session
) -> None:
    first = open_assessment(client, buyer, session, "300912")

    again = client.post(
        "/api/v1/assessments",
        json={
            "requirement": requirement(ART_03_LINKED),
            "variant_id": str(variant(session, "300912").id),
        },
        headers=buyer,
    )

    assert again.status_code == 409
    assert again.json()["assessment_id"] == first["id"]


def test_another_hospital_cannot_see_it(
    client: TestClient, orgs: Orgs, clock: FakeClock, buyer: dict[str, str], session: Session
) -> None:
    created = open_assessment(client, buyer, session, "300912")
    other = purchaser_headers(client, orgs, clock, tenant_code="ten_spital2")

    assert client.get(f"/api/v1/assessments/{created['id']}", headers=other).status_code == 404
    assert client.get("/api/v1/assessments", headers=other).json() == []


def test_a_variant_of_another_category_is_refused(
    client: TestClient, buyer: dict[str, str], session: Session
) -> None:
    response = client.post(
        "/api/v1/assessments",
        json={
            "requirement": requirement(ART_03_LINKED),
            "variant_id": str(variant(session, "304432").id),  # a needle
        },
        headers=buyer,
    )

    assert response.status_code == 422


def test_assigning_and_listing_mine(
    client: TestClient, buyer: dict[str, str], session: Session
) -> None:
    created = open_assessment(client, buyer, session, "300912")
    me = client.get("/api/v1/auth/me", headers=buyer).json()["subject_id"]

    assigned = client.put(
        f"/api/v1/assessments/{created['id']}/assignee",
        json={"subject_id": me},
        headers=buyer,
    )
    mine = client.get("/api/v1/assessments?assigned_to=me", headers=buyer).json()

    assert assigned.status_code == 200
    assert assigned.json()["assigned_to_subject_id"] == me
    assert [row["id"] for row in mine] == [created["id"]]
    by_ref = client.get("/api/v1/assessments?article_ref=ar_5MZQ4K7T2V9C", headers=buyer).json()
    assert len(by_ref) == 1


def test_suppliers_cannot_use_purchaser_endpoints(
    client: TestClient, session: Session, seeded: SeedReport
) -> None:

    bd = session.scalar(select(User).where(User.email == "catalog@bd-demo.example"))
    assert bd is not None

    response = client.get("/api/v1/assessments", headers=login(client, bd))

    assert response.status_code == 403


def test_a_reset_seed_wipes_assessments_in_flight(
    client: TestClient,
    buyer: dict[str, str],
    session: Session,
    hasher: PasswordHasher,
    settings: HubSettings,
    clock: FakeClock,
) -> None:
    # Assessments and requirements reference each other, which a plain delete order cannot undo.
    open_assessment(client, buyer, session, "300912")
    session.expire_all()

    seed(
        session,
        password="another demo password",
        hasher=hasher,
        llm=fake_normalizer(),
        settings=settings,
        now=clock(),
        reset=True,
    )
    session.commit()

    assert session.scalar(select(func.count()).select_from(Assessment)) == 0
