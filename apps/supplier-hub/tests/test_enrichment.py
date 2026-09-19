"""Supplier answers become facts without ever erasing one (§9: add facts, never overwrite)."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from equivalence_core.facts import SupplierSource
from hub_fixtures import (
    ART_03_WITH_SCALE,
    fetch,
    open_assessment,
    run_jobs,
    send_questions,
    variant,
)
from supplier_hub.models import ItemFact, ItemSearchProjection

NARROWER = "Entspricht der Luer-Lock-Ansatz zusätzlich der ISO 80369-7?"


def test_cannot_provide_on_a_narrower_question_keeps_the_value(
    client: TestClient, buyer: dict[str, str], bd: dict[str, str], session: Session
) -> None:
    """Found in the real-key run: a judge concern became a second `standards` question; BD
    listed its standards once and could not confirm ISO 80369-7, and the loop lost both."""
    created = open_assessment(client, buyer, session, "300912", ART_03_WITH_SCALE)
    run_jobs(client)
    review = fetch(client, buyer, created["id"])
    client.post(
        f"/api/v1/assessments/{created['id']}/questions",
        json={
            "version": review["version"],
            "addressee": "SUPPLIER",
            "attribute_key": "standards",
            "text": NARROWER,
        },
        headers=buyer,
    ).raise_for_status()
    send_questions(client, buyer, created["id"])

    request = client.get(f"/api/v1/supplier/requests/{created['id']}", headers=bd).json()
    answers: list[dict[str, Any]] = []
    for question in request["questions"]:
        entry: dict[str, Any] = {"question_id": question["id"], "applies_to_family": True}
        if question["text"] == NARROWER:
            entry |= {"cannot_provide": True, "comment": "Nicht spezifiziert."}
        else:
            entry["value"] = ART_03_WITH_SCALE[question["attribute_key"]]
        answers.append(entry)
    client.put(
        f"/api/v1/supplier/requests/{created['id']}/answers",
        json={"answers": answers},
        headers=bd,
    ).raise_for_status()
    client.post(f"/api/v1/supplier/requests/{created['id']}/submit", headers=bd).raise_for_status()
    run_jobs(client)

    session.expire_all()
    row = session.scalar(
        select(ItemSearchProjection).where(
            ItemSearchProjection.variant_id == variant(session, "300912").id
        )
    )
    assert row is not None
    assert row.attributes["standards"]["value"] == ["ISO 7886-1"]
    # Not merely outranked by a timestamp: the "cannot provide" is never written as a fact.
    unavailable = select(ItemFact).where(
        ItemFact.attribute_key == "standards", ItemFact.source == SupplierSource.UNAVAILABLE
    )
    assert session.scalar(unavailable) is None
    assert "standards" not in row.unknown_attributes
    final = fetch(client, buyer, created["id"])
    assert final["rounds"][-1]["rule_verdict"] == "EQUIVALENT_WITH_DEVIATIONS"
