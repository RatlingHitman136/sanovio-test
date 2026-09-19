"""The operator audit trail (H.23), newest first."""

from fastapi import APIRouter

from supplier_hub.api.deps import DbSession
from supplier_hub.models.audit import AuditAction
from supplier_hub.schemas.admin import AuditView
from supplier_hub.services import operator_audit

router = APIRouter()


@router.get("/audit")
def list_audit(session: DbSession, action: AuditAction | None = None) -> list[AuditView]:
    return [
        AuditView(
            id=row.id,
            operator=row.operator.email,
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            data=row.data,
            created_at=row.created_at,
        )
        for row in operator_audit.recent(session, action)
    ]
