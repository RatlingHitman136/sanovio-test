"""Node configuration, read from the environment (see `.env.example`)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class NodeSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    node_signing_key_file: Path
    node_signing_kid: str
