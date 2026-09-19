"""An operator changes how a category compares (§7.2, D52): a new hash, re-projected families."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from hub_fixtures import variant

URL = "/api/v1/admin/templates/syringe_single_use"


def _edit(client: TestClient, operator: dict[str, str], **body: Any) -> Any:
    return client.patch(URL, json={"change_note": "curation"} | body, headers=operator)


def _served(client: TestClient, operator: dict[str, str]) -> Any:
    return client.get("/api/v1/templates/syringe_single_use", headers=operator).json()


def _entry(template: Any, key: str) -> Any:
    return next(a for a in template["definition"]["attributes"] if a["key"] == key)


def test_a_changed_criticality_gives_a_new_hash_and_note(
    client: TestClient, operator: dict[str, str]
) -> None:
    before = _served(client, operator)

    edited = _edit(
        client,
        operator,
        set={"special_scale": {"criticality": "minor", "rule": "exact"}},
        change_note="special scale matters less",
    )

    assert edited.status_code == 200, edited.text
    after = _served(client, operator)
    assert after["definition_hash"] != before["definition_hash"]
    assert after["change_note"] == "special scale matters less"
    assert _entry(after, "special_scale")["criticality"] == "minor"
    audit = client.get(
        "/api/v1/admin/audit", params={"action": "TEMPLATE_EDITED"}, headers=operator
    ).json()
    assert [row["target_id"] for row in audit] == ["syringe_single_use"]


def test_a_removed_attribute_leaves_the_projection(
    client: TestClient, operator: dict[str, str], buyer: dict[str, str], session: Session
) -> None:
    plastipak = variant(session, "300912").id
    url = f"/api/v1/catalog/variants/{plastipak}/attributes"
    assert "connector" in client.get(url, headers=buyer).json()["attributes"]

    _edit(client, operator, remove=["connector"]).raise_for_status()

    assert "connector" not in client.get(url, headers=buyer).json()["attributes"]
    assert all(
        a["key"] != "connector" for a in _served(client, operator)["definition"]["attributes"]
    )


def test_a_rule_that_cannot_compare_the_type_is_refused(
    client: TestClient, operator: dict[str, str]
) -> None:
    response = _edit(
        client,
        operator,
        set={"connector": {"criticality": "critical", "rule": "tolerance", "tolerance": 0.1}},
    )

    assert response.status_code == 422
    assert "cannot compare" in response.json()["detail"]


def test_an_identifier_never_joins_a_template(client: TestClient, operator: dict[str, str]) -> None:
    response = _edit(client, operator, add={"gtin": {"criticality": "major", "rule": "exact"}})

    assert response.status_code == 422


def test_an_attribute_already_in_the_template_is_not_added_twice(
    client: TestClient, operator: dict[str, str]
) -> None:
    response = _edit(client, operator, add={"connector": {"criticality": "major", "rule": "exact"}})

    assert response.status_code == 409
    assert response.json()["code"] == "ATTRIBUTE_IN_TEMPLATE"


def test_an_edit_that_changes_nothing_is_refused(
    client: TestClient, operator: dict[str, str]
) -> None:
    current = _entry(_served(client, operator), "connector")
    settings = {name: current[name] for name in ("criticality", "rule", "tolerance", "shareable")}

    response = _edit(client, operator, set={"connector": settings})

    assert response.status_code == 422
    assert "changes nothing" in response.json()["detail"]


def test_an_unknown_key_or_category_is_refused(
    client: TestClient, operator: dict[str, str]
) -> None:
    settings = {"criticality": "major", "rule": "exact"}
    assert _edit(client, operator, set={"colour": settings}).status_code == 422
    missing = client.patch(
        "/api/v1/admin/templates/gloves", json={"change_note": "x"}, headers=operator
    )
    assert missing.status_code == 404


def test_a_change_note_is_required(client: TestClient, operator: dict[str, str]) -> None:
    response = client.patch(URL, json={"remove": ["connector"]}, headers=operator)

    assert response.status_code == 422
