"""N.7 egress_log: what the node issued for the hub (append-only)."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hospital_node.core.db import Base
from hospital_node.models.users import User
from service_kit.db import one_of


class EgressKind(StrEnum):
    ASSERTION = "ASSERTION"
    REQUIREMENT = "REQUIREMENT"


class EgressAlert(StrEnum):
    RATE_80_PERCENT = "RATE_80_PERCENT"
    RATE_EXCEEDED = "RATE_EXCEEDED"
    UNUSUAL_DAILY_VOLUME = "UNUSUAL_DAILY_VOLUME"


class EgressLog(Base):
    __tablename__ = "egress_log"
    __table_args__ = (
        one_of("kind", EgressKind),
        one_of("alert", EgressAlert),
        # A refused issuance leaves an alert-only row: nothing was issued, so no content.
        CheckConstraint(
            "(content IS NOT NULL AND content_sha256 IS NOT NULL)"
            " OR COALESCE(alert, '') = 'RATE_EXCEEDED'",
            name="content_unless_refused",
        ),
        Index("ix_egress_log_user_created", "user_id", "created_at"),
    )

    kind: Mapped[str]
    article_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("hospital_articles.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    content: Mapped[dict[str, Any] | None]
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    jti: Mapped[str | None]
    kid: Mapped[str | None]
    alert: Mapped[str | None]
    created_at: Mapped[datetime]

    user: Mapped[User] = relationship()

    @property
    def issued(self) -> bool:
        return self.content is not None
