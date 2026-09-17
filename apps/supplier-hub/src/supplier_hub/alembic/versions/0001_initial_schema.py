"""Initial hub schema: data-model H.1–H.8, H.10, H.11, H.19–H.21.

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
        sa.Column("assessment_id", sa.Uuid(), nullable=True),
        sa.Column("request", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("response", sa.JSON(none_as_null=True), nullable=True),
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
        sa.CheckConstraint(
            "purpose IN ('NORMALIZE_ITEM', 'JUDGE', 'EXTRACT_ANSWER', 'PROPOSE_ATTRIBUTE', 'SIMULATE_SUPPLIER')",
            name=op.f("ck_llm_calls_purpose"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_calls")),
    )
    op.create_table(
        "organizations",
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("supplier_facing_alias", sa.String(), nullable=True),
        sa.Column("disclose_name_to_suppliers", sa.Boolean(), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("cors_origin", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "type IN ('HOSPITAL', 'SUPPLIER', 'OPERATOR')", name=op.f("ck_organizations_type")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
        sa.UniqueConstraint("code", name=op.f("uq_organizations_code")),
        sa.UniqueConstraint(
            "supplier_facing_alias", name=op.f("uq_organizations_supplier_facing_alias")
        ),
    )
    op.create_table(
        "hospital_principals",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.String(), nullable=False),
        sa.Column("first_seen_at", service_kit.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", service_kit.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("is_blocked", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name=op.f("fk_hospital_principals_tenant_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hospital_principals")),
        sa.UniqueConstraint(
            "tenant_id", "subject_id", name=op.f("uq_hospital_principals_tenant_id_subject_id")
        ),
    )
    op.create_table(
        "used_assertion_jtis",
        sa.Column("jti", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", service_kit.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name=op.f("fk_used_assertion_jtis_tenant_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_used_assertion_jtis")),
        sa.UniqueConstraint("jti", name=op.f("uq_used_assertion_jtis_jti")),
    )
    op.create_table(
        "users",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("role IN ('SUPPLIER', 'OPERATOR')", name=op.f("ck_users_role")),
        sa.ForeignKeyConstraint(
            ["org_id"], ["organizations.id"], name=op.f("fk_users_org_id_organizations")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_table(
        "api_tokens",
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("principal_id", sa.Uuid(), nullable=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("kid", sa.String(), nullable=True),
        sa.Column("assertion_jti", sa.String(), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", service_kit.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", service_kit.db.UtcDateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", service_kit.db.UtcDateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "(user_id IS NULL) <> (principal_id IS NULL)", name=op.f("ck_api_tokens_one_owner")
        ),
        sa.ForeignKeyConstraint(
            ["principal_id"],
            ["hospital_principals.id"],
            name=op.f("fk_api_tokens_principal_id_hospital_principals"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["organizations.id"], name=op.f("fk_api_tokens_tenant_id_organizations")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_api_tokens_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_api_tokens_token_hash")),
    )
    op.create_table(
        "attribute_definitions",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("value_type", sa.String(), nullable=False),
        sa.Column("unit", sa.String(), nullable=True),
        sa.Column("options", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("labels", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("synonyms", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("question_hint", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("origin", sa.String(), nullable=False),
        sa.Column("merged_into_id", sa.Uuid(), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", service_kit.db.UtcDateTime(timezone=True), nullable=True),
        sa.Column("created_at", service_kit.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", service_kit.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('ATTRIBUTE', 'IDENTIFIER')", name=op.f("ck_attribute_definitions_kind")
        ),
        sa.CheckConstraint(
            "origin IN ('SEED', 'PROPOSAL')", name=op.f("ck_attribute_definitions_origin")
        ),
        sa.CheckConstraint(
            "status IN ('PROVISIONAL', 'APPROVED', 'DEPRECATED')",
            name=op.f("ck_attribute_definitions_status"),
        ),
        sa.CheckConstraint(
            "value_type IN ('number', 'bool', 'enum', 'text', 'list')",
            name=op.f("ck_attribute_definitions_value_type_known"),
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"], ["users.id"], name=op.f("fk_attribute_definitions_approved_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["merged_into_id"],
            ["attribute_definitions.id"],
            name=op.f("fk_attribute_definitions_merged_into_id_attribute_definitions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attribute_definitions")),
        sa.UniqueConstraint("key", name=op.f("uq_attribute_definitions_key")),
    )
    op.create_table(
        "category_templates",
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("parent_code", sa.String(), nullable=True),
        sa.Column("keywords", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("limited_template", sa.Boolean(), nullable=False),
        sa.Column("attributes", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("definition_hash", sa.String(length=64), nullable=False),
        sa.Column("change_note", sa.String(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", service_kit.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("created_at", service_kit.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["users.id"], name=op.f("fk_category_templates_updated_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_category_templates")),
        sa.UniqueConstraint("code", name=op.f("uq_category_templates_code")),
    )
    op.create_table(
        "product_families",
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("manufacturer", sa.String(), nullable=False),
        sa.Column("brand_name", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("product_type", sa.String(), nullable=True),
        sa.Column("category_code", sa.String(), nullable=True),
        sa.Column("category_source", sa.String(), nullable=True),
        sa.Column("category_set_by", sa.Uuid(), nullable=True),
        sa.Column("category_set_at", service_kit.db.UtcDateTime(timezone=True), nullable=True),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("properties_text", sa.String(), nullable=True),
        sa.Column("source_document", sa.String(), nullable=True),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("normalized_hash", sa.String(length=64), nullable=True),
        sa.Column("raw", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "category_source IN ('LLM_SUGGESTED', 'SUPPLIER')",
            name=op.f("ck_product_families_category_source"),
        ),
        sa.ForeignKeyConstraint(
            ["category_set_by"],
            ["users.id"],
            name=op.f("fk_product_families_category_set_by_users"),
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["organizations.id"],
            name=op.f("fk_product_families_supplier_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_families")),
    )
    op.create_table(
        "tenant_signing_keys",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("kid", sa.String(), nullable=False),
        sa.Column("public_jwk", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("not_before", service_kit.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("not_after", service_kit.db.UtcDateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", service_kit.db.UtcDateTime(timezone=True), nullable=True),
        sa.Column("registered_by", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "public_jwk NOT LIKE '%\"d\"%'", name=op.f("ck_tenant_signing_keys_public_key_only")
        ),
        sa.ForeignKeyConstraint(
            ["registered_by"], ["users.id"], name=op.f("fk_tenant_signing_keys_registered_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name=op.f("fk_tenant_signing_keys_tenant_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenant_signing_keys")),
        sa.UniqueConstraint("kid", name=op.f("uq_tenant_signing_keys_kid")),
    )
    op.create_table(
        "product_variants",
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("article_no", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("order_unit", sa.String(), nullable=True),
        sa.Column("units_per_order_unit", sa.Integer(), nullable=True),
        sa.Column("order_units_per_shipping_unit", sa.Integer(), nullable=True),
        sa.Column("source_row", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["family_id"],
            ["product_families.id"],
            name=op.f("fk_product_variants_family_id_product_families"),
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["organizations.id"],
            name=op.f("fk_product_variants_supplier_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_variants")),
        sa.UniqueConstraint(
            "supplier_id", "article_no", name=op.f("uq_product_variants_supplier_id_article_no")
        ),
    )
    op.create_table(
        "item_facts",
        sa.Column("family_id", sa.Uuid(), nullable=True),
        sa.Column("variant_id", sa.Uuid(), nullable=True),
        sa.Column("attribute_key", sa.String(), nullable=False),
        sa.Column("value", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("raw_value", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("evidence_quote", sa.String(), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", service_kit.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("llm_call_id", sa.Uuid(), nullable=True),
        sa.Column("model_id", sa.String(), nullable=True),
        sa.Column("prompt_version", sa.String(), nullable=True),
        sa.Column("superseded_by_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "source IN ('CATALOG', 'EXTRACTION', 'SUPPLIER_ANSWER', 'UNAVAILABLE')",
            name=op.f("ck_item_facts_source"),
        ),
        sa.CheckConstraint(
            "(family_id IS NULL) <> (variant_id IS NULL)", name=op.f("ck_item_facts_one_scope")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_item_facts_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["family_id"],
            ["product_families.id"],
            name=op.f("fk_item_facts_family_id_product_families"),
        ),
        sa.ForeignKeyConstraint(
            ["llm_call_id"], ["llm_calls.id"], name=op.f("fk_item_facts_llm_call_id_llm_calls")
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by_id"],
            ["item_facts.id"],
            name=op.f("fk_item_facts_superseded_by_id_item_facts"),
        ),
        sa.ForeignKeyConstraint(
            ["variant_id"],
            ["product_variants.id"],
            name=op.f("fk_item_facts_variant_id_product_variants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_item_facts")),
    )
    with op.batch_alter_table("item_facts", schema=None) as batch_op:
        batch_op.create_index(
            "ix_item_facts_family_active",
            ["family_id", "attribute_key"],
            unique=False,
            sqlite_where=sa.text("superseded_by_id IS NULL"),
            postgresql_where=sa.text("superseded_by_id IS NULL"),
        )
        batch_op.create_index(
            "ix_item_facts_variant_active",
            ["variant_id", "attribute_key"],
            unique=False,
            sqlite_where=sa.text("superseded_by_id IS NULL"),
            postgresql_where=sa.text("superseded_by_id IS NULL"),
        )

    op.create_table(
        "item_search_projection",
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("category_code", sa.String(), nullable=True),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("attributes", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("attribute_fact_ids", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("unknown_attributes", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("additional_attributes", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("identifiers", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("search_text", sa.String(), nullable=False),
        sa.Column("record_hash", sa.String(length=64), nullable=False),
        sa.Column("updated_at", service_kit.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["organizations.id"],
            name=op.f("fk_item_search_projection_supplier_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["variant_id"],
            ["product_variants.id"],
            name=op.f("fk_item_search_projection_variant_id_product_variants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_item_search_projection")),
        sa.UniqueConstraint("variant_id", name=op.f("uq_item_search_projection_variant_id")),
    )


def downgrade() -> None:
    op.drop_table("item_search_projection")
    with op.batch_alter_table("item_facts", schema=None) as batch_op:
        batch_op.drop_index(
            "ix_item_facts_variant_active",
            sqlite_where=sa.text("superseded_by_id IS NULL"),
            postgresql_where=sa.text("superseded_by_id IS NULL"),
        )
        batch_op.drop_index(
            "ix_item_facts_family_active",
            sqlite_where=sa.text("superseded_by_id IS NULL"),
            postgresql_where=sa.text("superseded_by_id IS NULL"),
        )

    op.drop_table("item_facts")
    op.drop_table("product_variants")
    op.drop_table("tenant_signing_keys")
    op.drop_table("product_families")
    op.drop_table("category_templates")
    op.drop_table("attribute_definitions")
    op.drop_table("api_tokens")
    op.drop_table("users")
    op.drop_table("used_assertion_jtis")
    op.drop_table("hospital_principals")
    op.drop_table("organizations")
    op.drop_table("llm_calls")
