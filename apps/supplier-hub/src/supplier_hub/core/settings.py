"""Hub configuration, read from the environment (see `.env.example`)."""

from typing import Annotated, Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from llm_client import Effort


class HubSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    app_env: Literal["dev", "prod"] = "dev"
    database_url: str = "sqlite:///var/hub.db"
    hub_audience: str = "sanovio-hub"
    cors_origins: Annotated[tuple[str, ...], NoDecode] = ()

    # Sessions: exchanged purchaser tokens are short-lived, supplier logins last a working day.
    token_ttl_hours: int = Field(default=8, ge=1)
    exchange_ttl_minutes: int = Field(default=30, ge=1)
    # Clock skew allowed on an assertion's `iat` / `exp` (§17).
    assertion_leeway_s: int = Field(default=60, ge=0)

    llm_mode: Literal["fake", "anthropic"] = "fake"
    anthropic_api_key: SecretStr | None = None
    normalize_item_model: str = "claude-sonnet-5"
    normalize_item_effort: Effort = "medium"
    judge_model: str = "claude-opus-5"
    judge_effort: Effort = "high"
    extract_answer_model: str = "claude-haiku-4-5"
    propose_attribute_model: str = "claude-sonnet-5"
    propose_attribute_effort: Effort = "medium"
    simulate_supplier_model: str = "claude-haiku-4-5"
    max_rounds: int = Field(default=3, ge=1)
    # The background job worker; tests switch it off and run jobs inline instead.
    worker_enabled: bool = True

    hub_seed_password: SecretStr | None = None

    @model_validator(mode="after")
    def _real_llm_needs_a_key(self) -> Self:
        if self.llm_mode == "anthropic" and self.anthropic_api_key is None:
            raise ValueError("ANTHROPIC_API_KEY is required when LLM_MODE=anthropic")
        return self

    @model_validator(mode="after")
    def _named_origins_only(self) -> Self:
        # The hub answers with credentials, and a wildcard origin would hand them to any site.
        if "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS must name origins; '*' is not allowed")
        return self

    @model_validator(mode="before")
    @classmethod
    def _comma_list(cls, values: object) -> object:
        if isinstance(values, dict) and isinstance(values.get("cors_origins"), str):
            origins = values["cors_origins"]
            values = values | {
                "cors_origins": tuple(part.strip() for part in origins.split(",") if part.strip())
            }
        return values
