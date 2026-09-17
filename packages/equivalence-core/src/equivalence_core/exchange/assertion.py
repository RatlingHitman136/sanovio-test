"""The short-lived statement a node signs so a purchaser can obtain a hub token (§17)."""

import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from equivalence_core.ids import SUBJECT_ID_PATTERN

ASSERTION_TYP = "assertion+jwt"
MAX_LIFETIME_SECONDS = 300


class HubAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    iss: str = Field(min_length=1)  # hospital tenant id
    sub: str = Field(pattern=SUBJECT_ID_PATTERN)  # pseudonymous purchaser subject
    aud: str = Field(min_length=1)
    scope: Literal["purchaser"] = "purchaser"
    iat: int
    exp: int
    jti: str = Field(min_length=1)

    @model_validator(mode="after")
    def _short_lived(self) -> Self:
        if not 0 < self.exp - self.iat <= MAX_LIFETIME_SECONDS:
            raise ValueError(f"an assertion must expire within {MAX_LIFETIME_SECONDS} s")
        return self


def issue_assertion(
    tenant: str,
    subject: str,
    audience: str,
    now: datetime,
    lifetime_seconds: int = MAX_LIFETIME_SECONDS,
) -> HubAssertion:
    issued_at = int(now.timestamp())
    return HubAssertion(
        iss=tenant,
        sub=subject,
        aud=audience,
        iat=issued_at,
        exp=issued_at + lifetime_seconds,
        jti=str(uuid.uuid4()),
    )
