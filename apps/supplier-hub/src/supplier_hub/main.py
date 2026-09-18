"""App factory; run with `uvicorn supplier_hub.main:create_app --factory`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from llm_client import LLMClient
from service_kit.clock import Clock, utc_now
from service_kit.db import make_engine, make_session_factory
from service_kit.http_errors import install_error_handlers
from supplier_hub.api.deps import HubContext
from supplier_hub.api.v1 import (
    admin,
    assessments,
    auth,
    catalog,
    dev,
    health,
    search,
    supplier,
    templates,
)
from supplier_hub.core.settings import HubSettings
from supplier_hub.jobs import handlers
from supplier_hub.jobs.worker import Worker
from supplier_hub.llm.factory import make_llm
from supplier_hub.services import assessment


def create_app(
    settings: HubSettings | None = None,
    *,
    clock: Clock = utc_now,
    llm: LLMClient | None = None,
) -> FastAPI:
    # Validated here so a misconfigured LLM mode fails before serving requests.
    resolved = settings or HubSettings()
    engine = make_engine(resolved.database_url)
    client = llm or make_llm(resolved)
    context = HubContext(
        settings=resolved,
        session_factory=make_session_factory(engine),
        clock=clock,
        llm=client,
        handlers=handlers.build(llm=client, settings=resolved),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        worker = None
        if resolved.worker_enabled:
            worker = Worker(
                context.session_factory,
                context.handlers,
                clock=clock,
                on_give_up=assessment.give_up,
            )
            worker.start()
        yield
        if worker is not None:
            worker.stop()
        engine.dispose()

    app = FastAPI(title="Supplier hub", lifespan=lifespan)
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
    for module in (health, auth, admin, templates, catalog, search, assessments, supplier):
        api.include_router(module.router)
    if resolved.app_env == "dev":
        api.include_router(dev.router)
    app.include_router(api)
    return app
