"""Suppliers add and maintain their own families and variants (§9, D59)."""

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from hub_fixtures import ART_03_WITH_SCALE, fetch, open_assessment, requirement, run_jobs, variant
from supplier_hub.models import ItemFact, Job, ProductFamily
from supplier_hub.models.jobs import JobKind

CATALOG = "/api/v1/supplier/catalog"
GTIN = "4006381333931"
FAMILY = {
    "name": "BD Luer-Lok™ Spritze 20 ml",
    "manufacturer": "BD",
    "brand_name": "BD Luer-Lok™",
    "product_type": "Einmalspritze, dreiteilig",
    "description": "Luer-Lock-Ansatz, zentrisch. Nicht hergestellt mit Latex.",
    "category_code": "syringe_single_use",
}
ROW = {
    "article_no": "300999",
    "label": "BD Luer-Lok™ 20 ml",
    "size_text": "20 ml",
    "order_unit": "Box",
    "units_per_order_unit": 48,
    "gtin": GTIN,
}


def _create(client: TestClient, bd: dict[str, str]) -> Any:
    response = client.post(f"{CATALOG}/families", json=FAMILY, headers=bd)
    assert response.status_code == 200, response.text
    return response.json()


def _add(client: TestClient, bd: dict[str, str], family_id: str, **row: Any) -> Any:
    return client.post(f"{CATALOG}/families/{family_id}/variants", json=ROW | row, headers=bd)


def _search_20ml(client: TestClient, buyer: dict[str, str]) -> set[str]:
    wanted = {"nominal_volume_ml": {"type": "number", "value": 20, "unit": "ml"}}
    body = {"requirement": requirement(wanted), "limit": 50}
    response = client.post("/api/v1/search", json=body, headers=buyer)
    assert response.status_code == 200, response.text
    return {candidate["article_no"] for candidate in response.json()["candidates"]}


def _jobs(session: Session, family_id: str) -> list[Job]:
    session.expire_all()
    jobs = session.scalars(select(Job).where(Job.kind == JobKind.NORMALIZE_ITEM)).all()
    return [job for job in jobs if job.payload["family_id"] == family_id]


def test_a_new_family_and_variant_are_read_like_a_printed_row(
    client: TestClient, bd: dict[str, str], buyer: dict[str, str], session: Session
) -> None:
    family = _create(client, bd)
    assert family["reading"] and family["variants"] == []

    added = _add(client, bd, family["id"])

    assert added.status_code == 200, added.text
    [row] = added.json()["variants"]
    assert row["values"]["nominal_volume_ml"]["value"] == {
        "type": "number",
        "value": 20.0,
        "unit": "ml",
    }
    new = variant(session, "300999")
    identifiers = {
        fact.attribute_key: fact.value
        for fact in session.scalars(select(ItemFact).where(ItemFact.variant_id == new.id))
        if fact.value and fact.value["type"] == "identifier"
    }
    assert identifiers["gtin"]["value"] == GTIN
    assert identifiers["supplier_article_no"]["value"] == "300999"
    assert new.created_by is not None
    assert "300999" in _search_20ml(client, buyer)


def test_the_description_is_read_once_in_the_background(
    client: TestClient, bd: dict[str, str], session: Session
) -> None:
    family = _create(client, bd)
    assert len(_jobs(session, family["id"])) == 1

    run_jobs(client)

    detail = client.get(f"{CATALOG}/families/{family['id']}", headers=bd).json()
    assert not detail["reading"]
    row = session.get(ProductFamily, uuid.UUID(family["id"]))
    assert row is not None and row.category_source == "SUPPLIER"


def test_an_edited_text_replaces_what_the_old_text_said(
    client: TestClient, bd: dict[str, str], session: Session
) -> None:
    plastipak = variant(session, "300912").family
    readings = [
        fact
        for fact in session.scalars(select(ItemFact).where(ItemFact.family_id == plastipak.id))
        if fact.source == "EXTRACTION" and fact.is_active
    ]
    assert readings, "the seed read Plastipak's catalog text"
    client.put(
        f"{CATALOG}/facts",
        json={
            "family_id": str(plastipak.id),
            "attribute_key": "dehp_free",
            "value": {"type": "bool", "value": True},
        },
        headers=bd,
    ).raise_for_status()
    text = {name: FAMILY[name] for name in ("name", "manufacturer", "description")}

    edited = client.patch(f"{CATALOG}/families/{plastipak.id}", json={"text": text}, headers=bd)

    assert edited.status_code == 200, edited.text
    assert edited.json()["reading"]
    session.expire_all()
    assert all(not fact.is_active for fact in readings)
    assert edited.json()["family_values"]["dehp_free"]["source"] == "SUPPLIER_ANSWER"
    assert len(_jobs(session, str(plastipak.id))) == 1


def test_a_chosen_category_reprojects_and_open_assessments_carry_on(
    client: TestClient, bd: dict[str, str], buyer: dict[str, str], session: Session
) -> None:
    created = open_assessment(client, buyer, session, "300912", ART_03_WITH_SCALE)
    run_jobs(client)
    plastipak = variant(session, "300912").family

    moved = client.patch(
        f"{CATALOG}/families/{plastipak.id}",
        json={"category_code": "hypodermic_needle"},
        headers=bd,
    )

    assert moved.status_code == 200, moved.text
    assert moved.json()["category_code"] == "hypodermic_needle"
    assert "gauge" in {attribute["key"] for attribute in moved.json()["attributes"]}
    assert fetch(client, buyer, created["id"])["status"] == "NEEDS_QUESTION_REVIEW"
    unknown = client.patch(
        f"{CATALOG}/families/{plastipak.id}", json={"category_code": "gloves"}, headers=bd
    )
    assert unknown.status_code == 422


def test_duplicates_bad_gtins_and_other_suppliers_are_refused(
    client: TestClient, bd: dict[str, str], buyer: dict[str, str], session: Session
) -> None:
    family = _create(client, bd)
    assert _add(client, bd, family["id"], article_no="300912").status_code == 409
    assert _add(client, bd, family["id"], gtin="4006381333932").status_code == 422

    braun = variant(session, "4606728V")
    foreign = [
        client.post(f"{CATALOG}/families/{braun.family_id}/variants", json=ROW, headers=bd),
        client.patch(
            f"{CATALOG}/families/{braun.family_id}",
            json={"category_code": "hypodermic_needle"},
            headers=bd,
        ),
        client.post(f"{CATALOG}/variants/{braun.id}/retire", headers=bd),
    ]
    assert [response.status_code for response in foreign] == [404, 404, 404]
    purchaser = client.post(f"{CATALOG}/families", json=FAMILY, headers=buyer)
    assert purchaser.status_code in (401, 403)


def test_a_retired_variant_leaves_search_and_can_come_back(
    client: TestClient, bd: dict[str, str], buyer: dict[str, str], session: Session
) -> None:
    family = _create(client, bd)
    _add(client, bd, family["id"]).raise_for_status()
    new = variant(session, "300999")

    retired = client.post(f"{CATALOG}/variants/{new.id}/retire", headers=bd)

    assert retired.status_code == 200
    assert [row["is_active"] for row in retired.json()["variants"]] == [False]
    assert "300999" not in _search_20ml(client, buyer)
    start = client.post(
        "/api/v1/assessments",
        json={
            "requirement": requirement(
                {"nominal_volume_ml": {"type": "number", "value": 20, "unit": "ml"}}
            ),
            "variant_id": str(new.id),
        },
        headers=buyer,
    )
    assert start.status_code == 404
    client.post(f"{CATALOG}/variants/{new.id}/reactivate", headers=bd).raise_for_status()
    assert "300999" in _search_20ml(client, buyer)
