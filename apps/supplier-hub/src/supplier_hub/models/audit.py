"""H.23 operator_actions: every change an operator makes at the hub (§17.1)."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from service_kit.db import one_of
from supplier_hub.core.db import Base
from supplier_hub.models.identity import User


class AuditAction(StrEnum):
    TENANT_CREATED = "TENANT_CREATED"
    SIGNING_KEY_REGISTERED = "SIGNING_KEY_REGISTERED"
    SIGNING_KEY_REVOKED = "SIGNING_KEY_REVOKED"
    PRINCIPAL_BLOCKED = "PRINCIPAL_BLOCKED"
    PRINCIPAL_UNBLOCKED = "PRINCIPAL_UNBLOCKED"
    PROPOSAL_APPROVED = "PROPOSAL_APPROVED"
    PROPOSAL_MERGED = "PROPOSAL_MERGED"
    PROPOSAL_REJECTED = "PROPOSAL_REJECTED"
    TEMPLATE_EDITED = "TEMPLATE_EDITED"
    SUPPLIER_CREATED = "SUPPLIER_CREATED"
    USER_CREATED = "USER_CREATED"
    USER_DEACTIVATED = "USER_DEACTIVATED"
    USER_REACTIVATED = "USER_REACTIVATED"
    PASSWORD_RESET = "PASSWORD_RESET"
    FAMILY_RENORMALIZED = "FAMILY_RENORMALIZED"
    JOB_RETRIED = "JOB_RETRIED"


class OperatorAction(Base):
    """Append-only. `data` names what changed, never a password or key material."""

    __tablename__ = "operator_actions"
    __table_args__ = (one_of("action", AuditAction),)

    operator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str]
    target_type: Mapped[str]
    target_id: Mapped[str]
    data: Mapped[dict[str, Any]]
    created_at: Mapped[datetime] = mapped_column(index=True)

    operator: Mapped[User] = relationship()
