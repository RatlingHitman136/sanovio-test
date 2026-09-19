"""Hospitals, the node keys the hub trusts, and their purchasers (§17)."""

import uuid

from fastapi import APIRouter

from supplier_hub.api.deps import Context, DbSession, Operator
from supplier_hub.models import Organization, TenantSigningKey
from supplier_hub.models.audit import AuditAction
from supplier_hub.schemas.admin import (
    PrincipalView,
    SigningKeyCreate,
    SigningKeyView,
    TenantCreate,
    TenantView,
)
from supplier_hub.services import operator_audit, tenants_keys

router = APIRouter()


@router.post("/tenants")
def create_tenant(
    body: TenantCreate, context: Context, session: DbSession, operator: Operator
) -> TenantView:
    tenant = tenants_keys.create_tenant(
        session,
        code=body.code,
        name=body.name,
        supplier_facing_alias=body.supplier_facing_alias,
        disclose_name_to_suppliers=body.disclose_name_to_suppliers,
        language=body.language,
        country=body.country,
    )
    operator_audit.record(
        session,
        operator,
        AuditAction.TENANT_CREATED,
        target_type="tenant",
        target_id=tenant.code,
        now=context.clock(),
    )
    return _tenant(tenant)


@router.get("/tenants")
def list_tenants(session: DbSession) -> list[TenantView]:
    return [_tenant(tenant) for tenant in tenants_keys.tenants(session)]


@router.post("/tenants/{tenant_id}/signing-keys")
def register_signing_key(
    tenant_id: uuid.UUID,
    body: SigningKeyCreate,
    context: Context,
    session: DbSession,
    operator: Operator,
) -> SigningKeyView:
    """The fingerprint in the response is what the operator confirms by phone (§17)."""
    tenant = tenants_keys.get_tenant(session, tenant_id)
    key = tenants_keys.register_key(
        session,
        tenant,
        public_jwk=body.public_jwk,
        not_before=body.not_before or context.clock(),
        registered_by=operator.id,
    )
    operator_audit.record(
        session,
        operator,
        AuditAction.SIGNING_KEY_REGISTERED,
        target_type="signing_key",
        target_id=key.kid,
        now=context.clock(),
        data={"tenant": tenant.code, "fingerprint": key.fingerprint},
    )
    return _key(key)


@router.get("/tenants/{tenant_id}/signing-keys")
def list_signing_keys(tenant_id: uuid.UUID, session: DbSession) -> list[SigningKeyView]:
    tenant = tenants_keys.get_tenant(session, tenant_id)
    return [_key(key) for key in tenants_keys.signing_keys(session, tenant)]


@router.post("/tenants/{tenant_id}/signing-keys/{kid}/revoke")
def revoke_signing_key(
    tenant_id: uuid.UUID, kid: str, context: Context, session: DbSession, operator: Operator
) -> SigningKeyView:
    """Immediate: assertions with this key are refused and its hub tokens end."""
    tenant = tenants_keys.get_tenant(session, tenant_id)
    key = tenants_keys.revoke_key(session, tenant, kid, now=context.clock())
    operator_audit.record(
        session,
        operator,
        AuditAction.SIGNING_KEY_REVOKED,
        target_type="signing_key",
        target_id=kid,
        now=context.clock(),
        data={"tenant": tenant.code},
    )
    return _key(key)


@router.get("/tenants/{tenant_id}/principals")
def list_principals(tenant_id: uuid.UUID, session: DbSession) -> list[PrincipalView]:
    tenant = tenants_keys.get_tenant(session, tenant_id)
    return [
        PrincipalView(
            subject_id=entry.principal.subject_id,
            first_seen_at=entry.principal.first_seen_at,
            last_seen_at=entry.principal.last_seen_at,
            is_blocked=entry.principal.is_blocked,
            assessments=entry.assessments,
        )
        for entry in tenants_keys.principals(session, tenant)
    ]


@router.post("/tenants/{tenant_id}/principals/{subject_id}/block", status_code=204)
def block_principal(
    tenant_id: uuid.UUID, subject_id: str, context: Context, session: DbSession, operator: Operator
) -> None:
    """Stops one purchaser without touching the hospital's key; their sessions end at once."""
    _set_blocked(tenant_id, subject_id, True, context, session, operator)


@router.post("/tenants/{tenant_id}/principals/{subject_id}/unblock", status_code=204)
def unblock_principal(
    tenant_id: uuid.UUID, subject_id: str, context: Context, session: DbSession, operator: Operator
) -> None:
    _set_blocked(tenant_id, subject_id, False, context, session, operator)


def _set_blocked(
    tenant_id: uuid.UUID,
    subject_id: str,
    blocked: bool,
    context: Context,
    session: DbSession,
    operator: Operator,
) -> None:
    tenant = tenants_keys.get_tenant(session, tenant_id)
    tenants_keys.set_blocked(session, tenant, subject_id, blocked=blocked, now=context.clock())
    operator_audit.record(
        session,
        operator,
        AuditAction.PRINCIPAL_BLOCKED if blocked else AuditAction.PRINCIPAL_UNBLOCKED,
        target_type="principal",
        target_id=subject_id,
        now=context.clock(),
        data={"tenant": tenant.code},
    )


def _tenant(tenant: Organization) -> TenantView:
    return TenantView(
        id=tenant.id,
        code=tenant.code,
        name=tenant.name,
        supplier_facing_alias=tenant.supplier_facing_alias,
        disclose_name_to_suppliers=tenant.disclose_name_to_suppliers,
        language=tenant.language,
        is_active=tenant.is_active,
    )


def _key(key: TenantSigningKey) -> SigningKeyView:
    return SigningKeyView(
        kid=key.kid,
        fingerprint=key.fingerprint,
        not_before=key.not_before,
        not_after=key.not_after,
        revoked_at=key.revoked_at,
    )
