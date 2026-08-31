"""Create deterministic document Chunk Set metadata.

Revision ID: 20260831_0005
Revises: 20260829_0004
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260831_0005"
down_revision: str | None = "20260829_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID_KEY_PATTERN = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_STORAGE_KEY_PATTERN = (
    f"^{_UUID_KEY_PATTERN}/[a-z][a-z0-9_-]{{0,31}}/[0-9]{{4}}/"
    f"(0[1-9]|1[0-2])/{_UUID_KEY_PATTERN}\\.[a-z0-9]{{1,16}}$"
)


def upgrade() -> None:
    """Create one metadata row per deterministic Chunk Artifact generation."""

    op.create_table(
        "document_chunk_sets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_schema_version", sa.String(length=64), nullable=False),
        sa.Column("content_hash_version", sa.String(length=64), nullable=False),
        sa.Column("routed_schema_version", sa.String(length=64), nullable=False),
        sa.Column("canonical_schema_version", sa.String(length=64), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "parsed_publication_sha256",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "selected_artifact_content_sha256",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column("chunker_name", sa.String(length=64), nullable=False),
        sa.Column("chunker_version", sa.String(length=100), nullable=False),
        sa.Column("token_counter_name", sa.String(length=64), nullable=False),
        sa.Column("token_counter_version", sa.String(length=100), nullable=False),
        sa.Column("normalization_version", sa.String(length=100), nullable=False),
        sa.Column(
            "config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("config_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("output_sha256", sa.String(length=64), nullable=True),
        sa.Column("chunk_storage_key", sa.String(length=512), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=True),
        sa.Column("text_chunk_count", sa.Integer(), nullable=True),
        sa.Column("table_chunk_count", sa.Integer(), nullable=True),
        sa.Column("total_token_count", sa.BigInteger(), nullable=True),
        sa.Column("excluded_span_count", sa.Integer(), nullable=True),
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
            "artifact_schema_version = 'm2-canonical-chunk-artifact-v1'",
            name=op.f("ck_document_chunk_sets_artifact_schema_version_allowed"),
        ),
        sa.CheckConstraint(
            "content_hash_version = 'm2-chunk-content-v1'",
            name=op.f("ck_document_chunk_sets_content_hash_version_allowed"),
        ),
        sa.CheckConstraint(
            "routed_schema_version = 'm2-routed-parsed-document-v1'",
            name=op.f("ck_document_chunk_sets_routed_schema_version_allowed"),
        ),
        sa.CheckConstraint(
            "canonical_schema_version = 'm2-canonical-parsed-artifact-v1'",
            name=op.f("ck_document_chunk_sets_canonical_schema_version_allowed"),
        ),
        sa.CheckConstraint(
            "source_sha256 ~ '^[0-9a-f]{64}$' "
            "AND parsed_publication_sha256 ~ '^[0-9a-f]{64}$' "
            "AND selected_artifact_content_sha256 ~ '^[0-9a-f]{64}$' "
            "AND config_sha256 ~ '^[0-9a-f]{64}$' "
            "AND (output_sha256 IS NULL "
            "OR output_sha256 ~ '^[0-9a-f]{64}$')",
            name=op.f("ck_document_chunk_sets_hashes_format"),
        ),
        sa.CheckConstraint(
            "chunker_name ~ '^[a-z][a-z0-9_]{0,63}$' "
            "AND char_length(chunker_version) BETWEEN 1 AND 100 "
            "AND token_counter_name ~ '^[a-z][a-z0-9_]{0,63}$' "
            "AND char_length(token_counter_version) BETWEEN 1 AND 100 "
            "AND char_length(normalization_version) BETWEEN 1 AND 100",
            name=op.f("ck_document_chunk_sets_implementation_identity_format"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(config_json) = 'object'",
            name=op.f("ck_document_chunk_sets_config_json_object"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'chunking', 'ready', 'failed')",
            name=op.f("ck_document_chunk_sets_status_allowed"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name=op.f("ck_document_chunk_sets_attempt_count_nonnegative"),
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND attempt_count = 0 "
            "AND started_at IS NULL AND completed_at IS NULL) "
            "OR (status = 'chunking' AND attempt_count >= 1 "
            "AND started_at IS NOT NULL AND completed_at IS NULL) "
            "OR (status IN ('ready', 'failed') AND attempt_count >= 1 "
            "AND started_at IS NOT NULL AND completed_at IS NOT NULL)",
            name=op.f("ck_document_chunk_sets_attempt_timestamps_match_status"),
        ),
        sa.CheckConstraint(
            "started_at IS NULL OR started_at >= created_at",
            name=op.f("ck_document_chunk_sets_started_after_created"),
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name=op.f("ck_document_chunk_sets_completed_after_started"),
        ),
        sa.CheckConstraint(
            "chunk_storage_key IS NULL "
            f"OR (chunk_storage_key ~ '{_STORAGE_KEY_PATTERN}' "
            "AND split_part(chunk_storage_key, '/', 1) = tenant_id::text "
            "AND split_part(chunk_storage_key, '/', 2) = 'chunks' "
            "AND split_part(split_part(chunk_storage_key, '/', 5), '.', 1) "
            "= id::text AND right(chunk_storage_key, 5) = '.json')",
            name=op.f("ck_document_chunk_sets_chunk_storage_key_format"),
        ),
        sa.CheckConstraint(
            "(status = 'ready' AND output_sha256 IS NOT NULL "
            "AND chunk_storage_key IS NOT NULL AND chunk_count IS NOT NULL "
            "AND text_chunk_count IS NOT NULL AND table_chunk_count IS NOT NULL "
            "AND total_token_count IS NOT NULL "
            "AND excluded_span_count IS NOT NULL AND error_message IS NULL) "
            "OR (status = 'failed' AND output_sha256 IS NULL "
            "AND chunk_storage_key IS NULL AND chunk_count IS NULL "
            "AND text_chunk_count IS NULL AND table_chunk_count IS NULL "
            "AND total_token_count IS NULL AND excluded_span_count IS NULL "
            "AND error_message IS NOT NULL) "
            "OR (status IN ('pending', 'chunking') AND output_sha256 IS NULL "
            "AND chunk_storage_key IS NULL AND chunk_count IS NULL "
            "AND text_chunk_count IS NULL AND table_chunk_count IS NULL "
            "AND total_token_count IS NULL AND excluded_span_count IS NULL "
            "AND error_message IS NULL)",
            name=op.f("ck_document_chunk_sets_result_matches_status"),
        ),
        sa.CheckConstraint(
            "chunk_count IS NULL OR (chunk_count >= 1 "
            "AND text_chunk_count >= 0 AND table_chunk_count >= 0 "
            "AND text_chunk_count + table_chunk_count = chunk_count "
            "AND total_token_count >= chunk_count "
            "AND excluded_span_count >= 0)",
            name=op.f("ck_document_chunk_sets_statistics_consistent"),
        ),
        sa.CheckConstraint(
            "error_message IS NULL OR char_length(error_message) BETWEEN 1 AND 1000",
            name=op.f("ck_document_chunk_sets_error_message_length"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_version_id", "document_id"],
            [
                "document_versions.tenant_id",
                "document_versions.id",
                "document_versions.document_id",
            ],
            name=op.f("fk_document_chunk_sets_tenant_version_document"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_chunk_sets")),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name=op.f("uq_document_chunk_sets_tenant_id"),
        ),
    )
    op.create_index(
        "ix_document_chunk_sets_tenant_status",
        "document_chunk_sets",
        ["tenant_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_document_chunk_sets_tenant_version_created",
        "document_chunk_sets",
        ["tenant_id", "document_version_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove Chunk Set metadata without touching document versions."""

    op.drop_index(
        "ix_document_chunk_sets_tenant_version_created",
        table_name="document_chunk_sets",
    )
    op.drop_index(
        "ix_document_chunk_sets_tenant_status",
        table_name="document_chunk_sets",
    )
    op.drop_table("document_chunk_sets")
