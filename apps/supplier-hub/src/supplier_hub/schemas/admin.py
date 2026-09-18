import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TenantCreate(BaseModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{2,40}$")
    name: str = Field(min_length=1, max_length=200)
    supplier_facing_alias: str = Field(min_length=1, max_length=100)
    disclose_name_to_suppliers: bool = False
    language: str = Field(default="de", min_length=2, max_length=2)
    country: str | None = Field(default=None, min_length=2, max_length=2)


class TenantView(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    supplier_facing_alias: str | None
    disclose_name_to_suppliers: bool
    language: str
    is_active: bool


class SigningKeyCreate(BaseModel):
    public_jwk: dict[str, str]
    not_before: datetime | None = None


class SigningKeyView(BaseModel):
    kid: str
    # Confirmed out of band before the key is trusted (§17).
    fingerprint: str
    not_before: datetime
    not_after: datetime | None
    revoked_at: datetime | None


class AttributeProposalView(BaseModel):
    id: uuid.UUID
    question_id: uuid.UUID
    question_text: str
    category_code: str
    result: str | None
    status: str
    proposal: dict[str, Any] | None
    attribute_key: str | None
    identifier_key: str | None
    review_note: str | None
    created_at: datetime
