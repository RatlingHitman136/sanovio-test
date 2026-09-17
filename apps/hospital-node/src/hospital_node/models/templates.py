"""N.11 template_versions: the current definition per category (D52)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from hospital_node.core.db import Base


class InstalledTemplate(Base):
    # The table name is kept from the versioned design for continuity with the data model.
    __tablename__ = "template_versions"

    code: Mapped[str] = mapped_column(unique=True)
    definition: Mapped[dict[str, Any]]
    definition_hash: Mapped[str] = mapped_column(String(64))
    hub_updated_at: Mapped[datetime]
    installed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    installed_at: Mapped[datetime]
