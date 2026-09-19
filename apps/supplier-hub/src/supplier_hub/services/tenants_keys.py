"""Tenants and the node signing keys the hub verifies assertions with (H.1, H.2; §17)."""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from equivalence_core.exchange.keys import JwkError, jwk_thumbprint, public_key_from_jwk
from service_kit.errors import Conflict, NotFound, Unprocessable
from supplier_hub.models import (
    ApiToken,
    Assessment,
    HospitalPrincipal,
    Organization,
    TenantSigningKey,
)
from supplier_hub.models.organizations import OrganizationType
from supplier_hub.services import auth


def create_tenant(
    session: Session,
    *,
    code: str,
    name: str,
    supplier_facing_alias: str,
    disclose_name_to_suppliers: bool = False,
    language: str = "de",
    country: str | None = None,
) -> Organization:
    taken = session.scalar(
        select(Organization.id).where(
            or_(
                Organization.supplier_facing_alias == supplier_facing_alias,
                Organization.code == code,
            )
        )
    )
    if taken is not None:
        raise Conflict("TENANT_EXISTS", f"{code!r} or {supplier_facing_alias!r} is already in use")
    tenant = Organization(
        code=code,
        name=name,
        type=OrganizationType.HOSPITAL,
        supplier_facing_alias=supplier_facing_alias,
        disclose_name_to_suppliers=disclose_name_to_suppliers,
        language=language,
        country=country,
    )
    session.add(tenant)
    session.flush()
    return tenant


def tenants(session: Session) -> Sequence[Organization]:
    query = select(Organization).where(Organization.type == OrganizationType.HOSPITAL)
    return session.scalars(query.order_by(Organization.name)).all()


def get_tenant(session: Session, tenant_id: uuid.UUID) -> Organization:
    tenant = session.get(Organization, tenant_id)
    if tenant is None or tenant.type != OrganizationType.HOSPITAL:
        raise NotFound("tenant not found")
    return tenant


def register_key(
    session: Session,
    tenant: Organization,
    *,
    public_jwk: Mapping[str, str],
    not_before: datetime,
    registered_by: uuid.UUID,
) -> TenantSigningKey:
    """The fingerprint is returned so the operator can confirm it out of band (§17)."""
    try:
        public_key_from_jwk(public_jwk)
    except JwkError as exc:
        raise Unprocessable(str(exc)) from exc
    kid = public_jwk.get("kid")
    if not kid:
        raise Unprocessable("the JWK must carry the kid the node signs with")
    if session.scalar(select(TenantSigningKey.id).where(TenantSigningKey.kid == kid)) is not None:
        raise Conflict("KID_TAKEN", f"the key id {kid!r} is already registered")
    key = TenantSigningKey(
        tenant_id=tenant.id,
        kid=kid,
        public_jwk=dict(public_jwk),
        fingerprint=jwk_thumbprint(public_jwk),
        not_before=not_before,
        registered_by=registered_by,
    )
    session.add(key)
    session.flush()
    return key


def signing_keys(session: Session, tenant: Organization) -> Sequence[TenantSigningKey]:
    query = select(TenantSigningKey).where(TenantSigningKey.tenant_id == tenant.id)
    return session.scalars(query.order_by(TenantSigningKey.not_before.desc())).all()


def revoke_key(
    session: Session, tenant: Organization, kid: str, *, now: datetime
) -> TenantSigningKey:
    """Revoking a key also ends every hub session that was exchanged with it (§17)."""
    key = session.scalar(
        select(TenantSigningKey).where(
            TenantSigningKey.tenant_id == tenant.id, TenantSigningKey.kid == kid
        )
    )
    if key is None:
        raise NotFound("signing key not found")
    if key.revoked_at is None:
        key.revoked_at = now
    auth.end_sessions(session, ApiToken.kid == kid, now=now)
    session.flush()
    return key


@dataclass(frozen=True)
class PrincipalSummary:
    """A purchaser as the hub knows them: a pseudonym, never a name (§17)."""

    principal: HospitalPrincipal
    assessments: int


def principals(session: Session, tenant: Organization) -> list[PrincipalSummary]:
    created = (
        select(func.count())
        .where(Assessment.created_by_principal_id == HospitalPrincipal.id)
        .scalar_subquery()
    )
    rows = session.execute(
        select(HospitalPrincipal, created)
        .where(HospitalPrincipal.tenant_id == tenant.id)
        .order_by(HospitalPrincipal.last_seen_at.desc())
    )
    return [PrincipalSummary(principal=row, assessments=count) for row, count in rows]


def set_blocked(
    session: Session, tenant: Organization, subject_id: str, *, blocked: bool, now: datetime
) -> HospitalPrincipal:
    """Stops one purchaser without touching the hospital's key; their sessions end at once."""
    principal = session.scalar(
        select(HospitalPrincipal).where(
            HospitalPrincipal.tenant_id == tenant.id, HospitalPrincipal.subject_id == subject_id
        )
    )
    if principal is None:
        raise NotFound("purchaser not found")
    principal.is_blocked = blocked
    if blocked:
        auth.end_sessions(session, ApiToken.principal_id == principal.id, now=now)
    session.flush()
    return principal


def active_key(
    session: Session, tenant_id: uuid.UUID, kid: str, *, now: datetime
) -> TenantSigningKey | None:
    """The key a `kid` names, but only for this tenant and only while it is usable."""
    key = session.scalar(
        select(TenantSigningKey).where(
            TenantSigningKey.tenant_id == tenant_id, TenantSigningKey.kid == kid
        )
    )
    if key is None or key.revoked_at is not None:
        return None
    if key.not_before > now or (key.not_after is not None and key.not_after <= now):
        return None
    return key
