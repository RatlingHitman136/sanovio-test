from pathlib import Path

from sqlalchemy import text

from service_kit.db import SQLITE_BUSY_TIMEOUT_MS, make_engine


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
