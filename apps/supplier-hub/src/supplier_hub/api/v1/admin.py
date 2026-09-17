import uuid

from fastapi import APIRouter

from supplier_hub.api.deps import Context, DbSession, Operator
from supplier_hub.models import Organization, TenantSigningKey
from supplier_hub.schemas.admin import (
    SigningKeyCreate,
    SigningKeyView,
    TenantCreate,
    TenantView,
)
from supplier_hub.services import tenants_keys

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/tenants")
def create_tenant(
    body: TenantCreate, context: Context, session: DbSession, _: Operator
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
    return _tenant(tenant)


@router.get("/tenants")
def list_tenants(session: DbSession, _: Operator) -> list[TenantView]:
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
    return _key(key)


@router.get("/tenants/{tenant_id}/signing-keys")
def list_signing_keys(
    tenant_id: uuid.UUID, session: DbSession, _: Operator
) -> list[SigningKeyView]:
    tenant = tenants_keys.get_tenant(session, tenant_id)
    return [_key(key) for key in tenants_keys.signing_keys(session, tenant)]


@router.post("/tenants/{tenant_id}/signing-keys/{kid}/revoke")
def revoke_signing_key(
    tenant_id: uuid.UUID, kid: str, context: Context, session: DbSession, _: Operator
) -> SigningKeyView:
    """Immediate: assertions with this key are refused and its hub tokens end."""
    tenant = tenants_keys.get_tenant(session, tenant_id)
    return _key(tenants_keys.revoke_key(session, tenant, kid, now=context.clock()))


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
