from sqlalchemy.orm import Session

from equivalence_core.identifiers import IdentifierScheme
from equivalence_core.values import NumberValue
from hospital_node.core.settings import NodeSettings
from hospital_node.models.users import Role
from hospital_node.services import articles, projection, template_sync
from hospital_node.services.facts import active_facts, retract
from hospital_node.services.seed import SeedReport
from node_fixtures import FakeClock, article, user


def test_origins_are_coarse(session: Session, seeded: SeedReport) -> None:
    syringe = article(session, "3")

    assert syringe.projection is not None
    assert syringe.projection.attribute_origin == {
        "mdr_class": "MASTER",
        "units_per_order_unit": "MASTER",
        "nominal_volume_ml": "EXTRACTED",
        "connector": "EXTRACTED",
        "sterile": "EXTRACTED",
    }


def test_identifiers_live_only_in_their_own_section(session: Session, seeded: SeedReport) -> None:
    syringe = article(session, "3")

    assert syringe.projection is not None
    assert {entry["scheme"] for entry in syringe.projection.identifiers} == {
        IdentifierScheme.GTIN,
        IdentifierScheme.EAN,
        IdentifierScheme.MANUFACTURER_REF,
    }
    assert not {"gtin", "ean", "manufacturer_ref"} & set(syringe.projection.attributes)
    gtin = next(e for e in syringe.projection.identifiers if e["scheme"] == "GTIN")
    assert gtin["value"] == "04040456781234"
    assert gtin["checksum_valid"] is True


def test_a_non_shareable_change_moves_only_the_record_hash(
    session: Session, seeded: SeedReport, settings: NodeSettings, clock: FakeClock
) -> None:
    syringe = article(session, "3")
    assert syringe.projection is not None
    before = (syringe.projection.record_hash, syringe.projection.requirement_hash)

    articles.set_fact(
        session,
        syringe,
        "units_per_order_unit",
        NumberValue(value=50, unit="pcs"),
        hub_question_id=None,
        user=user(session, Role.PURCHASER),
        templates=template_sync.installed(session),
        settings=settings,
        now=clock(),
    )

    assert syringe.projection.record_hash != before[0]
    assert syringe.projection.requirement_hash == before[1]


def test_retracted_facts_no_longer_count(
    session: Session, seeded: SeedReport, settings: NodeSettings, clock: FakeClock
) -> None:
    syringe = article(session, "3")
    connector = [f for f in active_facts(syringe) if f.attribute_key == "connector"]

    retract(connector, now=clock())
    rebuilt = projection.rebuild(
        session,
        syringe,
        template_sync.installed(session)["syringe_single_use"],
        settings=settings,
        now=clock(),
    )

    assert "connector" not in rebuilt.attributes
    assert "connector" in rebuilt.unknown_attributes
