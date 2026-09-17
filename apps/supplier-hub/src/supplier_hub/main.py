"""App factory; run with `uvicorn supplier_hub.main:create_app --factory`."""

from fastapi import FastAPI

from supplier_hub.api.v1 import health
from supplier_hub.core.settings import HubSettings


def create_app(settings: HubSettings | None = None) -> FastAPI:
    app = FastAPI(title="Supplier hub")
    # Validated at startup so a misconfigured LLM mode fails before serving requests.
    app.state.settings = settings or HubSettings()
    app.include_router(health.router, prefix="/api/v1")
    return app
