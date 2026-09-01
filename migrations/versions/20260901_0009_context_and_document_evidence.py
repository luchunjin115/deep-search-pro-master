"""Add Context Artifacts and document Evidence provenance.

Revision ID: 20260901_0009
Revises: 20260831_0008
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260901_0009"
down_revision: str | None = "20260831_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Preserve M1 rows while adding auditable document Context/Evidence."""

    op.create_unique_constraint(
        "uq_document_versions_evidence_source",
        "document_versions",
        ["tenant_id", "id", "document_id", "file_id"],
    )
    op.create_unique_constraint(
        "uq_document_chunks_evidence_source",
        "document_chunks",
        [
            "tenant_id",
            "id",
            "document_index_set_id",
            "document_chunk_set_id",
            "document_version_id",
            "document_id",
        ],
    )

    op.create_table(
        "context_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("contract_version", sa.String(length=64), nullable=False),
        sa.Column("token_counter_version", sa.String(length=100), nullable=False),
        sa.Column("query_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "retrieval_snapshot_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "retrieval_snapshot_sha256",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "config_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("config_sha256", sa.String(length=64), nullable=False),
        sa.Column("context_sha256", sa.String(length=64), nullable=False),
        sa.Column("identity_sha256", sa.String(length=64), nullable=False),
        sa.Column("max_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("segment_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "contract_version = 'm2-context-bundle-v1' "
            "AND token_counter_version = 'm2-unicode-token-counter-v1'",
            name=op.f("ck_context_artifacts_versions_allowed"),
        ),
        sa.CheckConstraint(
            "query_sha256 ~ '^[0-9a-f]{64}$' "
            "AND retrieval_snapshot_sha256 ~ '^[0-9a-f]{64}$' "
            "AND config_sha256 ~ '^[0-9a-f]{64}$' "
            "AND context_sha256 ~ '^[0-9a-f]{64}$' "
            "AND identity_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_context_artifacts_hashes_format"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(retrieval_snapshot_json) = 'object' "
            "AND jsonb_typeof(config_json) = 'object'",
            name=op.f("ck_context_artifacts_json_objects"),
        ),
        sa.CheckConstraint(
            "max_tokens BETWEEN 700 AND 16000 "
            "AND total_tokens BETWEEN 0 AND max_tokens "
            "AND segment_count BETWEEN 0 AND 12",
            name=op.f("ck_context_artifacts_budget_bounds"),
        ),
        sa.CheckConstraint(
            "(segment_count = 0 AND total_tokens = 0) "
            "OR (segment_count >= 1 AND total_tokens >= segment_count)",
            name=op.f("ck_context_artifacts_empty_state_consistent"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "requested_by_user_id"],
            ["users.tenant_id", "users.id"],
            name=op.f("fk_context_artifacts_tenant_user"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_context_artifacts")),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name=op.f("uq_context_artifacts_tenant_id"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "requested_by_user_id",
            "identity_sha256",
            name=op.f("uq_context_artifacts_tenant_user_identity"),
        ),
    )
    op.create_index(
        "ix_context_artifacts_tenant_user_created",
        "context_artifacts",
        ["tenant_id", "requested_by_user_id", "created_at"],
        unique=False,
    )

    for constraint_name in (
        "ck_evidences_access_scope_object",
        "ck_evidences_query_summary_object",
        "ck_evidences_source_name_allowed",
        "ck_evidences_source_type_database",
        "ck_evidences_structured_data_object",
    ):
        op.drop_constraint(op.f(constraint_name), "evidences", type_="check")
    op.drop_constraint(
        "fk_evidences_tenant_tool_call_run",
        "evidences",
        type_="foreignkey",
    )

    op.alter_column(
        "evidences",
        "agent_run_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
    op.alter_column(
        "evidences",
        "tool_call_id",
        existing_type=sa.Uuid(),
        nullable=True,
    )
    op.alter_column(
        "evidences",
        "source_locator",
        existing_type=sa.String(length=255),
        nullable=True,
    )
    op.alter_column(
        "evidences",
        "title",
        existing_type=sa.String(length=200),
        type_=sa.String(length=300),
        existing_nullable=False,
    )
    for column_name in ("query_summary", "structured_data", "access_scope"):
        op.alter_column(
            "evidences",
            column_name,
            existing_type=postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        )

    op.add_column(
        "evidences",
        sa.Column(
            "evidence_schema_version",
            sa.String(length=64),
            server_default="m1-database-evidence-v1",
            nullable=False,
        ),
    )
    op.add_column(
        "evidences",
        sa.Column(
            "source_locator_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    for column_name in (
        "context_artifact_id",
        "file_id",
        "document_id",
        "document_version_id",
        "document_chunk_set_id",
        "document_index_set_id",
        "document_chunk_id",
    ):
        op.add_column("evidences", sa.Column(column_name, sa.Uuid(), nullable=True))
    op.add_column(
        "evidences",
        sa.Column("citation_ordinal", sa.Integer(), nullable=True),
    )
    op.add_column(
        "evidences",
        sa.Column("source_content_sha256", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "evidences",
        sa.Column("context_text_sha256", sa.String(length=64), nullable=True),
    )

    op.create_check_constraint(
        op.f("ck_evidences_source_type_allowed"),
        "evidences",
        "source_type IN ('database', 'knowledge', 'user_file')",
    )
    op.create_check_constraint(
        op.f("ck_evidences_source_name_matches_type"),
        "evidences",
        "(source_type = 'database' AND source_name IN "
        "('synthetic_inventory', 'synthetic_product_catalog')) "
        "OR (source_type IN ('knowledge', 'user_file') "
        "AND source_name = 'document_chunk')",
    )
    op.create_check_constraint(
        op.f("ck_evidences_runtime_trace_pair"),
        "evidences",
        "(agent_run_id IS NULL AND tool_call_id IS NULL) "
        "OR (agent_run_id IS NOT NULL AND tool_call_id IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_evidences_json_shapes"),
        "evidences",
        "(query_summary IS NULL OR jsonb_typeof(query_summary) = 'object') "
        "AND (structured_data IS NULL OR jsonb_typeof(structured_data) = 'object') "
        "AND (access_scope IS NULL OR jsonb_typeof(access_scope) = 'object') "
        "AND (source_locator_json IS NULL "
        "OR jsonb_typeof(source_locator_json) = 'object')",
    )
    op.create_check_constraint(
        op.f("ck_evidences_citation_ordinal_range"),
        "evidences",
        "citation_ordinal IS NULL OR citation_ordinal BETWEEN 1 AND 12",
    )
    op.create_check_constraint(
        op.f("ck_evidences_hashes_format"),
        "evidences",
        "(source_content_sha256 IS NULL "
        "OR source_content_sha256 ~ '^[0-9a-f]{64}$') "
        "AND (context_text_sha256 IS NULL "
        "OR context_text_sha256 ~ '^[0-9a-f]{64}$')",
    )
    op.create_check_constraint(
        op.f("ck_evidences_public_text_lengths"),
        "evidences",
        "title = btrim(title) AND char_length(title) BETWEEN 1 AND 300 "
        "AND char_length(excerpt) BETWEEN 1 AND 1000",
    )
    op.create_check_constraint(
        op.f("ck_evidences_source_shape"),
        "evidences",
        "(source_type = 'database' "
        "AND evidence_schema_version = 'm1-database-evidence-v1' "
        "AND agent_run_id IS NOT NULL AND tool_call_id IS NOT NULL "
        "AND source_locator IS NOT NULL AND source_locator_json IS NULL "
        "AND query_summary IS NOT NULL AND structured_data IS NOT NULL "
        "AND access_scope IS NOT NULL AND trust_level = 'internal_demo' "
        "AND context_artifact_id IS NULL AND citation_ordinal IS NULL "
        "AND file_id IS NULL AND document_id IS NULL "
        "AND document_version_id IS NULL AND document_chunk_set_id IS NULL "
        "AND document_index_set_id IS NULL AND document_chunk_id IS NULL "
        "AND source_content_sha256 IS NULL AND context_text_sha256 IS NULL) "
        "OR (source_type IN ('knowledge', 'user_file') "
        "AND evidence_schema_version = 'm2-document-evidence-v1' "
        "AND source_locator IS NULL AND source_locator_json IS NOT NULL "
        "AND query_summary IS NULL AND structured_data IS NULL "
        "AND access_scope IS NULL AND trust_level = 'document_snapshot' "
        "AND context_artifact_id IS NOT NULL "
        "AND citation_ordinal IS NOT NULL AND file_id IS NOT NULL "
        "AND document_id IS NOT NULL AND document_version_id IS NOT NULL "
        "AND document_chunk_set_id IS NOT NULL "
        "AND document_index_set_id IS NOT NULL "
        "AND document_chunk_id IS NOT NULL "
        "AND source_content_sha256 IS NOT NULL "
        "AND context_text_sha256 IS NOT NULL)",
    )

    op.create_foreign_key(
        "fk_evidences_tenant_tool_call_run",
        "evidences",
        "tool_calls",
        ["tenant_id", "tool_call_id", "agent_run_id"],
        ["tenant_id", "id", "agent_run_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_evidences_tenant_context",
        "evidences",
        "context_artifacts",
        ["tenant_id", "context_artifact_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_evidences_tenant_version_document_file",
        "evidences",
        "document_versions",
        ["tenant_id", "document_version_id", "document_id", "file_id"],
        ["tenant_id", "id", "document_id", "file_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_evidences_tenant_chunk_provenance",
        "evidences",
        "document_chunks",
        [
            "tenant_id",
            "document_chunk_id",
            "document_index_set_id",
            "document_chunk_set_id",
            "document_version_id",
            "document_id",
        ],
        [
            "tenant_id",
            "id",
            "document_index_set_id",
            "document_chunk_set_id",
            "document_version_id",
            "document_id",
        ],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_evidences_context_citation",
        "evidences",
        ["tenant_id", "context_artifact_id", "citation_ordinal"],
    )
    op.create_unique_constraint(
        "uq_evidences_context_chunk",
        "evidences",
        ["tenant_id", "context_artifact_id", "document_chunk_id"],
    )
    op.create_index(
        "ix_evidences_tenant_context_citation",
        "evidences",
        ["tenant_id", "context_artifact_id", "citation_ordinal"],
        unique=False,
    )
    op.create_index(
        "ix_evidences_tenant_document_version",
        "evidences",
        ["tenant_id", "document_id", "document_version_id"],
        unique=False,
    )


def downgrade() -> None:
    """Restore the M1 database-only shape without silently deleting evidence."""

    bind = op.get_bind()
    has_context = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM context_artifacts LIMIT 1)")
    ).scalar_one()
    has_document_evidence = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM evidences "
            "WHERE source_type IN ('knowledge', 'user_file') LIMIT 1)"
        )
    ).scalar_one()
    if has_context or has_document_evidence:
        raise RuntimeError(
            "Cannot downgrade M2-18 Context/Evidence while document artifacts exist"
        )

    op.drop_index("ix_evidences_tenant_document_version", table_name="evidences")
    op.drop_index("ix_evidences_tenant_context_citation", table_name="evidences")
    op.drop_constraint(
        "uq_evidences_context_chunk",
        "evidences",
        type_="unique",
    )
    op.drop_constraint(
        "uq_evidences_context_citation",
        "evidences",
        type_="unique",
    )
    for constraint_name in (
        "fk_evidences_tenant_chunk_provenance",
        "fk_evidences_tenant_version_document_file",
        "fk_evidences_tenant_context",
        "fk_evidences_tenant_tool_call_run",
    ):
        op.drop_constraint(constraint_name, "evidences", type_="foreignkey")
    for constraint_name in (
        "ck_evidences_source_shape",
        "ck_evidences_public_text_lengths",
        "ck_evidences_hashes_format",
        "ck_evidences_citation_ordinal_range",
        "ck_evidences_json_shapes",
        "ck_evidences_runtime_trace_pair",
        "ck_evidences_source_name_matches_type",
        "ck_evidences_source_type_allowed",
    ):
        op.drop_constraint(op.f(constraint_name), "evidences", type_="check")

    for column_name in (
        "context_text_sha256",
        "source_content_sha256",
        "citation_ordinal",
        "document_chunk_id",
        "document_index_set_id",
        "document_chunk_set_id",
        "document_version_id",
        "document_id",
        "file_id",
        "context_artifact_id",
        "source_locator_json",
        "evidence_schema_version",
    ):
        op.drop_column("evidences", column_name)

    for column_name in ("query_summary", "structured_data", "access_scope"):
        op.alter_column(
            "evidences",
            column_name,
            existing_type=postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        )
    op.alter_column(
        "evidences",
        "title",
        existing_type=sa.String(length=300),
        type_=sa.String(length=200),
        existing_nullable=False,
    )
    op.alter_column(
        "evidences",
        "source_locator",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.alter_column(
        "evidences",
        "tool_call_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )
    op.alter_column(
        "evidences",
        "agent_run_id",
        existing_type=sa.Uuid(),
        nullable=False,
    )

    op.create_check_constraint(
        op.f("ck_evidences_access_scope_object"),
        "evidences",
        "jsonb_typeof(access_scope) = 'object'",
    )
    op.create_check_constraint(
        op.f("ck_evidences_query_summary_object"),
        "evidences",
        "jsonb_typeof(query_summary) = 'object'",
    )
    op.create_check_constraint(
        op.f("ck_evidences_source_name_allowed"),
        "evidences",
        "source_name IN ('synthetic_inventory', 'synthetic_product_catalog')",
    )
    op.create_check_constraint(
        op.f("ck_evidences_source_type_database"),
        "evidences",
        "source_type = 'database'",
    )
    op.create_check_constraint(
        op.f("ck_evidences_structured_data_object"),
        "evidences",
        "jsonb_typeof(structured_data) = 'object'",
    )
    op.create_foreign_key(
        "fk_evidences_tenant_tool_call_run",
        "evidences",
        "tool_calls",
        ["tenant_id", "tool_call_id", "agent_run_id"],
        ["tenant_id", "id", "agent_run_id"],
        ondelete="CASCADE",
    )

    op.drop_index(
        "ix_context_artifacts_tenant_user_created",
        table_name="context_artifacts",
    )
    op.drop_table("context_artifacts")
    op.drop_constraint(
        "uq_document_chunks_evidence_source",
        "document_chunks",
        type_="unique",
    )
    op.drop_constraint(
        "uq_document_versions_evidence_source",
        "document_versions",
        type_="unique",
    )
