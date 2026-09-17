from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from hospital_node.models import User
from node_fixtures import article, login

BODY: dict[str, Any] = {
    "variant_id": "var_injekt_ll_10",
    "label": "Injekt® Luer Lock Solo 10 ml (4606728V)",
    "attributes": {
        "connector": {"value": {"type": "enum", "value": "LUER"}, "fact_id": "fct_11"},
        "design": {"value": {"type": "enum", "value": "TWO_PART"}, "fact_id": "fct_40"},
        "gtin": {
            "value": {
                "type": "identifier",
                "scheme": "GTIN",
                "value": "04022495000011",
                "checksum_valid": True,
            }
        },
    },
}


def test_preview_then_link_then_undo(client: TestClient, anna: User, session: Session) -> None:
    headers = login(client, anna)
    url = f"/api/v1/articles/{article(session, '3').id}/reference"

    preview = client.post(f"{url}/preview", json=BODY, headers=headers).json()
    unresolved = client.put(url, json=BODY, headers=headers)
    linked = client.put(
        url, json=BODY | {"conflict_choices": {"connector": "KEEP_OURS"}}, headers=headers
    )
    undone = client.delete(url, headers=headers)

    assert preview["fills"] == [{"key": "design", "value": {"type": "enum", "value": "TWO_PART"}}]
    assert preview["conflicts"][0]["key"] == "connector"
    assert preview["conflicts"][0]["ours_source"] == "EXTRACTION"
    assert list(preview["identifiers_info"]) == ["gtin"]
    assert unresolved.status_code == 422
    assert "connector" in unresolved.json()["detail"]
    assert linked.status_code == 200
    assert linked.json()["reference"]["variant_id"] == "var_injekt_ll_10"
    design = next(a for a in linked.json()["attributes"] if a["key"] == "design")
    assert design["source"] == "REFERENCE_ITEM"
    assert undone.status_code == 200
    assert undone.json()["reference"] is None
    assert "design" in undone.json()["unknown_attributes"]


def test_reference_needs_a_login(client: TestClient, anna: User, session: Session) -> None:
    url = f"/api/v1/articles/{article(session, '3').id}/reference/preview"

    assert client.post(url, json=BODY).status_code == 401
