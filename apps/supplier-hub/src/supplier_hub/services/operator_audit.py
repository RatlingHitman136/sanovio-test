"""The operator audit trail (H.23): who changed what at the hub, and when (§17.1)."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from supplier_hub.models import OperatorAction, User
from supplier_hub.models.audit import AuditAction


def record(
    session: Session,
    operator: User,
    action: AuditAction,
    *,
    target_type: str,
    target_id: object,
    now: datetime,
    data: Mapping[str, Any] | None = None,
) -> OperatorAction:
    row = OperatorAction(
        operator_id=operator.id,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        data=dict(data or {}),
        created_at=now,
    )
    session.add(row)
    session.flush()
    return row


def recent(
    session: Session, action: AuditAction | None = None, *, limit: int = 200
) -> Sequence[OperatorAction]:
    query = select(OperatorAction).order_by(OperatorAction.created_at.desc()).limit(limit)
    if action is not None:
        query = query.where(OperatorAction.action == action)
    return session.scalars(query).all()
