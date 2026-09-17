"""Reads attribute values out of a short article name, e.g. "Einmalspritze 10 ml Luer-Lock steril".

Only what the text states is returned; anything else stays unknown. The ISO 6009 table is the one
exception: a gauge and an outer diameter imply each other, so either one fills in the other.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from equivalence_core.parsers.dimensions import Measurement, Quantity, find_measurements
from equivalence_core.parsers.gauge import (
    gauge_diameter_consistent,
    gauge_for_outer_diameter,
    outer_diameter_for_gauge,
)
from equivalence_core.parsers.synonyms import find_codes
from equivalence_core.parsers.units import UnitError, to_canonical
from equivalence_core.quality import DataQualityIssue
from equivalence_core.templates.model import TemplateDefinition, TemplateError, ValueType
from equivalence_core.values import AttributeValue, BoolValue, EnumValue, NumberValue

_VOLUME_UNITS = frozenset({"ml", "l"})
_LENGTH_UNITS = frozenset({"mm", "cm", "m", "µm", "um", '"', "″"})
_USABLE_VOLUME_CUE = "nutzbar"


@dataclass(frozen=True)
class Extraction:
    attribute_key: str
    value: AttributeValue
    quote: str
    # True when the value comes from the ISO 6009 table rather than from the text itself.
    derived: bool = False


@dataclass(frozen=True)
class NameReading:
    extractions: tuple[Extraction, ...]
    issues: tuple[DataQualityIssue, ...]

    def value_of(self, key: str) -> AttributeValue | None:
        return next((e.value for e in self.extractions if e.attribute_key == key), None)


def extract_attributes(text: str, template: TemplateDefinition) -> NameReading:
    found: dict[str, Extraction] = {}
    for extraction in _from_measurements(text, template):
        found.setdefault(extraction.attribute_key, extraction)
    for extraction in _from_synonyms(text, template):
        found.setdefault(extraction.attribute_key, extraction)
    issues = _complete_gauge_and_diameter(found, template)
    return NameReading(tuple(found.values()), tuple(issues))


def _from_measurements(text: str, template: TemplateDefinition) -> Iterable[Extraction]:
    keys = set(template.keys)
    for measurement in find_measurements(text):
        quantities = measurement.quantities
        if len(quantities) == 2:
            yield from _pair(measurement, keys, template)
        elif quantities[0].unit in _VOLUME_UNITS:
            before = text[: measurement.start].casefold()
            key = "usable_volume_ml" if _USABLE_VOLUME_CUE in before else "nominal_volume_ml"
            if key in keys:
                yield from _number(key, quantities[0], measurement.quote, template)
        elif quantities[0].unit == "G" and "gauge" in keys:
            yield from _number("gauge", quantities[0], measurement.quote, template)


def _pair(
    measurement: Measurement, keys: set[str], template: TemplateDefinition
) -> Iterable[Extraction]:
    first, second = measurement.quantities
    if second.unit not in _LENGTH_UNITS or "length_mm" not in keys:
        return
    # A needle size is written "diameter × length" or "gauge × length".
    first_key = "gauge" if first.unit == "G" else "outer_diameter_mm"
    if first_key in keys:
        yield from _number(first_key, first, measurement.quote, template)
    yield from _number("length_mm", second, measurement.quote, template)


def _number(
    key: str, quantity: Quantity, quote: str, template: TemplateDefinition
) -> Iterable[Extraction]:
    unit = template.attribute(key).unit
    if unit is None:
        raise TemplateError(f"{template.code}: number attribute {key!r} has no unit")
    try:
        value = to_canonical(quantity.value, quantity.unit, unit)
    except UnitError:
        return  # a quantity that cannot be expressed in the template's unit stays unknown
    yield Extraction(key, NumberValue(value=value, unit=unit), quote)


def _from_synonyms(text: str, template: TemplateDefinition) -> Iterable[Extraction]:
    for attribute in template.attributes:
        if not attribute.synonyms:
            continue
        matches = find_codes(text, attribute)
        # Contradicting phrases ("steril", "unsteril") leave the attribute unknown.
        if len({match.code for match in matches}) != 1:
            continue
        match = matches[0]
        value: AttributeValue = (
            BoolValue(value=match.code == "true")
            if attribute.type is ValueType.BOOL
            else EnumValue(value=match.code)
        )
        yield Extraction(attribute.key, value, match.quote)


def _complete_gauge_and_diameter(
    found: dict[str, Extraction], template: TemplateDefinition
) -> list[DataQualityIssue]:
    if not {"gauge", "outer_diameter_mm"} <= set(template.keys):
        return []
    gauge, diameter = found.get("gauge"), found.get("outer_diameter_mm")
    if gauge and diameter:
        consistent = gauge_diameter_consistent(_float(gauge), _float(diameter))
        return [] if consistent else [DataQualityIssue.GAUGE_DIAMETER_MISMATCH]
    if diameter and (derived_gauge := gauge_for_outer_diameter(_float(diameter))) is not None:
        found["gauge"] = Extraction(
            "gauge", NumberValue(value=derived_gauge, unit="G"), diameter.quote, derived=True
        )
    if gauge and (derived_diameter := outer_diameter_for_gauge(_float(gauge))) is not None:
        found["outer_diameter_mm"] = Extraction(
            "outer_diameter_mm",
            NumberValue(value=derived_diameter, unit="mm"),
            gauge.quote,
            derived=True,
        )
    return []


def _float(extraction: Extraction) -> float:
    if not isinstance(extraction.value, NumberValue):
        raise TypeError(f"{extraction.attribute_key} is not a number")
    return extraction.value.value
