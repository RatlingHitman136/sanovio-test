"""Hub configuration, read from the environment (see `.env.example`)."""

from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class HubSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    llm_mode: Literal["fake", "anthropic"] = "fake"
    anthropic_api_key: SecretStr | None = None

    @model_validator(mode="after")
    def _real_llm_needs_a_key(self) -> Self:
        if self.llm_mode == "anthropic" and self.anthropic_api_key is None:
            raise ValueError("ANTHROPIC_API_KEY is required when LLM_MODE=anthropic")
        return self
