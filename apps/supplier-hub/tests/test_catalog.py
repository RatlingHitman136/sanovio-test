"""The catalog as printed: the tables feed the parsers, the prose feeds normalize_item."""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from equivalence_core.facts import SupplierSource
from hub_fixtures import FakeClock, seed_hub_demo
from service_kit.security import PasswordHasher
from supplier_hub.core.settings import HubSettings
from supplier_hub.llm.fakes import fake_normalizer
from supplier_hub.models import ItemFact, ItemSearchProjection, LlmCall, ProductVariant
from supplier_hub.services import normalization, templates
from supplier_hub.services.seed import SeedReport


def _projection(session: Session, article_no: str) -> ItemSearchProjection:
    row = session.scalar(
        select(ItemSearchProjection)
        .join(ProductVariant, ProductVariant.id == ItemSearchProjection.variant_id)
        .where(ProductVariant.article_no == article_no)
    )
    assert row is not None, article_no
    return row


def _values(session: Session, article_no: str) -> dict[str, Any]:
    return {
        key: value["value"] for key, value in _projection(session, article_no).attributes.items()
    }


def test_both_catalogs_are_loaded(session: Session, seeded: SeedReport) -> None:
    assert (seeded.suppliers, seeded.families, seeded.variants) == (2, 6, 54)
    assert session.scalar(select(func.count()).select_from(ProductVariant)) == 54


def test_printed_rows_become_facts(session: Session, seeded: SeedReport) -> None:
    plastipak = _values(session, "300912")
    injekt = _values(session, "4606728V")

    assert plastipak["nominal_volume_ml"] == 10
    assert plastipak["graduation_step_ml"] == 0.2
    assert plastipak["cone_position"] == "CENTRIC"
    assert plastipak["connector"] == "LUER_LOCK"
    assert plastipak["units_per_order_unit"] == 100
    # "10 ml, nutzbar bis 12 ml" states both volumes.
    assert (injekt["nominal_volume_ml"], injekt["usable_volume_ml"]) == (10, 12)
    assert injekt["graduation_step_ml"] == 0.5


def test_needles_read_gauge_diameter_and_length(session: Session, seeded: SeedReport) -> None:
    sterican = _values(session, "4657527B")
    microlance = _values(session, "304432")

    assert (sterican["gauge"], sterican["outer_diameter_mm"]) == (21, 0.8)
    # Printed in millimetres and in inches; the millimetre column is the one that counts.
    assert sterican["length_mm"] == 40
    assert sterican["inner_diameter_mm"] == 0.58
    assert sterican["bevel"] == "LONG"
    assert microlance["wall_type"] == "THIN"
    assert microlance["colour_code"] == "grün"


def test_identifiers_come_from_the_printed_numbers(session: Session, seeded: SeedReport) -> None:
    injekt = _projection(session, "4606728V")

    identifiers = {entry["scheme"]: entry["value"] for entry in injekt.identifiers}

    assert identifiers == {
        "SUPPLIER_ARTICLE_NO": "4606728V",
        "PZN": "00611005",
        "HIMIV": "03.29.01.1052",
    }
    assert "supplier_article_no" not in injekt.attributes


def test_family_prose_becomes_family_facts(session: Session, seeded: SeedReport) -> None:
    injekt = _values(session, "4606728V")
    emerald = _values(session, "307736")

    # Only the prose says these.
    assert injekt["latex_free"] is True
    assert injekt["dehp_free"] is True
    assert injekt["iso_7886_1_compliant"] is True
    assert emerald["latex_free"] is True
    # "Zweiteilige" / "Dreiteilige" are read by the parsers from the family's own title.
    assert injekt["design"] == "TWO_PART"
    assert emerald["design"] == "THREE_PART"


def test_an_invented_quote_is_dropped(session: Session, seeded: SeedReport) -> None:
    """The scripted answer claims Injekt is pump-validated; the text never says so."""
    assert "pump_compatible" not in _values(session, "4606728V")
    assert _values(session, "300912")["pump_compatible"] is True


def test_family_facts_reach_every_variant_but_keep_their_scope(
    session: Session, seeded: SeedReport
) -> None:
    projection = _projection(session, "300912")

    fact_ids = projection.attribute_fact_ids
    latex = session.get(ItemFact, uuid.UUID(fact_ids["latex_free"]))
    graduation = session.get(ItemFact, uuid.UUID(fact_ids["graduation_step_ml"]))

    assert latex is not None and latex.family_id is not None and latex.variant_id is None
    assert graduation is not None and graduation.variant_id is not None
    assert latex.source == SupplierSource.EXTRACTION
    assert graduation.source == SupplierSource.CATALOG
    assert latex.evidence_quote == "Der latexfreie Stopfen"
    assert str(latex.confidence) == "0.93"


def test_one_call_for_the_whole_catalog_and_none_on_a_rerun(
    session: Session, hasher: PasswordHasher, settings: HubSettings, clock: FakeClock
) -> None:
    llm = fake_normalizer()

    seed_hub_demo(session, hasher, settings, clock, llm)

    assert len(llm.calls) == 1
    assert session.scalar(select(func.count()).select_from(LlmCall)) == 1
    assert normalization.stale_families(session) == []

    again = fake_normalizer()
    normalization.normalize(
        session,
        normalization.stale_families(session),
        llm=again,
        settings=settings,
        now=clock(),
    )
    assert again.calls == []


def test_without_an_llm_the_tables_alone_still_give_facts(
    session: Session, hasher: PasswordHasher, settings: HubSettings, clock: FakeClock
) -> None:
    seed_hub_demo(session, hasher, settings, clock, llm=None)

    plastipak = _values(session, "300912")
    assert plastipak["nominal_volume_ml"] == 10
    assert "latex_free" not in plastipak
    assert session.scalar(select(func.count()).select_from(LlmCall)) == 0


def test_every_variant_is_projected_with_its_category(session: Session, seeded: SeedReport) -> None:
    rows = session.scalars(select(ItemSearchProjection)).all()

    assert len(rows) == 54
    assert {row.category_code for row in rows} == {"syringe_single_use", "hypodermic_needle"}
    needle = _projection(session, "304432")
    assert "mdr_class" in needle.unknown_attributes
    assert needle.display_name == 'BD Microlance™ 21 G 1 1/2" – Nr. 2 (304432)'
    assert needle.record_hash


def test_the_registry_is_seeded_with_the_catalog(session: Session, seeded: SeedReport) -> None:
    assert set(templates.definitions(session)) == {
        "generic_consumable",
        "hypodermic_needle",
        "syringe_single_use",
    }
