"""Assessment loop: data-model H.12–H.18 and H.22, plus the foreign keys that
point at them from item_facts (answer_id) and llm_calls (assessment_id).

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import service_kit.db

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("dedupe_key", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("run_after", service_kit.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("locked_at", service_kit.db.UtcDateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("finished_at", service_kit.db.UtcDateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('NORMALIZE_ITEM', 'ASSESS', 'EXTRACT_ANSWERS', 'PROPOSE_ATTRIBUTE', 'REBUILD_PROJECTION')",
            name=op.f("ck_jobs_kind"),
        ),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED')", name=op.f("ck_jobs_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
        sa.UniqueConstraint("dedupe_key", name=op.f("uq_jobs_dedupe_key")),
    )
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.create_index("ix_jobs_ready", ["status", "run_after"], unique=False)

    op.create_table(
        "assessments",
        sa.Column("hospital_tenant_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("article_ref", sa.String(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("current_requirement_id", sa.Uuid(), nullable=True),
        sa.Column("template_code", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("current_round", sa.Integer(), nullable=False),
        sa.Column("max_rounds", sa.Integer(), nullable=False),
        sa.Column("proposed_verdict", sa.String(), nullable=True),
        sa.Column("final_verdict", sa.String(), nullable=True),
        sa.Column("resolution_kind", sa.String(), nullable=True),
        sa.Column("resolution_note", sa.String(), nullable=True),
        sa.Column("manual_reason", sa.String(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by_principal_id", sa.Uuid(), nullable=False),
        sa.Column("resolved_by_principal_id", sa.Uuid(), nullable=True),
        sa.Column("assigned_to_principal_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", service_kit.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", service_kit.db.UtcDateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "final_verdict IN ('EQUIVALENT', 'EQUIVALENT_WITH_DEVIATIONS', 'NOT_EQUIVALENT', 'UNDETERMINED')",
            name=op.f("ck_assessments_final_verdict"),
        ),
        sa.CheckConstraint(
            "manual_reason IN ('ROUND_CAP', 'NO_PROGRESS', 'BLOCKING_UNAVAILABLE')",
            name=op.f("ck_assessments_manual_reason"),
        ),
        sa.CheckConstraint(
            "proposed_verdict IN ('EQUIVALENT', 'EQUIVALENT_WITH_DEVIATIONS', 'NOT_EQUIVALENT')",
            name=op.f("ck_assessments_proposed_verdict"),
        ),
        sa.CheckConstraint(
            "resolution_kind IN ('CONFIRMED', 'OVERRIDDEN', 'MANUAL')",
            name=op.f("ck_assessments_resolution_kind"),
        ),
        sa.CheckConstraint(
            "status IN ('ASSESSING', 'NEEDS_QUESTION_REVIEW', 'AWAITING_ANSWERS', 'PROPOSED_RESOLUTION', 'NEEDS_MANUAL_DECISION', 'FAILED', 'RESOLVED', 'CANCELLED')",
            name=op.f("ck_assessments_status"),
        ),
        sa.ForeignKeyConstraint(
            ["assigned_to_principal_id"],
            ["hospital_principals.id"],
            name=op.f("fk_assessments_assigned_to_principal_id_hospital_principals"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_principal_id"],
            ["hospital_principals.id"],
            name=op.f("fk_assessments_created_by_principal_id_hospital_principals"),
        ),
        sa.ForeignKeyConstraint(
            ["current_requirement_id"],
            ["requirements.id"],
            name=op.f("fk_assessments_current_requirement_id_requirements"),
            use_alter=True,
        ),
        sa.ForeignKeyConstraint(
            ["hospital_tenant_id"],
            ["organizations.id"],
            name=op.f("fk_assessments_hospital_tenant_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by_principal_id"],
            ["hospital_principals.id"],
            name=op.f("fk_assessments_resolved_by_principal_id_hospital_principals"),
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["organizations.id"],
            name=op.f("fk_assessments_supplier_id_organizations"),
        ),
        sa.ForeignKeyConstraint(
            ["variant_id"],
            ["product_variants.id"],
            name=op.f("fk_assessments_variant_id_product_variants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessments")),
    )
    with op.batch_alter_table("assessments", schema=None) as batch_op:
        batch_op.create_index(
            "ix_assessments_assignee",
            ["hospital_tenant_id", "assigned_to_principal_id", "status"],
            unique=False,
        )
        batch_op.create_index(
            "ux_assessments_open_pair",
            ["hospital_tenant_id", "article_ref", "variant_id"],
            unique=True,
            sqlite_where=sa.text("(status NOT IN ('RESOLVED', 'CANCELLED'))"),
            postgresql_where=sa.text("(status NOT IN ('RESOLVED', 'CANCELLED'))"),
        )

    op.create_table(
        "events",
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_principal_id", sa.Uuid(), nullable=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("from_status", sa.String(), nullable=True),
        sa.Column("to_status", sa.String(), nullable=True),
        sa.Column("data", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("created_at", service_kit.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "type IN ('CREATED', 'ROUND_COMPLETED', 'STATUS_CHANGED', 'REQUIREMENT_RECEIVED', 'QUESTION_EDITED', 'QUESTION_ADDED', 'QUESTIONS_SENT', 'PURCHASER_ANSWERS_RECEIVED', 'ANSWERS_SUBMITTED', 'FACTS_ADDED', 'ATTRIBUTE_PROPOSED', 'ASSIGNED', 'RESOLVED', 'CANCELLED', 'JOB_FAILED')",
            name=op.f("ck_events_type"),
        ),
        sa.CheckConstraint(
            "actor_user_id IS NULL OR actor_principal_id IS NULL", name=op.f("ck_events_one_actor")
        ),
        sa.ForeignKeyConstraint(
            ["actor_principal_id"],
            ["hospital_principals.id"],
            name=op.f("fk_events_actor_principal_id_hospital_principals"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], name=op.f("fk_events_actor_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"], ["assessments.id"], name=op.f("fk_events_assessment_id_assessments")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
    )
    op.create_table(
        "requirements",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("requirement_version", sa.Integer(), nullable=False),
        sa.Column("article_ref", sa.String(), nullable=False),
        sa.Column("template_code", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("requirement_hash", sa.String(length=64), nullable=False),
        sa.Column("answered_question_ids", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("received_by_principal_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", service_kit.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name=op.f("fk_requirements_assessment_id_assessments"),
        ),
        sa.ForeignKeyConstraint(
            ["received_by_principal_id"],
            ["hospital_principals.id"],
            name=op.f("fk_requirements_received_by_principal_id_hospital_principals"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["organizations.id"],
            name=op.f("fk_requirements_tenant_id_organizations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_requirements")),
    )
    op.create_table(
        "assessment_rounds",
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("round_no", sa.Integer(), nullable=False),
        sa.Column("requirement_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_record_hash", sa.String(length=64), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("input_snapshot", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("identifier_evidence", sa.String(), nullable=False),
        sa.Column("attribute_judgments", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("rule_verdict", sa.String(), nullable=False),
        sa.Column("llm_verdict", sa.String(), nullable=True),
        sa.Column("llm_confidence", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column("disagreement", sa.Boolean(), nullable=False),
        sa.Column("rationale", sa.String(), nullable=True),
        sa.Column("extra_concerns", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("outcome_status", sa.String(), nullable=False),
        sa.Column("definition_hash", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(), nullable=True),
        sa.Column("model_id", sa.String(), nullable=True),
        sa.Column("llm_call_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", service_kit.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "identifier_evidence IN ('SAME_TRADE_ITEM', 'NO_INFORMATION')",
            name=op.f("ck_assessment_rounds_identifier_evidence"),
        ),
        sa.CheckConstraint(
            "llm_verdict IN ('EQUIVALENT', 'EQUIVALENT_WITH_DEVIATIONS', 'NOT_EQUIVALENT', 'INSUFFICIENT_DATA')",
            name=op.f("ck_assessment_rounds_llm_verdict"),
        ),
        sa.CheckConstraint(
            "rule_verdict IN ('EQUIVALENT', 'EQUIVALENT_WITH_DEVIATIONS', 'NOT_EQUIVALENT', 'INSUFFICIENT_DATA')",
            name=op.f("ck_assessment_rounds_rule_verdict"),
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name=op.f("fk_assessment_rounds_assessment_id_assessments"),
        ),
        sa.ForeignKeyConstraint(
            ["llm_call_id"],
            ["llm_calls.id"],
            name=op.f("fk_assessment_rounds_llm_call_id_llm_calls"),
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["requirements.id"],
            name=op.f("fk_assessment_rounds_requirement_id_requirements"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessment_rounds")),
        sa.UniqueConstraint(
            "assessment_id", "round_no", name=op.f("uq_assessment_rounds_assessment_id_round_no")
        ),
    )
    op.create_table(
        "questions",
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("round_id", sa.Uuid(), nullable=True),
        sa.Column("addressee", sa.String(), nullable=False),
        sa.Column("attribute_key", sa.String(), nullable=True),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("expected_answer", sa.JSON(none_as_null=True), nullable=False),
        sa.Column("rationale", sa.String(), nullable=True),
        sa.Column("origin", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("edited_by_purchaser", sa.Boolean(), nullable=False),
        sa.Column("answered_in_requirement_id", sa.Uuid(), nullable=True),
        sa.Column("sent_at", service_kit.db.UtcDateTime(timezone=True), nullable=True),
        sa.Column("created_at", service_kit.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "addressee IN ('SUPPLIER', 'PURCHASER')", name=op.f("ck_questions_addressee")
        ),
        sa.CheckConstraint(
            "origin IN ('LLM', 'TEMPLATE', 'PURCHASER')", name=op.f("ck_questions_origin")
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'SENT', 'ANSWERED', 'UNAVAILABLE', 'WITHDRAWN')",
            name=op.f("ck_questions_status"),
        ),
        sa.ForeignKeyConstraint(
            ["answered_in_requirement_id"],
            ["requirements.id"],
            name=op.f("fk_questions_answered_in_requirement_id_requirements"),
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name=op.f("fk_questions_assessment_id_assessments"),
        ),
        sa.ForeignKeyConstraint(
            ["round_id"],
            ["assessment_rounds.id"],
            name=op.f("fk_questions_round_id_assessment_rounds"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_questions")),
    )
    op.create_table(
        "answers",
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("answered_by", sa.Uuid(), nullable=False),
        sa.Column("value", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("comment", sa.String(), nullable=True),
        sa.Column("cannot_provide", sa.Boolean(), nullable=False),
        sa.Column("applies_to_family", sa.Boolean(), nullable=False),
        sa.Column("is_draft", sa.Boolean(), nullable=False),
        sa.Column("submitted_at", service_kit.db.UtcDateTime(timezone=True), nullable=True),
        sa.Column("extraction_status", sa.String(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "extraction_status IN ('NOT_NEEDED', 'PENDING', 'EXTRACTED', 'UNCLEAR')",
            name=op.f("ck_answers_extraction_status"),
        ),
        sa.ForeignKeyConstraint(
            ["answered_by"], ["users.id"], name=op.f("fk_answers_answered_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["question_id"], ["questions.id"], name=op.f("fk_answers_question_id_questions")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_answers")),
        sa.UniqueConstraint("question_id", name=op.f("uq_answers_question_id")),
    )
    op.create_table(
        "attribute_proposals",
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("category_code", sa.String(), nullable=False),
        sa.Column("result", sa.String(), nullable=True),
        sa.Column("matched_attribute_id", sa.Uuid(), nullable=True),
        sa.Column("proposal", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("attribute_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("identifier_key", sa.String(), nullable=True),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", service_kit.db.UtcDateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.String(), nullable=True),
        sa.Column("llm_call_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", service_kit.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", service_kit.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "result IN ('EXISTING', 'NEW', 'IDENTIFIER')",
            name=op.f("ck_attribute_proposals_result"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'MATCHED', 'PROVISIONAL', 'APPROVED', 'MERGED', 'REJECTED', 'ROUTED')",
            name=op.f("ck_attribute_proposals_status"),
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["assessments.id"],
            name=op.f("fk_attribute_proposals_assessment_id_assessments"),
        ),
        sa.ForeignKeyConstraint(
            ["attribute_id"],
            ["attribute_definitions.id"],
            name=op.f("fk_attribute_proposals_attribute_id_attribute_definitions"),
        ),
        sa.ForeignKeyConstraint(
            ["llm_call_id"],
            ["llm_calls.id"],
            name=op.f("fk_attribute_proposals_llm_call_id_llm_calls"),
        ),
        sa.ForeignKeyConstraint(
            ["matched_attribute_id"],
            ["attribute_definitions.id"],
            name=op.f("fk_attribute_proposals_matched_attribute_id_attribute_definitions"),
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_attribute_proposals_question_id_questions"),
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["users.id"], name=op.f("fk_attribute_proposals_reviewed_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attribute_proposals")),
        sa.UniqueConstraint("question_id", name=op.f("uq_attribute_proposals_question_id")),
    )
    with op.batch_alter_table("item_facts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("answer_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_item_facts_answer_id_answers"), "answers", ["answer_id"], ["id"]
        )

    with op.batch_alter_table("llm_calls", schema=None) as batch_op:
        batch_op.create_foreign_key(
            batch_op.f("fk_llm_calls_assessment_id_assessments"),
            "assessments",
            ["assessment_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("llm_calls", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_llm_calls_assessment_id_assessments"), type_="foreignkey"
        )

    with op.batch_alter_table("item_facts", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_item_facts_answer_id_answers"), type_="foreignkey")
        batch_op.drop_column("answer_id")

    op.drop_table("attribute_proposals")
    op.drop_table("answers")
    op.drop_table("questions")
    op.drop_table("assessment_rounds")
    op.drop_table("requirements")
    op.drop_table("events")
    with op.batch_alter_table("assessments", schema=None) as batch_op:
        batch_op.drop_index(
            "ux_assessments_open_pair",
            sqlite_where=sa.text("(status NOT IN ('RESOLVED', 'CANCELLED'))"),
            postgresql_where=sa.text("(status NOT IN ('RESOLVED', 'CANCELLED'))"),
        )
        batch_op.drop_index("ix_assessments_assignee")

    op.drop_table("assessments")
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_index("ix_jobs_ready")

    op.drop_table("jobs")
