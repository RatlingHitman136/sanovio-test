"""Stage 8: llm_calls may record COMPARE_TEXT (text read by meaning, §8), and a supplier may
withdraw its own item fact (§9), which the active-fact indexes then leave out.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import service_kit.db

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PURPOSES = "'NORMALIZE_ITEM', 'JUDGE', 'EXTRACT_ANSWER', 'PROPOSE_ATTRIBUTE', 'SIMULATE_SUPPLIER'"
_SUPERSEDED = "superseded_by_id IS NULL"
_ACTIVE = "superseded_by_id IS NULL AND withdrawn_at IS NULL"


def upgrade() -> None:
    _allow_purposes(f"{_PURPOSES}, 'COMPARE_TEXT'")
    with op.batch_alter_table("item_facts") as batch:
        batch.add_column(
            sa.Column("withdrawn_at", service_kit.db.UtcDateTime(timezone=True), nullable=True)
        )
        batch.add_column(sa.Column("withdrawn_by", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            op.f("fk_item_facts_withdrawn_by_users"), "users", ["withdrawn_by"], ["id"]
        )
    _active_indexes(_ACTIVE)


def downgrade() -> None:
    _active_indexes(_SUPERSEDED)
    with op.batch_alter_table("item_facts") as batch:
        batch.drop_constraint(op.f("fk_item_facts_withdrawn_by_users"), type_="foreignkey")
        batch.drop_column("withdrawn_by")
        batch.drop_column("withdrawn_at")
    op.execute("DELETE FROM llm_calls WHERE purpose = 'COMPARE_TEXT'")
    _allow_purposes(_PURPOSES)


def _allow_purposes(purposes: str) -> None:
    # SQLite cannot alter a CHECK in place; batch mode rebuilds the table.
    with op.batch_alter_table("llm_calls") as batch:
        batch.drop_constraint(op.f("ck_llm_calls_purpose"), type_="check")
        batch.create_check_constraint(op.f("ck_llm_calls_purpose"), f"purpose IN ({purposes})")


def _active_indexes(predicate: str) -> None:
    with op.batch_alter_table("item_facts") as batch:
        for scope in ("family", "variant"):
            batch.drop_index(f"ix_item_facts_{scope}_active")
            batch.create_index(
                f"ix_item_facts_{scope}_active",
                [f"{scope}_id", "attribute_key"],
                unique=False,
                sqlite_where=sa.text(predicate),
                postgresql_where=sa.text(predicate),
            )
