import base64
import stat
from pathlib import Path

import pytest

from equivalence_core.exchange.keys import (
    JwkError,
    KeyFileError,
    generate_private_key,
    jwk_thumbprint,
    load_private_key,
    public_jwk,
    public_key_from_jwk,
    write_private_key,
)


def test_written_key_is_owner_only_and_loads_back(tmp_path: Path) -> None:
    key = generate_private_key()
    path = tmp_path / "secrets" / "node.pem"

    write_private_key(key, path)

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert public_jwk(load_private_key(path), "k1") == public_jwk(key, "k1")


def test_existing_key_is_never_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "node.pem"
    write_private_key(generate_private_key(), path)
    original = path.read_bytes()

    with pytest.raises(KeyFileError, match="refusing to overwrite"):
        write_private_key(generate_private_key(), path)
    assert path.read_bytes() == original


def test_missing_key_file_is_reported(tmp_path: Path) -> None:
    with pytest.raises(KeyFileError, match="not found"):
        load_private_key(tmp_path / "absent.pem")


def test_key_readable_by_others_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "node.pem"
    write_private_key(generate_private_key(), path)
    path.chmod(0o644)

    with pytest.raises(KeyFileError, match="mode 644"):
        load_private_key(path)


def test_public_jwk_has_no_private_member() -> None:
    jwk = public_jwk(generate_private_key(), "ksp-2026-09")

    assert jwk.keys() == {"kty", "crv", "x", "kid"}
    assert (jwk["kty"], jwk["crv"], jwk["kid"]) == ("OKP", "Ed25519", "ksp-2026-09")


def test_thumbprint_matches_rfc_8037_example() -> None:
    # RFC 8037 appendix A.3: the thumbprint of this public key, base64url-encoded.
    jwk = {"kty": "OKP", "crv": "Ed25519", "x": "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo"}
    expected = base64.urlsafe_b64decode("kPrK_qmxVWaYVA9wwBF6Iuo3vVzz7TxHCTwXBygrS4k=").hex()

    assert jwk_thumbprint(jwk) == expected
    assert jwk_thumbprint({**jwk, "kid": "ignored"}) == expected


def test_a_registered_jwk_becomes_a_verifying_key() -> None:
    key = generate_private_key()
    jwk = public_jwk(key, "ksp-2026-09")

    public = public_key_from_jwk(jwk)

    signature = key.sign(b"payload")
    public.verify(signature, b"payload")  # raises if it is the wrong key


@pytest.mark.parametrize(
    "broken",
    [
        {"kty": "EC", "crv": "Ed25519", "x": "abc"},
        {"kty": "OKP", "crv": "X25519", "x": "abc"},
        {"kty": "OKP", "crv": "Ed25519"},
        {"kty": "OKP", "crv": "Ed25519", "x": "not base64!!"},
    ],
)
def test_unusable_jwks_are_refused(broken: dict[str, str]) -> None:
    with pytest.raises(JwkError):
        public_key_from_jwk(broken)


def test_a_jwk_carrying_a_private_member_is_refused() -> None:
    key = generate_private_key()
    jwk = dict(public_jwk(key, "k")) | {"d": "private"}

    with pytest.raises(JwkError):
        public_key_from_jwk(jwk)
