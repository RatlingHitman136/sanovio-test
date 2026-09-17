"""What the client reads from the catalog, and what a supplier may see of it (§14)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from hub_fixtures import FakeClock, Orgs, login, node_key, register_node_key
from supplier_hub.models import Organization, ProductFamily, ProductVariant
from supplier_hub.models.identity import UserRole
from supplier_hub.services.seed import SeedReport


@pytest.fixture
def purchaser(
    client: TestClient, orgs: Orgs, clock: FakeClock, seeded: SeedReport
) -> dict[str, str]:
    operator = login(
        client,
        orgs.user(orgs.operator("org_ops2", "Ops"), "ops2@sanovio.example", UserRole.OPERATOR),
    )
    tenant = client.get("/api/v1/admin/tenants", headers=operator).json()[0]
    key = node_key(tenant_code=tenant["code"])
    register_node_key(client, operator, tenant["id"], key)
    exchanged = client.post(
        "/api/v1/auth/token-exchange", json={"assertion": key.assertion(clock())}
    )
    return {"Authorization": f"Bearer {exchanged.json()['access_token']}"}


def _variant(session: Session, article_no: str) -> ProductVariant:
    found = session.scalar(select(ProductVariant).where(ProductVariant.article_no == article_no))
    assert found is not None
    return found


def test_suppliers_are_listed(client: TestClient, purchaser: dict[str, str]) -> None:
    body = client.get("/api/v1/suppliers", headers=purchaser).json()

    assert sorted(entry["name"] for entry in body) == ["B. Braun", "BD"]


def test_variants_can_be_browsed_and_searched(
    client: TestClient, purchaser: dict[str, str]
) -> None:
    needles = client.get(
        "/api/v1/catalog/variants?category=hypodermic_needle", headers=purchaser
    ).json()
    microlance = client.get("/api/v1/catalog/variants?q=Microlance", headers=purchaser).json()

    assert len(needles) == 35  # Sterican (22) and Microlance (13)
    assert {entry["supplier"] for entry in microlance} == {"BD"}
    assert all(entry["category_code"] == "hypodermic_needle" for entry in needles)


def test_variant_attributes_feed_the_nodes_current_product_preview(
    client: TestClient, purchaser: dict[str, str], session: Session
) -> None:
    injekt = _variant(session, "4606728V")

    body = client.get(f"/api/v1/catalog/variants/{injekt.id}/attributes", headers=purchaser).json()

    design: dict[str, Any] = body["attributes"]["design"]
    assert design["value"] == {"type": "enum", "value": "TWO_PART"}
    # The node stores this fact id with the copied value (§8.2).
    assert design["fact_id"]
    assert body["label"].endswith("(4606728V)")
    assert any(entry["scheme"] == "PZN" for entry in body["identifiers"])


def test_a_family_shows_where_it_was_printed(
    client: TestClient, purchaser: dict[str, str], session: Session
) -> None:
    family = session.scalar(select(ProductFamily).where(ProductFamily.name.like("%Emerald%")))
    assert family is not None

    body = client.get(f"/api/v1/catalog/families/{family.id}", headers=purchaser).json()

    assert (body["source_document"], body["source_page"]) == ("product_catalog_02.pdf", 12)
    assert body["manufacturer"] == "BD"
    assert len(body["variants"]) == 4


def test_a_supplier_sees_only_its_own_catalog(
    client: TestClient, session: Session, seeded: SeedReport
) -> None:
    bd_user = session.scalar(select(Organization).where(Organization.code == "org_bd"))
    assert bd_user is not None
    from supplier_hub.models import User

    account = session.scalar(select(User).where(User.org_id == bd_user.id))
    assert account is not None
    headers = login(client, account)

    body = client.get("/api/v1/supplier/catalog", headers=headers).json()

    assert {family["manufacturer"] for family in body} == {"BD"}
    assert len(body) == 4


def test_the_catalog_needs_a_purchaser_token(client: TestClient, seeded: SeedReport) -> None:
    assert client.get("/api/v1/catalog/variants").status_code == 401
    assert client.get("/api/v1/suppliers").status_code == 401
