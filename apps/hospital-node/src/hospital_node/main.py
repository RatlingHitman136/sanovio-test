"""App factory; run with `uvicorn hospital_node.main:create_app --factory`."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from hospital_node.api.deps import NodeContext
from hospital_node.api.v1 import (
    admin,
    articles,
    auth,
    dev,
    egress,
    health,
    hub_assertions,
    reference,
    requirements,
    templates,
    users,
)
from hospital_node.core.secrets import load_node_secrets
from hospital_node.core.settings import NodeSettings
from hospital_node.llm.factory import make_llm
from hospital_node.services import normalization, template_sync
from llm_client import LLMClient
from service_kit.clock import Clock, utc_now
from service_kit.db import make_engine, make_session_factory
from service_kit.http_errors import ERROR_RESPONSES, install_error_handlers

log = logging.getLogger(__name__)


def create_app(
    settings: NodeSettings | None = None,
    *,
    clock: Clock = utc_now,
    llm: LLMClient | None = None,
) -> FastAPI:
    resolved = settings or NodeSettings()
    engine = make_engine(resolved.database_url)
    context = NodeContext(
        settings=resolved,
        session_factory=make_session_factory(engine),
        clock=clock,
        llm=llm or make_llm(resolved),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Fail at startup, not on the first request, if the signing key is unusable.
        context.secrets = load_node_secrets(resolved)
        _normalize_changed_articles(context)
        yield
        engine.dispose()

    app = FastAPI(title="Hospital node", lifespan=lifespan)
    app.state.node = context
    install_error_handlers(app)

    api = APIRouter(prefix="/api/v1", responses=ERROR_RESPONSES)
    for module in (
        health,
        auth,
        users,
        articles,
        reference,
        requirements,
        hub_assertions,
        egress,
        templates,
        admin,
    ):
        api.include_router(module.router)
    if resolved.app_env == "dev":
        api.include_router(dev.router)
    app.include_router(api)
    return app


def _normalize_changed_articles(context: NodeContext) -> None:
    """D56: articles whose content changed since their last normalization are read now;
    an unchanged restart makes no LLM call."""
    with context.session_factory.begin() as session:
        count = normalization.normalize_stale(
            session,
            templates=template_sync.installed(session),
            llm=context.llm,
            settings=context.settings,
            now=context.clock(),
        )
    if count:
        log.info("normalized %d changed article(s) at startup", count)
