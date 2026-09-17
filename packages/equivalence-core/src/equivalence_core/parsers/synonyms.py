"""Spelling variants of enum codes and yes/no phrases, e.g. "BD Luer-Lok™" -> LUER_LOCK."""

import re
from dataclasses import dataclass

from equivalence_core.templates.model import AttributeDefinition


@dataclass(frozen=True)
class SynonymMatch:
    code: str
    quote: str
    start: int


def find_codes(text: str, definition: AttributeDefinition) -> list[SynonymMatch]:
    """Listed synonym phrases found in `text`; longer phrases win over the phrases inside them."""
    matches: list[SynonymMatch] = []
    for phrase in sorted(definition.synonyms, key=len, reverse=True):
        for match in _phrase_pattern(phrase).finditer(text):
            if any(
                match.start() < m.start + len(m.quote) and m.start < match.end() for m in matches
            ):
                continue
            matches.append(SynonymMatch(definition.synonyms[phrase], match.group(0), match.start()))
    return sorted(matches, key=lambda m: m.start)


def normalize_code(definition: AttributeDefinition, value: str) -> str | None:
    """The code a single field value stands for, or None when it is unknown or ambiguous."""
    folded = _fold(value)
    for option in definition.options:
        if _fold(option) == folded:
            return option
    codes = {match.code for match in find_codes(value, definition)}
    return codes.pop() if len(codes) == 1 else None


def _fold(text: str) -> str:
    cleaned = re.sub(r"[™®©]", "", text).replace("_", " ").replace("-", " ")
    return " ".join(cleaned.casefold().split())


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    # Hyphens and spaces are interchangeable ("Luer-Lock", "Luer Lock"); whole words only.
    words = [re.escape(word) for word in re.split(r"[\s\-]+", phrase) if word]
    return re.compile(rf"(?<!\w){r'[\s\-]+'.join(words)}(?!\w)", re.IGNORECASE)
