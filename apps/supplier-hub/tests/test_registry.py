"""The hub owns the registry; the nodes hold copies of what it serves (§7.2, D52)."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from equivalence_core.templates import definition_from_json, load_seed_templates
from hub_fixtures import FakeClock, Orgs, login
from supplier_hub.models.identity import UserRole
from supplier_hub.services import attribute_registry, templates


def _seeded(session: Session, clock: FakeClock) -> None:
    templates.seed_templates(session, now=clock())
    session.commit()


def test_the_served_definition_is_exactly_the_core_seed(session: Session, clock: FakeClock) -> None:
    _seeded(session, clock)

    for code, seeded in load_seed_templates().items():
        served = templates.definition(session, code)
        assert served == seeded, code
        assert served.definition_hash == seeded.definition_hash


def test_a_node_can_install_what_the_hub_serves(
    client: TestClient, orgs: Orgs, session: Session, clock: FakeClock
) -> None:
    _seeded(session, clock)
    headers = login(client, orgs.user(orgs.supplier(), "catalog@bd.example", UserRole.SUPPLIER))

    body = client.get("/api/v1/templates", headers=headers).json()

    assert [entry["code"] for entry in body] == [
        "generic_consumable",
        "hypodermic_needle",
        "syringe_single_use",
    ]
    for entry in body:
        # This is precisely what the node's PUT /templates validates.
        installed = definition_from_json(entry["definition"])
        assert installed.definition_hash == entry["definition_hash"]


def test_identifier_definitions_exist_but_never_sit_in_a_template(
    session: Session, clock: FakeClock
) -> None:
    _seeded(session, clock)

    gtin = attribute_registry.by_key(session, "gtin")
    template_keys = {
        key
        for code in ("syringe_single_use", "hypodermic_needle")
        for key in templates.definition(session, code).keys
    }

    assert gtin.kind == "IDENTIFIER"
    assert gtin.status == "APPROVED"
    assert not {"gtin", "ean", "pzn", "himiv", "supplier_article_no"} & template_keys


def test_attributes_can_be_listed_per_category(
    client: TestClient, orgs: Orgs, session: Session, clock: FakeClock
) -> None:
    _seeded(session, clock)
    headers = login(client, orgs.user(orgs.operator(), "ops@sanovio.example", UserRole.OPERATOR))

    needle = client.get("/api/v1/attributes?category=hypodermic_needle", headers=headers).json()
    everything = client.get("/api/v1/attributes", headers=headers).json()

    keys = {entry["key"] for entry in needle}
    assert {"gauge", "wall_type", "mdr_class"} <= keys
    assert "connector" in keys and "nominal_volume_ml" not in keys
    assert {"gtin", "pzn"} <= {entry["key"] for entry in everything}


def test_seeding_twice_changes_nothing(session: Session, clock: FakeClock) -> None:
    _seeded(session, clock)
    before = templates.row_for(session, "syringe_single_use").definition_hash

    clock.advance(days=1)
    templates.seed_templates(session, now=clock())
    session.commit()

    assert templates.row_for(session, "syringe_single_use").definition_hash == before
    assert len(templates.rows(session)) == 3


def test_an_unknown_category_is_404(
    client: TestClient, orgs: Orgs, session: Session, clock: FakeClock
) -> None:
    _seeded(session, clock)
    headers = login(client, orgs.user(orgs.supplier(), "catalog@bd.example", UserRole.SUPPLIER))

    assert client.get("/api/v1/templates/wipes", headers=headers).status_code == 404


def test_the_registry_needs_a_token(client: TestClient) -> None:
    assert client.get("/api/v1/templates").status_code == 401
