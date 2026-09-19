"""Deterministic attribute comparison (ARCHITECTURE §8.4).

The hospital side is a requirement, the supplier side a resolved record. Every template attribute
gets one judgment, and a comparator's decision is final: the judge only sees what is left over.
Nothing is ever guessed — a value the rules cannot read becomes `NEEDS_JUDGE`, never a mismatch.
"""

from collections.abc import Sequence
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from equivalence_core.exchange.requirement import AttributeOrigin, RequirementPayload
from equivalence_core.facts import ResolvedRecord, Scope
from equivalence_core.parsers.standards import canonical_standard
from equivalence_core.parsers.wording import canonical_text
from equivalence_core.templates.model import (
    ComparisonRule,
    Criticality,
    ResolvedAttribute,
    TemplateDefinition,
    TemplateError,
)
from equivalence_core.values import AttributeValue, ListValue, NumberValue, TextValue

# Numbers arrive in the template's canonical unit; this only absorbs float noise.
EPSILON = 1e-9


class ComparisonStatus(StrEnum):
    MATCH = "MATCH"
    ACCEPTABLE_DEVIATION = "ACCEPTABLE_DEVIATION"
    MISMATCH = "MISMATCH"
    UNKNOWN = "UNKNOWN"
    # A side answered "cannot provide"; §11's stop condition tells this from UNKNOWN.
    UNAVAILABLE = "UNAVAILABLE"
    # Shown, never counted: info_only and derived attributes.
    INFO = "INFO"
    # Left to the judge on purpose (semantic rules, or values whose types do not line up).
    NEEDS_JUDGE = "NEEDS_JUDGE"


# The reason on a text judgment the comparators leave open because only the wording differs;
# the hub reads these by meaning with a small model before the judge sees anything (§8).
WORDED_DIFFERENTLY = "worded differently"


class DecidedBy(StrEnum):
    COMPARATOR = "COMPARATOR"
    LLM = "LLM"


class MissingSide(StrEnum):
    HOSPITAL = "HOSPITAL"
    SUPPLIER = "SUPPLIER"
    BOTH = "BOTH"


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HospitalSide(_Frozen):
    """What the requirement carried; no node fact ids ever leave the node (§16)."""

    value: AttributeValue
    origin: AttributeOrigin


class SupplierSide(_Frozen):
    value: AttributeValue
    fact_id: str
    scope: Scope | None = None


class Judgment(_Frozen):
    """One attribute's result, stored as it is in `assessment_rounds.attribute_judgments`."""

    attribute_key: str
    criticality: Criticality
    rule: ComparisonRule
    status: ComparisonStatus
    decided_by: DecidedBy = DecidedBy.COMPARATOR
    hospital: HospitalSide | None = None
    supplier: SupplierSide | None = None
    missing: MissingSide | None = None
    # False when a gap must not become a question: the hospital withheld the attribute (§16).
    askable: bool = True
    detail: str | None = None
    confidence: float | None = None
    rationale: str | None = None

    @model_validator(mode="after")
    def _missing_matches_status(self) -> Self:
        gaps = {ComparisonStatus.UNKNOWN, ComparisonStatus.UNAVAILABLE}
        if (self.missing is not None) and self.status not in gaps:
            raise ValueError("only an UNKNOWN or UNAVAILABLE judgment names a missing side")
        return self


def compare(
    requirement: RequirementPayload, supplier: ResolvedRecord, template: TemplateDefinition
) -> tuple[Judgment, ...]:
    """One judgment per template attribute, in template order.

    Identifiers are not part of this: they are evidence before the comparison, never compared
    (D51), and the requirement has no place for them at all.
    """
    if requirement.template_code != template.code:
        raise TemplateError(
            f"requirement is for {requirement.template_code!r}, not {template.code!r}"
        )
    return tuple(
        _judge_attribute(attribute, requirement, supplier) for attribute in template.attributes
    )


def compare_values(
    attribute: ResolvedAttribute, hospital: AttributeValue, supplier: AttributeValue
) -> tuple[ComparisonStatus, str | None]:
    """The rule applied to two known values: status and, when it helps, a short reason."""
    if attribute.rule in (ComparisonRule.INFO_ONLY, ComparisonRule.DERIVED):
        return ComparisonStatus.INFO, None
    if type(hospital) is not type(supplier):
        # e.g. an enum against free text: the judge decides, a spelling can never be a mismatch.
        return ComparisonStatus.NEEDS_JUDGE, "the two sides state this differently"
    match attribute.rule:
        case ComparisonRule.EXACT:
            return _exact(hospital, supplier)
        case ComparisonRule.TOLERANCE:
            return _tolerance(attribute, hospital, supplier)
        case ComparisonRule.SAME_OR_FINER:
            return _same_or_finer(hospital, supplier)
        case ComparisonRule.SAME_OR_MORE:
            return _same_or_more(hospital, supplier)
        case ComparisonRule.INCLUDES:
            return _includes(hospital, supplier)
        case ComparisonRule.REQUIRED_IF_HOSPITAL:
            return _required_if_hospital(hospital, supplier)
        case ComparisonRule.SEMANTIC:
            return _semantic(hospital, supplier)
    raise TemplateError(f"no comparator for rule {attribute.rule}")


def _judge_attribute(
    attribute: ResolvedAttribute, requirement: RequirementPayload, supplier: ResolvedRecord
) -> Judgment:
    key = attribute.key
    hospital_value = requirement.attributes.get(key)
    resolved = supplier.attributes.get(key)
    hospital = (
        HospitalSide(value=hospital_value, origin=requirement.attribute_origin[key])
        if hospital_value is not None
        else None
    )
    supplier_side = (
        SupplierSide(value=resolved.value, fact_id=resolved.fact_id, scope=resolved.scope)
        if resolved is not None
        else None
    )
    if hospital is None or supplier_side is None:
        return _gap(attribute, requirement, supplier, hospital, supplier_side)
    status, detail = compare_values(attribute, hospital.value, supplier_side.value)
    return Judgment(
        attribute_key=key,
        criticality=attribute.criticality,
        rule=attribute.rule,
        status=status,
        hospital=hospital,
        supplier=supplier_side,
        detail=detail,
    )


def _gap(
    attribute: ResolvedAttribute,
    requirement: RequirementPayload,
    supplier: ResolvedRecord,
    hospital: HospitalSide | None,
    supplier_side: SupplierSide | None,
) -> Judgment:
    """What is missing, on which side, and whether anyone may be asked about it."""
    key = attribute.key
    hospital_unavailable = key in requirement.unavailable_attributes
    supplier_unavailable = key in supplier.unavailable_attributes
    withheld = key in requirement.withheld_attributes
    missing = (
        MissingSide.BOTH
        if hospital is None and supplier_side is None
        else MissingSide.HOSPITAL
        if hospital is None
        else MissingSide.SUPPLIER
    )
    unavailable = (hospital is None and hospital_unavailable) or (
        supplier_side is None and supplier_unavailable
    )
    status = ComparisonStatus.UNAVAILABLE if unavailable else ComparisonStatus.UNKNOWN
    if attribute.rule in (ComparisonRule.INFO_ONLY, ComparisonRule.DERIVED):
        # Information-only attributes never become a gap, so they never block or get asked.
        return Judgment(
            attribute_key=key,
            criticality=attribute.criticality,
            rule=attribute.rule,
            status=ComparisonStatus.INFO,
            hospital=hospital,
            supplier=supplier_side,
            askable=False,
        )
    return Judgment(
        attribute_key=key,
        criticality=attribute.criticality,
        rule=attribute.rule,
        status=status,
        hospital=hospital,
        supplier=supplier_side,
        missing=missing,
        askable=not withheld and status is ComparisonStatus.UNKNOWN,
        detail="withheld by the hospital" if withheld else None,
    )


def _exact(
    hospital: AttributeValue, supplier: AttributeValue
) -> tuple[ComparisonStatus, str | None]:
    if isinstance(hospital, NumberValue) and isinstance(supplier, NumberValue):
        return _numbers_equal(hospital, supplier), None
    if isinstance(hospital, TextValue) and isinstance(supplier, TextValue):
        # Free text written differently is not yet a mismatch: a model reads it by meaning.
        if canonical_text(hospital.value) == canonical_text(supplier.value):
            return ComparisonStatus.MATCH, None
        return ComparisonStatus.NEEDS_JUDGE, WORDED_DIFFERENTLY
    return (ComparisonStatus.MATCH if hospital == supplier else ComparisonStatus.MISMATCH), None


def _tolerance(
    attribute: ResolvedAttribute, hospital: AttributeValue, supplier: AttributeValue
) -> tuple[ComparisonStatus, str | None]:
    numbers = _numbers(attribute, hospital, supplier)
    if numbers is None:
        return ComparisonStatus.NEEDS_JUDGE, "not a number on both sides"
    ours, theirs = numbers
    tolerance = attribute.tolerance or 0.0
    difference = abs(ours - theirs)
    if difference <= tolerance + EPSILON:
        return ComparisonStatus.MATCH, None
    return ComparisonStatus.MISMATCH, f"differs by {difference:g}, tolerated is {tolerance:g}"


def _same_or_finer(
    hospital: AttributeValue, supplier: AttributeValue
) -> tuple[ComparisonStatus, str | None]:
    """A smaller step is finer: acceptable, but worth showing."""
    values = _plain_numbers(hospital, supplier)
    if values is None:
        return ComparisonStatus.NEEDS_JUDGE, "not a number on both sides"
    ours, theirs = values
    if abs(ours - theirs) <= EPSILON:
        return ComparisonStatus.MATCH, None
    if theirs < ours:
        return ComparisonStatus.ACCEPTABLE_DEVIATION, f"finer: {theirs:g} instead of {ours:g}"
    return ComparisonStatus.MISMATCH, f"coarser: {theirs:g} instead of {ours:g}"


def _same_or_more(
    hospital: AttributeValue, supplier: AttributeValue
) -> tuple[ComparisonStatus, str | None]:
    values = _plain_numbers(hospital, supplier)
    if values is None:
        return ComparisonStatus.NEEDS_JUDGE, "not a number on both sides"
    ours, theirs = values
    if theirs + EPSILON >= ours:
        return ComparisonStatus.MATCH, None
    return ComparisonStatus.MISMATCH, f"less than required: {theirs:g} < {ours:g}"


def _includes(
    hospital: AttributeValue, supplier: AttributeValue
) -> tuple[ComparisonStatus, str | None]:
    if not isinstance(hospital, ListValue) or not isinstance(supplier, ListValue):
        return ComparisonStatus.NEEDS_JUDGE, "not a list on both sides"
    offered = {canonical_standard(entry) for entry in supplier.value}
    missing = [entry for entry in hospital.value if canonical_standard(entry) not in offered]
    if not missing:
        return ComparisonStatus.MATCH, None
    return ComparisonStatus.MISMATCH, f"missing: {', '.join(missing)}"


def _required_if_hospital(
    hospital: AttributeValue, supplier: AttributeValue
) -> tuple[ComparisonStatus, str | None]:
    """Binds only when the hospital needs the property; otherwise it is information."""
    if hospital.value is not True:
        return ComparisonStatus.INFO, None
    if supplier.value is True:
        return ComparisonStatus.MATCH, None
    return ComparisonStatus.MISMATCH, "the hospital needs this property"


def _semantic(
    hospital: AttributeValue, supplier: AttributeValue
) -> tuple[ComparisonStatus, str | None]:
    if hospital == supplier or _same_text(hospital, supplier):
        return ComparisonStatus.MATCH, None
    return ComparisonStatus.NEEDS_JUDGE, "free text; the judge decides"


def _same_text(hospital: AttributeValue, supplier: AttributeValue) -> bool:
    return (
        isinstance(hospital, TextValue)
        and isinstance(supplier, TextValue)
        and canonical_text(hospital.value) == canonical_text(supplier.value)
    )


def _numbers_equal(hospital: NumberValue, supplier: NumberValue) -> ComparisonStatus:
    if hospital.unit != supplier.unit:
        return ComparisonStatus.MISMATCH
    same = abs(hospital.value - supplier.value) <= EPSILON
    return ComparisonStatus.MATCH if same else ComparisonStatus.MISMATCH


def _numbers(
    attribute: ResolvedAttribute, hospital: AttributeValue, supplier: AttributeValue
) -> tuple[float, float] | None:
    if not isinstance(hospital, NumberValue) or not isinstance(supplier, NumberValue):
        return None
    if attribute.unit not in (hospital.unit, None) or hospital.unit != supplier.unit:
        return None
    return hospital.value, supplier.value


def _plain_numbers(
    hospital: AttributeValue, supplier: AttributeValue
) -> tuple[float, float] | None:
    if not isinstance(hospital, NumberValue) or not isinstance(supplier, NumberValue):
        return None
    if hospital.unit != supplier.unit:
        return None
    return hospital.value, supplier.value


def keys_needing_judgement(judgments: Sequence[Judgment]) -> tuple[str, ...]:
    """What the judge call is built from (§8.4); everything else is already decided."""
    return tuple(
        judgment.attribute_key
        for judgment in judgments
        if judgment.status is ComparisonStatus.NEEDS_JUDGE
    )
