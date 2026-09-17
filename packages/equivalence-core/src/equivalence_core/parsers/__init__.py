"""Parsers for German catalog and article notation, shared so node and hub read text identically."""

from equivalence_core.parsers.dimensions import Measurement, Quantity, find_measurements
from equivalence_core.parsers.gauge import (
    gauge_diameter_consistent,
    gauge_for_outer_diameter,
    outer_diameter_for_gauge,
)
from equivalence_core.parsers.numbers import parse_number
from equivalence_core.parsers.packaging import Packaging, parse_packaging
from equivalence_core.parsers.synonyms import SynonymMatch, find_codes, normalize_code
from equivalence_core.parsers.text import Extraction, NameReading, extract_attributes
from equivalence_core.parsers.units import UnitError, to_canonical

__all__ = [
    "Extraction",
    "Measurement",
    "NameReading",
    "Packaging",
    "Quantity",
    "SynonymMatch",
    "UnitError",
    "extract_attributes",
    "find_codes",
    "find_measurements",
    "gauge_diameter_consistent",
    "gauge_for_outer_diameter",
    "normalize_code",
    "outer_diameter_for_gauge",
    "parse_number",
    "parse_packaging",
    "to_canonical",
]
