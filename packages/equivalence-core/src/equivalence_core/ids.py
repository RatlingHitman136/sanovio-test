"""Random opaque ids that cross between node and hub.

Crockford base32 (no I, L, O or U) keeps ids unambiguous when read aloud or retyped, and matches
the examples in the architecture documents.
"""

import secrets

CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_CHARACTER_CLASS = "[0-9A-HJKMNP-TV-Z]"
_BITS_PER_CHARACTER = 5

ARTICLE_REF_LENGTH = 12  # 60 bits
SUBJECT_ID_LENGTH = 20  # 100 bits
ARTICLE_REF_PATTERN = rf"^ar_{_CHARACTER_CLASS}{{{ARTICLE_REF_LENGTH}}}$"
SUBJECT_ID_PATTERN = rf"^sub_{_CHARACTER_CLASS}{{{SUBJECT_ID_LENGTH}}}$"


def new_article_ref() -> str:
    """A random article reference, never derived from the article's own ids."""
    return f"ar_{_random_code(ARTICLE_REF_LENGTH)}"


def _random_code(length: int) -> str:
    bits = secrets.randbits(length * _BITS_PER_CHARACTER)
    return "".join(
        CROCKFORD_ALPHABET[(bits >> (_BITS_PER_CHARACTER * index)) & 0b11111]
        for index in reversed(range(length))
    )
