import json

from sqlalchemy.orm import Session

from equivalence_core.exchange.requirement import RequirementPayload
from equivalence_core.values import EnumValue, TextValue
from hospital_node.core.settings import NodeSettings
from hospital_node.models import HospitalArticle
from hospital_node.models.users import Role
from hospital_node.services import articles, normalization, projection, template_sync
from hospital_node.services.requirement_builder import MAX_TEXT_LENGTH
from hospital_node.services.seed import SeedReport
from node_fixtures import FakeClock, article, user, values


def _requirement(
    session: Session, found: HospitalArticle, settings: NodeSettings
) -> RequirementPayload:
    assert found.projection is not None
    template = template_sync.installed(session)[found.category_code or ""]
    return projection.issue_requirement(found, found.projection, template, settings)


def test_the_requirement_carries_no_article_data(
    session: Session, seeded: SeedReport, settings: NodeSettings, clock: FakeClock
) -> None:
    """Every field of the master record is distinctive here, so a leak cannot hide."""
    raw = {
        "internal_id": "ZZINTERNALZZ",
        "Artikelbezeichnung": "Einmalspritze 10 ml Luer-Lock steril ZZNAMEZZ",
        "Marke": "ZZBRANDZZ",
        "Artikelnummer": "ZZARTNOZZ",
        "Jahresmenge": "424242",
        "Bestellmengeneinheit": "ZZORDERUNITZZ",
        "Basismengeneinheiten pro BME": "777",
        "Basismengeneinheit": "ZZBASEUNITZZ",
        "GTIN": "'04040456781234",
        "EAN": "'4040456781237",
        "MDR-Klasse": "IIa",
        "Netto-Zielpreis": "98.7654",
        "Währung": "ZZZ",
    }
    templates = template_sync.installed(session)
    secret = articles.ingest(session, raw, templates=templates, now=clock())
    normalization.normalize(
        session, [secret], templates=templates, llm=None, settings=settings, now=clock()
    )

    payload = json.dumps(_requirement(session, secret, settings).model_dump(mode="json"))

    for value in raw.values():
        assert value.lstrip("'") not in payload, value
    assert "Luer-Lock" not in payload  # the evidence quote
    assert "04040456781234" not in payload  # the identifier
    assert secret.article_ref in payload


def test_only_shareable_attributes_are_sent(
    session: Session, seeded: SeedReport, settings: NodeSettings
) -> None:
    syringe = article(session, "3")

    requirement = _requirement(session, syringe, settings)

    assert requirement.template_code == "syringe_single_use"
    assert requirement.attributes["connector"] == EnumValue(value="LUER_LOCK")
    assert requirement.attribute_origin["connector"] == "EXTRACTED"
    assert requirement.attribute_origin["mdr_class"] == "MASTER"
    # units_per_order_unit is a quantity, marked not shareable in the template.
    assert "units_per_order_unit" not in requirement.attributes
    assert "units_per_order_unit" not in requirement.unknown_attributes
    assert "design" in requirement.unknown_attributes
    assert requirement.product_hints is None
    assert requirement.limited_template is False


def test_the_projection_hash_is_the_hash_of_this_requirement(
    session: Session, seeded: SeedReport, settings: NodeSettings
) -> None:
    syringe = article(session, "3")

    assert syringe.projection is not None
    assert _requirement(session, syringe, settings).requirement_hash() == (
        syringe.projection.requirement_hash
    )


def test_denied_attributes_are_withheld(
    session: Session, seeded: SeedReport, settings: NodeSettings
) -> None:
    strict = settings.model_copy(update={"egress_deny_attributes": frozenset({"mdr_class"})})

    requirement = _requirement(session, article(session, "3"), strict)

    assert requirement.withheld_attributes == ("mdr_class",)
    assert "mdr_class" not in requirement.attributes


def test_long_free_text_is_sent_as_unknown(
    session: Session, seeded: SeedReport, settings: NodeSettings, clock: FakeClock
) -> None:
    syringe = article(session, "3")
    long_text = "Polyisopren, " * 10

    articles.set_fact(
        session,
        syringe,
        "stopper_material",
        TextValue(value=long_text),
        hub_question_id=None,
        user=user(session, Role.PURCHASER),
        templates=template_sync.installed(session),
        settings=settings,
        now=clock(),
    )

    assert len(values(syringe)["stopper_material"]) > MAX_TEXT_LENGTH
    requirement = _requirement(session, syringe, settings)
    assert "stopper_material" not in requirement.attributes
    assert "stopper_material" in requirement.unknown_attributes


def test_short_free_text_is_sent(
    session: Session, seeded: SeedReport, settings: NodeSettings, clock: FakeClock
) -> None:
    syringe = article(session, "3")

    articles.set_fact(
        session,
        syringe,
        "stopper_material",
        TextValue(value="Polyisopren"),
        hub_question_id=None,
        user=user(session, Role.PURCHASER),
        templates=template_sync.installed(session),
        settings=settings,
        now=clock(),
    )

    assert _requirement(session, syringe, settings).attributes["stopper_material"] == TextValue(
        value="Polyisopren"
    )


def test_product_hints_only_when_enabled_and_only_valid_identifiers(
    session: Session, seeded: SeedReport, settings: NodeSettings
) -> None:
    sharing = settings.model_copy(update={"share_product_hints": True})

    syringe = _requirement(session, article(session, "3"), sharing).product_hints
    needle = _requirement(session, article(session, "6"), sharing).product_hints

    assert syringe is not None
    assert (syringe.brand, syringe.gtin, syringe.manufacturer_article_no) == (
        "B. Braun",
        "04040456781234",
        "9154010",
    )
    # Article 6's GTIN fails its check digit, so it is left out; the article number still goes.
    assert needle is not None
    assert (needle.gtin, needle.manufacturer_article_no) == (None, "4657689")


def test_unavailable_attributes_are_reported(
    session: Session, seeded: SeedReport, settings: NodeSettings, clock: FakeClock
) -> None:
    syringe = article(session, "3")

    articles.set_fact(
        session,
        syringe,
        "dehp_free",
        None,
        hub_question_id="q_3",
        user=user(session, Role.PURCHASER),
        templates=template_sync.installed(session),
        settings=settings,
        now=clock(),
    )

    requirement = _requirement(session, syringe, settings)
    assert requirement.unavailable_attributes == ("dehp_free",)
    assert "dehp_free" not in requirement.unknown_attributes


def test_the_generic_template_is_marked_limited(
    session: Session, seeded: SeedReport, settings: NodeSettings
) -> None:
    assert _requirement(session, article(session, "1"), settings).limited_template is True
