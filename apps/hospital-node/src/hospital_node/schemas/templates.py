from datetime import datetime
from typing import Any

from pydantic import BaseModel


class InstalledTemplateView(BaseModel):
    code: str
    definition: dict[str, Any]
    definition_hash: str
    updated_at: datetime
    installed_at: datetime


class TemplateInstall(BaseModel):
    definition: dict[str, Any]
    # The hub's `updated_at` for this definition, so the client can tell when to sync again.
    updated_at: datetime | None = None
