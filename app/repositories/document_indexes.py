"""Tenant-scoped claiming and atomic completion for document Index Sets."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import FromClause

from app.models.knowledge import (
    Document,
    DocumentChunk,
    DocumentChunkSet,
    DocumentIndexSet,
    DocumentVersion,
    StoredFile,
)
from app.repositories.common import apply_statement_timeout
from app.services.documents.indexing.contracts import (
    DocumentChunkWriteFacts,
    DocumentIndexSetIdentity,
)


class DocumentIndexRepository:
    """Persist candidates without exposing half-complete indexes as active."""

    def __init__(self, session: Session, statement_timeout_ms: int = 2000) -> None:
        self._session = session
        self._statement_timeout_ms = statement_timeout_ms

    def claim_index_set(
        self,
        *,
        tenant_id: UUID,
        identity: DocumentIndexSetIdentity,
        claimed_at: datetime,
    ) -> DocumentIndexSet | None:
        """Claim one pending/failed identity or return its reusable ready row."""

        validated = _validated_identity(identity)
        if validated is None:
            return None
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        graph = self._load_live_graph_for_update(tenant_id, validated)
        if graph is None:
            return None
        document, version, file_row, _ = graph
        if not self._active_version_allows(document, version):
            return None
        other_candidate = self._session.scalar(
            select(DocumentIndexSet.id).where(
                DocumentIndexSet.tenant_id == tenant_id,
                DocumentIndexSet.document_version_id == validated.document_version_id,
                DocumentIndexSet.status == "indexing",
                DocumentIndexSet.id != validated.index_set_id,
            )
        )
        if other_candidate is not None:
            return None

        values = _index_set_values(tenant_id, validated)
        self._session.execute(
            postgresql_insert(DocumentIndexSet)
            .values(
                **values,
                status="pending",
                attempt_count=0,
                created_at=claimed_at,
            )
            .on_conflict_do_nothing()
        )
        claimed = self._session.scalar(
            update(DocumentIndexSet)
            .where(
                *_index_set_predicates(tenant_id, validated),
                DocumentIndexSet.status.in_(("pending", "failed")),
            )
            .values(
                status="indexing",
                attempt_count=DocumentIndexSet.attempt_count + 1,
                chunk_count=None,
                text_chunk_count=None,
                table_chunk_count=None,
                total_token_count=None,
                error_message=None,
                started_at=claimed_at,
                completed_at=None,
            )
            .returning(DocumentIndexSet)
        )
        if claimed is not None:
            if version.active_index_set_id is None:
                version.index_status = "indexing"
            file_row.status = "indexing"
            file_row.error_message = None
            self._session.flush()
            return claimed
        ready = self._session.scalar(
            select(DocumentIndexSet).where(
                *_index_set_predicates(tenant_id, validated),
                DocumentIndexSet.status == "ready",
            )
        )
        if ready is None:
            return None
        counts = self._session.execute(
            select(
                func.count(DocumentChunk.id),
                func.count(DocumentChunk.id).filter(DocumentChunk.kind == "text"),
                func.count(DocumentChunk.id).filter(DocumentChunk.kind == "table"),
                func.coalesce(func.sum(DocumentChunk.token_count), 0),
            ).where(
                DocumentChunk.tenant_id == tenant_id,
                DocumentChunk.document_index_set_id == validated.index_set_id,
            )
        ).one()
        if counts != (
            ready.chunk_count,
            ready.text_chunk_count,
            ready.table_chunk_count,
            ready.total_token_count,
        ):
            return None
        return ready

    def fail_index_set(
        self,
        *,
        tenant_id: UUID,
        identity: DocumentIndexSetIdentity,
        expected_attempt_count: int,
        error_message: str,
        completed_at: datetime,
    ) -> DocumentIndexSet | None:
        """Close only the current attempt and preserve any previous active set."""

        validated = _validated_identity(identity)
        if (
            validated is None
            or expected_attempt_count < 1
            or not isinstance(error_message, str)
            or error_message != error_message.strip()
            or not 1 <= len(error_message) <= 1000
        ):
            return None
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        index_set = self._session.scalar(
            select(DocumentIndexSet)
            .where(
                *_index_set_predicates(tenant_id, validated),
                DocumentIndexSet.status == "indexing",
                DocumentIndexSet.attempt_count == expected_attempt_count,
            )
            .with_for_update()
        )
        if index_set is None:
            return None
        version_and_file = self._session.execute(
            select(DocumentVersion, StoredFile)
            .select_from(DocumentVersion)
            .join(
                StoredFile,
                and_(
                    StoredFile.tenant_id == DocumentVersion.tenant_id,
                    StoredFile.id == DocumentVersion.file_id,
                ),
            )
            .where(
                DocumentVersion.tenant_id == tenant_id,
                DocumentVersion.id == validated.document_version_id,
                DocumentVersion.document_id == validated.document_id,
            )
            .with_for_update(of=(DocumentVersion, StoredFile))
        ).one_or_none()
        if version_and_file is None:
            return None
        version, file_row = version_and_file

        self._session.execute(
            delete(DocumentChunk).where(
                DocumentChunk.tenant_id == tenant_id,
                DocumentChunk.document_index_set_id == validated.index_set_id,
            )
        )
        index_set.status = "failed"
        index_set.chunk_count = None
        index_set.text_chunk_count = None
        index_set.table_chunk_count = None
        index_set.total_token_count = None
        index_set.error_message = error_message
        index_set.completed_at = completed_at
        if version.active_index_set_id is None:
            version.index_status = "failed"
            if file_row.status != "soft_deleted" and file_row.deleted_at is None:
                file_row.status = "failed"
                file_row.error_message = error_message
        elif file_row.status != "soft_deleted" and file_row.deleted_at is None:
            version.index_status = "ready"
            file_row.status = "ready"
            file_row.error_message = None
        self._session.flush()
        return index_set

    def fail_pipeline_before_claim(
        self,
        *,
        tenant_id: UUID,
        document_id: UUID,
        version_id: UUID,
        error_message: str,
    ) -> bool:
        """Record parse/chunk failure before an Index Set identity exists."""

        if (
            not isinstance(error_message, str)
            or error_message != error_message.strip()
            or not 1 <= len(error_message) <= 1000
        ):
            return False
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        graph = self._session.execute(
            select(Document, DocumentVersion, StoredFile)
            .select_from(DocumentVersion)
            .join(
                Document,
                and_(
                    Document.tenant_id == DocumentVersion.tenant_id,
                    Document.id == DocumentVersion.document_id,
                ),
            )
            .join(
                StoredFile,
                and_(
                    StoredFile.tenant_id == DocumentVersion.tenant_id,
                    StoredFile.id == DocumentVersion.file_id,
                ),
            )
            .where(
                DocumentVersion.tenant_id == tenant_id,
                DocumentVersion.id == version_id,
                DocumentVersion.document_id == document_id,
                Document.id == document_id,
                Document.deleted_at.is_(None),
                StoredFile.deleted_at.is_(None),
                StoredFile.status != "soft_deleted",
            )
            .with_for_update(of=(Document, DocumentVersion, StoredFile))
        ).one_or_none()
        if graph is None:
            return False
        _document, version, file_row = graph
        if version.active_index_set_id is None:
            version.index_status = "failed"
            file_row.status = "failed"
            file_row.error_message = error_message
        else:
            version.index_status = "ready"
            file_row.status = "ready"
            file_row.error_message = None
        self._session.flush()
        return True

    def complete_index_set(
        self,
        *,
        tenant_id: UUID,
        identity: DocumentIndexSetIdentity,
        expected_attempt_count: int,
        chunks: Sequence[DocumentChunkWriteFacts],
        completed_at: datetime,
    ) -> DocumentIndexSet | None:
        """Save every Chunk, mark ready, and switch both pointers in one transaction."""

        validated = _validated_identity(identity)
        validated_chunks = _validated_chunks(chunks)
        if validated is None or validated_chunks is None or expected_attempt_count < 1:
            return None
        if not _chunks_match_identity(tenant_id, validated, validated_chunks):
            return None

        apply_statement_timeout(self._session, self._statement_timeout_ms)
        graph = self._load_live_graph_for_update(
            tenant_id,
            validated,
            index_status="indexing",
            expected_attempt_count=expected_attempt_count,
        )
        if graph is None:
            return None
        document, version, file_row, chunk_set, index_set = graph
        if not self._active_version_allows(document, version):
            return None

        chunk_count = len(validated_chunks)
        text_chunk_count = sum(chunk.kind == "text" for chunk in validated_chunks)
        table_chunk_count = sum(chunk.kind == "table" for chunk in validated_chunks)
        total_token_count = sum(chunk.token_count for chunk in validated_chunks)
        if (
            chunk_set.chunk_count != chunk_count
            or chunk_set.text_chunk_count != text_chunk_count
            or chunk_set.table_chunk_count != table_chunk_count
            or chunk_set.total_token_count != total_token_count
        ):
            return None

        self._session.add_all(
            DocumentChunk(**chunk.model_dump(mode="python"))
            for chunk in validated_chunks
        )
        self._session.flush()
        persisted_count = self._session.scalar(
            select(func.count(DocumentChunk.id)).where(
                DocumentChunk.tenant_id == tenant_id,
                DocumentChunk.document_index_set_id == validated.index_set_id,
            )
        )
        if persisted_count != chunk_count:
            raise ValueError("document index Chunk count changed during completion")

        index_set.status = "ready"
        index_set.chunk_count = chunk_count
        index_set.text_chunk_count = text_chunk_count
        index_set.table_chunk_count = table_chunk_count
        index_set.total_token_count = total_token_count
        index_set.error_message = None
        index_set.completed_at = completed_at
        self._session.flush()

        version.index_status = "ready"
        version.active_index_set_id = validated.index_set_id
        document.active_version_id = version.id
        file_row.status = "ready"
        file_row.error_message = None
        self._session.flush()
        return index_set

    def _load_live_graph_for_update(
        self,
        tenant_id: UUID,
        identity: DocumentIndexSetIdentity,
        *,
        index_status: str | None = None,
        expected_attempt_count: int | None = None,
    ):
        lock_targets: list[FromClause] = [
            Document.__table__,
            DocumentVersion.__table__,
            StoredFile.__table__,
            DocumentChunkSet.__table__,
        ]
        statement = (
            select(Document, DocumentVersion, StoredFile, DocumentChunkSet)
            .select_from(DocumentVersion)
            .join(
                Document,
                and_(
                    Document.tenant_id == DocumentVersion.tenant_id,
                    Document.id == DocumentVersion.document_id,
                ),
            )
            .join(
                StoredFile,
                and_(
                    StoredFile.tenant_id == DocumentVersion.tenant_id,
                    StoredFile.id == DocumentVersion.file_id,
                ),
            )
            .join(
                DocumentChunkSet,
                and_(
                    DocumentChunkSet.tenant_id == DocumentVersion.tenant_id,
                    DocumentChunkSet.document_version_id == DocumentVersion.id,
                    DocumentChunkSet.document_id == DocumentVersion.document_id,
                ),
            )
            .where(
                DocumentVersion.tenant_id == tenant_id,
                DocumentVersion.id == identity.document_version_id,
                DocumentVersion.document_id == identity.document_id,
                DocumentVersion.parse_status == "ready",
                Document.id == identity.document_id,
                Document.deleted_at.is_(None),
                StoredFile.deleted_at.is_(None),
                StoredFile.status != "soft_deleted",
                DocumentChunkSet.id == identity.document_chunk_set_id,
                DocumentChunkSet.status == "ready",
            )
        )
        if index_status is not None and expected_attempt_count is not None:
            statement = statement.join(
                DocumentIndexSet,
                and_(
                    DocumentIndexSet.tenant_id == DocumentVersion.tenant_id,
                    DocumentIndexSet.document_version_id == DocumentVersion.id,
                    DocumentIndexSet.document_id == DocumentVersion.document_id,
                    DocumentIndexSet.document_chunk_set_id == DocumentChunkSet.id,
                ),
            ).where(
                *_index_set_predicates(tenant_id, identity),
                DocumentIndexSet.status == index_status,
                DocumentIndexSet.attempt_count == expected_attempt_count,
            )
            statement = statement.add_columns(DocumentIndexSet)
            lock_targets.append(DocumentIndexSet.__table__)
        return self._session.execute(
            statement.with_for_update(of=lock_targets)
        ).one_or_none()

    def _active_version_allows(
        self,
        document: Document,
        candidate: DocumentVersion,
    ) -> bool:
        if document.active_version_id in {None, candidate.id}:
            return True
        active_version_no = self._session.scalar(
            select(DocumentVersion.version_no).where(
                DocumentVersion.tenant_id == candidate.tenant_id,
                DocumentVersion.document_id == candidate.document_id,
                DocumentVersion.id == document.active_version_id,
            )
        )
        return (
            active_version_no is not None and active_version_no < candidate.version_no
        )


def _validated_identity(
    identity: DocumentIndexSetIdentity,
) -> DocumentIndexSetIdentity | None:
    try:
        return DocumentIndexSetIdentity.model_validate(identity.model_dump(mode="json"))
    except (AttributeError, ValidationError):
        return None


def _validated_chunks(
    chunks: Sequence[DocumentChunkWriteFacts],
) -> tuple[DocumentChunkWriteFacts, ...] | None:
    if isinstance(chunks, (str, bytes)):
        return None
    try:
        values = tuple(
            DocumentChunkWriteFacts.model_validate(chunk.model_dump(mode="json"))
            for chunk in chunks
        )
    except (AttributeError, TypeError, ValidationError):
        return None
    return values or None


def _chunks_match_identity(
    tenant_id: UUID,
    identity: DocumentIndexSetIdentity,
    chunks: tuple[DocumentChunkWriteFacts, ...],
) -> bool:
    return all(
        chunk.tenant_id == tenant_id
        and chunk.document_id == identity.document_id
        and chunk.document_version_id == identity.document_version_id
        and chunk.document_chunk_set_id == identity.document_chunk_set_id
        and chunk.document_index_set_id == identity.index_set_id
        and chunk.embedding_model == identity.embedding_model
        and chunk.embedding_version == identity.embedding_version
        for chunk in chunks
    )


def _index_set_values(
    tenant_id: UUID,
    identity: DocumentIndexSetIdentity,
) -> dict[str, object]:
    return {
        "id": identity.index_set_id,
        "tenant_id": tenant_id,
        "document_id": identity.document_id,
        "document_version_id": identity.document_version_id,
        "document_chunk_set_id": identity.document_chunk_set_id,
        "index_schema_version": identity.index_schema_version,
        "embedding_identity_json": identity.embedding_identity_json.model_dump(
            mode="json"
        ),
        "embedding_identity_sha256": identity.embedding_identity_sha256,
        "embedding_model": identity.embedding_model,
        "embedding_version": identity.embedding_version,
        "embedding_purpose": identity.embedding_purpose,
        "fts_builder_version": identity.fts_builder_version,
    }


def _index_set_predicates(
    tenant_id: UUID,
    identity: DocumentIndexSetIdentity,
) -> tuple[ColumnElement[bool], ...]:
    return (
        DocumentIndexSet.id == identity.index_set_id,
        DocumentIndexSet.tenant_id == tenant_id,
        DocumentIndexSet.document_id == identity.document_id,
        DocumentIndexSet.document_version_id == identity.document_version_id,
        DocumentIndexSet.document_chunk_set_id == identity.document_chunk_set_id,
        DocumentIndexSet.index_schema_version == identity.index_schema_version,
        DocumentIndexSet.embedding_identity_json
        == identity.embedding_identity_json.model_dump(mode="json"),
        DocumentIndexSet.embedding_identity_sha256
        == identity.embedding_identity_sha256,
        DocumentIndexSet.embedding_model == identity.embedding_model,
        DocumentIndexSet.embedding_version == identity.embedding_version,
        DocumentIndexSet.embedding_purpose == identity.embedding_purpose,
        DocumentIndexSet.fts_builder_version == identity.fts_builder_version,
    )
