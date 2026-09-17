from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from equivalence_core.facts import (
    HospitalFact,
    HospitalSource,
    ResolvedValue,
    Scope,
    SupplierFact,
    SupplierSource,
    resolve_hospital,
    resolve_supplier,
)
from equivalence_core.identifiers import IdentifierScheme
from equivalence_core.templates import load_seed_templates
from equivalence_core.values import EnumValue, IdentifierValue, NumberValue

SYRINGE = load_seed_templates()["syringe_single_use"]
T0 = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)


def hospital(
    fact_id: str,
    source: HospitalSource,
    value: object = None,
    key: str = "connector",
    minutes: int = 0,
    superseded_by: str | None = None,
) -> HospitalFact:
    return HospitalFact(
        id=fact_id,
        attribute_key=key,
        value=value,
        source=source,
        created_at=T0 + timedelta(minutes=minutes),
        superseded_by=superseded_by,
    )


def supplier(
    fact_id: str, source: SupplierSource, scope: Scope, value: object, minutes: int = 0
) -> SupplierFact:
    return SupplierFact(
        id=fact_id,
        attribute_key="connector",
        value=value,
        source=source,
        scope=scope,
        created_at=T0 + timedelta(minutes=minutes),
    )


LUER = EnumValue(value="LUER")
LUER_LOCK = EnumValue(value="LUER_LOCK")


def _winner(record_attributes: dict[str, ResolvedValue]) -> str:
    return record_attributes["connector"].fact_id


def test_hospital_precedence() -> None:
    facts = [
        hospital("extracted", HospitalSource.EXTRACTION, LUER),
        hospital("master", HospitalSource.HOSPITAL_MASTER, LUER),
        hospital("reference", HospitalSource.REFERENCE_ITEM, LUER),
        hospital("answer", HospitalSource.PURCHASER_ANSWER, LUER_LOCK),
    ]
    for present in range(len(facts), 0, -1):
        record = resolve_hospital(facts[:present], SYRINGE)
        assert _winner(record.attributes) == facts[present - 1].id


def test_newer_fact_wins_within_the_same_source() -> None:
    facts = [
        hospital("old", HospitalSource.PURCHASER_ANSWER, LUER),
        hospital("new", HospitalSource.PURCHASER_ANSWER, LUER_LOCK, minutes=5),
    ]
    assert _winner(resolve_hospital(facts, SYRINGE).attributes) == "new"


def test_superseded_facts_are_ignored() -> None:
    facts = [
        hospital("corrected", HospitalSource.PURCHASER_ANSWER, LUER, superseded_by="fixed"),
        hospital("fixed", HospitalSource.EXTRACTION, LUER_LOCK),
    ]
    assert _winner(resolve_hospital(facts, SYRINGE).attributes) == "fixed"


def test_supplier_precedence_with_family_and_variant() -> None:
    family_answer = supplier("family_answer", SupplierSource.SUPPLIER_ANSWER, Scope.FAMILY, LUER)
    variant_catalog = supplier("variant_catalog", SupplierSource.CATALOG, Scope.VARIANT, LUER)
    family_catalog = supplier("family_catalog", SupplierSource.CATALOG, Scope.FAMILY, LUER)
    variant_extraction = supplier("variant_extr", SupplierSource.EXTRACTION, Scope.VARIANT, LUER)

    def winner(*facts: SupplierFact) -> str:
        return _winner(resolve_supplier(facts, SYRINGE).attributes)

    assert winner(variant_catalog, family_answer) == "family_answer"
    assert winner(family_catalog, variant_catalog) == "variant_catalog"
    assert winner(variant_extraction, family_catalog) == "family_catalog"


def test_unavailable_is_reported_separately() -> None:
    facts = [
        hospital("extracted", HospitalSource.EXTRACTION, LUER),
        hospital("cannot", HospitalSource.UNAVAILABLE, None, minutes=1),
    ]
    record = resolve_hospital(facts, SYRINGE)

    assert "connector" not in record.attributes
    assert record.unavailable_attributes == ("connector",)
    assert "connector" not in record.unknown_attributes


def test_unknown_lists_every_template_attribute_without_a_value() -> None:
    record = resolve_hospital([hospital("a", HospitalSource.EXTRACTION, LUER)], SYRINGE)

    assert set(record.unknown_attributes) == set(SYRINGE.keys) - {"connector"}


def test_facts_outside_the_template_are_ignored() -> None:
    record = resolve_hospital(
        [hospital("a", HospitalSource.PURCHASER_ANSWER, LUER, key="peel_off_label")], SYRINGE
    )
    assert record.attributes == {}


def _gtin(fact_id: str, code: str, valid: bool) -> HospitalFact:
    value = IdentifierValue(scheme=IdentifierScheme.GTIN, value=code, checksum_valid=valid)
    return hospital(fact_id, HospitalSource.HOSPITAL_MASTER, value, key="gtin")


def test_identifiers_are_kept_as_a_set_and_never_as_attributes() -> None:
    record = resolve_hospital(
        [_gtin("carton", "14040456781231", False), _gtin("unit", "04040456781234", True)], SYRINGE
    )

    assert [entry.fact_id for entry in record.identifiers] == ["unit", "carton"]
    assert "gtin" not in record.attributes
    assert "gtin" not in record.unknown_attributes


def test_record_hash_ignores_fact_order_and_changes_with_values() -> None:
    volume = hospital(
        "v", HospitalSource.EXTRACTION, NumberValue(value=10, unit="ml"), key="nominal_volume_ml"
    )
    connector = hospital("c", HospitalSource.EXTRACTION, LUER_LOCK)
    gtin = _gtin("g", "04040456781234", True)

    base = resolve_hospital([volume, connector, gtin], SYRINGE).record_hash()

    assert resolve_hospital([gtin, connector, volume], SYRINGE).record_hash() == base
    changed = hospital("c2", HospitalSource.EXTRACTION, LUER)
    assert resolve_hospital([volume, changed, gtin], SYRINGE).record_hash() != base
    assert resolve_hospital([volume, connector], SYRINGE).record_hash() != base


def test_value_is_required_unless_unavailable() -> None:
    with pytest.raises(ValidationError):
        hospital("x", HospitalSource.EXTRACTION, None)
    with pytest.raises(ValidationError):
        hospital("x", HospitalSource.UNAVAILABLE, LUER)
