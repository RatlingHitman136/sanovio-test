from datetime import datetime

from pydantic import BaseModel, Field

from supplier_hub.models.identity import UserRole


class LoginRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=1024)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


class ExchangeRequest(BaseModel):
    assertion: str = Field(max_length=8192)


class ExchangeResponse(TokenResponse):
    # Suppliers and purchasers alike only ever see the alias of a hospital.
    tenant_alias: str


class Me(BaseModel):
    """Who the caller is; the two kinds of principal never overlap."""

    kind: str
    display_name: str
    organization: str
    role: UserRole | None = None
    subject_id: str | None = None
