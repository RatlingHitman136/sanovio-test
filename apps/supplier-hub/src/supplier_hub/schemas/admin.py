import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, SecretStr

from equivalence_core.templates import Labels, RuleSettings
from service_kit.security import MIN_PASSWORD_LENGTH


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
    # How many supplier values the attribute holds so far, shown as information (§7.2 step 5).
    value_count: int
    created_at: datetime


class ProposalApproval(RuleSettings):
    """The category settings, and optionally corrected wording (§7.2 step 6)."""

    labels: Labels | None = None
    synonyms: dict[str, str] | None = None


class ProposalMerge(BaseModel):
    attribute_key: str
    note: str = Field(min_length=1, max_length=1000)


class ProposalRejection(BaseModel):
    note: str = Field(min_length=1, max_length=1000)


class TemplateEditBody(BaseModel):
    """`set` changes settings of attributes in the category, `add` brings in approved ones."""

    set: dict[str, RuleSettings] = {}
    add: dict[str, RuleSettings] = {}
    remove: list[str] = []
    change_note: str = Field(min_length=1, max_length=1000)


class PrincipalView(BaseModel):
    """A purchaser as the hub knows them: a pseudonymous subject, never a name."""

    subject_id: str
    first_seen_at: datetime
    last_seen_at: datetime
    is_blocked: bool
    assessments: int


class OrganizationView(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    type: str


class SupplierCreate(BaseModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{2,40}$")
    name: str = Field(min_length=1, max_length=200)


class UserView(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    organization: str
    email: str
    display_name: str
    role: str
    is_active: bool


class UserCreate(BaseModel):
    org_id: uuid.UUID
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+$", max_length=200)
    display_name: str = Field(min_length=1, max_length=200)
    password: SecretStr = Field(min_length=MIN_PASSWORD_LENGTH)


class PasswordReset(BaseModel):
    password: SecretStr = Field(min_length=MIN_PASSWORD_LENGTH)


class FamilyRow(BaseModel):
    id: uuid.UUID
    name: str
    manufacturer: str
    supplier: str
    category_code: str | None
    variants: int
    # False while the catalog text changed since it was last read (§9).
    normalized: bool


class JobView(BaseModel):
    id: uuid.UUID
    kind: str
    status: str
    # IDs only (H.18), so a job never carries hospital data.
    payload: dict[str, Any]
    attempts: int
    max_attempts: int
    run_after: datetime
    finished_at: datetime | None
    last_error: str | None
    retryable: bool


class UsageView(BaseModel):
    day: date
    purpose: str
    model: str
    calls: int
    errors: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cost_usd: Decimal
    mean_latency_ms: int
    p95_latency_ms: int


class FailedCallView(BaseModel):
    id: uuid.UUID
    purpose: str
    model: str
    created_at: datetime
    error_kind: str


class AssessmentCountsView(BaseModel):
    tenant_code: str
    by_status: dict[str, int]
    by_verdict: dict[str, int]


class AuditView(BaseModel):
    id: uuid.UUID
    operator: str
    action: str
    target_type: str
    target_id: str
    data: dict[str, Any]
    created_at: datetime
