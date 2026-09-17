"""Alembic environment: the node models are the target, the URL comes from the caller."""

import os

from alembic import context

import hospital_node.models  # noqa: F401  (registers every table on Base.metadata)
from hospital_node.core.db import Base
from hospital_node.core.settings import NodeSettings
from service_kit.db import make_engine

_DEFAULT_URL: str = NodeSettings.model_fields["database_url"].default


def _url() -> str:
    # `hospital-node migrate` passes the URL explicitly; the plain alembic CLI reads the env.
    return context.config.get_main_option("sqlalchemy.url") or os.environ.get(
        "DATABASE_URL", _DEFAULT_URL
    )


def run_migrations() -> None:
    engine = make_engine(_url())
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            # SQLite needs table rebuilds for most ALTERs.
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations()
