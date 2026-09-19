"""Stage 10: suppliers enter and maintain families and variants themselves (§9, D59), so both
tables record who entered a row and when it last changed.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

import service_kit.db

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("product_families", "product_variants")


def upgrade() -> None:
    now = datetime.now(UTC)
    for table in _TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("created_by", sa.Uuid(), nullable=True))
            batch.add_column(
                sa.Column("updated_at", service_kit.db.UtcDateTime(timezone=True), nullable=True)
            )
            batch.create_foreign_key(
                op.f(f"fk_{table}_created_by_users"), "users", ["created_by"], ["id"]
            )
        # Rows from before this stage were loaded from the catalogs; they count as changed now.
        rows = sa.table(table, sa.column("updated_at", service_kit.db.UtcDateTime(timezone=True)))
        op.execute(rows.update().values(updated_at=now))
        with op.batch_alter_table(table) as batch:
            batch.alter_column(
                "updated_at",
                existing_type=service_kit.db.UtcDateTime(timezone=True),
                nullable=False,
            )


def downgrade() -> None:
    for table in _TABLES:
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(op.f(f"fk_{table}_created_by_users"), type_="foreignkey")
            batch.drop_column("updated_at")
            batch.drop_column("created_by")
