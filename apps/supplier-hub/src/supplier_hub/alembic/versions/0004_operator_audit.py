"""Stage 9: the operator audit trail (H.23), which §17 promised as "operator access is audited".

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import service_kit.db

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIONS = (
    "TENANT_CREATED",
    "SIGNING_KEY_REGISTERED",
    "SIGNING_KEY_REVOKED",
    "PRINCIPAL_BLOCKED",
    "PRINCIPAL_UNBLOCKED",
    "PROPOSAL_APPROVED",
    "PROPOSAL_MERGED",
    "PROPOSAL_REJECTED",
    "TEMPLATE_EDITED",
    "SUPPLIER_CREATED",
    "USER_CREATED",
    "USER_DEACTIVATED",
    "USER_REACTIVATED",
    "PASSWORD_RESET",
    "FAMILY_RENORMALIZED",
    "JOB_RETRIED",
)


def upgrade() -> None:
    allowed = ", ".join(f"'{action}'" for action in _ACTIONS)
    op.create_table(
        "operator_actions",
        sa.Column("operator_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column("data", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("created_at", service_kit.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(f"action IN ({allowed})", name=op.f("ck_operator_actions_action")),
        sa.ForeignKeyConstraint(
            ["operator_id"], ["users.id"], name=op.f("fk_operator_actions_operator_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_operator_actions")),
    )
    op.create_index(
        op.f("ix_operator_actions_created_at"), "operator_actions", ["created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_operator_actions_created_at"), table_name="operator_actions")
    op.drop_table("operator_actions")
