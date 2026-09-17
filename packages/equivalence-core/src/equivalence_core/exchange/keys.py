"""Ed25519 signing keys: generation, owner-only PEM storage and public JWK export."""

import base64
import hashlib
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
)

KEY_FILE_MODE = 0o600
KEY_DIR_MODE = 0o700

type PublicJwk = dict[str, str]


class KeyFileError(Exception):
    """A private key file is missing, unreadable, too permissive or not an Ed25519 key."""


def generate_private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def write_private_key(key: Ed25519PrivateKey, path: Path) -> None:
    """Store `key` as PKCS#8 PEM readable by the owner only; never overwrite an existing file."""
    path.parent.mkdir(mode=KEY_DIR_MODE, parents=True, exist_ok=True)
    pem = key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    # O_EXCL makes creation atomic, so an existing key can never be replaced by accident.
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, KEY_FILE_MODE)
    except FileExistsError as exc:
        raise KeyFileError(f"refusing to overwrite existing key file {path}") from exc
    with os.fdopen(fd, "wb") as file:
        file.write(pem)


def load_private_key(path: Path) -> Ed25519PrivateKey:
    """Load an Ed25519 key, rejecting files that group or others can access."""
    try:
        mode = path.stat().st_mode & 0o777
    except FileNotFoundError as exc:
        raise KeyFileError(f"key file not found: {path}") from exc
    if mode & 0o077:
        raise KeyFileError(f"key file {path} has mode {mode:o}; expected {KEY_FILE_MODE:o}")
    key = load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise KeyFileError(f"key file {path} does not hold an Ed25519 private key")
    return key


def public_jwk(key: Ed25519PrivateKey, kid: str) -> PublicJwk:
    """The public half as a JWK (RFC 8037); the private member `d` is never included."""
    raw = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return {"kty": "OKP", "crv": "Ed25519", "x": _b64url(raw), "kid": kid}


def jwk_thumbprint(jwk: PublicJwk) -> str:
    """RFC 7638 SHA-256 thumbprint as hex, used as the key fingerprint confirmed out of band."""
    required = {name: jwk[name] for name in ("crv", "kty", "x")}
    canonical = json.dumps(required, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()
