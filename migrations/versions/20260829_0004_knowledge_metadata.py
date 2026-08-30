"""Create M2 file, document, version, and ACL metadata.

Revision ID: 20260829_0004
Revises: 20260828_0003
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260829_0004"
down_revision: str | None = "20260828_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID_KEY_PATTERN = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_STORAGE_KEY_PATTERN = (
    f"^{_UUID_KEY_PATTERN}/[a-z][a-z0-9_-]{{0,31}}/[0-9]{{4}}/"
    f"(0[1-9]|1[0-2])/{_UUID_KEY_PATTERN}\\.[a-z0-9]{{1,16}}$"
)


def upgrade() -> None:
    """Create the M2 knowledge metadata and authorization boundary."""

    op.create_table(
        "files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("extension", sa.String(length=8), nullable=False),
        sa.Column("mime_type", sa.String(length=127), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'uploaded'"),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "category ~ '^[a-z][a-z0-9_-]{0,31}$'",
            name=op.f("ck_files_category_format"),
        ),
        sa.CheckConstraint(
            "(status = 'soft_deleted' AND deleted_at IS NOT NULL) "
            "OR (status <> 'soft_deleted' AND deleted_at IS NULL)",
            name=op.f("ck_files_deleted_at_matches_status"),
        ),
        sa.CheckConstraint(
            "deleted_at IS NULL OR deleted_at >= created_at",
            name=op.f("ck_files_deleted_after_created"),
        ),
        sa.CheckConstraint(
            "(status = 'failed' AND error_message IS NOT NULL) "
            "OR status = 'soft_deleted' "
            "OR (status NOT IN ('failed', 'soft_deleted') "
            "AND error_message IS NULL)",
            name=op.f("ck_files_error_matches_status"),
        ),
        sa.CheckConstraint(
            "error_message IS NULL OR char_length(error_message) BETWEEN 1 AND 1000",
            name=op.f("ck_files_error_message_length"),
        ),
        sa.CheckConstraint(
            "extension IN ('.pdf', '.docx', '.xlsx', '.csv') "
            "AND right(storage_key, char_length(extension)) = extension",
            name=op.f("ck_files_extension_allowed"),
        ),
        sa.CheckConstraint(
            "mime_type = lower(mime_type) "
            "AND mime_type ~ '^[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*$'",
            name=op.f("ck_files_mime_type_format"),
        ),
        sa.CheckConstraint(
            "original_name = btrim(original_name) "
            "AND char_length(original_name) BETWEEN 1 AND 255 "
            "AND position('/' in original_name) = 0 "
            "AND position(chr(92) in original_name) = 0",
            name=op.f("ck_files_original_name_format"),
        ),
        sa.CheckConstraint(
            "sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_files_sha256_format"),
        ),
        sa.CheckConstraint(
            "size_bytes >= 0",
            name=op.f("ck_files_size_bytes_nonnegative"),
        ),
        sa.CheckConstraint(
            "status IN "
            "('uploaded', 'validating', 'parsing', 'indexing', "
            "'ready', 'failed', 'soft_deleted')",
            name=op.f("ck_files_status_allowed"),
        ),
        sa.CheckConstraint(
            f"storage_key ~ '{_STORAGE_KEY_PATTERN}' "
            "AND split_part(storage_key, '/', 1) = tenant_id::text "
            "AND split_part(storage_key, '/', 2) = category "
            "AND split_part(storage_key, '/', 3) >= '1970' "
            "AND split_part(split_part(storage_key, '/', 5), '.', 1) = id::text",
            name=op.f("ck_files_storage_key_format"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_files_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "owner_user_id"],
            ["users.tenant_id", "users.id"],
            name=op.f("fk_files_tenant_owner"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_files")),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name=op.f("uq_files_tenant_id_id"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "storage_key",
            name=op.f("uq_files_tenant_storage_key"),
        ),
    )
    op.create_index(
        "ix_files_tenant_owner_created",
        "files",
        ["tenant_id", "owner_user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_files_tenant_status",
        "files",
        ["tenant_id", "status"],
        unique=False,
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("document_type", sa.String(length=32), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=True),
        sa.Column("market", sa.String(length=2), nullable=True),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column(
            "access_level",
            sa.String(length=16),
            server_default=sa.text("'private'"),
            nullable=False,
        ),
        sa.Column("active_version_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "access_level IN ('private', 'tenant', 'restricted')",
            name=op.f("ck_documents_access_level_allowed"),
        ),
        sa.CheckConstraint(
            "deleted_at IS NULL OR deleted_at >= created_at",
            name=op.f("ck_documents_deleted_after_created"),
        ),
        sa.CheckConstraint(
            "document_type ~ '^[a-z][a-z0-9_-]{0,31}$'",
            name=op.f("ck_documents_document_type_format"),
        ),
        sa.CheckConstraint(
            "language IS NULL OR language ~ '^[a-z]{2}(-[A-Z]{2})?$'",
            name=op.f("ck_documents_language_format"),
        ),
        sa.CheckConstraint(
            "market IS NULL OR market ~ '^[A-Z]{2}$'",
            name=op.f("ck_documents_market_format"),
        ),
        sa.CheckConstraint(
            "title = btrim(title) AND char_length(title) BETWEEN 1 AND 300",
            name=op.f("ck_documents_title_length"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_documents_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "owner_user_id"],
            ["users.tenant_id", "users.id"],
            name=op.f("fk_documents_tenant_owner"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name=op.f("fk_documents_tenant_product"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name=op.f("uq_documents_tenant_id_id"),
        ),
    )
    op.create_index(
        "ix_documents_tenant_active",
        "documents",
        ["tenant_id", "active_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_documents_tenant_owner_created",
        "documents",
        ["tenant_id", "owner_user_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "document_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("file_id", sa.Uuid(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("parser_name", sa.String(length=64), nullable=True),
        sa.Column("parser_version", sa.String(length=64), nullable=True),
        sa.Column("parsed_storage_key", sa.String(length=512), nullable=True),
        sa.Column(
            "parse_status",
            sa.String(length=16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "index_status",
            sa.String(length=16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_document_versions_content_hash_format"),
        ),
        sa.CheckConstraint(
            "index_status IN ('pending', 'indexing', 'ready', 'failed')",
            name=op.f("ck_document_versions_index_status_allowed"),
        ),
        sa.CheckConstraint(
            "parse_status IN ('pending', 'parsing', 'ready', 'failed')",
            name=op.f("ck_document_versions_parse_status_allowed"),
        ),
        sa.CheckConstraint(
            "parsed_storage_key IS NULL "
            f"OR (parsed_storage_key ~ '{_STORAGE_KEY_PATTERN}' "
            "AND split_part(parsed_storage_key, '/', 1) = tenant_id::text)",
            name=op.f("ck_document_versions_parsed_storage_key_format"),
        ),
        sa.CheckConstraint(
            "parser_name IS NULL OR parser_name ~ '^[a-z][a-z0-9_-]{0,63}$'",
            name=op.f("ck_document_versions_parser_name_format"),
        ),
        sa.CheckConstraint(
            "parser_version IS NULL OR char_length(parser_version) BETWEEN 1 AND 64",
            name=op.f("ck_document_versions_parser_version_length"),
        ),
        sa.CheckConstraint(
            "index_status <> 'ready' OR parse_status = 'ready'",
            name=op.f("ck_document_versions_ready_index_has_ready_parse"),
        ),
        sa.CheckConstraint(
            "parse_status <> 'ready' "
            "OR (parser_name IS NOT NULL AND parser_version IS NOT NULL "
            "AND parsed_storage_key IS NOT NULL)",
            name=op.f("ck_document_versions_ready_parse_has_artifact"),
        ),
        sa.CheckConstraint(
            "version_no >= 1",
            name=op.f("ck_document_versions_version_no_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["documents.tenant_id", "documents.id"],
            name=op.f("fk_document_versions_tenant_document"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "file_id"],
            ["files.tenant_id", "files.id"],
            name=op.f("fk_document_versions_tenant_file"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_versions")),
        sa.UniqueConstraint(
            "tenant_id",
            "document_id",
            "content_hash",
            name=op.f("uq_document_versions_tenant_document_hash"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "document_id",
            "version_no",
            name=op.f("uq_document_versions_tenant_document_version"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "file_id",
            name=op.f("uq_document_versions_tenant_file"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            "document_id",
            name=op.f("uq_document_versions_tenant_id_document_id"),
        ),
    )

    op.create_foreign_key(
        "fk_documents_active_version",
        "documents",
        "document_versions",
        ["tenant_id", "active_version_id", "id"],
        ["tenant_id", "id", "document_id"],
    )

    op.create_table(
        "document_acl",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("subject_type", sa.String(length=16), nullable=False),
        sa.Column("role_name", sa.String(length=64), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("market_code", sa.String(length=2), nullable=True),
        sa.Column(
            "permission",
            sa.String(length=16),
            server_default=sa.text("'read'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "market_code IS NULL OR market_code ~ '^[A-Z]{2}$'",
            name=op.f("ck_document_acl_market_code_format"),
        ),
        sa.CheckConstraint(
            "permission = 'read'",
            name=op.f("ck_document_acl_permission_read_only"),
        ),
        sa.CheckConstraint(
            "role_name IS NULL "
            "OR role_name IN "
            "('company_owner', 'product_scout', 'amazon_operator')",
            name=op.f("ck_document_acl_role_name_allowed"),
        ),
        sa.CheckConstraint(
            "(subject_type = 'role' AND role_name IS NOT NULL "
            "AND user_id IS NULL AND market_code IS NULL) "
            "OR (subject_type = 'user' AND role_name IS NULL "
            "AND user_id IS NOT NULL AND market_code IS NULL) "
            "OR (subject_type = 'market' AND role_name IS NULL "
            "AND user_id IS NULL AND market_code IS NOT NULL)",
            name=op.f("ck_document_acl_subject_shape"),
        ),
        sa.CheckConstraint(
            "subject_type IN ('role', 'user', 'market')",
            name=op.f("ck_document_acl_subject_type_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["role_name"],
            ["roles.name"],
            name=op.f("fk_document_acl_role_name_roles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["documents.tenant_id", "documents.id"],
            name=op.f("fk_document_acl_tenant_document"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name=op.f("fk_document_acl_tenant_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_acl")),
    )
    op.create_index(
        "ix_document_acl_tenant_document",
        "document_acl",
        ["tenant_id", "document_id"],
        unique=False,
    )
    op.create_index(
        "uq_document_acl_market",
        "document_acl",
        ["tenant_id", "document_id", "market_code"],
        unique=True,
        postgresql_where=sa.text("subject_type = 'market'"),
    )
    op.create_index(
        "uq_document_acl_role",
        "document_acl",
        ["tenant_id", "document_id", "role_name"],
        unique=True,
        postgresql_where=sa.text("subject_type = 'role'"),
    )
    op.create_index(
        "uq_document_acl_user",
        "document_acl",
        ["tenant_id", "document_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("subject_type = 'user'"),
    )


def downgrade() -> None:
    """Remove the M2 knowledge metadata boundary only."""

    op.drop_table("document_acl")
    op.drop_constraint(
        "fk_documents_active_version",
        "documents",
        type_="foreignkey",
    )
    op.drop_table("document_versions")
    op.drop_table("documents")
    op.drop_table("files")
