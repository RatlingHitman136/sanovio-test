from pathlib import Path

from alembic import command
from sqlalchemy import Engine, inspect

from hub_fixtures import FakeClock, seed_hub_demo
from service_kit.db import make_engine, make_session_factory
from service_kit.security import PasswordHasher
from supplier_hub.core.migrations import alembic_config, upgrade_to_head
from supplier_hub.core.settings import HubSettings
from supplier_hub.llm.fakes import fake_llm


def test_migrations_create_exactly_the_modelled_schema(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'var' / 'hub.db'}"

    upgrade_to_head(url)
    # Raises if the models and the migration history differ.
    command.check(alembic_config(url))

    engine = make_engine(url)
    tables = set(inspect(engine).get_table_names())
    engine.dispose()
    assert {
        "organizations",
        "tenant_signing_keys",
        "hospital_principals",
        "api_tokens",
        "used_assertion_jtis",
        "product_families",
        "product_variants",
        "item_facts",
        "item_search_projection",
        "attribute_definitions",
        "category_templates",
        "llm_calls",
    } <= tables


def test_the_node_schema_is_not_part_of_the_hub_schema(tmp_path: Path) -> None:
    """Both services share the plumbing but never the metadata."""
    url = f"sqlite:///{tmp_path / 'hub.db'}"
    upgrade_to_head(url)

    engine = make_engine(url)
    tables = set(inspect(engine).get_table_names())
    engine.dispose()
    assert "hospital_articles" not in tables
    assert "egress_log" not in tables


def test_downgrade_to_the_first_revision_and_back(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'hub.db'}"
    upgrade_to_head(url)

    command.downgrade(alembic_config(url), "0001")
    engine = make_engine(url)
    tables = set(inspect(engine).get_table_names())
    engine.dispose()
    assert "assessments" not in tables and "organizations" in tables

    upgrade_to_head(url)
    command.check(alembic_config(url))


def test_table_rebuilds_keep_a_seeded_database_intact(
    tmp_path: Path, hasher: PasswordHasher, settings: HubSettings, clock: FakeClock
) -> None:
    """Found when migrating a used database: SQLite rebuilds llm_calls and item_facts in 0003,
    and with foreign keys enforced, dropping a table that rows point at failed."""
    url = f"sqlite:///{tmp_path / 'hub.db'}"
    upgrade_to_head(url)
    engine = make_engine(url)
    with make_session_factory(engine).begin() as session:
        seed_hub_demo(session, hasher, settings, clock, fake_llm())
    before = _counts(engine)
    assert before["llm_calls"] and before["item_facts"]

    command.downgrade(alembic_config(url), "0002")
    upgrade_to_head(url)

    assert _counts(engine) == before
    engine.dispose()
    command.check(alembic_config(url))


def _counts(engine: Engine) -> dict[str, int]:
    with engine.connect() as connection:
        return {
            table: connection.exec_driver_sql(f"SELECT count(*) FROM {table}").scalar_one()
            for table in ("llm_calls", "item_facts", "product_variants")
        }
