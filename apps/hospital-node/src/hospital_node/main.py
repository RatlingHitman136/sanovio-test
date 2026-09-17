"""App factory; run with `uvicorn hospital_node.main:create_app --factory`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from hospital_node.api.v1 import health
from hospital_node.core.secrets import load_node_secrets
from hospital_node.core.settings import NodeSettings


def create_app(settings: NodeSettings | None = None) -> FastAPI:
    resolved = settings or NodeSettings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Fail at startup, not on the first request, if the signing key is unusable.
        app.state.secrets = load_node_secrets(resolved)
        yield

    app = FastAPI(title="Hospital node", lifespan=lifespan)
    app.include_router(health.router, prefix="/api/v1")
    return app
