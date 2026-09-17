"""Initial node schema: data-model N.1–N.3, N.5–N.7, N.10, N.11.

Revision ID: 0001
Revises: —
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import service_kit.db

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_calls",
        sa.Column("purpose", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("effort", sa.String(), nullable=True),
        sa.Column("prompt_version", sa.String(), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("response", sa.JSON(), nullable=True),
        sa.Column("stop_reason", sa.String(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", service_kit.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("purpose IN ('NORMALIZE_ARTICLE')", name=op.f("ck_llm_calls_purpose")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_calls")),
    )
    op.create_table(
        "users",
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("hub_subject_id", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("role IN ('PURCHASER', 'NODE_ADMIN')", name=op.f("ck_users_role")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.UniqueConstraint("hub_subject_id", name=op.f("uq_users_hub_subject_id")),
    )
    op.create_table(
        "api_tokens",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", service_kit.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", service_kit.db.UtcDateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", service_kit.db.UtcDateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_api_tokens_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_api_tokens_token_hash")),
    )
    op.create_table(
        "hospital_articles",
        sa.Column("internal_id", sa.String(), nullable=False),
        sa.Column("article_ref", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("brand", sa.String(), nullable=True),
        sa.Column("annual_quantity", sa.Integer(), nullable=True),
        sa.Column("order_unit", sa.String(), nullable=True),
        sa.Column("base_units_per_order_unit", sa.Integer(), nullable=True),
        sa.Column("base_unit", sa.String(), nullable=True),
        sa.Column("target_net_price", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("category_code", sa.String(), nullable=True),
        sa.Column("category_source", sa.String(), nullable=True),
        sa.Column("category_set_by", sa.Uuid(), nullable=True),
        sa.Column("category_set_at", service_kit.db.UtcDateTime(timezone=True), nullable=True),
        sa.Column("reference_hub_variant_id", sa.String(), nullable=True),
        sa.Column("reference_label", sa.String(), nullable=True),
        sa.Column("reference_source", sa.String(), nullable=True),
        sa.Column("reference_linked_by", sa.Uuid(), nullable=True),
        sa.Column("reference_linked_at", service_kit.db.UtcDateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("normalized_hash", sa.String(length=64), nullable=True),
        sa.Column("data_quality_issues", sa.JSON(), nullable=False),
        sa.Column("raw", sa.JSON(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "category_source IN ('RULES', 'LLM_SUGGESTED', 'PURCHASER')",
            name=op.f("ck_hospital_articles_category_source"),
        ),
        sa.CheckConstraint(
            "reference_source IN ('CLIENT_REPORTED')",
            name=op.f("ck_hospital_articles_reference_source"),
        ),
        sa.ForeignKeyConstraint(
            ["category_set_by"],
            ["users.id"],
            name=op.f("fk_hospital_articles_category_set_by_users"),
        ),
        sa.ForeignKeyConstraint(
            ["reference_linked_by"],
            ["users.id"],
            name=op.f("fk_hospital_articles_reference_linked_by_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hospital_articles")),
        sa.UniqueConstraint("article_ref", name=op.f("uq_hospital_articles_article_ref")),
        sa.UniqueConstraint("internal_id", name=op.f("uq_hospital_articles_internal_id")),
    )
    op.create_table(
        "template_versions",
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("definition_hash", sa.String(length=64), nullable=False),
        sa.Column("hub_updated_at", service_kit.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("installed_by", sa.Uuid(), nullable=False),
        sa.Column("installed_at", service_kit.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["installed_by"], ["users.id"], name=op.f("fk_template_versions_installed_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_template_versions")),
        sa.UniqueConstraint("code", name=op.f("uq_template_versions_code")),
    )
    op.create_table(
        "article_facts",
        sa.Column("article_id", sa.Uuid(), nullable=False),
        sa.Column("attribute_key", sa.String(), nullable=False),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column("raw_value", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("method", sa.String(), nullable=True),
        sa.Column("evidence_quote", sa.String(), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column("hub_variant_id", sa.String(), nullable=True),
        sa.Column("hub_fact_id", sa.String(), nullable=True),
        sa.Column("hub_question_id", sa.String(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", service_kit.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("parser_version", sa.String(), nullable=True),
        sa.Column("llm_call_id", sa.Uuid(), nullable=True),
        sa.Column("model_id", sa.String(), nullable=True),
        sa.Column("prompt_version", sa.String(), nullable=True),
        sa.Column("superseded_by_id", sa.Uuid(), nullable=True),
        sa.Column("retracted_at", service_kit.db.UtcDateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("method IN ('RULES', 'LLM')", name=op.f("ck_article_facts_method")),
        sa.CheckConstraint(
            "source IN ('HOSPITAL_MASTER', 'EXTRACTION', 'REFERENCE_ITEM', 'PURCHASER_ANSWER', 'UNAVAILABLE')",
            name=op.f("ck_article_facts_source"),
        ),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["hospital_articles.id"],
            name=op.f("fk_article_facts_article_id_hospital_articles"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_article_facts_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["llm_call_id"], ["llm_calls.id"], name=op.f("fk_article_facts_llm_call_id_llm_calls")
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by_id"],
            ["article_facts.id"],
            name=op.f("fk_article_facts_superseded_by_id_article_facts"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_article_facts")),
    )
    with op.batch_alter_table("article_facts", schema=None) as batch_op:
        batch_op.create_index(
            "ix_article_facts_active",
            ["article_id", "attribute_key"],
            unique=False,
            sqlite_where=sa.text("superseded_by_id IS NULL AND retracted_at IS NULL"),
            postgresql_where=sa.text("superseded_by_id IS NULL AND retracted_at IS NULL"),
        )

    op.create_table(
        "article_projection",
        sa.Column("article_id", sa.Uuid(), nullable=False),
        sa.Column("category_code", sa.String(), nullable=True),
        sa.Column("definition_hash", sa.String(length=64), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("attribute_origin", sa.JSON(), nullable=False),
        sa.Column("identifiers", sa.JSON(), nullable=False),
        sa.Column("attribute_fact_ids", sa.JSON(), nullable=False),
        sa.Column("unknown_attributes", sa.JSON(), nullable=False),
        sa.Column("unavailable_attributes", sa.JSON(), nullable=False),
        sa.Column("record_hash", sa.String(length=64), nullable=False),
        sa.Column("requirement_hash", sa.String(length=64), nullable=False),
        sa.Column("updated_at", service_kit.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["hospital_articles.id"],
            name=op.f("fk_article_projection_article_id_hospital_articles"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_article_projection")),
        sa.UniqueConstraint("article_id", name=op.f("uq_article_projection_article_id")),
    )
    op.create_table(
        "egress_log",
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("article_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
        sa.Column("jti", sa.String(), nullable=True),
        sa.Column("kid", sa.String(), nullable=True),
        sa.Column("alert", sa.String(), nullable=True),
        sa.Column("created_at", service_kit.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "(content IS NOT NULL AND content_sha256 IS NOT NULL) OR COALESCE(alert, '') = 'RATE_EXCEEDED'",
            name=op.f("ck_egress_log_content_unless_refused"),
        ),
        sa.CheckConstraint(
            "alert IN ('RATE_80_PERCENT', 'RATE_EXCEEDED', 'UNUSUAL_DAILY_VOLUME')",
            name=op.f("ck_egress_log_alert"),
        ),
        sa.CheckConstraint("kind IN ('ASSERTION', 'REQUIREMENT')", name=op.f("ck_egress_log_kind")),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["hospital_articles.id"],
            name=op.f("fk_egress_log_article_id_hospital_articles"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_egress_log_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_egress_log")),
    )
    with op.batch_alter_table("egress_log", schema=None) as batch_op:
        batch_op.create_index("ix_egress_log_user_created", ["user_id", "created_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("egress_log", schema=None) as batch_op:
        batch_op.drop_index("ix_egress_log_user_created")

    op.drop_table("egress_log")
    op.drop_table("article_projection")
    with op.batch_alter_table("article_facts", schema=None) as batch_op:
        batch_op.drop_index(
            "ix_article_facts_active",
            sqlite_where=sa.text("superseded_by_id IS NULL AND retracted_at IS NULL"),
            postgresql_where=sa.text("superseded_by_id IS NULL AND retracted_at IS NULL"),
        )

    op.drop_table("article_facts")
    op.drop_table("template_versions")
    op.drop_table("hospital_articles")
    op.drop_table("api_tokens")
    op.drop_table("users")
    op.drop_table("llm_calls")
