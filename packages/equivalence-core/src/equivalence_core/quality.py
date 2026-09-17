"""Data-quality flags stored on an article or variant; they warn, they never decide equivalence."""

from enum import StrEnum


class DataQualityIssue(StrEnum):
    GTIN_CHECKSUM_INVALID = "GTIN_CHECKSUM_INVALID"
    EAN_CHECKSUM_INVALID = "EAN_CHECKSUM_INVALID"
    GTIN_EAN_MISMATCH = "GTIN_EAN_MISMATCH"
    # A source whose outer diameter disagrees with its own gauge; the gauge wins.
    GAUGE_DIAMETER_MISMATCH = "GAUGE_DIAMETER_MISMATCH"
