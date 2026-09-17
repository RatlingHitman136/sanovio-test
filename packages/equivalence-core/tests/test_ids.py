import re

import pytest

from equivalence_core.ids import (
    ARTICLE_REF_PATTERN,
    CROCKFORD_ALPHABET,
    SUBJECT_ID_PATTERN,
    new_article_ref,
)


@pytest.mark.parametrize("example", ["ar_5MZQ4K7T2V9C", "ar_H8R2WX3N6J4D", "ar_Q7C1PV5M9K2T"])
def test_article_refs_from_the_architecture_match(example: str) -> None:
    assert re.fullmatch(ARTICLE_REF_PATTERN, example)


def test_subject_from_the_architecture_matches() -> None:
    assert re.fullmatch(SUBJECT_ID_PATTERN, "sub_7QF2M4XK9P3TZC8W1N6R")


@pytest.mark.parametrize("letter", ["I", "L", "O", "U"])
def test_ambiguous_letters_are_excluded(letter: str) -> None:
    assert letter not in CROCKFORD_ALPHABET
    assert not re.fullmatch(ARTICLE_REF_PATTERN, f"ar_{letter * 12}")


def test_new_article_refs_are_well_formed_and_random() -> None:
    refs = {new_article_ref() for _ in range(200)}

    assert len(refs) == 200
    assert all(re.fullmatch(ARTICLE_REF_PATTERN, ref) for ref in refs)
    # 2,400 random characters cover the whole 32-symbol alphabet with overwhelming probability.
    assert set("".join(ref[3:] for ref in refs)) == set(CROCKFORD_ALPHABET)
