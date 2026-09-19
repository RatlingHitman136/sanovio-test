"""Curation beyond approval: a provisional attribute is merged or rejected (§7.2 step 6)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from hub_fixtures import (
    ART_03_WITH_SCALE,
    FakeClock,
    Orgs,
    ask_free_question,
    fetch,
    open_assessment,
    purchaser_headers,
    run_jobs,
    send_questions,
    supplier_answers,
    variant,
)
from supplier_hub.models import AttributeDefinition, ItemFact, OperatorAction
from supplier_hub.models.registry import AttributeStatus

LABEL_QUESTION = "Liegt der Packung ein abziehbares Dokumentationsetikett bei?"


@pytest.fixture
def provisional(
    client: TestClient, buyer: dict[str, str], bd: dict[str, str], session: Session
) -> Any:
    """Scenario 7 up to BD's answer: `peel_off_label` is PROVISIONAL and holds BD's value."""
    review = open_assessment(client, buyer, session, "300912", ART_03_WITH_SCALE)
    run_jobs(client)
    ask_free_question(client, buyer, review["id"], LABEL_QUESTION).raise_for_status()
    run_jobs(client)
    send_questions(client, buyer, review["id"])
    typed = ART_03_WITH_SCALE | {"peel_off_label": {"type": "bool", "value": True}}
    supplier_answers(client, bd, review["id"], typed)
    run_jobs(client)
    return review


def _proposal(client: TestClient, operator: dict[str, str]) -> Any:
    [proposal] = client.get(
        "/api/v1/admin/attribute-proposals", params={"status": "PROVISIONAL"}, headers=operator
    ).json()
    return proposal


def _shown(client: TestClient, orgs: Orgs, clock: FakeClock, session: Session) -> Any:
    """What another hospital sees on a sibling variant of the family."""
    other = purchaser_headers(client, orgs, clock, tenant_code="ten_spital2")
    sibling = variant(session, "309628")
    response = client.get(f"/api/v1/catalog/variants/{sibling.id}/attributes", headers=other)
    return response.json()


def _row(session: Session, key: str) -> AttributeDefinition:
    session.expire_all()
    row = session.scalar(select(AttributeDefinition).where(AttributeDefinition.key == key))
    assert row is not None
    return row


def test_the_proposal_list_counts_the_values_already_shared(
    client: TestClient, operator: dict[str, str], provisional: Any
) -> None:
    assert _proposal(client, operator)["value_count"] == 1


def test_a_rejected_attribute_is_no_longer_shown(
    client: TestClient,
    operator: dict[str, str],
    orgs: Orgs,
    clock: FakeClock,
    session: Session,
    provisional: Any,
) -> None:
    proposal = _proposal(client, operator)

    rejected = client.post(
        f"/api/v1/admin/attribute-proposals/{proposal['id']}/reject",
        json={"note": "a pack detail, not a product property"},
        headers=operator,
    )

    assert rejected.status_code == 200, rejected.text
    assert (rejected.json()["status"], rejected.json()["review_note"]) == (
        "REJECTED",
        "a pack detail, not a product property",
    )
    assert _row(session, "peel_off_label").status == AttributeStatus.DEPRECATED
    assert _shown(client, orgs, clock, session)["additional_information"] == {}
    # Kept for audit: the fact itself stays.
    facts = select(ItemFact).where(ItemFact.attribute_key == "peel_off_label")
    assert session.scalars(facts).all()
    audit = select(OperatorAction).where(OperatorAction.action == "PROPOSAL_REJECTED")
    assert [row.target_id for row in session.scalars(audit)] == [proposal["id"]]


def test_a_merged_attribute_moves_its_values_and_questions(
    client: TestClient,
    operator: dict[str, str],
    buyer: dict[str, str],
    orgs: Orgs,
    clock: FakeClock,
    session: Session,
    provisional: Any,
) -> None:
    proposal = _proposal(client, operator)

    merged = client.post(
        f"/api/v1/admin/attribute-proposals/{proposal['id']}/merge",
        json={"attribute_key": "latex_free", "note": "asked the same"},
        headers=operator,
    )

    assert merged.status_code == 200, merged.text
    assert merged.json()["status"] == "MERGED"
    old, target = _row(session, "peel_off_label"), _row(session, "latex_free")
    assert (old.status, old.merged_into_id) == (AttributeStatus.DEPRECATED, target.id)
    moved = session.scalars(
        select(ItemFact).where(ItemFact.attribute_key == "peel_off_label")
    ).all()
    assert all(fact.superseded_by_id is not None for fact in moved)
    asked = next(
        q
        for q in fetch(client, buyer, provisional["id"])["questions"]
        if q["text"] == LABEL_QUESTION
    )
    assert asked["attribute_key"] == "latex_free"
    shown = _shown(client, orgs, clock, session)
    assert "peel_off_label" not in shown["additional_information"]
    # BD's answer now counts under the target key, above its catalog value (§9 precedence).
    assert shown["attributes"]["latex_free"]["value"] == {"type": "bool", "value": True}
    [moved_to] = session.scalars(
        select(ItemFact).where(
            ItemFact.attribute_key == "latex_free",
            ItemFact.source == "SUPPLIER_ANSWER",
            ItemFact.superseded_by_id.is_(None),
        )
    ).all()
    # Moved with its provenance: the same answer, the same supplier user, the same scope.
    [before] = moved
    assert (moved_to.answer_id, moved_to.created_by, moved_to.family_id) == (
        before.answer_id,
        before.created_by,
        before.family_id,
    )
    assert before.superseded_by_id == moved_to.id


def test_a_merge_target_of_another_type_is_refused(
    client: TestClient, operator: dict[str, str], session: Session, provisional: Any
) -> None:
    proposal = _proposal(client, operator)

    response = client.post(
        f"/api/v1/admin/attribute-proposals/{proposal['id']}/merge",
        json={"attribute_key": "nominal_volume_ml", "note": "wrong"},
        headers=operator,
    )

    assert response.status_code == 422
    assert _row(session, "peel_off_label").status == AttributeStatus.PROVISIONAL


def test_a_merge_stops_on_a_value_the_target_cannot_hold(
    client: TestClient, operator: dict[str, str], session: Session, provisional: Any
) -> None:
    """All or nothing: nothing moves when one value does not fit."""
    row = _row(session, "peel_off_label")
    row.value_type, row.options = "enum", ["WITH_LABEL"]
    fact = session.scalar(select(ItemFact).where(ItemFact.attribute_key == "peel_off_label"))
    assert fact is not None
    fact.value = {"type": "enum", "value": "WITH_LABEL"}
    session.commit()
    proposal = _proposal(client, operator)

    response = client.post(
        f"/api/v1/admin/attribute-proposals/{proposal['id']}/merge",
        json={"attribute_key": "connector", "note": "wrong"},
        headers=operator,
    )

    assert response.status_code == 422
    assert "connector cannot hold" in response.json()["detail"]
    session.expire_all()
    assert fact.superseded_by_id is None


def test_approval_can_correct_the_labels_but_never_name_a_supplier(
    client: TestClient, operator: dict[str, str], session: Session, provisional: Any
) -> None:
    proposal = _proposal(client, operator)
    url = f"/api/v1/admin/attribute-proposals/{proposal['id']}/approve"
    settings = {"criticality": "minor", "rule": "exact"}

    branded = client.post(
        url, json=settings | {"labels": {"de": "BD Etikett", "en": "BD label"}}, headers=operator
    )
    assert branded.status_code == 422

    labels = {"de": "Dokumentationsetikett", "en": "Documentation label"}
    approved = client.post(url, json=settings | {"labels": labels}, headers=operator)
    assert approved.status_code == 200, approved.text
    assert _row(session, "peel_off_label").labels == labels


def test_only_a_provisional_attribute_can_be_rejected(
    client: TestClient, operator: dict[str, str], provisional: Any
) -> None:
    proposal = _proposal(client, operator)
    url = f"/api/v1/admin/attribute-proposals/{proposal['id']}/reject"
    client.post(url, json={"note": "no"}, headers=operator).raise_for_status()

    again = client.post(url, json={"note": "no"}, headers=operator)

    assert again.status_code == 409
    assert again.json()["code"] == "NOT_PROVISIONAL"
