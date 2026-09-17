from pathlib import Path

from alembic import command
from sqlalchemy import inspect

from hospital_node.core.migrations import alembic_config, upgrade_to_head
from service_kit.db import make_engine


def test_migrations_create_exactly_the_modelled_schema(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'var' / 'node.db'}"

    upgrade_to_head(url)
    # Raises if the models and the migration history differ.
    command.check(alembic_config(url))

    engine = make_engine(url)
    tables = set(inspect(engine).get_table_names())
    engine.dispose()
    assert {"users", "article_facts", "egress_log", "template_versions"} <= tables


def test_downgrade_removes_everything(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'node.db'}"
    upgrade_to_head(url)

    command.downgrade(alembic_config(url), "base")

    engine = make_engine(url)
    assert inspect(engine).get_table_names() == ["alembic_version"]
    engine.dispose()
