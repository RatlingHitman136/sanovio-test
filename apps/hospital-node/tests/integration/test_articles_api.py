from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from hospital_node.models import User
from hospital_node.services.seed import SeedReport
from node_fixtures import article, login


def _detail(client: TestClient, headers: dict[str, str], internal_id: str) -> dict[str, Any]:
    (found,) = client.get(f"/api/v1/articles?q={internal_id}", headers=headers).json()
    response = client.get(f"/api/v1/articles/{found['id']}", headers=headers)
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def test_list_and_search(client: TestClient, anna: User) -> None:
    headers = login(client, anna)

    everything = client.get("/api/v1/articles", headers=headers).json()
    needles = client.get("/api/v1/articles?q=Kan%C3%BCle", headers=headers).json()

    assert len(everything) == 10
    assert [a["internal_id"] for a in needles] == ["6"]
    assert needles[0]["category_code"] == "hypodermic_needle"
    assert "GTIN_CHECKSUM_INVALID" in needles[0]["data_quality_issues"]


def test_lookup_by_article_refs(client: TestClient, anna: User, session: Session) -> None:
    headers = login(client, anna)
    refs = [article(session, "3").article_ref, article(session, "6").article_ref]

    found = client.get(f"/api/v1/articles?article_ref={','.join(refs)}", headers=headers).json()

    assert sorted(a["article_ref"] for a in found) == sorted(refs)


def test_detail_shows_values_sources_and_identifiers(client: TestClient, anna: User) -> None:
    body = _detail(client, login(client, anna), "3")

    connector = next(a for a in body["attributes"] if a["key"] == "connector")
    assert connector["value"] == {"type": "enum", "value": "LUER_LOCK"}
    assert (connector["source"], connector["method"], connector["quote"]) == (
        "EXTRACTION",
        "RULES",
        "Luer-Lock",
    )
    assert {"design", "cone_position"} <= set(body["unknown_attributes"])
    gtin = next(i for i in body["identifiers"] if i["scheme"] == "GTIN")
    assert gtin == {"scheme": "GTIN", "value": "04040456781234", "checksum_valid": True}
    assert body["data_quality_issues"] == ["EAN_CHECKSUM_INVALID", "GTIN_EAN_MISMATCH"]
    assert body["target_net_price"] == "0.1200"
    assert body["reference"] is None
    assert body["article_ref"].startswith("ar_")


def test_unknown_article_is_404(client: TestClient, anna: User) -> None:
    response = client.get(
        "/api/v1/articles/00000000-0000-7000-8000-000000000000", headers=login(client, anna)
    )

    assert response.status_code == 404


def test_category_change_is_recorded_as_purchaser(client: TestClient, anna: User) -> None:
    headers = login(client, anna)
    cup = _detail(client, headers, "9")

    response = client.put(
        f"/api/v1/articles/{cup['id']}/category",
        json={"category_code": "syringe_single_use"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["category_source"] == "PURCHASER"
    assert response.json()["category_set_at"] is not None


def test_facts_endpoint_takes_values_identifiers_and_cannot_provide(
    client: TestClient, anna: User
) -> None:
    headers = login(client, anna)
    syringe = _detail(client, headers, "3")
    url = f"/api/v1/articles/{syringe['id']}/facts"

    design = client.put(
        f"{url}/design", json={"value": {"type": "enum", "value": "zweiteilig"}}, headers=headers
    )
    dehp = client.put(
        f"{url}/dehp_free", json={"cannot_provide": True, "hub_question_id": "q_3"}, headers=headers
    )
    gtin = client.put(
        f"{url}/pharmacode",
        json={
            "value": {
                "type": "identifier",
                "scheme": "PHARMACODE",
                "value": "1234567",
                "checksum_valid": True,
            }
        },
        headers=headers,
    )

    assert design.status_code == dehp.status_code == gtin.status_code == 200
    body = gtin.json()
    assert any(
        a["key"] == "design" and a["source"] == "PURCHASER_ANSWER" for a in body["attributes"]
    )
    assert body["unavailable_attributes"] == ["dehp_free"]
    assert {"scheme": "PHARMACODE", "value": "1234567", "checksum_valid": None} in body[
        "identifiers"
    ]


@pytest.mark.parametrize(
    ("key", "body"),
    [
        ("connector", {"value": {"type": "enum", "value": "Bajonett"}}),
        ("connector", {}),
        ("connector", {"value": {"type": "enum", "value": "LUER"}, "cannot_provide": True}),
        ("price", {"value": {"type": "number", "value": 1, "unit": "CHF"}}),
    ],
)
def test_invalid_corrections_are_422(
    client: TestClient, anna: User, key: str, body: dict[str, Any]
) -> None:
    headers = login(client, anna)
    syringe = _detail(client, headers, "3")

    response = client.put(
        f"/api/v1/articles/{syringe['id']}/facts/{key}", json=body, headers=headers
    )

    assert response.status_code == 422


def test_articles_need_a_login(client: TestClient, seeded: SeedReport) -> None:
    assert client.get("/api/v1/articles").status_code == 401


def test_admins_may_read_articles(client: TestClient, admin: User) -> None:
    assert client.get("/api/v1/articles", headers=login(client, admin)).status_code == 200
