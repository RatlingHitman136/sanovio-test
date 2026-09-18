from pathlib import Path

from alembic import command
from sqlalchemy import inspect

from service_kit.db import make_engine
from supplier_hub.core.migrations import alembic_config, upgrade_to_head


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
