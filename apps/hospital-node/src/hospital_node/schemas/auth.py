from datetime import datetime

from pydantic import BaseModel, Field

from hospital_node.models.users import Role


class LoginRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=1024)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


class Me(BaseModel):
    email: str
    display_name: str
    role: Role
    hub_subject_id: str
