"""Node configuration, read from the environment (see `.env.example`)."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from llm_client import Effort


class NodeSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    app_env: Literal["dev", "prod"] = "dev"
    database_url: str = "sqlite:///var/node_ksp.db"

    # Identity towards the hub (ARCHITECTURE §17).
    node_tenant_id: str = "ten_ksp"
    hub_audience: str = "sanovio-hub"
    node_signing_key_file: Path
    node_signing_kid: str

    # Normalization at ingestion (D42, D56). The key is the hospital's own.
    anthropic_api_key: SecretStr | None = None
    normalize_mode: Literal["llm", "rules"] = "llm"
    normalize_batch_size: int = Field(default=25, ge=1)
    normalize_model: str = "claude-sonnet-5"
    normalize_effort: Effort = "medium"

    # Egress (ARCHITECTURE §16, D47, D48).
    egress_deny_attributes: Annotated[frozenset[str], NoDecode] = frozenset()
    share_product_hints: bool = False
    requirement_rate_limit_per_hour: int = Field(default=120, ge=1)
    assertion_rate_limit_per_hour: int = Field(default=30, ge=1)
    egress_daily_alert_per_user: int = Field(default=300, ge=1)

    token_ttl_hours: int = Field(default=8, ge=1)
    # Password given to the demo users by `hospital-node seed`.
    node_seed_password: SecretStr | None = None

    @field_validator("egress_deny_attributes", mode="before")
    @classmethod
    def _comma_list(cls, value: object) -> object:
        if isinstance(value, str):
            return frozenset(item.strip() for item in value.split(",") if item.strip())
        return value
