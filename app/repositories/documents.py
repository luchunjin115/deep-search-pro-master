"""Fixed tenant/ACL-scoped document metadata queries for M2."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import ColumnElement, and_, exists, func, or_, select, true, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session

from app.models.identity import Role, User
from app.models.knowledge import (
    Document,
    DocumentAcl,
    DocumentChunkSet,
    DocumentVersion,
    StoredFile,
)
from app.repositories.common import apply_statement_timeout


def document_access_clause(
    *,
    tenant_id: UUID,
    user_id: UUID,
    role_names: tuple[str, ...],
    market_scopes: tuple[str, ...],
    company_owner: bool,
) -> ColumnElement[bool]:
    """Build the SQL authorization clause shared by document and file reads."""

    acl_subjects: list[ColumnElement[bool]] = [
        and_(
            DocumentAcl.subject_type == "user",
            DocumentAcl.user_id == user_id,
        )
    ]
    if role_names:
        acl_subjects.append(
            and_(
                DocumentAcl.subject_type == "role",
                DocumentAcl.role_name.in_(role_names),
            )
        )
    if market_scopes:
        acl_subjects.append(
            and_(
                DocumentAcl.subject_type == "market",
                DocumentAcl.market_code.in_(market_scopes),
            )
        )

    acl_match = exists(
        select(DocumentAcl.id).where(
            DocumentAcl.tenant_id == tenant_id,
            DocumentAcl.document_id == Document.id,
            DocumentAcl.permission == "read",
            or_(*acl_subjects),
        )
    )
    access_options: list[ColumnElement[bool]] = [
        Document.owner_user_id == user_id,
        acl_match,
    ]
    if company_owner:
        access_options.append(true())
    return or_(*access_options)


def document_live_file_clause() -> ColumnElement[bool]:
    """Require the pending or active document version to reference a live file."""

    live_version = exists(
        select(DocumentVersion.id)
        .join(
            StoredFile,
            and_(
                StoredFile.tenant_id == DocumentVersion.tenant_id,
                StoredFile.id == DocumentVersion.file_id,
            ),
        )
        .where(
            DocumentVersion.tenant_id == Document.tenant_id,
            DocumentVersion.document_id == Document.id,
            StoredFile.status != "soft_deleted",
            StoredFile.deleted_at.is_(None),
            or_(
                Document.active_version_id.is_(None),
                DocumentVersion.id == Document.active_version_id,
            ),
        )
    )
    return live_version


class DocumentRepository:
    """Persist and read document metadata through fixed SQLAlchemy statements."""

    def __init__(self, session: Session, statement_timeout_ms: int = 2000) -> None:
        self._session = session
        self._statement_timeout_ms = statement_timeout_ms

    def create_initial(
        self,
        *,
        document_id: UUID,
        version_id: UUID,
        tenant_id: UUID,
        owner_user_id: UUID,
        file_id: UUID,
        title: str,
        document_type: str,
        language: str | None,
        market: str | None,
        product_id: UUID | None,
        access_level: str,
        content_hash: str,
    ) -> tuple[Document, DocumentVersion]:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        document = Document(
            id=document_id,
            tenant_id=tenant_id,
            owner_user_id=owner_user_id,
            title=title,
            document_type=document_type,
            language=language,
            market=market,
            product_id=product_id,
            access_level=access_level,
        )
        version = DocumentVersion(
            id=version_id,
            tenant_id=tenant_id,
            document_id=document_id,
            file_id=file_id,
            version_no=1,
            content_hash=content_hash,
        )
        self._session.add(document)
        self._session.flush()
        self._session.add(version)
        self._session.flush()
        return document, version

    def find_accessible_by_id(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        role_names: tuple[str, ...],
        market_scopes: tuple[str, ...],
        document_id: UUID,
    ) -> Document | None:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        return self._session.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.tenant_id == tenant_id,
                Document.deleted_at.is_(None),
                document_live_file_clause(),
                document_access_clause(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    role_names=role_names,
                    market_scopes=market_scopes,
                    company_owner="company_owner" in role_names,
                ),
            )
        )

    def find_manageable_by_id(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        company_owner: bool,
        document_id: UUID,
    ) -> Document | None:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        ownership = true() if company_owner else Document.owner_user_id == user_id
        return self._session.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.tenant_id == tenant_id,
                Document.deleted_at.is_(None),
                document_live_file_clause(),
                ownership,
            )
        )

    def list_accessible(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        role_names: tuple[str, ...],
        market_scopes: tuple[str, ...],
        limit: int,
    ) -> list[Document]:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        statement = (
            select(Document)
            .where(
                Document.tenant_id == tenant_id,
                Document.deleted_at.is_(None),
                document_live_file_clause(),
                document_access_clause(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    role_names=role_names,
                    market_scopes=market_scopes,
                    company_owner="company_owner" in role_names,
                ),
            )
            .order_by(Document.created_at.desc(), Document.id)
            .limit(limit)
        )
        return list(self._session.scalars(statement))

    def list_versions(
        self, *, tenant_id: UUID, document_id: UUID
    ) -> list[DocumentVersion]:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        return list(
            self._session.scalars(
                select(DocumentVersion)
                .where(
                    DocumentVersion.tenant_id == tenant_id,
                    DocumentVersion.document_id == document_id,
                )
                .order_by(DocumentVersion.version_no)
            )
        )

    def list_acl(self, *, tenant_id: UUID, document_id: UUID) -> list[DocumentAcl]:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        return list(
            self._session.scalars(
                select(DocumentAcl)
                .where(
                    DocumentAcl.tenant_id == tenant_id,
                    DocumentAcl.document_id == document_id,
                )
                .order_by(DocumentAcl.created_at, DocumentAcl.id)
            )
        )

    def find_version(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
        version_id: UUID,
    ) -> DocumentVersion | None:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        return self._session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.id == version_id,
                DocumentVersion.tenant_id == tenant_id,
                DocumentVersion.document_id == document_id,
            )
        )

    def find_version_by_hash(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
        content_hash: str,
    ) -> DocumentVersion | None:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        return self._session.scalar(
            select(DocumentVersion).where(
                DocumentVersion.tenant_id == tenant_id,
                DocumentVersion.document_id == document_id,
                DocumentVersion.content_hash == content_hash,
            )
        )

    def add_version(
        self,
        *,
        version_id: UUID,
        tenant_id: UUID,
        document_id: UUID,
        file_id: UUID,
        content_hash: str,
    ) -> DocumentVersion:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        next_number = self._session.scalar(
            select(func.coalesce(func.max(DocumentVersion.version_no), 0) + 1).where(
                DocumentVersion.tenant_id == tenant_id,
                DocumentVersion.document_id == document_id,
            )
        )
        row = DocumentVersion(
            id=version_id,
            tenant_id=tenant_id,
            document_id=document_id,
            file_id=file_id,
            version_no=int(next_number or 1),
            content_hash=content_hash,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def add_acl(
        self,
        *,
        acl_id: UUID,
        tenant_id: UUID,
        document_id: UUID,
        subject_type: str,
        role_name: str | None,
        user_id: UUID | None,
        market_code: str | None,
    ) -> DocumentAcl:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        row = DocumentAcl(
            id=acl_id,
            tenant_id=tenant_id,
            document_id=document_id,
            subject_type=subject_type,
            role_name=role_name,
            user_id=user_id,
            market_code=market_code,
            permission="read",
        )
        self._session.add(row)
        self._session.flush()
        return row

    def find_acl(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
        subject_type: str,
        role_name: str | None,
        user_id: UUID | None,
        market_code: str | None,
    ) -> DocumentAcl | None:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        return self._session.scalar(
            select(DocumentAcl).where(
                DocumentAcl.tenant_id == tenant_id,
                DocumentAcl.document_id == document_id,
                DocumentAcl.subject_type == subject_type,
                DocumentAcl.role_name.is_not_distinct_from(role_name),
                DocumentAcl.user_id.is_not_distinct_from(user_id),
                DocumentAcl.market_code.is_not_distinct_from(market_code),
            )
        )

    def acl_subject_exists(
        self,
        *,
        tenant_id: UUID,
        subject_type: str,
        role_name: str | None,
        user_id: UUID | None,
        market_code: str | None,
    ) -> bool:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        if subject_type == "role":
            return (
                self._session.scalar(select(Role.id).where(Role.name == role_name))
                is not None
            )
        if subject_type == "user":
            return (
                self._session.scalar(
                    select(User.id).where(
                        User.tenant_id == tenant_id,
                        User.id == user_id,
                        User.status == "active",
                    )
                )
                is not None
            )
        return subject_type == "market" and market_code in {"DE", "FR"}

    def update_parse_state(
        self,
        row: DocumentVersion,
        *,
        status: str,
        parser_name: str | None,
        parser_version: str | None,
        parsed_storage_key: str | None,
    ) -> DocumentVersion:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        row.parse_status = status
        row.parser_name = parser_name
        row.parser_version = parser_version
        row.parsed_storage_key = parsed_storage_key
        self._session.flush()
        return row

    def claim_parse(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
        version_id: UUID,
    ) -> DocumentVersion | None:
        """Atomically claim one pending/failed version for a single worker."""

        apply_statement_timeout(self._session, self._statement_timeout_ms)
        statement = (
            update(DocumentVersion)
            .where(
                DocumentVersion.id == version_id,
                DocumentVersion.tenant_id == tenant_id,
                DocumentVersion.document_id == document_id,
                DocumentVersion.parse_status.in_(("pending", "failed")),
            )
            .values(
                parse_status="parsing",
                parser_name=None,
                parser_version=None,
                parsed_storage_key=None,
            )
            .returning(DocumentVersion)
        )
        return self._session.scalar(statement)

    def complete_parse(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
        version_id: UUID,
        parser_name: str,
        parser_version: str,
        parsed_storage_key: str,
    ) -> DocumentVersion | None:
        """Publish metadata only while this version remains claimed."""

        apply_statement_timeout(self._session, self._statement_timeout_ms)
        statement = (
            update(DocumentVersion)
            .where(
                DocumentVersion.id == version_id,
                DocumentVersion.tenant_id == tenant_id,
                DocumentVersion.document_id == document_id,
                DocumentVersion.parse_status == "parsing",
            )
            .values(
                parse_status="ready",
                parser_name=parser_name,
                parser_version=parser_version,
                parsed_storage_key=parsed_storage_key,
            )
            .returning(DocumentVersion)
        )
        return self._session.scalar(statement)

    def fail_parse(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
        version_id: UUID,
    ) -> DocumentVersion | None:
        """Clear unpublished metadata and close one claimed parse as failed."""

        apply_statement_timeout(self._session, self._statement_timeout_ms)
        statement = (
            update(DocumentVersion)
            .where(
                DocumentVersion.id == version_id,
                DocumentVersion.tenant_id == tenant_id,
                DocumentVersion.document_id == document_id,
                DocumentVersion.parse_status == "parsing",
            )
            .values(
                parse_status="failed",
                parser_name=None,
                parser_version=None,
                parsed_storage_key=None,
            )
            .returning(DocumentVersion)
        )
        return self._session.scalar(statement)

    def claim_chunk_set(
        self,
        *,
        chunk_set_id: UUID,
        tenant_id: UUID,
        document_id: UUID,
        version_id: UUID,
        artifact_schema_version: str,
        content_hash_version: str,
        routed_schema_version: str,
        canonical_schema_version: str,
        source_sha256: str,
        parsed_publication_sha256: str,
        selected_artifact_content_sha256: str,
        chunker_name: str,
        chunker_version: str,
        token_counter_name: str,
        token_counter_version: str,
        normalization_version: str,
        config_json: dict[str, object],
        config_sha256: str,
        claimed_at: datetime,
    ) -> DocumentChunkSet | None:
        """Create-or-claim one exact deterministic Chunk Set without races."""

        apply_statement_timeout(self._session, self._statement_timeout_ms)
        identity = {
            "id": chunk_set_id,
            "tenant_id": tenant_id,
            "document_id": document_id,
            "document_version_id": version_id,
            "artifact_schema_version": artifact_schema_version,
            "content_hash_version": content_hash_version,
            "routed_schema_version": routed_schema_version,
            "canonical_schema_version": canonical_schema_version,
            "source_sha256": source_sha256,
            "parsed_publication_sha256": parsed_publication_sha256,
            "selected_artifact_content_sha256": selected_artifact_content_sha256,
            "chunker_name": chunker_name,
            "chunker_version": chunker_version,
            "token_counter_name": token_counter_name,
            "token_counter_version": token_counter_version,
            "normalization_version": normalization_version,
            "config_json": config_json,
            "config_sha256": config_sha256,
        }
        self._session.execute(
            postgresql_insert(DocumentChunkSet)
            .values(
                **identity,
                status="pending",
                attempt_count=0,
                created_at=claimed_at,
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
        statement = (
            update(DocumentChunkSet)
            .where(
                DocumentChunkSet.id == chunk_set_id,
                DocumentChunkSet.tenant_id == tenant_id,
                DocumentChunkSet.document_id == document_id,
                DocumentChunkSet.document_version_id == version_id,
                DocumentChunkSet.status.in_(("pending", "failed")),
                DocumentChunkSet.artifact_schema_version == artifact_schema_version,
                DocumentChunkSet.content_hash_version == content_hash_version,
                DocumentChunkSet.routed_schema_version == routed_schema_version,
                DocumentChunkSet.canonical_schema_version == canonical_schema_version,
                DocumentChunkSet.source_sha256 == source_sha256,
                DocumentChunkSet.parsed_publication_sha256 == parsed_publication_sha256,
                DocumentChunkSet.selected_artifact_content_sha256
                == selected_artifact_content_sha256,
                DocumentChunkSet.chunker_name == chunker_name,
                DocumentChunkSet.chunker_version == chunker_version,
                DocumentChunkSet.token_counter_name == token_counter_name,
                DocumentChunkSet.token_counter_version == token_counter_version,
                DocumentChunkSet.normalization_version == normalization_version,
                DocumentChunkSet.config_json == config_json,
                DocumentChunkSet.config_sha256 == config_sha256,
            )
            .values(
                status="chunking",
                attempt_count=DocumentChunkSet.attempt_count + 1,
                output_sha256=None,
                chunk_storage_key=None,
                chunk_count=None,
                text_chunk_count=None,
                table_chunk_count=None,
                total_token_count=None,
                excluded_span_count=None,
                error_message=None,
                started_at=claimed_at,
                completed_at=None,
            )
            .returning(DocumentChunkSet)
        )
        return self._session.scalar(statement)

    def find_chunk_set(
        self,
        *,
        chunk_set_id: UUID,
        tenant_id: UUID,
        document_id: UUID,
        version_id: UUID,
    ) -> DocumentChunkSet | None:
        """Load one Chunk Set only inside its complete ownership boundary."""

        apply_statement_timeout(self._session, self._statement_timeout_ms)
        return self._session.scalar(
            select(DocumentChunkSet).where(
                DocumentChunkSet.id == chunk_set_id,
                DocumentChunkSet.tenant_id == tenant_id,
                DocumentChunkSet.document_id == document_id,
                DocumentChunkSet.document_version_id == version_id,
            )
        )

    def complete_chunk_set(
        self,
        *,
        chunk_set_id: UUID,
        tenant_id: UUID,
        document_id: UUID,
        version_id: UUID,
        output_sha256: str,
        chunk_storage_key: str,
        chunk_count: int,
        text_chunk_count: int,
        table_chunk_count: int,
        total_token_count: int,
        excluded_span_count: int,
        completed_at: datetime,
    ) -> DocumentChunkSet | None:
        """Publish final facts only while this exact Chunk Set is claimed."""

        apply_statement_timeout(self._session, self._statement_timeout_ms)
        statement = (
            update(DocumentChunkSet)
            .where(
                DocumentChunkSet.id == chunk_set_id,
                DocumentChunkSet.tenant_id == tenant_id,
                DocumentChunkSet.document_id == document_id,
                DocumentChunkSet.document_version_id == version_id,
                DocumentChunkSet.status == "chunking",
            )
            .values(
                status="ready",
                output_sha256=output_sha256,
                chunk_storage_key=chunk_storage_key,
                chunk_count=chunk_count,
                text_chunk_count=text_chunk_count,
                table_chunk_count=table_chunk_count,
                total_token_count=total_token_count,
                excluded_span_count=excluded_span_count,
                error_message=None,
                completed_at=completed_at,
            )
            .returning(DocumentChunkSet)
        )
        return self._session.scalar(statement)

    def fail_chunk_set(
        self,
        *,
        chunk_set_id: UUID,
        tenant_id: UUID,
        document_id: UUID,
        version_id: UUID,
        error_message: str,
        completed_at: datetime,
    ) -> DocumentChunkSet | None:
        """Clear unpublished results and close one claimed Chunk Set as failed."""

        apply_statement_timeout(self._session, self._statement_timeout_ms)
        statement = (
            update(DocumentChunkSet)
            .where(
                DocumentChunkSet.id == chunk_set_id,
                DocumentChunkSet.tenant_id == tenant_id,
                DocumentChunkSet.document_id == document_id,
                DocumentChunkSet.document_version_id == version_id,
                DocumentChunkSet.status == "chunking",
            )
            .values(
                status="failed",
                output_sha256=None,
                chunk_storage_key=None,
                chunk_count=None,
                text_chunk_count=None,
                table_chunk_count=None,
                total_token_count=None,
                excluded_span_count=None,
                error_message=error_message,
                completed_at=completed_at,
            )
            .returning(DocumentChunkSet)
        )
        return self._session.scalar(statement)

    def update_index_state(
        self,
        row: DocumentVersion,
        *,
        status: str,
    ) -> DocumentVersion:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        row.index_status = status
        self._session.flush()
        return row

    def activate_version(
        self,
        document: Document,
        version: DocumentVersion,
    ) -> Document:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        document.active_version_id = version.id
        self._session.flush()
        return document

    def soft_delete(self, document: Document, *, deleted_at: datetime) -> Document:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        document.deleted_at = deleted_at
        self._session.flush()
        return document
