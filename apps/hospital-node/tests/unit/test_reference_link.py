import pytest
from sqlalchemy.orm import Session

from equivalence_core.facts import HospitalSource
from equivalence_core.identifiers import IdentifierScheme
from equivalence_core.templates import TemplateDefinition
from equivalence_core.values import BoolValue, EnumValue, IdentifierValue, NumberValue
from hospital_node.core.settings import NodeSettings
from hospital_node.models import HospitalArticle
from hospital_node.models.users import Role
from hospital_node.services import articles, reference_link, template_sync
from hospital_node.services.errors import Unprocessable
from hospital_node.services.reference_link import Choice, Reported
from hospital_node.services.seed import SeedReport
from node_fixtures import FakeClock, article, user, values

# Injekt® Luer Lock Solo 10 ml as the hub would report it (ARCHITECTURE §21).
INJEKT = {
    "nominal_volume_ml": Reported(NumberValue(value=10, unit="ml"), "fct_10"),
    "connector": Reported(EnumValue(value="LUER_LOCK"), "fct_11"),
    "design": Reported(EnumValue(value="TWO_PART"), "fct_40"),
    "cone_position": Reported(EnumValue(value="CENTRIC"), "fct_41"),
    "graduation_step_ml": Reported(NumberValue(value=0.5, unit="ml"), "fct_42"),
    "latex_free": Reported(BoolValue(value=True), "fct_43"),
    "gtin": Reported(
        IdentifierValue(scheme=IdentifierScheme.GTIN, value="04022495000011", checksum_valid=True)
    ),
    "colour_code": Reported(EnumValue(value="GREEN")),
}


@pytest.fixture
def syringe(session: Session, seeded: SeedReport) -> HospitalArticle:
    return article(session, "3")


@pytest.fixture
def template(session: Session, seeded: SeedReport) -> TemplateDefinition:
    return template_sync.installed(session)["syringe_single_use"]


def _link(
    session: Session,
    target: HospitalArticle,
    template: TemplateDefinition,
    settings: NodeSettings,
    clock: FakeClock,
    reported: dict[str, Reported],
    choices: dict[str, Choice] | None = None,
    variant: str = "var_injekt_ll_10",
) -> reference_link.Preview:
    return reference_link.link(
        session,
        target,
        template,
        variant_id=variant,
        label="Injekt® Luer Lock Solo 10 ml (4606728V)",
        reported=reported,
        choices=choices or {},
        user=user(session, Role.PURCHASER),
        settings=settings,
        now=clock(),
    )


def test_preview_lists_fills_and_leaves_identifiers_alone(
    syringe: HospitalArticle, template: TemplateDefinition
) -> None:
    plan = reference_link.preview(syringe, template, INJEKT)

    assert sorted(plan.fills) == ["cone_position", "design", "graduation_step_ml", "latex_free"]
    assert plan.conflicts == {}
    assert list(plan.identifiers) == ["gtin"]
    assert plan.ignored == ["colour_code"]


def test_linking_fills_unknowns_with_hub_provenance_and_no_identifier(
    session: Session,
    syringe: HospitalArticle,
    template: TemplateDefinition,
    settings: NodeSettings,
    clock: FakeClock,
) -> None:
    _link(session, syringe, template, settings, clock, INJEKT)

    assert values(syringe)["design"] == "TWO_PART"
    assert syringe.projection is not None
    assert syringe.projection.attribute_origin["design"] == "REFERENCE"
    reference = [f for f in syringe.facts if f.source == HospitalSource.REFERENCE_ITEM]
    assert {(f.attribute_key, f.hub_variant_id, f.hub_fact_id) for f in reference} >= {
        ("design", "var_injekt_ll_10", "fct_40")
    }
    assert all(f.attribute_key != "gtin" for f in reference)
    assert [e["value"] for e in syringe.projection.identifiers if e["scheme"] == "GTIN"] == [
        "04040456781234"
    ]
    assert syringe.reference_hub_variant_id == "var_injekt_ll_10"
    assert syringe.reference_source == "CLIENT_REPORTED"


def test_conflicts_need_a_choice(
    session: Session,
    syringe: HospitalArticle,
    template: TemplateDefinition,
    settings: NodeSettings,
    clock: FakeClock,
) -> None:
    luer = INJEKT | {"connector": Reported(EnumValue(value="LUER"))}

    plan = reference_link.preview(syringe, template, luer)
    assert plan.conflicts["connector"].ours == EnumValue(value="LUER_LOCK")
    assert plan.conflicts["connector"].ours_source == HospitalSource.EXTRACTION

    with pytest.raises(Unprocessable, match="connector"):
        _link(session, syringe, template, settings, clock, luer)
    assert syringe.reference_hub_variant_id is None


def test_keep_ours_keeps_the_extracted_value(
    session: Session,
    syringe: HospitalArticle,
    template: TemplateDefinition,
    settings: NodeSettings,
    clock: FakeClock,
) -> None:
    luer = INJEKT | {"connector": Reported(EnumValue(value="LUER"))}

    _link(session, syringe, template, settings, clock, luer, {"connector": Choice.KEEP_OURS})

    assert values(syringe)["connector"] == "LUER_LOCK"


def test_take_reference_replaces_the_extracted_value(
    session: Session,
    syringe: HospitalArticle,
    template: TemplateDefinition,
    settings: NodeSettings,
    clock: FakeClock,
) -> None:
    luer = INJEKT | {"connector": Reported(EnumValue(value="LUER"))}

    _link(session, syringe, template, settings, clock, luer, {"connector": Choice.TAKE_REFERENCE})

    assert values(syringe)["connector"] == "LUER"


def test_purchaser_answers_are_never_overridden(
    session: Session,
    syringe: HospitalArticle,
    template: TemplateDefinition,
    settings: NodeSettings,
    clock: FakeClock,
) -> None:
    articles.set_fact(
        session,
        syringe,
        "design",
        EnumValue(value="THREE_PART"),
        hub_question_id=None,
        user=user(session, Role.PURCHASER),
        templates=template_sync.installed(session),
        settings=settings,
        now=clock(),
    )

    plan = _link(session, syringe, template, settings, clock, INJEKT)

    assert "design" in plan.kept_purchaser
    assert values(syringe)["design"] == "THREE_PART"


def test_a_second_product_replaces_the_first(
    session: Session,
    syringe: HospitalArticle,
    template: TemplateDefinition,
    settings: NodeSettings,
    clock: FakeClock,
) -> None:
    _link(session, syringe, template, settings, clock, INJEKT)
    clock.advance(minutes=1)
    plastipak = {
        "design": Reported(EnumValue(value="THREE_PART"), "fct_90"),
        "graduation_step_ml": Reported(NumberValue(value=0.2, unit="ml"), "fct_91"),
    }

    plan = _link(session, syringe, template, settings, clock, plastipak, variant="var_300912")

    # Compared with the article without its old product, so these are fills, not conflicts.
    assert sorted(plan.fills) == ["design", "graduation_step_ml"]
    current = values(syringe)
    assert (current["design"], current["graduation_step_ml"]) == ("THREE_PART", 0.2)
    assert "cone_position" not in current
    assert syringe.reference_hub_variant_id == "var_300912"


def test_unlinking_restores_the_previous_projection(
    session: Session,
    syringe: HospitalArticle,
    template: TemplateDefinition,
    settings: NodeSettings,
    clock: FakeClock,
) -> None:
    assert syringe.projection is not None
    before = syringe.projection.record_hash
    _link(session, syringe, template, settings, clock, INJEKT)
    assert syringe.projection.record_hash != before

    reference_link.unlink(session, syringe, template, settings=settings, now=clock())

    assert syringe.projection.record_hash == before
    assert syringe.reference_hub_variant_id is None
