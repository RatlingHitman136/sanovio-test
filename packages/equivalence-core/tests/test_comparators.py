from datetime import UTC, datetime

import pytest

from equivalence_core.comparators import (
    ComparisonStatus,
    DecidedBy,
    Judgment,
    MissingSide,
    compare,
    compare_values,
    keys_needing_judgement,
)
from equivalence_core.exchange.requirement import AttributeOrigin, RequirementPayload
from equivalence_core.facts import Scope, SupplierFact, resolve_supplier
from equivalence_core.ids import new_article_ref
from equivalence_core.templates import TemplateDefinition, TemplateError, load_seed_templates
from equivalence_core.values import (
    AttributeValue,
    BoolValue,
    EnumValue,
    ListValue,
    NumberValue,
    TextValue,
)

NOW = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def syringe() -> TemplateDefinition:
    return load_seed_templates()["syringe_single_use"]


@pytest.fixture(scope="module")
def needle() -> TemplateDefinition:
    return load_seed_templates()["hypodermic_needle"]


def _requirement(
    template: TemplateDefinition,
    attributes: dict[str, AttributeValue],
    *,
    unknown: tuple[str, ...] = (),
    unavailable: tuple[str, ...] = (),
    withheld: tuple[str, ...] = (),
) -> RequirementPayload:
    return RequirementPayload(
        article_ref=new_article_ref(),
        template_code=template.code,
        attributes=attributes,
        attribute_origin=dict.fromkeys(attributes, AttributeOrigin.EXTRACTED),
        unknown_attributes=unknown,
        unavailable_attributes=unavailable,
        withheld_attributes=withheld,
    )


def _supplier(
    template: TemplateDefinition,
    attributes: dict[str, AttributeValue],
    *,
    unavailable: tuple[str, ...] = (),
    scope: Scope = Scope.VARIANT,
):
    facts = [
        SupplierFact(
            id=f"fct_{key}",
            attribute_key=key,
            value=value,
            source="CATALOG",
            scope=scope,
            created_at=NOW,
        )
        for key, value in attributes.items()
    ]
    facts += [
        SupplierFact(
            id=f"fct_{key}_none",
            attribute_key=key,
            value=None,
            source="UNAVAILABLE",
            scope=scope,
            created_at=NOW,
        )
        for key in unavailable
    ]
    return resolve_supplier(facts, template)


def _one(
    template: TemplateDefinition,
    key: str,
    ours: AttributeValue | None,
    theirs: AttributeValue | None,
    **kwargs: object,
) -> Judgment:
    requirement = _requirement(template, {key: ours} if ours is not None else {}, **kwargs)  # type: ignore[arg-type]
    supplier = _supplier(template, {key: theirs} if theirs is not None else {})
    return next(j for j in compare(requirement, supplier, template) if j.attribute_key == key)


@pytest.mark.parametrize(
    ("ours", "theirs", "status"),
    [
        (EnumValue(value="LUER_LOCK"), EnumValue(value="LUER_LOCK"), ComparisonStatus.MATCH),
        (EnumValue(value="LUER_LOCK"), EnumValue(value="LUER"), ComparisonStatus.MISMATCH),
    ],
)
def test_exact_enums(
    syringe: TemplateDefinition,
    ours: AttributeValue,
    theirs: AttributeValue,
    status: ComparisonStatus,
) -> None:
    judgment = _one(syringe, "connector", ours, theirs)

    assert judgment.status is status
    assert judgment.decided_by is DecidedBy.COMPARATOR
    assert judgment.rule == "exact"
    assert judgment.criticality == "critical"


def test_exact_numbers_and_units(syringe: TemplateDefinition) -> None:
    same = _one(
        syringe,
        "nominal_volume_ml",
        NumberValue(value=10, unit="ml"),
        NumberValue(value=10, unit="ml"),
    )
    other = _one(
        syringe,
        "nominal_volume_ml",
        NumberValue(value=10, unit="ml"),
        NumberValue(value=20, unit="ml"),
    )

    assert (same.status, other.status) == (ComparisonStatus.MATCH, ComparisonStatus.MISMATCH)


def test_exact_bools(syringe: TemplateDefinition) -> None:
    judgment = _one(syringe, "sterile", BoolValue(value=True), BoolValue(value=False))

    assert judgment.status is ComparisonStatus.MISMATCH


@pytest.mark.parametrize(
    ("theirs", "status"),
    [
        (0.60, ComparisonStatus.MATCH),
        (0.58, ComparisonStatus.MATCH),  # exactly the ±0.02 tolerance, float noise included
        (0.62, ComparisonStatus.MATCH),  # the other side of it
        (0.63, ComparisonStatus.MISMATCH),
    ],
)
def test_tolerance(needle: TemplateDefinition, theirs: float, status: ComparisonStatus) -> None:
    judgment = _one(
        needle,
        "inner_diameter_mm",
        NumberValue(value=0.60, unit="mm"),
        NumberValue(value=theirs, unit="mm"),
    )

    assert judgment.status is status


@pytest.mark.parametrize(
    ("theirs", "status"),
    [
        (0.5, ComparisonStatus.MATCH),
        (0.2, ComparisonStatus.ACCEPTABLE_DEVIATION),
        (1.0, ComparisonStatus.MISMATCH),
    ],
)
def test_same_or_finer(
    syringe: TemplateDefinition, theirs: float, status: ComparisonStatus
) -> None:
    judgment = _one(
        syringe,
        "graduation_step_ml",
        NumberValue(value=0.5, unit="ml"),
        NumberValue(value=theirs, unit="ml"),
    )

    assert judgment.status is status


@pytest.mark.parametrize(
    ("theirs", "status"),
    [(12, ComparisonStatus.MATCH), (10, ComparisonStatus.MATCH), (9, ComparisonStatus.MISMATCH)],
)
def test_same_or_more(syringe: TemplateDefinition, theirs: float, status: ComparisonStatus) -> None:
    judgment = _one(
        syringe,
        "usable_volume_ml",
        NumberValue(value=10, unit="ml"),
        NumberValue(value=theirs, unit="ml"),
    )

    assert judgment.status is status


def test_includes_lists(syringe: TemplateDefinition) -> None:
    ours = ListValue(value=("ISO 7886-1", "ISO 80369-7"))

    complete = _one(
        syringe, "standards", ours, ListValue(value=("ISO 80369-7", "ISO 7886-1", "ISO 594"))
    )
    partial = _one(syringe, "standards", ours, ListValue(value=("ISO 7886-1",)))

    assert complete.status is ComparisonStatus.MATCH
    assert partial.status is ComparisonStatus.MISMATCH
    assert partial.detail is not None and "ISO 80369-7" in partial.detail


def test_includes_reads_adoptions_and_editions_as_the_same_standard(
    syringe: TemplateDefinition,
) -> None:
    """Found in the real-key run: the catalog said "DIN EN ISO 7864", the hospital "ISO 7864"."""
    ours = ListValue(value=("ISO 7886-1",))

    judgment = _one(syringe, "standards", ours, ListValue(value=("DIN EN ISO 7886-1:2018",)))

    assert judgment.status is ComparisonStatus.MATCH


@pytest.mark.parametrize(
    ("ours", "theirs", "status"),
    [
        (True, True, ComparisonStatus.MATCH),
        (True, False, ComparisonStatus.MISMATCH),
        (False, False, ComparisonStatus.INFO),
        (False, True, ComparisonStatus.INFO),
    ],
)
def test_required_if_hospital(
    syringe: TemplateDefinition, ours: bool, theirs: bool, status: ComparisonStatus
) -> None:
    judgment = _one(syringe, "pump_compatible", BoolValue(value=ours), BoolValue(value=theirs))

    assert judgment.status is status


def test_semantic_text_goes_to_the_judge(syringe: TemplateDefinition) -> None:
    different = _one(
        syringe,
        "stopper_material",
        TextValue(value="Polyisopren"),
        TextValue(value="latexfreier Stopfen"),
    )
    identical = _one(
        syringe, "stopper_material", TextValue(value="Polyisopren"), TextValue(value="Polyisopren")
    )

    assert different.status is ComparisonStatus.NEEDS_JUDGE
    assert identical.status is ComparisonStatus.MATCH


def test_differing_value_types_go_to_the_judge(syringe: TemplateDefinition) -> None:
    judgment = _one(
        syringe, "connector", EnumValue(value="LUER_LOCK"), TextValue(value="Luer-Lock-Ansatz")
    )

    assert judgment.status is ComparisonStatus.NEEDS_JUDGE


def test_info_only_and_derived_never_count(needle: TemplateDefinition) -> None:
    derived = _one(
        needle,
        "outer_diameter_mm",
        NumberValue(value=0.8, unit="mm"),
        NumberValue(value=0.9, unit="mm"),
    )
    missing_derived = _one(needle, "colour_code", None, None)

    assert derived.status is ComparisonStatus.INFO
    assert missing_derived.status is ComparisonStatus.INFO
    assert missing_derived.askable is False


@pytest.mark.parametrize(
    ("ours", "theirs", "missing"),
    [
        (None, EnumValue(value="TWO_PART"), MissingSide.HOSPITAL),
        (EnumValue(value="TWO_PART"), None, MissingSide.SUPPLIER),
        (None, None, MissingSide.BOTH),
    ],
)
def test_unknown_values_name_the_missing_side(
    syringe: TemplateDefinition,
    ours: AttributeValue | None,
    theirs: AttributeValue | None,
    missing: MissingSide,
) -> None:
    judgment = _one(syringe, "design", ours, theirs)

    assert judgment.status is ComparisonStatus.UNKNOWN
    assert judgment.missing is missing
    assert judgment.askable is True


def test_cannot_provide_is_unavailable_on_either_side(syringe: TemplateDefinition) -> None:
    ours = _one(syringe, "dehp_free", None, BoolValue(value=True), unavailable=("dehp_free",))
    requirement = _requirement(syringe, {})
    supplier = _supplier(syringe, {}, unavailable=("dehp_free",))
    theirs = next(
        j for j in compare(requirement, supplier, syringe) if j.attribute_key == "dehp_free"
    )

    assert ours.status is ComparisonStatus.UNAVAILABLE
    assert theirs.status is ComparisonStatus.UNAVAILABLE


def test_withheld_attributes_are_unknown_and_never_asked(syringe: TemplateDefinition) -> None:
    judgment = _one(syringe, "mdr_class", None, EnumValue(value="IIA"), withheld=("mdr_class",))

    assert judgment.status is ComparisonStatus.UNKNOWN
    assert judgment.askable is False
    assert judgment.detail == "withheld by the hospital"


def test_supplier_provenance_survives_the_family_merge(syringe: TemplateDefinition) -> None:
    facts = [
        SupplierFact(
            id="fct_family",
            attribute_key="design",
            value=EnumValue(value="THREE_PART"),
            source="CATALOG",
            scope=Scope.FAMILY,
            created_at=NOW,
        ),
        SupplierFact(
            id="fct_variant",
            attribute_key="connector",
            value=EnumValue(value="LUER_LOCK"),
            source="CATALOG",
            scope=Scope.VARIANT,
            created_at=NOW,
        ),
    ]
    requirement = _requirement(
        syringe, {"design": EnumValue(value="TWO_PART"), "connector": EnumValue(value="LUER_LOCK")}
    )

    judgments = {
        j.attribute_key: j for j in compare(requirement, resolve_supplier(facts, syringe), syringe)
    }

    assert judgments["design"].supplier is not None
    assert judgments["design"].supplier.fact_id == "fct_family"
    assert judgments["design"].supplier.scope is Scope.FAMILY
    assert judgments["connector"].supplier is not None
    assert judgments["connector"].supplier.scope is Scope.VARIANT
    assert judgments["design"].hospital is not None
    assert judgments["design"].hospital.origin is AttributeOrigin.EXTRACTED


def test_every_template_attribute_is_judged_once(syringe: TemplateDefinition) -> None:
    judgments = compare(_requirement(syringe, {}), _supplier(syringe, {}), syringe)

    assert [j.attribute_key for j in judgments] == list(syringe.keys)


def test_a_requirement_for_another_category_is_refused(
    syringe: TemplateDefinition, needle: TemplateDefinition
) -> None:
    with pytest.raises(TemplateError):
        compare(_requirement(needle, {}), _supplier(syringe, {}), syringe)


def test_the_judge_call_is_built_from_needs_judge_only(syringe: TemplateDefinition) -> None:
    requirement = _requirement(
        syringe,
        {
            "stopper_material": TextValue(value="Polyisopren"),
            "connector": EnumValue(value="LUER_LOCK"),
        },
    )
    supplier = _supplier(
        syringe,
        {
            "stopper_material": TextValue(value="latexfreier Stopfen"),
            "connector": EnumValue(value="LUER_LOCK"),
        },
    )

    assert keys_needing_judgement(compare(requirement, supplier, syringe)) == ("stopper_material",)


def test_compare_values_is_usable_on_its_own(syringe: TemplateDefinition) -> None:
    status, detail = compare_values(
        syringe.attribute("graduation_step_ml"),
        NumberValue(value=0.5, unit="ml"),
        NumberValue(value=0.2, unit="ml"),
    )

    assert status is ComparisonStatus.ACCEPTABLE_DEVIATION
    assert detail is not None
