"""Synchronous orchestration for one deterministic document index generation."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import (
    DocumentChunkPublicationError,
    DocumentIndexingError,
    DocumentNotFoundError,
    DocumentParsingError,
    DocumentStateConflictError,
)
from app.models.knowledge import Document, DocumentIndexSet
from app.repositories.document_indexes import DocumentIndexRepository
from app.repositories.documents import DocumentRepository
from app.schemas.auth import CurrentUser
from app.services.documents.chunking.service import DocumentChunkService
from app.services.documents.indexing.mapping import (
    build_document_index_set_identity,
    map_document_chunk_rows,
)
from app.services.documents.parser_service import DocumentParserService
from app.services.retrieval import EmbeddingBatch, EmbeddingProvider, EmbeddingPurpose
from app.services.retrieval.embedding import EMBEDDING_MAX_TEXTS
from app.services.storage import StorageBackend

if TYPE_CHECKING:
    from app.core.config import Settings
    from app.services.documents.parsers.docling import DoclingProvider


@dataclass(frozen=True, slots=True)
class DocumentIndexResult:
    """Safe service result for one ready or reused Index Set."""

    index_set_id: UUID
    document_id: UUID
    version_id: UUID
    chunk_set_id: UUID
    status: Literal["ready"]
    reused: bool
    version_activated: bool
    embedding_model: str
    embedding_version: str
    chunk_count: int
    text_chunk_count: int
    table_chunk_count: int
    total_token_count: int
    completed_at: datetime


class DocumentIndexService:
    """Run slow indexing work between short claim and completion transactions."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        storage: StorageBackend,
        settings: Settings,
        embedding_provider: EmbeddingProvider,
        *,
        docling_provider: DoclingProvider | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage
        self._settings = settings
        self._embedding_provider = embedding_provider
        self._clock = clock or (lambda: datetime.now(UTC))
        self._parser = DocumentParserService(
            session_factory,
            storage,
            settings,
            docling_provider=docling_provider,
            clock=self._clock,
        )
        self._chunker = DocumentChunkService(
            session_factory,
            storage,
            settings,
            clock=self._clock,
        )

    def index_version(
        self,
        user: CurrentUser,
        *,
        document_id: UUID,
        version_id: UUID,
    ) -> DocumentIndexResult:
        """Parse, chunk, embed, save, and activate one document version."""

        try:
            self._ensure_parsed(
                user,
                document_id=document_id,
                version_id=version_id,
            )
            artifact = self._chunker.ensure_chunk_version(
                user,
                document_id=document_id,
                version_id=version_id,
            )
        except (DocumentParsingError, DocumentChunkPublicationError):
            self._record_pre_index_failure(
                user.tenant_id,
                document_id=document_id,
                version_id=version_id,
            )
            raise
        identity = build_document_index_set_identity(
            artifact,
            self._embedding_provider.identity,
        )

        claim_session = self._session_factory()
        try:
            document = claim_session.get(Document, document_id)
            version_was_active = (
                document is not None and document.active_version_id == version_id
            )
            claimed = DocumentIndexRepository(
                claim_session,
                self._settings.database_statement_timeout_ms,
            ).claim_index_set(
                tenant_id=user.tenant_id,
                identity=identity,
                claimed_at=self._now(),
            )
            if claimed is None:
                raise DocumentStateConflictError
            claim_session.commit()
            if claimed.status == "ready":
                return _result_from_ready(
                    claimed,
                    reused=True,
                    version_activated=False,
                )
        except Exception:
            claim_session.rollback()
            raise
        finally:
            claim_session.close()

        try:
            embeddings = _embed_document_texts(
                self._embedding_provider,
                [chunk.retrieval_text for chunk in artifact.chunks],
            )
            rows = map_document_chunk_rows(
                tenant_id=user.tenant_id,
                artifact=artifact,
                index_identity=identity,
                embeddings=embeddings,
            )
            complete_session = self._session_factory()
            try:
                ready = DocumentIndexRepository(
                    complete_session,
                    self._settings.database_statement_timeout_ms,
                ).complete_index_set(
                    tenant_id=user.tenant_id,
                    identity=identity,
                    expected_attempt_count=claimed.attempt_count,
                    chunks=rows,
                    completed_at=self._now(),
                )
                if ready is None:
                    raise DocumentStateConflictError
                complete_session.commit()
                return _result_from_ready(
                    ready,
                    reused=False,
                    version_activated=not version_was_active,
                )
            except Exception:
                complete_session.rollback()
                raise
            finally:
                complete_session.close()
        except Exception:  # noqa: BLE001 - all post-claim failures must close safely.
            self._record_index_failure(
                user.tenant_id,
                identity=identity,
                expected_attempt_count=claimed.attempt_count,
            )
            raise DocumentIndexingError from None

    def _ensure_parsed(
        self,
        user: CurrentUser,
        *,
        document_id: UUID,
        version_id: UUID,
    ) -> None:
        session = self._session_factory()
        try:
            documents = DocumentRepository(
                session,
                self._settings.database_statement_timeout_ms,
            )
            document = documents.find_manageable_by_id(
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                company_owner="company_owner" in user.roles,
                document_id=document_id,
            )
            if document is None:
                raise DocumentNotFoundError
            version = documents.find_version(
                tenant_id=user.tenant_id,
                document_id=document_id,
                version_id=version_id,
            )
            if version is None:
                raise DocumentNotFoundError
            parse_status = version.parse_status
        finally:
            session.close()
        if parse_status == "ready":
            return
        if parse_status not in {"pending", "failed"}:
            raise DocumentStateConflictError
        self._parser.parse_version(
            user,
            document_id=document_id,
            version_id=version_id,
        )

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("index clock must be timezone-aware")
        return now

    def _record_pre_index_failure(
        self,
        tenant_id: UUID,
        *,
        document_id: UUID,
        version_id: UUID,
    ) -> None:
        session = self._session_factory()
        try:
            DocumentIndexRepository(
                session,
                self._settings.database_statement_timeout_ms,
            ).fail_pipeline_before_claim(
                tenant_id=tenant_id,
                document_id=document_id,
                version_id=version_id,
                error_message="文档索引失败",
            )
            session.commit()
        except Exception:  # noqa: BLE001 - preserve the original stage error.
            session.rollback()
        finally:
            session.close()

    def _record_index_failure(
        self,
        tenant_id: UUID,
        *,
        identity,
        expected_attempt_count: int,
    ) -> None:
        session = self._session_factory()
        try:
            DocumentIndexRepository(
                session,
                self._settings.database_statement_timeout_ms,
            ).fail_index_set(
                tenant_id=tenant_id,
                identity=identity,
                expected_attempt_count=expected_attempt_count,
                error_message="文档索引失败",
                completed_at=self._now(),
            )
            session.commit()
        except Exception:  # noqa: BLE001 - preserve the original index error.
            session.rollback()
        finally:
            session.close()


def _result_from_ready(
    row: DocumentIndexSet,
    *,
    reused: bool,
    version_activated: bool,
) -> DocumentIndexResult:
    if (
        row.status != "ready"
        or row.chunk_count is None
        or row.text_chunk_count is None
        or row.table_chunk_count is None
        or row.total_token_count is None
        or row.completed_at is None
    ):
        raise ValueError("Index Set is not a complete ready result")
    return DocumentIndexResult(
        index_set_id=row.id,
        document_id=row.document_id,
        version_id=row.document_version_id,
        chunk_set_id=row.document_chunk_set_id,
        status="ready",
        reused=reused,
        version_activated=version_activated,
        embedding_model=row.embedding_model,
        embedding_version=row.embedding_version,
        chunk_count=row.chunk_count,
        text_chunk_count=row.text_chunk_count,
        table_chunk_count=row.table_chunk_count,
        total_token_count=row.total_token_count,
        completed_at=row.completed_at,
    )


def _embed_document_texts(
    provider: EmbeddingProvider,
    texts: Sequence[str],
) -> EmbeddingBatch:
    """Embed bounded batches and restore the exact original document order."""

    vectors: list[tuple[float, ...]] = []
    cache_keys: list[str] = []
    effective_batch_sizes: list[int] = []
    identity = provider.identity
    for start in range(0, len(texts), EMBEDDING_MAX_TEXTS):
        part = texts[start : start + EMBEDDING_MAX_TEXTS]
        batch = provider.embed(part, purpose=EmbeddingPurpose.DOCUMENT)
        if (
            batch.identity != identity
            or batch.purpose is not EmbeddingPurpose.DOCUMENT
            or len(batch.vectors) != len(part)
            or len(batch.cache_keys) != len(part)
        ):
            raise ValueError("Embedding batch changed identity, purpose, or count")
        vectors.extend(batch.vectors)
        cache_keys.extend(batch.cache_keys)
        effective_batch_sizes.append(batch.effective_batch_size)
    if not vectors or not effective_batch_sizes:
        raise ValueError("document has no text to embed")
    return EmbeddingBatch(
        vectors=tuple(vectors),
        cache_keys=tuple(cache_keys),
        purpose=EmbeddingPurpose.DOCUMENT,
        identity=identity,
        effective_batch_size=min(effective_batch_sizes),
    )
