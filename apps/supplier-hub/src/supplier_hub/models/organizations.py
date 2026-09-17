"""H.1 organizations: hospitals (tenants), suppliers and the operator."""

from enum import StrEnum

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from service_kit.db import one_of
from supplier_hub.core.db import Base


class OrganizationType(StrEnum):
    HOSPITAL = "HOSPITAL"
    SUPPLIER = "SUPPLIER"
    OPERATOR = "OPERATOR"


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (one_of("type", OrganizationType),)

    # The readable id the outside world uses: a node signs `iss: ten_ksp`, and the operator
    # CLI addresses tenants by it. Internal references stay UUIDs.
    code: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    type: Mapped[str]
    # Hospitals are named to suppliers by their alias only, unless they disclose themselves.
    supplier_facing_alias: Mapped[str | None] = mapped_column(unique=True)
    disclose_name_to_suppliers: Mapped[bool] = mapped_column(default=False)
    language: Mapped[str] = mapped_column(String(2), default="de")
    country: Mapped[str | None] = mapped_column(String(2))
    cors_origin: Mapped[str | None]
    is_active: Mapped[bool] = mapped_column(default=True)
