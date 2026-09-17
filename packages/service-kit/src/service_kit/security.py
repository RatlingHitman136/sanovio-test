"""Password hashing and opaque bearer tokens (ARCHITECTURE §17)."""

import hashlib
import secrets
from functools import cached_property

from pwdlib import PasswordHash

_TOKEN_BYTES = 32  # 256 bits


class PasswordHasher:
    """argon2id with pwdlib's recommended parameters."""

    def __init__(self) -> None:
        self._hash = PasswordHash.recommended()

    def hash(self, password: str) -> str:
        return self._hash.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        return self._hash.verify(password, password_hash)

    def verify_unknown_user(self, password: str) -> None:
        """Spend the same time as a real check, so response time does not reveal which
        email addresses have an account."""
        self._hash.verify(password, self._dummy_hash)

    @cached_property
    def _dummy_hash(self) -> str:
        return self._hash.hash(secrets.token_urlsafe(16))


def new_token() -> tuple[str, str]:
    """(token shown once to the caller, hash stored in the database)."""
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
