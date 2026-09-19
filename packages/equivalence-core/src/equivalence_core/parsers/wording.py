"""Free text in a comparable form: the same statement written two ways compares equal.

Only spelling is normalized here, never meaning: "nein" and "keine" both say "nothing", but
"0,2 ml" and "fein unterteilt" are left different, for a model to judge (ARCHITECTURE §8).
"""

import re

# Whole answers that say "there is none"; a purchaser writes "nein", a catalog "keine".
NOTHING = "none"
_NOTHING_WORDS = frozenset(
    {"keine", "kein", "keiner", "keines", "nein", "ohne", "none", "no", "nothing", "na", "n a"}
)
_DECIMAL_COMMA = re.compile(r"(?<=\d),(?=\d)")
_NOT_WORD = re.compile(r"[^\w.]+")


def canonical_text(text: str) -> str:
    """Casefolded, punctuation and spacing collapsed, decimal commas as points, and any
    whole-answer "nothing" as one token. An answer of only dashes or blanks is "nothing"."""
    folded = _DECIMAL_COMMA.sub(".", text.casefold())
    words = _NOT_WORD.sub(" ", folded).replace("_", " ").strip(" .")
    words = " ".join(words.split())
    if not words or words in _NOTHING_WORDS:
        return NOTHING
    return words
