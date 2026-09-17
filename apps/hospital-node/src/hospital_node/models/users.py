"""N.1 users and N.2 api_tokens."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from hospital_node.core.db import Base
from service_kit.db import one_of


class Role(StrEnum):
    PURCHASER = "PURCHASER"
    NODE_ADMIN = "NODE_ADMIN"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (one_of("role", Role),)

    email: Mapped[str] = mapped_column(unique=True)
    password_hash: Mapped[str]
    role: Mapped[str]
    display_name: Mapped[str]
    hub_subject_id: Mapped[str] = mapped_column(unique=True)
    is_active: Mapped[bool] = mapped_column(default=True)


class ApiToken(Base):
    __tablename__ = "api_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    last_used_at: Mapped[datetime | None]

    user: Mapped[User] = relationship()
