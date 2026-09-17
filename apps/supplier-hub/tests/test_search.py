"""One requirement in, ranked variants out (ARCHITECTURE §15; §21 scenarios 1, 2 and 4)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from equivalence_core.exchange.requirement import AttributeOrigin, RequirementPayload
from equivalence_core.templates import load_seed_templates
from equivalence_core.values import BoolValue, EnumValue, NumberValue
from hub_fixtures import FakeClock, NodeKey, Orgs, login, node_key, register_node_key
from supplier_hub.models import Organization
from supplier_hub.models.identity import UserRole
from supplier_hub.services import candidate_search, templates
from supplier_hub.services.seed import SeedReport

ARTICLE_REF = "ar_5MZQ4K7T2V9C"
SYRINGE = "syringe_single_use"


def _requirement(**overrides: Any) -> RequirementPayload:
    """CSV #3 as the node would send it: volume, connector and sterility, nothing else."""
    attributes = overrides.pop("attributes", None) or {
        "nominal_volume_ml": NumberValue(value=10, unit="ml"),
        "connector": EnumValue(value="LUER_LOCK"),
        "sterile": BoolValue(value=True),
        "mdr_class": EnumValue(value="IIA"),
    }
    template = load_seed_templates()[overrides.pop("template_code", SYRINGE)]
    known = set(attributes)
    return RequirementPayload(
        article_ref=ARTICLE_REF,
        template_code=template.code,
        attributes=attributes,
        attribute_origin=dict.fromkeys(attributes, AttributeOrigin.EXTRACTED),
        unknown_attributes=tuple(key for key in template.keys if key not in known),
        **overrides,
    )


@pytest.fixture
def purchaser(
    client: TestClient, orgs: Orgs, clock: FakeClock, seeded: SeedReport
) -> dict[str, str]:
    """A purchaser of ten_ksp, arriving the way they always do: through the exchange (§17)."""
    operator = login(
        client,
        orgs.user(orgs.operator("org_ops2", "Ops"), "ops2@sanovio.example", UserRole.OPERATOR),
    )
    tenant = client.get("/api/v1/admin/tenants", headers=operator).json()[0]
    key: NodeKey = node_key(tenant_code=tenant["code"])
    register_node_key(client, operator, tenant["id"], key)
    exchanged = client.post(
        "/api/v1/auth/token-exchange", json={"assertion": key.assertion(clock())}
    )
    assert exchanged.status_code == 200, exchanged.text
    return {"Authorization": f"Bearer {exchanged.json()['access_token']}"}


def _search(client: TestClient, headers: dict[str, str], **body: Any) -> Any:
    payload = {"requirement": _requirement().model_dump(mode="json"), **body}
    response = client.post("/api/v1/search", json=payload, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_thin_requirement_finds_the_two_luer_lock_syringes(
    client: TestClient, purchaser: dict[str, str]
) -> None:
    body = _search(client, purchaser)

    found = {candidate["article_no"] for candidate in body["candidates"]}
    assert "300912" in found  # BD Plastipak™ Luer-Lok™ 10 ml
    assert "4606728V" in found  # B. Braun Injekt® Luer Lock Solo 10 ml
    # BD Emerald™ 10 ml is a Luer cone: a known contradiction on a critical attribute.
    assert "307736" not in found
    assert body["excluded_by"]["connector"] >= 1


def test_the_spec_says_what_was_filtered_and_what_is_missing(
    client: TestClient, purchaser: dict[str, str]
) -> None:
    body = _search(client, purchaser)

    spec = body["search_spec"]
    assert spec["category"] == SYRINGE
    # Every critical attribute with an exact rule and a known value, and nothing else.
    assert set(spec["hard_filters"]) == {"nominal_volume_ml", "connector", "mdr_class", "sterile"}
    assert spec["soft_criteria"] == []
    assert "design" in spec["hospital_gaps"]
    assert body["hospital_gaps"] == spec["hospital_gaps"]


def test_an_unknown_attribute_never_excludes(client: TestClient, purchaser: dict[str, str]) -> None:
    body = _search(client, purchaser)

    # No variant states an MDR class, yet the MDR filter removes nobody.
    assert "mdr_class" not in body["excluded_by"]
    assert body["candidates"]


def test_candidates_carry_their_precheck_and_score(
    client: TestClient, purchaser: dict[str, str]
) -> None:
    body = _search(client, purchaser)

    plastipak = next(c for c in body["candidates"] if c["article_no"] == "300912")
    precheck = {entry["attribute_key"]: entry["status"] for entry in plastipak["precheck"]}
    assert precheck["connector"] == "MATCH"
    assert precheck["nominal_volume_ml"] == "MATCH"
    assert precheck["mdr_class"] == "UNKNOWN"
    assert 0 < plastipak["score"] <= 1
    assert 0 < plastipak["coverage"] <= 1
    assert plastipak["critical_unknowns"] >= 1
    assert plastipak["supplier"] == "BD"


def test_an_enriched_requirement_narrows_the_search(
    client: TestClient, purchaser: dict[str, str]
) -> None:
    """After marking Injekt as the current product the requirement carries more (§15.9)."""
    thin = _search(client, purchaser)
    enriched = _requirement(
        attributes={
            "nominal_volume_ml": NumberValue(value=10, unit="ml"),
            "connector": EnumValue(value="LUER_LOCK"),
            "sterile": BoolValue(value=True),
            "mdr_class": EnumValue(value="IIA"),
            "needle_included": BoolValue(value=False),
            "cone_position": EnumValue(value="CENTRIC"),
            "design": EnumValue(value="TWO_PART"),
            "graduation_step_ml": NumberValue(value=0.5, unit="ml"),
        }
    )

    body = _search(client, purchaser, requirement=enriched.model_dump(mode="json"))

    assert set(body["search_spec"]["hard_filters"]) > set(thin["search_spec"]["hard_filters"])
    assert len(body["search_spec"]["hospital_gaps"]) < len(thin["search_spec"]["hospital_gaps"])

    by_article = {candidate["article_no"]: candidate for candidate in body["candidates"]}
    injekt, plastipak = by_article["4606728V"], by_article["300912"]
    design = {
        article: next(e["status"] for e in candidate["precheck"] if e["attribute_key"] == "design")
        for article, candidate in by_article.items()
    }
    # The two-part Injekt matches the design the hospital now states; Plastipak does not.
    assert (design["4606728V"], design["300912"]) == ("MATCH", "MISMATCH")
    assert injekt["score"] > plastipak["score"]
    # Plastipak still leads the list: §15.6 ranks fewest critical unknowns before score, and its
    # catalog answers `needle_included`, which Injekt's text leaves open.
    assert plastipak["critical_unknowns"] < injekt["critical_unknowns"]
    assert [candidate["article_no"] for candidate in body["candidates"]][0] == "300912"


def test_product_hints_rank_an_exact_identifier_match_first(
    client: TestClient, purchaser: dict[str, str], session: Session
) -> None:
    hinted = _requirement().model_dump(mode="json")
    hinted["product_hints"] = {"brand": "B. Braun", "manufacturer_article_no": "4606728V"}

    body = _search(client, purchaser, requirement=hinted)

    first = body["candidates"][0]
    assert (first["article_no"], first["identifier_match"]) == ("4606728V", "ARTICLE_NO")
    assert all(c["identifier_match"] is None for c in body["candidates"][1:])


def test_hints_from_another_manufacturer_match_nothing(
    client: TestClient, purchaser: dict[str, str]
) -> None:
    hinted = _requirement().model_dump(mode="json")
    hinted["product_hints"] = {"brand": "BD", "manufacturer_article_no": "4606728V"}

    body = _search(client, purchaser, requirement=hinted)

    assert all(candidate["identifier_match"] is None for candidate in body["candidates"])


def test_the_search_can_be_limited_to_one_supplier(
    client: TestClient, purchaser: dict[str, str], session: Session
) -> None:
    bd = session.scalar(select(Organization).where(Organization.code == "org_bd"))
    assert bd is not None

    body = _search(client, purchaser, supplier_id=str(bd.id), limit=5)

    assert {candidate["supplier"] for candidate in body["candidates"]} == {"BD"}
    assert len(body["candidates"]) <= 5


def test_needles_and_syringes_never_mix(client: TestClient, purchaser: dict[str, str]) -> None:
    needle = _requirement(
        template_code="hypodermic_needle",
        attributes={
            "gauge": NumberValue(value=21, unit="G"),
            "length_mm": NumberValue(value=40, unit="mm"),
        },
    )

    body = _search(client, purchaser, requirement=needle.model_dump(mode="json"))

    found = {candidate["article_no"] for candidate in body["candidates"]}
    assert {"4657527B", "304432"} <= found  # Sterican and Microlance, both 21 G × 40 mm
    assert "300912" not in found


@pytest.mark.parametrize(
    "broken",
    [
        pytest.param({"name": "Einmalspritze 10 ml"}, id="a field that does not exist"),
        pytest.param({"template_code": "wipes"}, id="an unknown category"),
    ],
)
def test_a_requirement_the_hub_will_not_take(
    client: TestClient, purchaser: dict[str, str], broken: dict[str, Any]
) -> None:
    payload = _requirement().model_dump(mode="json") | broken

    response = client.post("/api/v1/search", json={"requirement": payload}, headers=purchaser)

    assert response.status_code == 422


def test_search_is_for_purchasers_only(client: TestClient, orgs: Orgs, seeded: SeedReport) -> None:
    supplier_user = orgs.user(
        orgs.supplier("org_bd2", "BD Zwei"), "catalog@bd2.example", UserRole.SUPPLIER
    )
    headers = login(client, supplier_user)

    response = client.post(
        "/api/v1/search",
        json={"requirement": _requirement().model_dump(mode="json")},
        headers=headers,
    )

    assert response.status_code == 403
    assert client.post("/api/v1/search", json={}).status_code == 401


def test_the_spec_alone_is_pure(session: Session, seeded: SeedReport) -> None:
    """Building the spec touches no database and no hospital data beyond the requirement."""
    spec = candidate_search.build_spec(_requirement(), templates.definition(session, SYRINGE))

    assert spec.category == SYRINGE
    assert spec.hard_filters["connector"] == EnumValue(value="LUER_LOCK")
    assert "graduation_step_ml" not in spec.hard_filters  # major, not critical
    assert "usable_volume_ml" in spec.hospital_gaps
