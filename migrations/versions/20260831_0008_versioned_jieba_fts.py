"""Allow versioned raw and deterministic jieba FTS Index Sets.

Revision ID: 20260831_0008
Revises: 20260831_0007
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0008"
down_revision: str | None = "20260831_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_IDENTITY_PREFIX = (
    "index_schema_version = 'm2-document-index-set-v1' "
    "AND embedding_purpose = 'document' "
)
_IDENTITY_SUFFIX = (
    "AND embedding_identity_sha256 ~ '^[0-9a-f]{64}$' "
    "AND embedding_model = btrim(embedding_model) "
    "AND char_length(embedding_model) BETWEEN 1 AND 200 "
    "AND embedding_version = btrim(embedding_version) "
    "AND char_length(embedding_version) BETWEEN 1 AND 100"
)


def upgrade() -> None:
    """Permit old raw indexes and new fixed jieba-search indexes to coexist."""

    op.drop_constraint(
        op.f("ck_document_index_sets_identity_format"),
        "document_index_sets",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_document_index_sets_identity_format"),
        "document_index_sets",
        _IDENTITY_PREFIX + "AND fts_builder_version IN "
        "('m2-fts-raw-retrieval-v1', 'm2-fts-jieba-search-v1') " + _IDENTITY_SUFFIX,
    )


def downgrade() -> None:
    """Restore the old-only contract without silently deleting new Index Sets."""

    new_index_count = op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM document_index_sets "
            "WHERE fts_builder_version = :builder_version"
        ),
        {"builder_version": "m2-fts-jieba-search-v1"},
    )
    if new_index_count:
        raise RuntimeError(
            "cannot downgrade while versioned jieba FTS Index Sets exist"
        )

    op.drop_constraint(
        op.f("ck_document_index_sets_identity_format"),
        "document_index_sets",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_document_index_sets_identity_format"),
        "document_index_sets",
        _IDENTITY_PREFIX
        + "AND fts_builder_version = 'm2-fts-raw-retrieval-v1' "
        + _IDENTITY_SUFFIX,
    )
