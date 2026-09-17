import base64
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from equivalence_core.exchange.assertion import ASSERTION_TYP, issue_assertion
from equivalence_core.exchange.jws import JwsError, sign, verify
from equivalence_core.exchange.keys import generate_private_key

NOW = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)
AUDIENCE = "sanovio-hub"
KSP_KEY = generate_private_key()
OTHER_KEY = generate_private_key()
# Only ten_ksp's own kid resolves for issuer ten_ksp.
REGISTERED = {
    ("ten_ksp", "ksp-2026-09"): KSP_KEY.public_key(),
    ("ten_spital2", "sp2-2026-09"): OTHER_KEY.public_key(),
}


def lookup(issuer: str, kid: str) -> Ed25519PublicKey | None:
    return REGISTERED.get((issuer, kid))


def claims(now: datetime = NOW) -> dict[str, Any]:
    return issue_assertion("ten_ksp", "sub_7QF2M4XK9P3TZC8W1N6R", AUDIENCE, now).model_dump()


def token(**overrides: Any) -> str:
    return sign(
        overrides.pop("claims", claims()),
        overrides.pop("key", KSP_KEY),
        overrides.pop("kid", "ksp-2026-09"),
        overrides.pop("typ", ASSERTION_TYP),
    )


def check(value: str, now: datetime = NOW, typ: str = ASSERTION_TYP) -> dict[str, Any]:
    return verify(value, typ=typ, audience=AUDIENCE, key_lookup=lookup, now=now)


def test_a_valid_assertion_is_accepted() -> None:
    assert check(token())["iss"] == "ten_ksp"


def test_clock_skew_within_the_leeway_is_tolerated() -> None:
    assert check(token(), now=NOW + timedelta(seconds=300 + 59))["iss"] == "ten_ksp"


def _unsigned(header: dict[str, Any], body: dict[str, Any]) -> str:
    def part(data: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    return f"{part(header)}.{part(body)}."


def _public_pem() -> bytes:
    return KSP_KEY.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)


REJECTED: dict[str, Callable[[], str]] = {
    "alg none": lambda: _unsigned(
        {"alg": "none", "typ": ASSERTION_TYP, "kid": "ksp-2026-09"}, claims()
    ),
    # jwt.encode refuses a PEM as an HMAC secret, so the token is forged by hand.
    "HS256 with the public key as secret": lambda: _forge_hs256(),
    "wrong typ": lambda: token(typ="template+jwt"),
    "wrong audience": lambda: token(claims={**claims(), "aud": "someone-else"}),
    "unknown kid": lambda: token(kid="ksp-1999-01"),
    "kid of another issuer": lambda: token(kid="sp2-2026-09", key=OTHER_KEY),
    "signed with an unregistered key": lambda: token(key=generate_private_key()),
    "tampered payload": lambda: _tampered(),
    "missing jti": lambda: token(claims={k: v for k, v in claims().items() if k != "jti"}),
    "not a token": lambda: "not.a.token",
}


def _forge_hs256() -> str:
    import hashlib
    import hmac

    header = {"alg": "HS256", "typ": ASSERTION_TYP, "kid": "ksp-2026-09"}
    unsigned = _unsigned(header, claims())[:-1]
    signature = hmac.new(_public_pem(), unsigned.encode(), hashlib.sha256).digest()
    return f"{unsigned}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


def _tampered() -> str:
    header, _, signature = token().split(".")
    forged = {**claims(), "iss": "ten_ksp", "sub": "sub_AAAAAAAAAAAAAAAAAAAA"}
    body = base64.urlsafe_b64encode(json.dumps(forged).encode()).rstrip(b"=").decode()
    return f"{header}.{body}.{signature}"


@pytest.mark.parametrize("case", sorted(REJECTED))
def test_rejected(case: str) -> None:
    with pytest.raises(JwsError):
        check(REJECTED[case]())


def test_expired_assertion_is_rejected() -> None:
    with pytest.raises(JwsError, match="expired"):
        check(token(), now=NOW + timedelta(seconds=300 + 61))


def test_assertion_from_the_future_is_rejected() -> None:
    with pytest.raises(JwsError, match="future"):
        check(token(claims=claims(NOW + timedelta(seconds=61))))


def test_keys_in_the_header_are_ignored() -> None:
    attacker = generate_private_key()
    forged = jwt.encode(
        claims(),
        attacker,
        algorithm="EdDSA",
        headers={
            "kid": "ksp-2026-09",
            "typ": ASSERTION_TYP,
            "jwk": {"kty": "OKP", "crv": "Ed25519", "x": "attacker"},
        },
    )
    with pytest.raises(JwsError):
        check(forged)
