from pathlib import Path

import pytest
from sqlalchemy import text

from service_kit.db import (
    SQLITE_BUSY_TIMEOUT_MS,
    DanglingReferences,
    make_engine,
    migration_connection,
)


def test_sqlite_connections_enforce_keys_and_wait_for_the_writer(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'var' / 'service.db'}")
    with engine.connect() as connection:
        pragmas = {
            name: connection.execute(text(f"PRAGMA {name}")).scalar()
            for name in ("foreign_keys", "journal_mode", "busy_timeout")
        }
    engine.dispose()

    assert pragmas == {
        "foreign_keys": 1,
        "journal_mode": "wal",
        "busy_timeout": SQLITE_BUSY_TIMEOUT_MS,
    }
    assert (tmp_path / "var").is_dir()


def test_a_migration_may_rebuild_tables_but_never_leave_references_dangling(
    tmp_path: Path,
) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'service.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql(
            "CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id))"
        )
        connection.exec_driver_sql("INSERT INTO parent VALUES (1)")
        connection.exec_driver_sql("INSERT INTO child VALUES (1, 1)")

    # A rebuild of a referenced table, as Alembic's batch mode does it, is allowed.
    with engine.connect() as raw, migration_connection(raw) as connection:
        connection.exec_driver_sql("CREATE TABLE parent_new (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO parent_new SELECT id FROM parent")
        connection.exec_driver_sql("DROP TABLE parent")
        connection.exec_driver_sql("ALTER TABLE parent_new RENAME TO parent")
        connection.commit()

    # Losing the row a child points at is not.
    with (
        pytest.raises(DanglingReferences),
        engine.connect() as raw,
        migration_connection(raw) as connection,
    ):
        connection.exec_driver_sql("DELETE FROM parent")
        connection.commit()
    engine.dispose()
