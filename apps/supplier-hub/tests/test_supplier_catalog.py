"""A supplier adjusts its own catalog per family and per variant (§9, stage 8)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from hub_fixtures import login, variant
from supplier_hub.models import User
from supplier_hub.services.seed import SeedReport


@pytest.fixture
def braun(client: TestClient, session: Session, seeded: SeedReport) -> dict[str, str]:
    user = session.scalar(select(User).where(User.email == "katalog@bbraun-demo.example"))
    assert user is not None
    return login(client, user)


def _family(client: TestClient, bd: dict[str, str], session: Session) -> Any:
    family_id = variant(session, "300912").family_id
    response = client.get(f"/api/v1/supplier/catalog/families/{family_id}", headers=bd)
    assert response.status_code == 200, response.text
    return response.json()


def _put(client: TestClient, headers: dict[str, str], **body: Any) -> Any:
    return client.put("/api/v1/supplier/catalog/facts", json=body, headers=headers)


def _plastipak_10(detail: Any) -> Any:
    return next(v for v in detail["variants"] if v["article_no"] == "300912")


def test_the_family_page_shows_values_with_their_source_and_scope(
    client: TestClient, bd: dict[str, str], session: Session
) -> None:
    detail = _family(client, bd, session)

    assert detail["category_code"] == "syringe_single_use"
    assert {a["key"] for a in detail["attributes"]} >= {"nominal_volume_ml", "dehp_free"}
    volume = _plastipak_10(detail)["values"]["nominal_volume_ml"]
    assert (volume["value"]["value"], volume["scope"]) == (10.0, "VARIANT")
    assert detail["own_facts"] == []


def test_a_family_value_reaches_every_variant_and_outranks_the_catalog(
    client: TestClient, bd: dict[str, str], session: Session
) -> None:
    family_id = variant(session, "300912").family_id

    response = _put(
        client,
        bd,
        family_id=str(family_id),
        attribute_key="dehp_free",
        value={"type": "bool", "value": True},
    )

    assert response.status_code == 200, response.text
    detail = _family(client, bd, session)
    assert all(v["values"]["dehp_free"]["value"]["value"] is True for v in detail["variants"])
    assert _plastipak_10(detail)["values"]["dehp_free"]["source"] == "SUPPLIER_ANSWER"
    assert [f["attribute_key"] for f in detail["own_facts"]] == ["dehp_free"]


def test_a_variant_override_beats_the_family_and_can_be_withdrawn(
    client: TestClient, bd: dict[str, str], session: Session
) -> None:
    family_id = variant(session, "300912").family_id
    target = variant(session, "300912")
    _put(
        client,
        bd,
        family_id=str(family_id),
        attribute_key="special_scale",
        value={"type": "text", "value": "keine"},
    )
    override = _put(
        client,
        bd,
        variant_id=str(target.id),
        attribute_key="special_scale",
        value={"type": "text", "value": "Insulinskala"},
    ).json()

    detail = _family(client, bd, session)
    scale = _plastipak_10(detail)["values"]["special_scale"]
    assert (scale["value"]["value"], scale["scope"]) == ("Insulinskala", "VARIANT")

    withdrawn = client.delete(f"/api/v1/supplier/catalog/facts/{override['fact_id']}", headers=bd)
    assert withdrawn.status_code == 204
    scale = _plastipak_10(_family(client, bd, session))["values"]["special_scale"]
    assert (scale["value"]["value"], scale["scope"]) == ("keine", "FAMILY")


def test_not_available_is_a_value_too(
    client: TestClient, bd: dict[str, str], session: Session
) -> None:
    target = variant(session, "300912")

    _put(client, bd, variant_id=str(target.id), attribute_key="light_protected", unavailable=True)

    assert "light_protected" in _plastipak_10(_family(client, bd, session))["unavailable"]


def test_the_purchasers_see_the_new_value(
    client: TestClient, bd: dict[str, str], buyer: dict[str, str], session: Session
) -> None:
    target = variant(session, "300912")
    _put(
        client,
        bd,
        variant_id=str(target.id),
        attribute_key="pump_compatible",
        value={"type": "bool", "value": False},
    )

    seen = client.get(f"/api/v1/catalog/variants/{target.id}/attributes", headers=buyer).json()

    assert seen["attributes"]["pump_compatible"]["value"] == {"type": "bool", "value": False}


def test_what_is_refused(
    client: TestClient, bd: dict[str, str], braun: dict[str, str], session: Session
) -> None:
    family_id = str(variant(session, "300912").family_id)
    target = str(variant(session, "300912").id)
    detail = _family(client, bd, session)
    catalog_fact = _plastipak_10(detail)["values"]["nominal_volume_ml"]["fact_id"]

    # Another supplier's family does not exist for B. Braun.
    assert (
        client.get(f"/api/v1/supplier/catalog/families/{family_id}", headers=braun).status_code
        == 404
    )
    assert (
        _put(
            client,
            braun,
            family_id=family_id,
            attribute_key="dehp_free",
            value={"type": "bool", "value": True},
        ).status_code
        == 404
    )
    # A value must fit the attribute, and name exactly one scope.
    assert (
        _put(
            client,
            bd,
            family_id=family_id,
            attribute_key="connector",
            value={"type": "enum", "value": "BAYONET"},
        ).status_code
        == 422
    )
    assert (
        _put(
            client,
            bd,
            family_id=family_id,
            variant_id=target,
            attribute_key="dehp_free",
            value={"type": "bool", "value": True},
        ).status_code
        == 422
    )
    # Catalog readings are not the supplier's to withdraw.
    assert (
        client.delete(f"/api/v1/supplier/catalog/facts/{catalog_fact}", headers=bd).status_code
        == 422
    )
