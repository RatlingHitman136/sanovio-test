"""Standard designations in a comparable form: "DIN EN ISO 7886-1:2018" is ISO 7886-1.

National adoptions (DIN, ÖNORM, SN …) and the European one (EN) of an ISO standard are the same
text as the ISO standard, and the year says only which edition; catalogs and hospitals write the
same standard all of these ways.
"""

import re

_NATIONAL = re.compile(r"^(?:(?:DIN|ÖNORM|OENORM|SN|BS|NF|UNI|NEN)\s+)+")
_EUROPEAN_ADOPTION = re.compile(r"^EN\s+(?=(?:ISO|IEC)\b)")
_EDITION = re.compile(r":\d{4}(?:\s*\+\s*A\d+(?::\d{4})?)*$")


def canonical_standard(designation: str) -> str:
    text = " ".join(designation.upper().split())
    text = _NATIONAL.sub("", text)
    text = _EUROPEAN_ADOPTION.sub("", text)
    return _EDITION.sub("", text).strip()
