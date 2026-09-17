"""Ed25519 JWS for hub assertions, with the RFC 8725 checks from ARCHITECTURE §17.

PyJWT does not know the RFC 9864 name "Ed25519", so the algorithm is pinned to "EdDSA" and the
key type is enforced separately: only an Ed25519 public key from `key_lookup` is ever used.
"""

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

ALGORITHM = "EdDSA"
DEFAULT_LEEWAY_SECONDS = 60

type KeyLookup = Callable[[str, str], Ed25519PublicKey | None]
"""(issuer, kid) -> the issuer's registered public key, or None if unknown or revoked."""


class JwsError(Exception):
    """The token is not acceptable. The message is for logs, never for the caller."""


def sign(claims: Mapping[str, Any], key: Ed25519PrivateKey, kid: str, typ: str) -> str:
    return jwt.encode(dict(claims), key, algorithm=ALGORITHM, headers={"kid": kid, "typ": typ})


def verify(
    token: str,
    *,
    typ: str,
    audience: str,
    key_lookup: KeyLookup,
    now: datetime,
    leeway: int = DEFAULT_LEEWAY_SECONDS,
) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
        unverified = jwt.decode(token, options={"verify_signature": False})
    except jwt.InvalidTokenError as exc:
        raise JwsError(f"malformed token: {exc}") from exc

    # Header checks first; keys embedded in the header (jwk, jku, x5u) are never used.
    if header.get("alg") != ALGORITHM:
        raise JwsError(f"algorithm {header.get('alg')!r} is not allowed")
    if header.get("typ") != typ:
        raise JwsError(f"expected typ {typ!r}, got {header.get('typ')!r}")
    kid, issuer = header.get("kid"), unverified.get("iss")
    if not isinstance(kid, str) or not isinstance(issuer, str):
        raise JwsError("kid and iss are required")
    # The key is looked up for this issuer only, so a kid registered to another tenant fails here.
    key = key_lookup(issuer, kid)
    if not isinstance(key, Ed25519PublicKey):
        raise JwsError(f"no usable key {kid!r} for issuer {issuer!r}")

    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=[ALGORITHM],
            audience=audience,
            # Times are checked below against the injected clock.
            options={
                "require": ["iss", "aud", "iat", "exp", "jti"],
                "verify_exp": False,
                "verify_iat": False,
                "verify_nbf": False,
            },
        )
    except jwt.InvalidTokenError as exc:
        raise JwsError(f"invalid token: {exc}") from exc

    current = now.timestamp()
    if claims["exp"] <= current - leeway:
        raise JwsError("token has expired")
    if claims["iat"] > current + leeway:
        raise JwsError("token was issued in the future")
    return claims
