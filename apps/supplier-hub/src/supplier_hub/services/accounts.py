"""Hub accounts: supplier organizations, and the users of suppliers and the operator (H.1, H.4).

Hospital staff never have an account here (§17); an operator only manages logins at the hub.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from service_kit.errors import Conflict, NotFound, Unprocessable
from service_kit.security import MIN_PASSWORD_LENGTH, PasswordHasher
from supplier_hub.models import ApiToken, Organization, User
from supplier_hub.models.identity import UserRole
from supplier_hub.models.organizations import OrganizationType
from supplier_hub.services import auth

_ROLE_OF = {
    OrganizationType.SUPPLIER: UserRole.SUPPLIER,
    OrganizationType.OPERATOR: UserRole.OPERATOR,
}


def organizations(session: Session) -> Sequence[Organization]:
    """The organizations that can hold hub logins: suppliers and the operator."""
    query = select(Organization).where(Organization.type.in_(list(_ROLE_OF)))
    return session.scalars(query.order_by(Organization.type, Organization.name)).all()


def get_organization(session: Session, org_id: uuid.UUID) -> Organization:
    org = session.get(Organization, org_id)
    if org is None or org.type not in _ROLE_OF:
        raise NotFound("organization not found")
    return org


def create_supplier(session: Session, *, code: str, name: str) -> Organization:
    taken = session.scalar(
        select(Organization.id).where(or_(Organization.code == code, Organization.name == name))
    )
    if taken is not None:
        raise Conflict("ORGANIZATION_EXISTS", f"{code!r} or {name!r} is already in use")
    supplier = Organization(code=code, name=name, type=OrganizationType.SUPPLIER)
    session.add(supplier)
    session.flush()
    return supplier


def users(session: Session, org_id: uuid.UUID | None = None) -> Sequence[User]:
    query = select(User).order_by(User.email)
    if org_id is not None:
        query = query.where(User.org_id == org_id)
    return session.scalars(query).all()


def get_user(session: Session, user_id: uuid.UUID) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise NotFound("user not found")
    return user


def create_user(
    session: Session,
    hasher: PasswordHasher,
    org: Organization,
    *,
    email: str,
    display_name: str,
    password: str,
) -> User:
    """The role follows the organization: a supplier's user supplies, the operator's operates."""
    role = _ROLE_OF.get(OrganizationType(org.type))
    if role is None:
        raise Unprocessable("hospital staff sign in at their node, not at the hub")
    _check_password(password)
    normalized = email.strip().lower()
    if session.scalar(select(User.id).where(User.email == normalized)) is not None:
        raise Conflict("USER_EXISTS", f"a user with email {normalized} already exists")
    user = User(
        org_id=org.id,
        email=normalized,
        password_hash=hasher.hash(password),
        role=role,
        display_name=display_name,
    )
    session.add(user)
    session.flush()
    return user


def set_active(
    session: Session, user: User, *, active: bool, operator: User, now: datetime
) -> User:
    """Deactivating ends the user's sessions at once; the account and its history stay.
    The acting operator stays active, so the hub always keeps one."""
    if not active:
        if user.id == operator.id:
            raise Conflict("OWN_ACCOUNT", "an operator cannot deactivate their own account")
        auth.end_sessions(session, ApiToken.user_id == user.id, now=now)
    user.is_active = active
    session.flush()
    return user


def reset_password(
    session: Session, hasher: PasswordHasher, user: User, password: str, *, now: datetime
) -> User:
    _check_password(password)
    user.password_hash = hasher.hash(password)
    auth.end_sessions(session, ApiToken.user_id == user.id, now=now)
    session.flush()
    return user


def _check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise Unprocessable(f"a password needs at least {MIN_PASSWORD_LENGTH} characters")
