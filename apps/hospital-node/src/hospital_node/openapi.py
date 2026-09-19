"""The node's OpenAPI document, which the purchaser app's typed client is generated from."""

from pathlib import Path
from typing import Any

from hospital_node.core.settings import NodeSettings
from hospital_node.main import create_app


def spec() -> dict[str, Any]:
    """Built without starting the app: no database, key or model is touched. Dev routes are
    included, as the purchaser app offers them in development."""
    settings = NodeSettings(
        _env_file=None,
        database_url="sqlite://",
        node_signing_key_file=Path("unused.pem"),
        node_signing_kid="openapi",
        normalize_mode="rules",
        app_env="dev",
    )
    document: dict[str, Any] = create_app(settings).openapi()
    return document
