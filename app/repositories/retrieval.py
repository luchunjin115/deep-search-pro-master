"""Shared authorized active-Chunk boundary for all retrieval strategies."""

from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import asdict, dataclass, is_dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.knowledge import (
    Document,
    DocumentChunk,
    DocumentIndexSet,
    DocumentVersion,
    StoredFile,
)
from app.repositories.common import apply_statement_timeout
from app.repositories.documents import document_access_clause
from app.schemas.auth import CurrentUser
from app.schemas.retrieval import RerankedRetrievalResponse, RerankedRetrievalResult

if TYPE_CHECKING:
    from app.services.retrieval.embedding import EmbeddingIdentity


@dataclass(frozen=True, slots=True)
class DenseCandidateRecord:
    """One authorized pgvector row without tenant, ACL, vector, or Storage key."""

    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    index_set_id: UUID
    title: str
    document_type: str
    language: str | None
    market: str | None
    body_text: str
    file_extension: str
    heading_path: list[object]
    page_numbers: list[object]
    source_spans: list[object]
    table_json: dict[str, object] | None
    distance: float


@dataclass(frozen=True, slots=True)
class LexicalCandidateRecord:
    """One authorized PostgreSQL FTS row without ACL or generated-vector data."""

    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    index_set_id: UUID
    title: str
    document_type: str
    language: str | None
    market: str | None
    body_text: str
    file_extension: str
    heading_path: list[object]
    page_numbers: list[object]
    source_spans: list[object]
    table_json: dict[str, object] | None
    score: float


@dataclass(frozen=True, slots=True)
class ContextChunkRecord:
    """One freshly authorized Chunk snapshot with complete trusted provenance."""

    chunk_id: UUID
    canonical_chunk_id: str
    chunk_index: int
    kind: str
    document_id: UUID
    version_id: UUID
    chunk_set_id: UUID
    index_set_id: UUID
    file_id: UUID
    title: str
    document_type: str
    language: str | None
    market: str | None
    access_level: str
    file_extension: str
    body_text: str
    token_count: int
    content_sha256: str
    heading_path: list[object]
    page_numbers: list[object]
    source_block_ids: list[object]
    source_spans: list[object]
    bounding_boxes: list[object]
    overlap_json: dict[str, object] | None
    table_json: dict[str, object] | None
    warnings: list[object]


@dataclass(frozen=True, slots=True)
class ContextChunkWindowRecord:
    """One Reranker anchor and its optional immediate same-generation neighbors."""

    anchor: ContextChunkRecord
    previous: ContextChunkRecord | None
    next: ContextChunkRecord | None


class ContextChunkRehydrationError(RuntimeError):
    """A generic failure that does not reveal whether a source row exists."""

    def __init__(self) -> None:
        super().__init__("reranked context source is unavailable")


class RetrievalRepository:
    """Build retrieval statements from one shared trusted authorization scope."""

    def __init__(self, session: Session, statement_timeout_ms: int = 2000) -> None:
        self._session = session
        self._statement_timeout_ms = statement_timeout_ms

    def authorized_active_chunks_statement(
        self,
        current_user: CurrentUser,
    ) -> Select[
        tuple[
            DocumentChunk,
            Document,
            DocumentVersion,
            DocumentIndexSet,
            StoredFile,
        ]
    ]:
        """Return the common pre-ranking scope for future Dense and Lexical SQL."""

        if not isinstance(current_user, CurrentUser):
            raise TypeError("current_user must be a trusted CurrentUser")
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        role_names = tuple(current_user.roles)
        market_scopes = tuple(current_user.market_scopes)
        return (
            select(
                DocumentChunk,
                Document,
                DocumentVersion,
                DocumentIndexSet,
                StoredFile,
            )
            .select_from(DocumentChunk)
            .join(
                DocumentIndexSet,
                and_(
                    DocumentIndexSet.tenant_id == DocumentChunk.tenant_id,
                    DocumentIndexSet.id == DocumentChunk.document_index_set_id,
                    DocumentIndexSet.document_chunk_set_id
                    == DocumentChunk.document_chunk_set_id,
                    DocumentIndexSet.document_version_id
                    == DocumentChunk.document_version_id,
                    DocumentIndexSet.document_id == DocumentChunk.document_id,
                ),
            )
            .join(
                DocumentVersion,
                and_(
                    DocumentVersion.tenant_id == DocumentChunk.tenant_id,
                    DocumentVersion.id == DocumentChunk.document_version_id,
                    DocumentVersion.document_id == DocumentChunk.document_id,
                ),
            )
            .join(
                Document,
                and_(
                    Document.tenant_id == DocumentChunk.tenant_id,
                    Document.id == DocumentChunk.document_id,
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
                DocumentChunk.tenant_id == current_user.tenant_id,
                Document.tenant_id == current_user.tenant_id,
                Document.deleted_at.is_(None),
                Document.active_version_id == DocumentVersion.id,
                DocumentVersion.parse_status == "ready",
                DocumentVersion.index_status == "ready",
                DocumentVersion.active_index_set_id == DocumentIndexSet.id,
                DocumentIndexSet.status == "ready",
                StoredFile.tenant_id == current_user.tenant_id,
                StoredFile.status != "soft_deleted",
                StoredFile.deleted_at.is_(None),
                document_access_clause(
                    tenant_id=current_user.tenant_id,
                    user_id=current_user.user_id,
                    role_names=role_names,
                    market_scopes=market_scopes,
                    company_owner="company_owner" in role_names,
                ),
            )
        )

    def list_authorized_embedding_identities(
        self,
        current_user: CurrentUser,
    ) -> list[dict[str, object]]:
        """List active authorized identities before loading a query model."""

        statement = (
            self.authorized_active_chunks_statement(current_user)
            .with_only_columns(DocumentIndexSet.embedding_identity_json)
            .distinct()
        )
        return list(self._session.scalars(statement).all())

    def dense_candidates_statement(
        self,
        current_user: CurrentUser,
        *,
        query_vector: tuple[float, ...],
        embedding_identity: EmbeddingIdentity,
        limit: int,
    ) -> Select[
        tuple[
            DocumentChunk,
            Document,
            DocumentVersion,
            DocumentIndexSet,
            StoredFile,
            float,
        ]
    ]:
        """Append identity, cosine ranking, and Top K to the shared scope."""

        _validate_dense_arguments(query_vector, embedding_identity, limit)
        identity_json = asdict(embedding_identity)
        distance = DocumentChunk.embedding.cosine_distance(list(query_vector)).label(
            "dense_distance"
        )
        return (
            self.authorized_active_chunks_statement(current_user)
            .where(
                DocumentIndexSet.embedding_identity_json == identity_json,
                DocumentIndexSet.embedding_model == embedding_identity.model_id,
                DocumentIndexSet.embedding_version == embedding_identity.revision,
                DocumentChunk.embedding.is_not(None),
                DocumentChunk.embedding_model == embedding_identity.model_id,
                DocumentChunk.embedding_version == embedding_identity.revision,
            )
            .add_columns(distance)
            .order_by(distance.asc(), DocumentChunk.id.asc())
            .limit(limit)
        )

    def search_dense(
        self,
        current_user: CurrentUser,
        *,
        query_vector: tuple[float, ...],
        embedding_identity: EmbeddingIdentity,
        limit: int,
    ) -> list[DenseCandidateRecord]:
        """Execute one bounded Dense query built from the shared scope."""

        rows = self._session.execute(
            self.dense_candidates_statement(
                current_user,
                query_vector=query_vector,
                embedding_identity=embedding_identity,
                limit=limit,
            )
        ).all()
        return [
            DenseCandidateRecord(
                chunk_id=chunk.id,
                document_id=document.id,
                version_id=version.id,
                index_set_id=index_set.id,
                title=document.title,
                document_type=document.document_type,
                language=document.language,
                market=document.market,
                body_text=chunk.body_text,
                file_extension=file_row.extension,
                heading_path=chunk.heading_path,
                page_numbers=chunk.page_numbers,
                source_spans=chunk.source_spans,
                table_json=chunk.table_json,
                distance=float(distance),
            )
            for chunk, document, version, index_set, file_row, distance in rows
        ]

    def lexical_candidates_statement(
        self,
        current_user: CurrentUser,
        *,
        lexical_tsquery: str,
        fts_builder_version: str,
        limit: int,
    ) -> Select[
        tuple[
            DocumentChunk,
            Document,
            DocumentVersion,
            DocumentIndexSet,
            StoredFile,
            float,
        ]
    ]:
        """Append FTS identity, matching, ranking, and Top K to the shared scope."""

        _validate_lexical_arguments(lexical_tsquery, fts_builder_version, limit)
        tsquery = func.to_tsquery("simple", lexical_tsquery)
        score = func.ts_rank_cd(DocumentChunk.search_vector, tsquery, 32).label(
            "lexical_score"
        )
        return (
            self.authorized_active_chunks_statement(current_user)
            .where(
                DocumentIndexSet.fts_builder_version == fts_builder_version,
                DocumentChunk.search_vector.op("@@")(tsquery),
            )
            .add_columns(score)
            .order_by(score.desc(), DocumentChunk.id.asc())
            .limit(limit)
        )

    def search_lexical(
        self,
        current_user: CurrentUser,
        *,
        lexical_tsquery: str,
        fts_builder_version: str,
        limit: int,
    ) -> list[LexicalCandidateRecord]:
        """Execute one bounded Lexical query built from the shared scope."""

        rows = self._session.execute(
            self.lexical_candidates_statement(
                current_user,
                lexical_tsquery=lexical_tsquery,
                fts_builder_version=fts_builder_version,
                limit=limit,
            )
        ).all()
        return [
            LexicalCandidateRecord(
                chunk_id=chunk.id,
                document_id=document.id,
                version_id=version.id,
                index_set_id=index_set.id,
                title=document.title,
                document_type=document.document_type,
                language=document.language,
                market=document.market,
                body_text=chunk.body_text,
                file_extension=file_row.extension,
                heading_path=chunk.heading_path,
                page_numbers=chunk.page_numbers,
                source_spans=chunk.source_spans,
                table_json=chunk.table_json,
                score=float(score),
            )
            for chunk, document, version, index_set, file_row, score in rows
        ]

    def rehydrate_context_windows(
        self,
        current_user: CurrentUser,
        response: RerankedRetrievalResponse,
        *,
        neighbor_window: int,
    ) -> list[ContextChunkWindowRecord]:
        """Reload trusted anchors and immediate neighbors through the shared scope."""

        if not isinstance(current_user, CurrentUser):
            raise TypeError("current_user must be a trusted CurrentUser")
        if not isinstance(response, RerankedRetrievalResponse):
            raise TypeError("response must be a RerankedRetrievalResponse")
        if (
            not isinstance(neighbor_window, int)
            or isinstance(neighbor_window, bool)
            or not 0 <= neighbor_window <= 1
        ):
            raise ValueError("neighbor window must be between 0 and 1")
        if not response.results:
            return []

        requested_ids = [result.identity.chunk_id for result in response.results]
        if len(requested_ids) != len(set(requested_ids)):
            raise ContextChunkRehydrationError()

        anchor_statement = self.authorized_active_chunks_statement(current_user).where(
            or_(*(_anchor_identity_clause(result) for result in response.results))
        )
        first_rows = self._session.execute(anchor_statement).all()
        trusted_anchors = {
            chunk.id: _context_chunk_record(
                chunk,
                document,
                version,
                file_row,
            )
            for chunk, document, version, _index_set, file_row in first_rows
        }
        _validate_reranked_anchor_facts(response.results, trusted_anchors)

        neighbor_statement = self.authorized_active_chunks_statement(
            current_user
        ).where(
            or_(
                *(
                    and_(
                        DocumentChunk.document_id == anchor.document_id,
                        DocumentChunk.document_version_id == anchor.version_id,
                        DocumentChunk.document_chunk_set_id == anchor.chunk_set_id,
                        DocumentChunk.document_index_set_id == anchor.index_set_id,
                        DocumentChunk.chunk_index.between(
                            max(1, anchor.chunk_index - neighbor_window),
                            anchor.chunk_index + neighbor_window,
                        ),
                    )
                    for anchor in trusted_anchors.values()
                )
            )
        )
        second_rows = self._session.execute(neighbor_statement).all()
        trusted_window_rows = [
            _context_chunk_record(chunk, document, version, file_row)
            for chunk, document, version, _index_set, file_row in second_rows
        ]
        final_anchors = {row.chunk_id: row for row in trusted_window_rows}
        _validate_reranked_anchor_facts(response.results, final_anchors)
        by_generation_index = {
            (
                row.document_id,
                row.version_id,
                row.chunk_set_id,
                row.index_set_id,
                row.chunk_index,
            ): row
            for row in trusted_window_rows
        }

        windows: list[ContextChunkWindowRecord] = []
        for result in response.results:
            anchor = final_anchors[result.identity.chunk_id]
            generation = (
                anchor.document_id,
                anchor.version_id,
                anchor.chunk_set_id,
                anchor.index_set_id,
            )
            previous = (
                by_generation_index.get((*generation, anchor.chunk_index - 1))
                if neighbor_window == 1 and anchor.chunk_index > 1
                else None
            )
            next_chunk = (
                by_generation_index.get((*generation, anchor.chunk_index + 1))
                if neighbor_window == 1
                else None
            )
            windows.append(
                ContextChunkWindowRecord(
                    anchor=anchor,
                    previous=previous,
                    next=next_chunk,
                )
            )
        return windows

    def reauthorize_context_sources(
        self,
        current_user: CurrentUser,
        sources: tuple[ContextChunkRecord, ...],
    ) -> tuple[ContextChunkRecord, ...]:
        """Lock and recheck final Context sources immediately before persistence."""

        if not isinstance(current_user, CurrentUser):
            raise TypeError("current_user must be a trusted CurrentUser")
        if not isinstance(sources, tuple) or not all(
            isinstance(source, ContextChunkRecord) for source in sources
        ):
            raise TypeError("sources must be trusted ContextChunkRecord values")
        if not sources:
            return ()
        source_ids = [source.chunk_id for source in sources]
        if len(source_ids) != len(set(source_ids)):
            raise ContextChunkRehydrationError()

        statement = (
            self.authorized_active_chunks_statement(current_user)
            .where(DocumentChunk.id.in_(source_ids))
            .with_for_update()
        )
        rows = self._session.execute(statement).all()
        trusted_by_id = {
            chunk.id: _context_chunk_record(chunk, document, version, file_row)
            for chunk, document, version, _index_set, file_row in rows
        }
        if len(trusted_by_id) != len(sources):
            raise ContextChunkRehydrationError()
        ordered = tuple(trusted_by_id[source.chunk_id] for source in sources)
        if ordered != sources:
            raise ContextChunkRehydrationError()
        return ordered


def _anchor_identity_clause(result: RerankedRetrievalResult):  # type: ignore[no-untyped-def]
    identity = result.identity
    return and_(
        DocumentChunk.id == identity.chunk_id,
        DocumentChunk.document_id == identity.document_id,
        DocumentChunk.document_version_id == identity.version_id,
        DocumentChunk.document_index_set_id == identity.index_set_id,
    )


def _context_chunk_record(
    chunk: DocumentChunk,
    document: Document,
    version: DocumentVersion,
    file_row: StoredFile,
) -> ContextChunkRecord:
    return ContextChunkRecord(
        chunk_id=chunk.id,
        canonical_chunk_id=chunk.chunk_id,
        chunk_index=chunk.chunk_index,
        kind=chunk.kind,
        document_id=document.id,
        version_id=version.id,
        chunk_set_id=chunk.document_chunk_set_id,
        index_set_id=chunk.document_index_set_id,
        file_id=version.file_id,
        title=document.title,
        document_type=document.document_type,
        language=document.language,
        market=document.market,
        access_level=document.access_level,
        file_extension=file_row.extension,
        body_text=chunk.body_text,
        token_count=chunk.token_count,
        content_sha256=chunk.content_sha256,
        heading_path=deepcopy(chunk.heading_path),
        page_numbers=deepcopy(chunk.page_numbers),
        source_block_ids=deepcopy(chunk.source_block_ids),
        source_spans=deepcopy(chunk.source_spans),
        bounding_boxes=deepcopy(chunk.bounding_boxes),
        overlap_json=deepcopy(chunk.overlap_json),
        table_json=deepcopy(chunk.table_json),
        warnings=deepcopy(chunk.warnings),
    )


def _validate_reranked_anchor_facts(
    results: list[RerankedRetrievalResult],
    trusted: dict[UUID, ContextChunkRecord],
) -> None:
    if len(trusted) < len(results):
        raise ContextChunkRehydrationError()
    for result in results:
        row = trusted.get(result.identity.chunk_id)
        if row is None or (
            row.document_id != result.identity.document_id
            or row.version_id != result.identity.version_id
            or row.index_set_id != result.identity.index_set_id
            or row.body_text != result.body_text
            or row.title != result.document.title
            or row.document_type != result.document.document_type
            or row.language != result.document.language
            or row.market != result.document.market
        ):
            raise ContextChunkRehydrationError()


def _validate_dense_arguments(
    query_vector: tuple[float, ...],
    embedding_identity: EmbeddingIdentity,
    limit: int,
) -> None:
    if not is_dataclass(embedding_identity) or isinstance(embedding_identity, type):
        raise TypeError("embedding_identity must be EmbeddingIdentity")
    if len(query_vector) != embedding_identity.dimensions or not all(
        isinstance(value, float) and math.isfinite(value) for value in query_vector
    ):
        raise ValueError("query vector does not match the embedding identity")
    if not 1 <= limit <= 100:
        raise ValueError("dense limit must be between 1 and 100")


def _validate_lexical_arguments(
    lexical_tsquery: str,
    fts_builder_version: str,
    limit: int,
) -> None:
    tokens = lexical_tsquery.split(" | ")
    if (
        not lexical_tsquery
        or any(not token or not token.isalnum() for token in tokens)
        or " | ".join(tokens) != lexical_tsquery
    ):
        raise ValueError("lexical tsquery must contain bounded alphanumeric tokens")
    if not fts_builder_version or len(fts_builder_version) > 128:
        raise ValueError("FTS builder version is outside the bounded contract")
    if not 1 <= limit <= 100:
        raise ValueError("lexical limit must be between 1 and 100")
