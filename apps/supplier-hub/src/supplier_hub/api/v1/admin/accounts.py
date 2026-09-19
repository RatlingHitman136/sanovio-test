"""Hub logins: supplier organizations, their users and the operator's (H.1, H.4)."""

import uuid

from fastapi import APIRouter

from supplier_hub.api.deps import Context, DbSession, Operator
from supplier_hub.models import Organization, User
from supplier_hub.models.audit import AuditAction
from supplier_hub.schemas.admin import (
    OrganizationView,
    PasswordReset,
    SupplierCreate,
    UserCreate,
    UserView,
)
from supplier_hub.services import accounts, operator_audit

router = APIRouter()


@router.get("/organizations")
def list_organizations(session: DbSession) -> list[OrganizationView]:
    """Suppliers and the operator: every organization that can hold a hub login."""
    return [_organization(org) for org in accounts.organizations(session)]


@router.post("/suppliers")
def create_supplier(
    body: SupplierCreate, context: Context, session: DbSession, operator: Operator
) -> OrganizationView:
    supplier = accounts.create_supplier(session, code=body.code, name=body.name)
    _audit(session, operator, context, AuditAction.SUPPLIER_CREATED, "organization", supplier.code)
    return _organization(supplier)


@router.get("/users")
def list_users(session: DbSession, org: uuid.UUID | None = None) -> list[UserView]:
    return [_user(user) for user in accounts.users(session, org)]


@router.post("/users")
def create_user(
    body: UserCreate, context: Context, session: DbSession, operator: Operator
) -> UserView:
    user = accounts.create_user(
        session,
        context.hasher,
        accounts.get_organization(session, body.org_id),
        email=body.email,
        display_name=body.display_name,
        password=body.password.get_secret_value(),
    )
    _audit(session, operator, context, AuditAction.USER_CREATED, "user", user.email)
    return _user(user)


@router.post("/users/{user_id}/deactivate")
def deactivate_user(
    user_id: uuid.UUID, context: Context, session: DbSession, operator: Operator
) -> UserView:
    """The user's sessions end at once; the account and its history stay."""
    user = accounts.set_active(
        session,
        accounts.get_user(session, user_id),
        active=False,
        operator=operator,
        now=context.clock(),
    )
    _audit(session, operator, context, AuditAction.USER_DEACTIVATED, "user", user.email)
    return _user(user)


@router.post("/users/{user_id}/reactivate")
def reactivate_user(
    user_id: uuid.UUID, context: Context, session: DbSession, operator: Operator
) -> UserView:
    user = accounts.set_active(
        session,
        accounts.get_user(session, user_id),
        active=True,
        operator=operator,
        now=context.clock(),
    )
    _audit(session, operator, context, AuditAction.USER_REACTIVATED, "user", user.email)
    return _user(user)


@router.post("/users/{user_id}/password", status_code=204)
def reset_password(
    user_id: uuid.UUID,
    body: PasswordReset,
    context: Context,
    session: DbSession,
    operator: Operator,
) -> None:
    """The new password is set by the operator and passed on out of band; sessions end."""
    user = accounts.reset_password(
        session,
        context.hasher,
        accounts.get_user(session, user_id),
        body.password.get_secret_value(),
        now=context.clock(),
    )
    _audit(session, operator, context, AuditAction.PASSWORD_RESET, "user", user.email)


def _audit(
    session: DbSession,
    operator: Operator,
    context: Context,
    action: AuditAction,
    target_type: str,
    target_id: str,
) -> None:
    operator_audit.record(
        session,
        operator,
        action,
        target_type=target_type,
        target_id=target_id,
        now=context.clock(),
    )


def _organization(org: Organization) -> OrganizationView:
    return OrganizationView(id=org.id, code=org.code, name=org.name, type=org.type)


def _user(user: User) -> UserView:
    return UserView(
        id=user.id,
        org_id=user.org_id,
        organization=user.org.name,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
    )
