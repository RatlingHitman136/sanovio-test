from equivalence_core.hashing import canonical_json, sha256_hex
from equivalence_core.values import NumberValue


def test_key_order_does_not_matter() -> None:
    assert sha256_hex({"a": 1, "b": {"x": 1, "y": 2}}) == sha256_hex(
        {"b": {"y": 2, "x": 1}, "a": 1}
    )


def test_integral_floats_hash_like_integers() -> None:
    assert sha256_hex({"volume": 10.0}) == sha256_hex({"volume": 10})
    assert sha256_hex({"volume": 10.5}) != sha256_hex({"volume": 10})


def test_models_are_hashed_by_their_json_form() -> None:
    assert canonical_json(NumberValue(value=10, unit="ml")) == (
        '{"type":"number","unit":"ml","value":10}'
    )


def test_non_ascii_is_kept_verbatim() -> None:
    assert canonical_json({"name": "Kanüle"}) == '{"name":"Kanüle"}'
