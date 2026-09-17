import pytest

from equivalence_core.parsers.synonyms import find_codes, normalize_code
from equivalence_core.templates import load_seed_templates

SYRINGE = load_seed_templates()["syringe_single_use"]
CONNECTOR = SYRINGE.attribute("connector")


@pytest.mark.parametrize("value", ["BD Luer-Lok™", "Luer-Lock", "Luer Lock", "luer-lock", "LL"])
def test_luer_lock_spellings(value: str) -> None:
    assert normalize_code(CONNECTOR, value) == "LUER_LOCK"


def test_luer_lock_is_never_read_as_plain_luer() -> None:
    matches = find_codes("Einmalspritze 10 ml Luer-Lock steril", CONNECTOR)

    assert [(m.code, m.quote) for m in matches] == [("LUER_LOCK", "Luer-Lock")]


def test_plain_luer_is_still_recognised() -> None:
    assert normalize_code(CONNECTOR, "Luer-Ansatz") == "LUER"


def test_option_codes_match_as_field_values_only() -> None:
    mdr = SYRINGE.attribute("mdr_class")
    assert normalize_code(mdr, "IIa") == "IIA"
    # Scanning a name never matches bare codes such as "I".
    assert find_codes("Nitrilhandschuh I", mdr) == []


def test_unknown_spellings_fall_through() -> None:
    assert normalize_code(CONNECTOR, "Bajonett") is None


def test_bool_phrases() -> None:
    sterile = SYRINGE.attribute("sterile")
    assert normalize_code(sterile, "steril") == "true"
    assert normalize_code(sterile, "unsteril") == "false"
    assert [m.code for m in find_codes("nicht steril", sterile)] == ["false"]
