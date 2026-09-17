"""H.2–H.6: tenant keys, hospital principals, hub users, tokens and spent assertion ids."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from service_kit.db import one_of
from supplier_hub.core.db import Base
from supplier_hub.models.organizations import Organization


class UserRole(StrEnum):
    SUPPLIER = "SUPPLIER"
    OPERATOR = "OPERATOR"


class TenantSigningKey(Base):
    """A hospital node's public key, confirmed out of band before it is registered (§17)."""

    __tablename__ = "tenant_signing_keys"
    __table_args__ = (
        # A private key must never reach the hub; the JWK is stored as text and checked here.
        CheckConstraint("public_jwk NOT LIKE '%\"d\"%'", name="public_key_only"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    kid: Mapped[str] = mapped_column(unique=True)
    public_jwk: Mapped[dict[str, Any]]
    fingerprint: Mapped[str] = mapped_column(String(64))
    not_before: Mapped[datetime]
    not_after: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]
    registered_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    tenant: Mapped[Organization] = relationship()


class HospitalPrincipal(Base):
    """One purchaser at one hospital, known to the hub only by their pseudonymous subject."""

    __tablename__ = "hospital_principals"
    __table_args__ = (UniqueConstraint("tenant_id", "subject_id"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    subject_id: Mapped[str]
    first_seen_at: Mapped[datetime]
    last_seen_at: Mapped[datetime]
    # An operator can stop one purchaser without revoking the hospital's key.
    is_blocked: Mapped[bool] = mapped_column(default=False)

    tenant: Mapped[Organization] = relationship()


class User(Base):
    """H.4: supplier users and operators. Hospital staff never have an account here."""

    __tablename__ = "users"
    __table_args__ = (one_of("role", UserRole),)

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    email: Mapped[str] = mapped_column(unique=True)
    password_hash: Mapped[str]
    role: Mapped[str]
    display_name: Mapped[str]
    is_active: Mapped[bool] = mapped_column(default=True)

    org: Mapped[Organization] = relationship()


class ApiToken(Base):
    __tablename__ = "api_tokens"
    __table_args__ = (
        # A token belongs either to a hub login or to an exchanged purchaser assertion.
        CheckConstraint("(user_id IS NULL) <> (principal_id IS NULL)", name="one_owner"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    principal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("hospital_principals.id"))
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"))
    # Revoking a signing key revokes every token exchanged from it.
    kid: Mapped[str | None]
    assertion_jti: Mapped[str | None]
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    last_used_at: Mapped[datetime | None]

    user: Mapped[User | None] = relationship()
    principal: Mapped[HospitalPrincipal | None] = relationship()


class UsedAssertionJti(Base):
    """H.6: every assertion is single use; rows expire with the assertion itself."""

    __tablename__ = "used_assertion_jtis"

    jti: Mapped[str] = mapped_column(unique=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    expires_at: Mapped[datetime]
