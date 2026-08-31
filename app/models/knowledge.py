"""Knowledge-file metadata, document versions, and access-control models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
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
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
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
        ForeignKeyConstraint(
            [
                "tenant_id",
                "active_index_set_id",
                "id",
                "document_id",
                "index_status",
            ],
            [
                "document_index_sets.tenant_id",
                "document_index_sets.id",
                "document_index_sets.document_version_id",
                "document_index_sets.document_id",
                "document_index_sets.status",
            ],
            name="fk_document_versions_active_index_set",
            use_alter=True,
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
        CheckConstraint(
            "active_index_set_id IS NULL OR index_status = 'ready'",
            name="active_index_set_matches_status",
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
    active_index_set_id: Mapped[UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    document: Mapped[Document] = relationship(
        back_populates="versions",
        foreign_keys=[tenant_id, document_id],
    )
    chunk_sets: Mapped[list[DocumentChunkSet]] = relationship(
        back_populates="document_version",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys=lambda: [
            DocumentChunkSet.tenant_id,
            DocumentChunkSet.document_version_id,
            DocumentChunkSet.document_id,
        ],
    )


class DocumentChunkSet(Base):
    """One deterministic, retryable Chunk Artifact generation for a version."""

    __tablename__ = "document_chunk_sets"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_document_chunk_sets_tenant_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            "document_version_id",
            "document_id",
            name="uq_document_chunk_sets_tenant_id_version_document",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "document_version_id", "document_id"],
            [
                "document_versions.tenant_id",
                "document_versions.id",
                "document_versions.document_id",
            ],
            name="fk_document_chunk_sets_tenant_version_document",
            ondelete="CASCADE",
        ),
        Index(
            "ix_document_chunk_sets_tenant_version_created",
            "tenant_id",
            "document_version_id",
            "created_at",
        ),
        Index(
            "ix_document_chunk_sets_tenant_status",
            "tenant_id",
            "status",
        ),
        CheckConstraint(
            "artifact_schema_version = 'm2-canonical-chunk-artifact-v1'",
            name="artifact_schema_version_allowed",
        ),
        CheckConstraint(
            "content_hash_version = 'm2-chunk-content-v1'",
            name="content_hash_version_allowed",
        ),
        CheckConstraint(
            "routed_schema_version = 'm2-routed-parsed-document-v1'",
            name="routed_schema_version_allowed",
        ),
        CheckConstraint(
            "canonical_schema_version = 'm2-canonical-parsed-artifact-v1'",
            name="canonical_schema_version_allowed",
        ),
        CheckConstraint(
            "source_sha256 ~ '^[0-9a-f]{64}$' "
            "AND parsed_publication_sha256 ~ '^[0-9a-f]{64}$' "
            "AND selected_artifact_content_sha256 ~ '^[0-9a-f]{64}$' "
            "AND config_sha256 ~ '^[0-9a-f]{64}$' "
            "AND (output_sha256 IS NULL OR output_sha256 ~ '^[0-9a-f]{64}$')",
            name="hashes_format",
        ),
        CheckConstraint(
            "chunker_name ~ '^[a-z][a-z0-9_]{0,63}$' "
            "AND char_length(chunker_version) BETWEEN 1 AND 100 "
            "AND token_counter_name ~ '^[a-z][a-z0-9_]{0,63}$' "
            "AND char_length(token_counter_version) BETWEEN 1 AND 100 "
            "AND char_length(normalization_version) BETWEEN 1 AND 100",
            name="implementation_identity_format",
        ),
        CheckConstraint(
            "jsonb_typeof(config_json) = 'object'",
            name="config_json_object",
        ),
        CheckConstraint(
            "status IN ('pending', 'chunking', 'ready', 'failed')",
            name="status_allowed",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint(
            "(status = 'pending' AND attempt_count = 0 "
            "AND started_at IS NULL AND completed_at IS NULL) "
            "OR (status = 'chunking' AND attempt_count >= 1 "
            "AND started_at IS NOT NULL AND completed_at IS NULL) "
            "OR (status IN ('ready', 'failed') AND attempt_count >= 1 "
            "AND started_at IS NOT NULL AND completed_at IS NOT NULL)",
            name="attempt_timestamps_match_status",
        ),
        CheckConstraint(
            "started_at IS NULL OR started_at >= created_at",
            name="started_after_created",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="completed_after_started",
        ),
        CheckConstraint(
            "chunk_storage_key IS NULL "
            f"OR (chunk_storage_key ~ '{_STORAGE_KEY_PATTERN}' "
            "AND split_part(chunk_storage_key, '/', 1) = tenant_id::text "
            "AND split_part(chunk_storage_key, '/', 2) = 'chunks' "
            "AND split_part(split_part(chunk_storage_key, '/', 5), '.', 1) "
            "= id::text AND right(chunk_storage_key, 5) = '.json')",
            name="chunk_storage_key_format",
        ),
        CheckConstraint(
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
            name="result_matches_status",
        ),
        CheckConstraint(
            "chunk_count IS NULL OR (chunk_count >= 1 "
            "AND text_chunk_count >= 0 AND table_chunk_count >= 0 "
            "AND text_chunk_count + table_chunk_count = chunk_count "
            "AND total_token_count >= chunk_count "
            "AND excluded_span_count >= 0)",
            name="statistics_consistent",
        ),
        CheckConstraint(
            "error_message IS NULL OR char_length(error_message) BETWEEN 1 AND 1000",
            name="error_message_length",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    document_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    document_version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    artifact_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash_version: Mapped[str] = mapped_column(String(64), nullable=False)
    routed_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    parsed_publication_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    selected_artifact_content_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    chunker_name: Mapped[str] = mapped_column(String(64), nullable=False)
    chunker_version: Mapped[str] = mapped_column(String(100), nullable=False)
    token_counter_name: Mapped[str] = mapped_column(String(64), nullable=False)
    token_counter_version: Mapped[str] = mapped_column(String(100), nullable=False)
    normalization_version: Mapped[str] = mapped_column(String(100), nullable=False)
    config_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    config_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    output_sha256: Mapped[str | None] = mapped_column(String(64))
    chunk_storage_key: Mapped[str | None] = mapped_column(String(512))
    chunk_count: Mapped[int | None] = mapped_column(Integer)
    text_chunk_count: Mapped[int | None] = mapped_column(Integer)
    table_chunk_count: Mapped[int | None] = mapped_column(Integer)
    total_token_count: Mapped[int | None] = mapped_column(BigInteger)
    excluded_span_count: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    document_version: Mapped[DocumentVersion] = relationship(
        back_populates="chunk_sets",
        foreign_keys=[tenant_id, document_version_id, document_id],
    )
    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="chunk_set",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys=lambda: [
            DocumentChunk.tenant_id,
            DocumentChunk.document_chunk_set_id,
            DocumentChunk.document_version_id,
            DocumentChunk.document_id,
        ],
    )


class DocumentIndexSet(Base):
    """One deterministic index generation prepared before atomic activation."""

    __tablename__ = "document_index_sets"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_document_index_sets_tenant_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            "document_version_id",
            "document_id",
            "status",
            name="uq_document_index_sets_active_target",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            "document_chunk_set_id",
            "document_version_id",
            "document_id",
            name="uq_document_index_sets_chunk_target",
        ),
        UniqueConstraint(
            "tenant_id",
            "document_version_id",
            "document_chunk_set_id",
            "index_schema_version",
            "embedding_identity_sha256",
            "embedding_purpose",
            "fts_builder_version",
            name="uq_document_index_sets_version_identity",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "document_version_id", "document_id"],
            [
                "document_versions.tenant_id",
                "document_versions.id",
                "document_versions.document_id",
            ],
            name="fk_document_index_sets_tenant_version_document",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
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
            name="fk_document_index_sets_tenant_set_version_document",
            ondelete="CASCADE",
        ),
        Index(
            "ix_document_index_sets_tenant_version_status",
            "tenant_id",
            "document_version_id",
            "status",
        ),
        Index(
            "ix_document_index_sets_tenant_document_created",
            "tenant_id",
            "document_id",
            "created_at",
        ),
        CheckConstraint(
            "index_schema_version = 'm2-document-index-set-v1' "
            "AND embedding_purpose = 'document' "
            "AND fts_builder_version IN "
            "('m2-fts-raw-retrieval-v1', 'm2-fts-jieba-search-v1') "
            "AND embedding_identity_sha256 ~ '^[0-9a-f]{64}$' "
            "AND embedding_model = btrim(embedding_model) "
            "AND char_length(embedding_model) BETWEEN 1 AND 200 "
            "AND embedding_version = btrim(embedding_version) "
            "AND char_length(embedding_version) BETWEEN 1 AND 100",
            name="identity_format",
        ),
        CheckConstraint(
            "jsonb_typeof(embedding_identity_json) = 'object'",
            name="identity_json_object",
        ),
        CheckConstraint(
            "status IN ('pending', 'indexing', 'ready', 'failed')",
            name="status_allowed",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        CheckConstraint(
            "(status = 'pending' AND attempt_count = 0 "
            "AND started_at IS NULL AND completed_at IS NULL) "
            "OR (status = 'indexing' AND attempt_count >= 1 "
            "AND started_at IS NOT NULL AND completed_at IS NULL) "
            "OR (status IN ('ready', 'failed') AND attempt_count >= 1 "
            "AND started_at IS NOT NULL AND completed_at IS NOT NULL)",
            name="attempt_timestamps_match_status",
        ),
        CheckConstraint(
            "started_at IS NULL OR started_at >= created_at",
            name="started_after_created",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="completed_after_started",
        ),
        CheckConstraint(
            "(status = 'ready' AND chunk_count IS NOT NULL "
            "AND text_chunk_count IS NOT NULL AND table_chunk_count IS NOT NULL "
            "AND total_token_count IS NOT NULL AND error_message IS NULL) "
            "OR (status = 'failed' AND chunk_count IS NULL "
            "AND text_chunk_count IS NULL AND table_chunk_count IS NULL "
            "AND total_token_count IS NULL AND error_message IS NOT NULL) "
            "OR (status IN ('pending', 'indexing') AND chunk_count IS NULL "
            "AND text_chunk_count IS NULL AND table_chunk_count IS NULL "
            "AND total_token_count IS NULL AND error_message IS NULL)",
            name="result_matches_status",
        ),
        CheckConstraint(
            "chunk_count IS NULL OR (chunk_count >= 1 "
            "AND text_chunk_count >= 0 AND table_chunk_count >= 0 "
            "AND text_chunk_count + table_chunk_count = chunk_count "
            "AND total_token_count >= chunk_count)",
            name="statistics_consistent",
        ),
        CheckConstraint(
            "error_message IS NULL OR char_length(error_message) BETWEEN 1 AND 1000",
            name="error_message_length",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    document_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    document_version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    document_chunk_set_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    index_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_identity_json: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
    )
    embedding_identity_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    embedding_model: Mapped[str] = mapped_column(String(200), nullable=False)
    embedding_version: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding_purpose: Mapped[str] = mapped_column(String(16), nullable=False)
    fts_builder_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    chunk_count: Mapped[int | None] = mapped_column(Integer)
    text_chunk_count: Mapped[int | None] = mapped_column(Integer)
    table_chunk_count: Mapped[int | None] = mapped_column(Integer)
    total_token_count: Mapped[int | None] = mapped_column(BigInteger)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentChunk(Base):
    """One persisted text or table Chunk prepared for later retrieval."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "document_index_set_id",
            "chunk_id",
            name="uq_document_chunks_index_set_chunk_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "document_index_set_id",
            "chunk_index",
            name="uq_document_chunks_index_set_chunk_index",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "document_version_id", "document_id"],
            [
                "document_versions.tenant_id",
                "document_versions.id",
                "document_versions.document_id",
            ],
            name="fk_document_chunks_tenant_version_document",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            [
                "tenant_id",
                "document_index_set_id",
                "document_chunk_set_id",
                "document_version_id",
                "document_id",
            ],
            [
                "document_index_sets.tenant_id",
                "document_index_sets.id",
                "document_index_sets.document_chunk_set_id",
                "document_index_sets.document_version_id",
                "document_index_sets.document_id",
            ],
            name=("fk_document_chunks_tenant_index_set_chunk_set_version_document"),
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
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
            name="fk_document_chunks_tenant_set_version_document",
            ondelete="CASCADE",
        ),
        Index(
            "ix_document_chunks_tenant_document_version_index_set_index",
            "tenant_id",
            "document_id",
            "document_version_id",
            "document_index_set_id",
            "chunk_index",
        ),
        Index(
            "ix_document_chunks_search_vector_gin",
            "search_vector",
            postgresql_using="gin",
        ),
        Index(
            "ix_document_chunks_embedding_hnsw_cosine",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        CheckConstraint(
            "chunk_id ~ '^c[0-9]{6}$'",
            name="chunk_id_format",
        ),
        CheckConstraint("chunk_index >= 1", name="chunk_index_positive"),
        CheckConstraint("kind IN ('text', 'table')", name="kind_allowed"),
        CheckConstraint(
            "char_length(body_text) BETWEEN 1 AND 2000000 "
            "AND char_length(retrieval_text) BETWEEN 1 AND 2000000 "
            "AND char_length(fts_text) BETWEEN 1 AND 2000000",
            name="text_length",
        ),
        CheckConstraint(
            "token_count BETWEEN 1 AND 1000000",
            name="token_count_range",
        ),
        CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'",
            name="content_sha256_format",
        ),
        CheckConstraint(
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
            name="metadata_shapes",
        ),
        CheckConstraint(
            "overlap_json IS NULL OR jsonb_typeof(overlap_json) = 'object'",
            name="overlap_json_object",
        ),
        CheckConstraint(
            "(kind = 'text' AND table_json IS NULL) "
            "OR (kind = 'table' AND table_json IS NOT NULL "
            "AND jsonb_typeof(table_json) = 'object' "
            "AND table_json ? 'source_kind' AND table_json ? 'rows')",
            name="table_matches_kind",
        ),
        CheckConstraint(
            "embedding IS NOT NULL AND embedding_model IS NOT NULL "
            "AND embedding_version IS NOT NULL",
            name="embedding_identity_matches_vector",
        ),
        CheckConstraint(
            "embedding_model IS NULL OR "
            "(embedding_model = btrim(embedding_model) "
            "AND char_length(embedding_model) BETWEEN 1 AND 200)",
            name="embedding_model_format",
        ),
        CheckConstraint(
            "embedding_version IS NULL OR "
            "(embedding_version = btrim(embedding_version) "
            "AND char_length(embedding_version) BETWEEN 1 AND 100)",
            name="embedding_version_format",
        ),
        CheckConstraint(
            "embedding_cache_key ~ '^sha256:[0-9a-f]{64}$'",
            name="embedding_cache_key_format",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    document_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    document_version_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    document_chunk_set_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    document_index_set_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    chunk_id: Mapped[str] = mapped_column(String(16), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    retrieval_text: Mapped[str] = mapped_column(Text, nullable=False)
    fts_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    heading_path: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    page_numbers: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    source_block_ids: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    source_spans: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    bounding_boxes: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    overlap_json: Mapped[dict[str, object] | None] = mapped_column(
        JSONB(none_as_null=True)
    )
    table_json: Mapped[dict[str, object] | None] = mapped_column(
        JSONB(none_as_null=True)
    )
    warnings: Mapped[list[object]] = mapped_column(JSONB, nullable=False)
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple'::regconfig, fts_text)", persisted=True),
        nullable=False,
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))
    embedding_model: Mapped[str | None] = mapped_column(String(200))
    embedding_version: Mapped[str | None] = mapped_column(String(100))
    embedding_cache_key: Mapped[str] = mapped_column(String(71), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    chunk_set: Mapped[DocumentChunkSet] = relationship(
        back_populates="chunks",
        foreign_keys=[
            tenant_id,
            document_chunk_set_id,
            document_version_id,
            document_id,
        ],
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
