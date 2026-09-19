"""The hub's OpenAPI document, which both apps' typed hub client is generated from."""

from typing import Any

from supplier_hub.core.settings import HubSettings
from supplier_hub.main import create_app


def spec() -> dict[str, Any]:
    """Built without starting the app: no database, worker or model is touched. Dev routes
    are included, as the supplier app offers the simulator in development."""
    settings = HubSettings(
        _env_file=None,
        database_url="sqlite://",
        llm_mode="fake",
        worker_enabled=False,
        app_env="dev",
    )
    document: dict[str, Any] = create_app(settings).openapi()
    return document
