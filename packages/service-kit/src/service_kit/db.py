"""Database engine, sessions and the declarative base every service model inherits."""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, Engine, create_engine, event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator[datetime]):
    """Timezone-aware UTC in, timezone-aware UTC out; SQLite would otherwise drop the zone."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetimes are not stored")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


_NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


# Stable constraint names, so Alembic migrations stay reviewable across databases.
NAMING_CONVENTION = _NAMING

# none_as_null: Python None must be SQL NULL, not the JSON literal null, or "IS NULL" checks
# and constraints silently stop working.
TYPE_MAP: dict[Any, Any] = {
    datetime: UtcDateTime,
    dict[str, Any]: JSON(none_as_null=True),
    list[Any]: JSON(none_as_null=True),
}


class UuidPrimaryKey:
    """UUIDv7 keys sort by creation time, so "newest first" queries stay index-friendly."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid7)


SQLITE_BUSY_TIMEOUT_MS = 30_000


def make_engine(url: str) -> Engine:
    engine = create_engine(url)
    if engine.dialect.name == "sqlite":
        if engine.url.database not in (None, "", ":memory:"):
            Path(engine.url.database).parent.mkdir(parents=True, exist_ok=True)
        event.listen(engine, "connect", _sqlite_pragmas)
    return engine


def one_of(column: str, values: type[StrEnum], name: str | None = None) -> CheckConstraint:
    """A CHECK built from an enum, so the allowed values exist in exactly one place."""
    allowed = ", ".join(f"'{member.value}'" for member in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=name or column)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def _sqlite_pragmas(connection: DBAPIConnection, _: ConnectionPoolEntry) -> None:
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    # One writer at a time: a request waits for the hub's worker instead of failing at once.
    cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
    cursor.close()
