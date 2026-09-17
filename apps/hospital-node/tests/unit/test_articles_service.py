import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from equivalence_core.identifiers import IdentifierScheme
from equivalence_core.values import BoolValue, EnumValue, IdentifierValue, TypedValue
from hospital_node.core.settings import NodeSettings
from hospital_node.models import HospitalArticle
from hospital_node.models.articles import CategorySource
from hospital_node.models.users import Role
from hospital_node.services import articles, template_sync
from hospital_node.services.seed import SeedReport
from node_fixtures import FakeClock, article, user, values
from service_kit.errors import NotFound, Unprocessable


def _set(
    session: Session,
    settings: NodeSettings,
    clock: FakeClock,
    internal_id: str,
    key: str,
    value: TypedValue | None,
    question: str | None = None,
) -> HospitalArticle:
    found = article(session, internal_id)
    articles.set_fact(
        session,
        found,
        key,
        value,
        hub_question_id=question,
        user=user(session, Role.PURCHASER),
        templates=template_sync.installed(session),
        settings=settings,
        now=clock(),
    )
    return found


def test_identifier_problems_match_the_client_data(session: Session, seeded: SeedReport) -> None:
    rows = session.scalars(select(HospitalArticle)).all()

    def count(issue: str) -> int:
        return sum(issue in row.data_quality_issues for row in rows)

    assert count("GTIN_CHECKSUM_INVALID") == 7
    assert count("GTIN_EAN_MISMATCH") == 9
    assert "GTIN_EAN_MISMATCH" not in article(session, "4").data_quality_issues


def test_master_record_is_kept_exactly(session: Session, seeded: SeedReport) -> None:
    syringe = article(session, "3")

    assert syringe.raw["GTIN"] == "'04040456781234"
    assert syringe.target_net_price == Decimal("0.12")
    assert syringe.annual_quantity == 15000
    assert syringe.article_ref.startswith("ar_")


def test_names_are_read_by_the_parsers(session: Session, seeded: SeedReport) -> None:
    syringe = values(article(session, "3"))
    assert (syringe["nominal_volume_ml"], syringe["connector"], syringe["sterile"]) == (
        10,
        "LUER_LOCK",
        True,
    )
    needle = values(article(session, "6"))
    assert (needle["outer_diameter_mm"], needle["length_mm"]) == (0.8, 40)


def test_a_purchaser_gtin_replaces_the_checksum_problem(
    session: Session, seeded: SeedReport, settings: NodeSettings, clock: FakeClock
) -> None:
    gtin = IdentifierValue(
        scheme=IdentifierScheme.GTIN, value=" 04040456999882", checksum_valid=False
    )

    needle = _set(session, settings, clock, "6", "gtin", gtin)

    assert needle.data_quality_issues == ["EAN_CHECKSUM_INVALID", "GTIN_EAN_MISMATCH"]
    assert needle.projection is not None
    stored = [e for e in needle.projection.identifiers if e["value"] == "04040456999882"]
    # checksum_valid is computed by the node, not taken from the caller.
    assert stored[0]["checksum_valid"] is True


def test_cannot_provide_marks_the_attribute_unavailable(
    session: Session, seeded: SeedReport, settings: NodeSettings, clock: FakeClock
) -> None:
    syringe = _set(session, settings, clock, "3", "design", None, question="q_9")

    assert syringe.projection is not None
    assert syringe.projection.unavailable_attributes == ["design"]
    assert syringe.facts[-1].hub_question_id == "q_9"


def test_answers_are_normalized_and_win(
    session: Session, seeded: SeedReport, settings: NodeSettings, clock: FakeClock
) -> None:
    syringe = _set(session, settings, clock, "3", "connector", EnumValue(value="Luer"))

    assert values(syringe)["connector"] == "LUER"
    assert syringe.projection is not None
    assert syringe.projection.attribute_origin["connector"] == "PURCHASER"


def test_a_new_answer_supersedes_the_previous_answer(
    session: Session, seeded: SeedReport, settings: NodeSettings, clock: FakeClock
) -> None:
    _set(session, settings, clock, "3", "latex_free", BoolValue(value=True))
    syringe = _set(session, settings, clock, "3", "latex_free", None)

    answers = [f for f in syringe.facts if f.attribute_key == "latex_free"]
    assert [f.is_active for f in answers] == [False, True]
    assert answers[0].superseded_by_id == answers[1].id


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("colour", EnumValue(value="RED")),
        ("sterile", EnumValue(value="yes")),
        ("gtin", EnumValue(value="04040456781234")),
        ("gtin", IdentifierValue(scheme=IdentifierScheme.EAN, value="1", checksum_valid=None)),
        ("gtin", None),
    ],
)
def test_invalid_answers_are_refused(
    session: Session,
    seeded: SeedReport,
    settings: NodeSettings,
    clock: FakeClock,
    key: str,
    value: TypedValue | None,
) -> None:
    with pytest.raises(Unprocessable):
        _set(session, settings, clock, "3", key, value)


def test_a_purchaser_category_rereads_the_name(
    session: Session, seeded: SeedReport, settings: NodeSettings, clock: FakeClock
) -> None:
    cup = article(session, "9")
    purchaser = user(session, Role.PURCHASER)

    articles.set_category(
        session,
        cup,
        "syringe_single_use",
        user=purchaser,
        templates=template_sync.installed(session),
        settings=settings,
        now=clock(),
    )

    assert (cup.category_source, cup.category_set_by) == (CategorySource.PURCHASER, purchaser.id)
    assert values(cup)["nominal_volume_ml"] == 100


def test_an_uninstalled_category_is_refused(
    session: Session, seeded: SeedReport, settings: NodeSettings, clock: FakeClock
) -> None:
    with pytest.raises(Unprocessable):
        articles.set_category(
            session,
            article(session, "9"),
            "wipes",
            user=user(session, Role.PURCHASER),
            templates=template_sync.installed(session),
            settings=settings,
            now=clock(),
        )


def test_search_by_text_internal_id_and_reference(session: Session, seeded: SeedReport) -> None:
    syringe = article(session, "3")

    assert [a.internal_id for a in articles.search(session, text="kanüle")] == ["6"]
    assert [a.internal_id for a in articles.search(session, text="3")] == ["3"]
    by_ref = articles.search(session, article_refs=[syringe.article_ref, "ar_000000000000"])
    assert by_ref == [syringe]
    with pytest.raises(NotFound):
        articles.get(session, uuid.UUID(int=0))
