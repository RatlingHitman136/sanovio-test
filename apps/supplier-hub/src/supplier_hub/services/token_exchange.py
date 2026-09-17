"""Turning a node assertion into a hub token (ARCHITECTURE §17).

This is the only door hospital staff come through, so every check is explicit and ordered:
algorithm and type, the key's ownership and lifetime, the signature, the claims, single use,
then the state of the tenant and the principal.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from equivalence_core.exchange.assertion import ASSERTION_TYP, MAX_LIFETIME_SECONDS
from equivalence_core.exchange.jws import JwsError, verify
from equivalence_core.exchange.keys import JwkError, public_key_from_jwk
from service_kit.errors import Unauthorized
from service_kit.security import new_token
from supplier_hub.models import ApiToken, HospitalPrincipal, Organization, UsedAssertionJti
from supplier_hub.models.organizations import OrganizationType
from supplier_hub.services import tenants_keys

# One message for every failure: a caller learns that it was refused, never why.
_REFUSED = "the assertion was not accepted"


@dataclass(frozen=True)
class ExchangedToken:
    access_token: str
    expires_at: datetime
    tenant_alias: str


def exchange(
    session: Session,
    assertion: str,
    *,
    audience: str,
    now: datetime,
    ttl: timedelta,
    leeway: int,
) -> ExchangedToken:
    claims = _verified_claims(session, assertion, audience=audience, now=now, leeway=leeway)
    tenant = _active_tenant(session, claims["iss"])
    _spend_jti(session, claims, tenant, now=now)
    principal = _principal(session, tenant, claims["sub"], now=now)

    token, token_hash = new_token()
    expires_at = now + ttl
    session.add(
        ApiToken(
            principal_id=principal.id,
            tenant_id=tenant.id,
            kid=claims["kid"],
            assertion_jti=claims["jti"],
            token_hash=token_hash,
            expires_at=expires_at,
        )
    )
    session.flush()
    return ExchangedToken(
        access_token=token,
        expires_at=expires_at,
        # Suppliers only ever see the alias (§4).
        tenant_alias=tenant.supplier_facing_alias or tenant.name,
    )


def _verified_claims(
    session: Session, assertion: str, *, audience: str, now: datetime, leeway: int
) -> dict[str, str]:
    """`jws.verify` pins the algorithm, the `typ`, the audience and the clock; the lookup here
    is what binds a `kid` to the tenant that claims it."""
    used_kid: list[str] = []

    def key_lookup(issuer: str, kid: str):  # type: ignore[no-untyped-def]
        tenant = _hospital_by_code(session, issuer)
        if tenant is None:
            return None
        key = tenants_keys.active_key(session, tenant.id, kid, now=now)
        if key is None:
            return None
        used_kid.append(kid)
        try:
            return public_key_from_jwk(key.public_jwk)
        except JwkError:
            return None

    try:
        claims = verify(
            assertion,
            typ=ASSERTION_TYP,
            audience=audience,
            key_lookup=key_lookup,
            now=now,
            leeway=leeway,
        )
    except JwsError as exc:
        raise Unauthorized(_REFUSED) from exc
    if claims.get("scope") != "purchaser":
        raise Unauthorized(_REFUSED)
    if int(claims["exp"]) - int(claims["iat"]) > MAX_LIFETIME_SECONDS:
        raise Unauthorized(_REFUSED)
    return {
        "iss": str(claims["iss"]),
        "sub": str(claims["sub"]),
        "jti": str(claims["jti"]),
        "exp": str(claims["exp"]),
        "kid": used_kid[-1],
    }


def _hospital_by_code(session: Session, code: str) -> Organization | None:
    tenant = session.scalar(select(Organization).where(Organization.code == code))
    return tenant if tenant is not None and tenant.type == OrganizationType.HOSPITAL else None


def _active_tenant(session: Session, code: str) -> Organization:
    tenant = _hospital_by_code(session, code)
    if tenant is None or not tenant.is_active:
        raise Unauthorized(_REFUSED)
    return tenant


def _spend_jti(
    session: Session, claims: dict[str, str], tenant: Organization, *, now: datetime
) -> None:
    """An assertion is single use; the unique index is what actually stops a replay."""
    expires_at = datetime.fromtimestamp(int(claims["exp"]), tz=now.tzinfo)
    session.add(UsedAssertionJti(jti=claims["jti"], tenant_id=tenant.id, expires_at=expires_at))
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise Unauthorized(_REFUSED) from exc


def _principal(
    session: Session, tenant: Organization, subject: str, *, now: datetime
) -> HospitalPrincipal:
    principal = session.scalar(
        select(HospitalPrincipal).where(
            HospitalPrincipal.tenant_id == tenant.id, HospitalPrincipal.subject_id == subject
        )
    )
    if principal is None:
        principal = HospitalPrincipal(
            tenant_id=tenant.id, subject_id=subject, first_seen_at=now, last_seen_at=now
        )
        session.add(principal)
        session.flush()
        return principal
    if principal.is_blocked:
        raise Unauthorized(_REFUSED)
    principal.last_seen_at = now
    return principal


def expire_used_jtis(session: Session, *, now: datetime) -> int:
    """Housekeeping: a replay after expiry already fails on `exp`."""
    stale = session.scalars(select(UsedAssertionJti).where(UsedAssertionJti.expires_at < now)).all()
    for row in stale:
        session.delete(row)
    return len(stale)
