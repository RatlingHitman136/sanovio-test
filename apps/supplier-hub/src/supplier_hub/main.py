"""App factory; run with `uvicorn supplier_hub.main:create_app --factory`."""

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from service_kit.clock import Clock, utc_now
from service_kit.db import make_engine, make_session_factory
from service_kit.http_errors import install_error_handlers
from supplier_hub.api.deps import HubContext
from supplier_hub.api.v1 import admin, auth, catalog, health, search, templates
from supplier_hub.core.settings import HubSettings


def create_app(settings: HubSettings | None = None, *, clock: Clock = utc_now) -> FastAPI:
    # Validated here so a misconfigured LLM mode fails before serving requests.
    resolved = settings or HubSettings()
    engine = make_engine(resolved.database_url)
    context = HubContext(
        settings=resolved, session_factory=make_session_factory(engine), clock=clock
    )

    app = FastAPI(title="Supplier hub")
    app.state.hub = context
    if resolved.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(resolved.cors_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    install_error_handlers(app)

    api = APIRouter(prefix="/api/v1")
    for module in (health, auth, admin, templates, catalog, search):
        api.include_router(module.router)
    app.include_router(api)
    return app
