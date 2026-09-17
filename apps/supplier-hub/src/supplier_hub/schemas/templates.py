from datetime import datetime
from typing import Any

from pydantic import BaseModel


class TemplateView(BaseModel):
    code: str
    # The core `TemplateDefinition` as JSON; a node validates and installs it unchanged.
    definition: dict[str, Any]
    definition_hash: str
    updated_at: datetime


class AttributeView(BaseModel):
    key: str
    kind: str
    value_type: str
    unit: str | None
    options: list[str] | None
    labels: dict[str, str]
    status: str
    origin: str
