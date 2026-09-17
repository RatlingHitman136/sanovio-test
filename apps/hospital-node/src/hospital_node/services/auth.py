"""Node login sessions: opaque bearer tokens stored as hashes (N.2)."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from hospital_node.models import ApiToken, User
from service_kit.errors import Unauthorized
from service_kit.security import PasswordHasher, hash_token, new_token

_INVALID_LOGIN = "invalid email or password"
_INVALID_TOKEN = "invalid or expired token"


@dataclass(frozen=True)
class IssuedToken:
    access_token: str
    expires_at: datetime


def login(
    session: Session,
    hasher: PasswordHasher,
    email: str,
    password: str,
    *,
    now: datetime,
    ttl: timedelta,
) -> IssuedToken:
    user = session.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        hasher.verify_unknown_user(password)
        raise Unauthorized(_INVALID_LOGIN)
    # Same message for a wrong password and an inactive account.
    if not hasher.verify(password, user.password_hash) or not user.is_active:
        raise Unauthorized(_INVALID_LOGIN)
    token, token_hash = new_token()
    expires_at = now + ttl
    session.add(ApiToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
    session.flush()
    return IssuedToken(access_token=token, expires_at=expires_at)


def authenticate(session: Session, token: str, *, now: datetime) -> User:
    row = session.scalar(select(ApiToken).where(ApiToken.token_hash == hash_token(token)))
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        raise Unauthorized(_INVALID_TOKEN)
    if not row.user.is_active:
        raise Unauthorized(_INVALID_TOKEN)
    row.last_used_at = now
    return row.user


def logout(session: Session, token: str, *, now: datetime) -> None:
    row = session.scalar(select(ApiToken).where(ApiToken.token_hash == hash_token(token)))
    if row is not None and row.revoked_at is None:
        row.revoked_at = now
