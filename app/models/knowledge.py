"""Knowledge-file metadata, document versions, and access-control models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

_UUID_KEY_PATTERN = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_STORAGE_KEY_PATTERN = (
    f"^{_UUID_KEY_PATTERN}/[a-z][a-z0-9_-]{{0,31}}/[0-9]{{4}}/"
    f"(0[1-9]|1[0-2])/{_UUID_KEY_PATTERN}\\.[a-z0-9]{{1,16}}$"
)


class StoredFile(Base):
    """Metadata for one immutable binary object in the Storage backend."""

    __tablename__ = "files"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_files_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "storage_key",
            name="uq_files_tenant_storage_key",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "owner_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_files_tenant_owner",
            ondelete="CASCADE",
        ),
        Index(
            "ix_files_tenant_owner_created",
            "tenant_id",
            "owner_user_id",
            "created_at",
        ),
        Index("ix_files_tenant_status", "tenant_id", "status"),
        CheckConstraint(
            "original_name = btrim(original_name) "
            "AND char_length(original_name) BETWEEN 1 AND 255 "
            "AND position('/' in original_name) = 0 "
            "AND position(chr(92) in original_name) = 0",
            name="original_name_format",
        ),
        CheckConstraint(
            f"storage_key ~ '{_STORAGE_KEY_PATTERN}' "
            "AND split_part(storage_key, '/', 1) = tenant_id::text "
            "AND split_part(storage_key, '/', 2) = category "
            "AND split_part(storage_key, '/', 3) >= '1970' "
            "AND split_part(split_part(storage_key, '/', 5), '.', 1) = id::text",
            name="storage_key_format",
        ),
        CheckConstraint(
            "extension IN ('.pdf', '.docx', '.xlsx', '.csv') "
            "AND right(storage_key, char_length(extension)) = extension",
            name="extension_allowed",
        ),
        CheckConstraint(
            "mime_type = lower(mime_type) "
            "AND mime_type ~ '^[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*$'",
            name="mime_type_format",
        ),
        CheckConstraint("size_bytes >= 0", name="size_bytes_nonnegative"),
        CheckConstraint(
            "sha256 ~ '^[0-9a-f]{64}$'",
            name="sha256_format",
        ),
        CheckConstraint(
            "category ~ '^[a-z][a-z0-9_-]{0,31}$'",
            name="category_format",
        ),
        CheckConstraint(
            "status IN "
            "('uploaded', 'validating', 'parsing', 'indexing', "
            "'ready', 'failed', 'soft_deleted')",
            name="status_allowed",
        ),
        CheckConstraint(
            "(status = 'failed' AND error_message IS NOT NULL) "
            "OR status = 'soft_deleted' "
            "OR (status NOT IN ('failed', 'soft_deleted') "
            "AND error_message IS NULL)",
            name="error_matches_status",
        ),
        CheckConstraint(
            "error_message IS NULL OR char_length(error_message) BETWEEN 1 AND 1000",
            name="error_message_length",
        ),
        CheckConstraint(
            "(status = 'soft_deleted' AND deleted_at IS NOT NULL) "
            "OR (status <> 'soft_deleted' AND deleted_at IS NULL)",
            name="deleted_at_matches_status",
        ),
        CheckConstraint(
            "deleted_at IS NULL OR deleted_at >= created_at",
            name="deleted_after_created",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    extension: Mapped[str] = mapped_column(String(8), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="uploaded",
        server_default="uploaded",
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Document(Base):
    """Stable logical identity whose active version changes atomically later."""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_documents_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "owner_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_documents_tenant_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name="fk_documents_tenant_product",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "active_version_id", "id"],
            [
                "document_versions.tenant_id",
                "document_versions.id",
                "document_versions.document_id",
            ],
            name="fk_documents_active_version",
            use_alter=True,
        ),
        Index(
            "ix_documents_tenant_owner_created",
            "tenant_id",
            "owner_user_id",
            "created_at",
        ),
        Index("ix_documents_tenant_active", "tenant_id", "active_version_id"),
        CheckConstraint(
            "title = btrim(title) AND char_length(title) BETWEEN 1 AND 300",
            name="title_length",
        ),
        CheckConstraint(
            "document_type ~ '^[a-z][a-z0-9_-]{0,31}$'",
            name="document_type_format",
        ),
        CheckConstraint(
            "language IS NULL OR language ~ '^[a-z]{2}(-[A-Z]{2})?$'",
            name="language_format",
        ),
        CheckConstraint(
            "market IS NULL OR market ~ '^[A-Z]{2}$'",
            name="market_format",
        ),
        CheckConstraint(
            "access_level IN ('private', 'tenant', 'restricted')",
            name="access_level_allowed",
        ),
        CheckConstraint(
            "deleted_at IS NULL OR deleted_at >= created_at",
            name="deleted_after_created",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    owner_user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[str | None] = mapped_column(String(8))
    market: Mapped[str | None] = mapped_column(String(2))
    product_id: Mapped[UUID | None] = mapped_column(Uuid)
    access_level: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="private",
        server_default="private",
    )
    active_version_id: Mapped[UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys=lambda: [
            DocumentVersion.tenant_id,
            DocumentVersion.document_id,
        ],
    )
    acl_entries: Mapped[list[DocumentAcl]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys=lambda: [DocumentAcl.tenant_id, DocumentAcl.document_id],
    )


class DocumentVersion(Base):
    """One immutable content revision and its parsing/indexing state."""

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            "document_id",
            name="uq_document_versions_tenant_id_document_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "document_id",
            "version_no",
            name="uq_document_versions_tenant_document_version",
        ),
        UniqueConstraint(
            "tenant_id",
            "document_id",
            "content_hash",
            name="uq_document_versions_tenant_document_hash",
        ),
        UniqueConstraint(
            "tenant_id",
            "file_id",
            name="uq_document_versions_tenant_file",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["documents.tenant_id", "documents.id"],
            name="fk_document_versions_tenant_document",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "file_id"],
            ["files.tenant_id", "files.id"],
            name="fk_document_versions_tenant_file",
            ondelete="RESTRICT",
        ),
        CheckConstraint("version_no >= 1", name="version_no_positive"),
        CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'",
            name="content_hash_format",
        ),
        CheckConstraint(
            "parser_name IS NULL OR parser_name ~ '^[a-z][a-z0-9_-]{0,63}$'",
            name="parser_name_format",
        ),
        CheckConstraint(
            "parser_version IS NULL OR char_length(parser_version) BETWEEN 1 AND 64",
            name="parser_version_length",
        ),
        CheckConstraint(
            "parsed_storage_key IS NULL "
            f"OR (parsed_storage_key ~ '{_STORAGE_KEY_PATTERN}' "
            "AND split_part(parsed_storage_key, '/', 1) = tenant_id::text)",
            name="parsed_storage_key_format",
        ),
        CheckConstraint(
            "parse_status IN ('pending', 'parsing', 'ready', 'failed')",
            name="parse_status_allowed",
        ),
        CheckConstraint(
            "index_status IN ('pending', 'indexing', 'ready', 'failed')",
            name="index_status_allowed",
        ),
        CheckConstraint(
            "parse_status <> 'ready' "
            "OR (parser_name IS NOT NULL AND parser_version IS NOT NULL "
            "AND parsed_storage_key IS NOT NULL)",
            name="ready_parse_has_artifact",
        ),
        CheckConstraint(
            "index_status <> 'ready' OR parse_status = 'ready'",
            name="ready_index_has_ready_parse",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    document_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    file_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_name: Mapped[str | None] = mapped_column(String(64))
    parser_version: Mapped[str | None] = mapped_column(String(64))
    parsed_storage_key: Mapped[str | None] = mapped_column(String(512))
    parse_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    index_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    document: Mapped[Document] = relationship(
        back_populates="versions",
        foreign_keys=[tenant_id, document_id],
    )


class DocumentAcl(Base):
    """One explicit read grant to a role, user, or market."""

    __tablename__ = "document_acl"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["documents.tenant_id", "documents.id"],
            name="fk_document_acl_tenant_document",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_document_acl_tenant_user",
            ondelete="CASCADE",
        ),
        Index("ix_document_acl_tenant_document", "tenant_id", "document_id"),
        Index(
            "uq_document_acl_role",
            "tenant_id",
            "document_id",
            "role_name",
            unique=True,
            postgresql_where=text("subject_type = 'role'"),
        ),
        Index(
            "uq_document_acl_user",
            "tenant_id",
            "document_id",
            "user_id",
            unique=True,
            postgresql_where=text("subject_type = 'user'"),
        ),
        Index(
            "uq_document_acl_market",
            "tenant_id",
            "document_id",
            "market_code",
            unique=True,
            postgresql_where=text("subject_type = 'market'"),
        ),
        CheckConstraint(
            "subject_type IN ('role', 'user', 'market')",
            name="subject_type_allowed",
        ),
        CheckConstraint(
            "(subject_type = 'role' AND role_name IS NOT NULL "
            "AND user_id IS NULL AND market_code IS NULL) "
            "OR (subject_type = 'user' AND role_name IS NULL "
            "AND user_id IS NOT NULL AND market_code IS NULL) "
            "OR (subject_type = 'market' AND role_name IS NULL "
            "AND user_id IS NULL AND market_code IS NOT NULL)",
            name="subject_shape",
        ),
        CheckConstraint(
            "role_name IS NULL "
            "OR role_name IN "
            "('company_owner', 'product_scout', 'amazon_operator')",
            name="role_name_allowed",
        ),
        CheckConstraint(
            "market_code IS NULL OR market_code ~ '^[A-Z]{2}$'",
            name="market_code_format",
        ),
        CheckConstraint("permission = 'read'", name="permission_read_only"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    document_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    subject_type: Mapped[str] = mapped_column(String(16), nullable=False)
    role_name: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("roles.name", ondelete="CASCADE"),
    )
    user_id: Mapped[UUID | None] = mapped_column(Uuid)
    market_code: Mapped[str | None] = mapped_column(String(2))
    permission: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="read",
        server_default="read",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    document: Mapped[Document] = relationship(
        back_populates="acl_entries",
        foreign_keys=[tenant_id, document_id],
    )
