"""Create document Chunk rows with PostgreSQL FTS and pgvector.

Revision ID: 20260831_0006
Revises: 20260831_0005
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "20260831_0006"
down_revision: str | None = "20260831_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create one constrained row per Canonical Chunk."""

    op.create_unique_constraint(
        "uq_document_chunk_sets_tenant_id_version_document",
        "document_chunk_sets",
        ["tenant_id", "id", "document_version_id", "document_id"],
    )
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version_id", sa.Uuid(), nullable=False),
        sa.Column("document_chunk_set_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.String(length=16), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("retrieval_text", sa.Text(), nullable=False),
        sa.Column("fts_text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "heading_path", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "page_numbers", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "source_block_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "source_spans", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "bounding_boxes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "overlap_json",
            postgresql.JSONB(astext_type=sa.Text(), none_as_null=True),
            nullable=True,
        ),
        sa.Column(
            "table_json",
            postgresql.JSONB(astext_type=sa.Text(), none_as_null=True),
            nullable=True,
        ),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('simple'::regconfig, fts_text)",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("embedding_model", sa.String(length=200), nullable=True),
        sa.Column("embedding_version", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "chunk_id ~ '^c[0-9]{6}$'",
            name=op.f("ck_document_chunks_chunk_id_format"),
        ),
        sa.CheckConstraint(
            "chunk_index >= 1",
            name=op.f("ck_document_chunks_chunk_index_positive"),
        ),
        sa.CheckConstraint(
            "kind IN ('text', 'table')",
            name=op.f("ck_document_chunks_kind_allowed"),
        ),
        sa.CheckConstraint(
            "char_length(body_text) BETWEEN 1 AND 2000000 "
            "AND char_length(retrieval_text) BETWEEN 1 AND 2000000 "
            "AND char_length(fts_text) BETWEEN 1 AND 2000000",
            name=op.f("ck_document_chunks_text_length"),
        ),
        sa.CheckConstraint(
            "token_count BETWEEN 1 AND 1000000",
            name=op.f("ck_document_chunks_token_count_range"),
        ),
        sa.CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_document_chunks_content_sha256_format"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(heading_path) = 'array' "
            "AND jsonb_array_length(heading_path) <= 9 "
            "AND jsonb_typeof(page_numbers) = 'array' "
            "AND jsonb_array_length(page_numbers) <= 2000 "
            "AND jsonb_typeof(source_block_ids) = 'array' "
            "AND jsonb_array_length(source_block_ids) BETWEEN 1 AND 1000 "
            "AND jsonb_typeof(source_spans) = 'array' "
            "AND jsonb_array_length(source_spans) BETWEEN 1 AND 1000 "
            "AND jsonb_typeof(bounding_boxes) = 'array' "
            "AND jsonb_typeof(warnings) = 'array' "
            "AND jsonb_array_length(warnings) <= 100",
            name=op.f("ck_document_chunks_metadata_shapes"),
        ),
        sa.CheckConstraint(
            "overlap_json IS NULL OR jsonb_typeof(overlap_json) = 'object'",
            name=op.f("ck_document_chunks_overlap_json_object"),
        ),
        sa.CheckConstraint(
            "(kind = 'text' AND table_json IS NULL) "
            "OR (kind = 'table' AND table_json IS NOT NULL "
            "AND jsonb_typeof(table_json) = 'object' "
            "AND table_json ? 'source_kind' AND table_json ? 'rows')",
            name=op.f("ck_document_chunks_table_matches_kind"),
        ),
        sa.CheckConstraint(
            "(embedding IS NULL AND embedding_model IS NULL "
            "AND embedding_version IS NULL) "
            "OR (embedding IS NOT NULL AND embedding_model IS NOT NULL "
            "AND embedding_version IS NOT NULL)",
            name=op.f("ck_document_chunks_embedding_identity_matches_vector"),
        ),
        sa.CheckConstraint(
            "embedding_model IS NULL OR "
            "(embedding_model = btrim(embedding_model) "
            "AND char_length(embedding_model) BETWEEN 1 AND 200)",
            name=op.f("ck_document_chunks_embedding_model_format"),
        ),
        sa.CheckConstraint(
            "embedding_version IS NULL OR "
            "(embedding_version = btrim(embedding_version) "
            "AND char_length(embedding_version) BETWEEN 1 AND 100)",
            name=op.f("ck_document_chunks_embedding_version_format"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_version_id", "document_id"],
            [
                "document_versions.tenant_id",
                "document_versions.id",
                "document_versions.document_id",
            ],
            name=op.f("fk_document_chunks_tenant_version_document"),
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
            name=op.f("fk_document_chunks_tenant_set_version_document"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_chunks")),
        sa.UniqueConstraint(
            "tenant_id",
            "document_chunk_set_id",
            "chunk_id",
            name=op.f("uq_document_chunks_set_chunk_id"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "document_chunk_set_id",
            "chunk_index",
            name=op.f("uq_document_chunks_set_chunk_index"),
        ),
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
    op.create_index(
        "ix_document_chunks_search_vector_gin",
        "document_chunks",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_document_chunks_embedding_hnsw_cosine",
        "document_chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    """Remove Chunk rows and the supporting Chunk Set reference key."""

    op.drop_index(
        "ix_document_chunks_embedding_hnsw_cosine",
        table_name="document_chunks",
        postgresql_using="hnsw",
    )
    op.drop_index(
        "ix_document_chunks_search_vector_gin",
        table_name="document_chunks",
        postgresql_using="gin",
    )
    op.drop_index(
        "ix_document_chunks_tenant_document_version_set_index",
        table_name="document_chunks",
    )
    op.drop_table("document_chunks")
    op.drop_constraint(
        "uq_document_chunk_sets_tenant_id_version_document",
        "document_chunk_sets",
        type_="unique",
    )
