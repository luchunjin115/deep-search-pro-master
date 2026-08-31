"""Create retryable document Index Sets and atomic active pointers.

Revision ID: 20260831_0007
Revises: 20260831_0006
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260831_0007"
down_revision: str | None = "20260831_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add one independently retryable index generation per identity."""

    op.create_table(
        "document_index_sets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("document_chunk_set_id", sa.Uuid(), nullable=False),
        sa.Column("index_schema_version", sa.String(length=64), nullable=False),
        sa.Column(
            "embedding_identity_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "embedding_identity_sha256",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column("embedding_model", sa.String(length=200), nullable=False),
        sa.Column("embedding_version", sa.String(length=100), nullable=False),
        sa.Column("embedding_purpose", sa.String(length=16), nullable=False),
        sa.Column("fts_builder_version", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("chunk_count", sa.Integer(), nullable=True),
        sa.Column("text_chunk_count", sa.Integer(), nullable=True),
        sa.Column("table_chunk_count", sa.Integer(), nullable=True),
        sa.Column("total_token_count", sa.BigInteger(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "index_schema_version = 'm2-document-index-set-v1' "
            "AND embedding_purpose = 'document' "
            "AND fts_builder_version = 'm2-fts-raw-retrieval-v1' "
            "AND embedding_identity_sha256 ~ '^[0-9a-f]{64}$' "
            "AND embedding_model = btrim(embedding_model) "
            "AND char_length(embedding_model) BETWEEN 1 AND 200 "
            "AND embedding_version = btrim(embedding_version) "
            "AND char_length(embedding_version) BETWEEN 1 AND 100",
            name=op.f("ck_document_index_sets_identity_format"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(embedding_identity_json) = 'object'",
            name=op.f("ck_document_index_sets_identity_json_object"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'indexing', 'ready', 'failed')",
            name=op.f("ck_document_index_sets_status_allowed"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name=op.f("ck_document_index_sets_attempt_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND attempt_count = 0 "
            "AND started_at IS NULL AND completed_at IS NULL) "
            "OR (status = 'indexing' AND attempt_count >= 1 "
            "AND started_at IS NOT NULL AND completed_at IS NULL) "
            "OR (status IN ('ready', 'failed') AND attempt_count >= 1 "
            "AND started_at IS NOT NULL AND completed_at IS NOT NULL)",
            name=op.f("ck_document_index_sets_attempt_timestamps_match_status"),
        ),
        sa.CheckConstraint(
            "started_at IS NULL OR started_at >= created_at",
            name=op.f("ck_document_index_sets_started_after_created"),
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name=op.f("ck_document_index_sets_completed_after_started"),
        ),
        sa.CheckConstraint(
            "(status = 'ready' AND chunk_count IS NOT NULL "
            "AND text_chunk_count IS NOT NULL AND table_chunk_count IS NOT NULL "
            "AND total_token_count IS NOT NULL AND error_message IS NULL) "
            "OR (status = 'failed' AND chunk_count IS NULL "
            "AND text_chunk_count IS NULL AND table_chunk_count IS NULL "
            "AND total_token_count IS NULL AND error_message IS NOT NULL) "
            "OR (status IN ('pending', 'indexing') AND chunk_count IS NULL "
            "AND text_chunk_count IS NULL AND table_chunk_count IS NULL "
            "AND total_token_count IS NULL AND error_message IS NULL)",
            name=op.f("ck_document_index_sets_result_matches_status"),
        ),
        sa.CheckConstraint(
            "chunk_count IS NULL OR (chunk_count >= 1 "
            "AND text_chunk_count >= 0 AND table_chunk_count >= 0 "
            "AND text_chunk_count + table_chunk_count = chunk_count "
            "AND total_token_count >= chunk_count)",
            name=op.f("ck_document_index_sets_statistics_consistent"),
        ),
        sa.CheckConstraint(
            "error_message IS NULL OR char_length(error_message) BETWEEN 1 AND 1000",
            name=op.f("ck_document_index_sets_error_message_length"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_version_id", "document_id"],
            [
                "document_versions.tenant_id",
                "document_versions.id",
                "document_versions.document_id",
            ],
            name=op.f("fk_document_index_sets_tenant_version_document"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            [
                "tenant_id",
                "document_chunk_set_id",
                "document_version_id",
                "document_id",
            ],
            [
                "document_chunk_sets.tenant_id",
                "document_chunk_sets.id",
                "document_chunk_sets.document_version_id",
                "document_chunk_sets.document_id",
            ],
            name=op.f("fk_document_index_sets_tenant_set_version_document"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_index_sets")),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name=op.f("uq_document_index_sets_tenant_id"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            "document_version_id",
            "document_id",
            "status",
            name=op.f("uq_document_index_sets_active_target"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            "document_chunk_set_id",
            "document_version_id",
            "document_id",
            name=op.f("uq_document_index_sets_chunk_target"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "document_version_id",
            "document_chunk_set_id",
            "index_schema_version",
            "embedding_identity_sha256",
            "embedding_purpose",
            "fts_builder_version",
            name=op.f("uq_document_index_sets_version_identity"),
        ),
    )
    op.create_index(
        "ix_document_index_sets_tenant_version_status",
        "document_index_sets",
        ["tenant_id", "document_version_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_document_index_sets_tenant_document_created",
        "document_index_sets",
        ["tenant_id", "document_id", "created_at"],
        unique=False,
    )

    op.add_column(
        "document_versions",
        sa.Column("active_index_set_id", sa.Uuid(), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_document_versions_active_index_set_matches_status"),
        "document_versions",
        "active_index_set_id IS NULL OR index_status = 'ready'",
    )
    op.create_foreign_key(
        "fk_document_versions_active_index_set",
        "document_versions",
        "document_index_sets",
        [
            "tenant_id",
            "active_index_set_id",
            "id",
            "document_id",
            "index_status",
        ],
        ["tenant_id", "id", "document_version_id", "document_id", "status"],
    )

    op.add_column(
        "document_chunks",
        sa.Column("document_index_set_id", sa.Uuid(), nullable=False),
    )
    op.add_column(
        "document_chunks",
        sa.Column("embedding_cache_key", sa.String(length=71), nullable=False),
    )
    op.drop_constraint(
        "uq_document_chunks_set_chunk_id",
        "document_chunks",
        type_="unique",
    )
    op.drop_constraint(
        "uq_document_chunks_set_chunk_index",
        "document_chunks",
        type_="unique",
    )
    op.drop_constraint(
        op.f("ck_document_chunks_embedding_identity_matches_vector"),
        "document_chunks",
        type_="check",
    )
    op.drop_index(
        "ix_document_chunks_tenant_document_version_set_index",
        table_name="document_chunks",
    )
    op.create_unique_constraint(
        "uq_document_chunks_index_set_chunk_id",
        "document_chunks",
        ["tenant_id", "document_index_set_id", "chunk_id"],
    )
    op.create_unique_constraint(
        "uq_document_chunks_index_set_chunk_index",
        "document_chunks",
        ["tenant_id", "document_index_set_id", "chunk_index"],
    )
    op.create_check_constraint(
        op.f("ck_document_chunks_embedding_identity_matches_vector"),
        "document_chunks",
        "embedding IS NOT NULL AND embedding_model IS NOT NULL "
        "AND embedding_version IS NOT NULL",
    )
    op.create_check_constraint(
        op.f("ck_document_chunks_embedding_cache_key_format"),
        "document_chunks",
        "embedding_cache_key ~ '^sha256:[0-9a-f]{64}$'",
    )
    op.create_foreign_key(
        "fk_document_chunks_tenant_index_set_chunk_set_version_document",
        "document_chunks",
        "document_index_sets",
        [
            "tenant_id",
            "document_index_set_id",
            "document_chunk_set_id",
            "document_version_id",
            "document_id",
        ],
        [
            "tenant_id",
            "id",
            "document_chunk_set_id",
            "document_version_id",
            "document_id",
        ],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_document_chunks_tenant_document_version_index_set_index",
        "document_chunks",
        [
            "tenant_id",
            "document_id",
            "document_version_id",
            "document_index_set_id",
            "chunk_index",
        ],
        unique=False,
    )


def downgrade() -> None:
    """Restore the M2-13 Chunk Set-only storage shape."""

    op.drop_constraint(
        "fk_document_versions_active_index_set",
        "document_versions",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("ck_document_versions_active_index_set_matches_status"),
        "document_versions",
        type_="check",
    )
    op.drop_column("document_versions", "active_index_set_id")

    op.drop_index(
        "ix_document_chunks_tenant_document_version_index_set_index",
        table_name="document_chunks",
    )
    op.drop_constraint(
        "fk_document_chunks_tenant_index_set_chunk_set_version_document",
        "document_chunks",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("ck_document_chunks_embedding_cache_key_format"),
        "document_chunks",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_document_chunks_embedding_identity_matches_vector"),
        "document_chunks",
        type_="check",
    )
    op.drop_constraint(
        "uq_document_chunks_index_set_chunk_index",
        "document_chunks",
        type_="unique",
    )
    op.drop_constraint(
        "uq_document_chunks_index_set_chunk_id",
        "document_chunks",
        type_="unique",
    )
    op.drop_column("document_chunks", "embedding_cache_key")
    op.drop_column("document_chunks", "document_index_set_id")
    op.create_check_constraint(
        op.f("ck_document_chunks_embedding_identity_matches_vector"),
        "document_chunks",
        "(embedding IS NULL AND embedding_model IS NULL "
        "AND embedding_version IS NULL) "
        "OR (embedding IS NOT NULL AND embedding_model IS NOT NULL "
        "AND embedding_version IS NOT NULL)",
    )
    op.create_unique_constraint(
        "uq_document_chunks_set_chunk_id",
        "document_chunks",
        ["tenant_id", "document_chunk_set_id", "chunk_id"],
    )
    op.create_unique_constraint(
        "uq_document_chunks_set_chunk_index",
        "document_chunks",
        ["tenant_id", "document_chunk_set_id", "chunk_index"],
    )
    op.create_index(
        "ix_document_chunks_tenant_document_version_set_index",
        "document_chunks",
        [
            "tenant_id",
            "document_id",
            "document_version_id",
            "document_chunk_set_id",
            "chunk_index",
        ],
        unique=False,
    )

    op.drop_table("document_index_sets")
