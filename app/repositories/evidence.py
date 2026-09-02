"""Tenant-scoped Evidence reads and idempotent M2 Context persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.knowledge import (
    Document,
    DocumentChunk,
    DocumentIndexSet,
    DocumentVersion,
    StoredFile,
)
from app.models.runtime import ContextArtifact, Evidence, ToolCall, ToolContextLink
from app.repositories.common import apply_statement_timeout
from app.repositories.retrieval import ContextChunkRecord, RetrievalRepository
from app.schemas.auth import CurrentUser


@dataclass(frozen=True, slots=True)
class AuthorizedCitationContext:
    """Minimal current-user allow-list consumed by citation validation."""

    context_id: UUID
    evidence_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class AuthorizedDocumentEvidence:
    """Public-safe document Evidence facts after current authorization checks."""

    id: UUID
    source_type: str
    file_id: UUID
    context_id: UUID
    citation_ordinal: int
    document_id: UUID
    document_version_id: UUID
    document_index_set_id: UUID
    document_chunk_id: UUID
    title: str
    excerpt: str
    observed_at: datetime
    document_title: str
    document_type: str
    language: str | None
    market: str | None
    source_locator: dict[str, object]
    source_content_sha256: str
    context_text_sha256: str
    created_at: datetime


class KnowledgeEvidenceRepository:
    """Persist one Context and its document Evidence without committing."""

    def __init__(self, session: Session, statement_timeout_ms: int = 2000) -> None:
        self._session = session
        self._statement_timeout_ms = statement_timeout_ms

    def reauthorize_sources(
        self,
        current_user: CurrentUser,
        sources: tuple[ContextChunkRecord, ...],
    ) -> tuple[ContextChunkRecord, ...]:
        return RetrievalRepository(
            self._session,
            statement_timeout_ms=self._statement_timeout_ms,
        ).reauthorize_context_sources(current_user, sources)

    def insert_context_artifact(self, values: dict[str, object]) -> bool:
        statement = (
            insert(ContextArtifact)
            .values(**values)
            .on_conflict_do_nothing()
            .returning(ContextArtifact.id)
        )
        return self._session.scalar(statement) is not None

    def find_context_artifact(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        identity_sha256: str,
    ) -> ContextArtifact | None:
        return self._session.scalar(
            select(ContextArtifact)
            .where(
                ContextArtifact.tenant_id == tenant_id,
                ContextArtifact.requested_by_user_id == user_id,
                ContextArtifact.identity_sha256 == identity_sha256,
            )
            .with_for_update()
        )

    def insert_document_evidences(self, values: list[dict[str, object]]) -> None:
        if not values:
            return
        self._session.execute(insert(Evidence).values(values).on_conflict_do_nothing())

    def list_document_evidences(
        self,
        *,
        tenant_id: UUID,
        context_id: UUID,
    ) -> list[Evidence]:
        return list(
            self._session.scalars(
                select(Evidence)
                .where(
                    Evidence.tenant_id == tenant_id,
                    Evidence.context_artifact_id == context_id,
                )
                .order_by(Evidence.citation_ordinal.asc())
                .with_for_update()
            ).all()
        )

    def find_knowledge_tool_call(
        self,
        *,
        tenant_id: UUID,
        agent_run_id: UUID,
        tool_call_id: UUID,
    ) -> ToolCall | None:
        """Lock one allowed knowledge ToolCall before linking business data."""

        return self._session.scalar(
            select(ToolCall)
            .where(
                ToolCall.tenant_id == tenant_id,
                ToolCall.agent_run_id == agent_run_id,
                ToolCall.id == tool_call_id,
                ToolCall.tool_name == "search_knowledge",
                ToolCall.permission_result == "allowed",
                ToolCall.status.in_(("running", "success")),
            )
            .with_for_update(read=True, key_share=True)
        )

    def insert_tool_context_link(self, values: dict[str, object]) -> bool:
        statement = (
            insert(ToolContextLink)
            .values(**values)
            .on_conflict_do_nothing()
            .returning(ToolContextLink.id)
        )
        return self._session.scalar(statement) is not None

    def find_tool_context_link(
        self,
        *,
        tenant_id: UUID,
        agent_run_id: UUID,
        tool_call_id: UUID,
    ) -> ToolContextLink | None:
        return self._session.scalar(
            select(ToolContextLink)
            .where(
                ToolContextLink.tenant_id == tenant_id,
                ToolContextLink.agent_run_id == agent_run_id,
                ToolContextLink.tool_call_id == tool_call_id,
            )
            .with_for_update()
        )

    def load_authorized_citation_context(
        self,
        current_user: CurrentUser,
        context_id: UUID,
    ) -> AuthorizedCitationContext | None:
        """Return a complete Evidence allow-list only while every source is readable."""

        if not isinstance(current_user, CurrentUser) or not isinstance(
            context_id, UUID
        ):
            raise TypeError("citation Context requires trusted typed input")
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        context = self._session.scalar(
            select(ContextArtifact).where(
                ContextArtifact.id == context_id,
                ContextArtifact.tenant_id == current_user.tenant_id,
                ContextArtifact.requested_by_user_id == current_user.user_id,
            )
        )
        if context is None:
            return None

        evidence_rows = list(
            self._session.scalars(
                select(Evidence)
                .where(
                    Evidence.tenant_id == current_user.tenant_id,
                    Evidence.context_artifact_id == context_id,
                )
                .order_by(Evidence.citation_ordinal.asc())
            ).all()
        )
        ordinals = [row.citation_ordinal for row in evidence_rows]
        if (
            context.contract_version != "m2-context-bundle-v1"
            or context.token_counter_version != "m2-unicode-token-counter-v1"
            or len(evidence_rows) != context.segment_count
            or ordinals != list(range(1, context.segment_count + 1))
            or any(
                row.evidence_schema_version != "m2-document-evidence-v1"
                or row.source_type not in {"knowledge", "user_file"}
                or row.source_name != "document_chunk"
                for row in evidence_rows
            )
        ):
            return None
        if not evidence_rows:
            return AuthorizedCitationContext(context_id=context.id, evidence_ids=())

        authorized_statement = (
            RetrievalRepository(
                self._session,
                statement_timeout_ms=self._statement_timeout_ms,
            )
            .authorized_active_chunks_statement(current_user)
            .join(
                Evidence,
                and_(
                    Evidence.tenant_id == current_user.tenant_id,
                    Evidence.document_chunk_id == DocumentChunk.id,
                    Evidence.document_id == DocumentChunk.document_id,
                    Evidence.document_version_id == DocumentChunk.document_version_id,
                    Evidence.document_chunk_set_id
                    == DocumentChunk.document_chunk_set_id,
                    Evidence.document_index_set_id
                    == DocumentChunk.document_index_set_id,
                ),
            )
            .where(
                Evidence.context_artifact_id == context_id,
                Evidence.evidence_schema_version == "m2-document-evidence-v1",
            )
            .with_only_columns(Evidence.id)
            .order_by(Evidence.citation_ordinal.asc())
        )
        authorized_ids = tuple(self._session.scalars(authorized_statement).all())
        expected_ids = tuple(row.id for row in evidence_rows)
        if authorized_ids != expected_ids:
            return None
        return AuthorizedCitationContext(
            context_id=context.id,
            evidence_ids=expected_ids,
        )


class EvidenceRepository:
    """Load one Evidence row only inside a trusted tenant boundary."""

    def __init__(self, session: Session, statement_timeout_ms: int) -> None:
        self._session = session
        self._statement_timeout_ms = statement_timeout_ms

    def find_by_id(self, *, tenant_id: UUID, evidence_id: UUID) -> Evidence | None:
        apply_statement_timeout(self._session, self._statement_timeout_ms)
        return self._session.scalar(
            select(Evidence).where(
                Evidence.id == evidence_id,
                Evidence.tenant_id == tenant_id,
            )
        )

    def find_authorized_document_by_id(
        self,
        current_user: CurrentUser,
        evidence_id: UUID,
    ) -> AuthorizedDocumentEvidence | None:
        """Return one current, requester-bound document Evidence or hide it."""

        if not isinstance(current_user, CurrentUser) or not isinstance(
            evidence_id, UUID
        ):
            raise TypeError("document Evidence requires trusted typed input")
        statement = (
            RetrievalRepository(
                self._session,
                statement_timeout_ms=self._statement_timeout_ms,
            )
            .authorized_active_chunks_statement(current_user)
            .join(
                Evidence,
                and_(
                    Evidence.tenant_id == current_user.tenant_id,
                    Evidence.document_chunk_id == DocumentChunk.id,
                    Evidence.document_id == DocumentChunk.document_id,
                    Evidence.document_version_id == DocumentChunk.document_version_id,
                    Evidence.document_chunk_set_id
                    == DocumentChunk.document_chunk_set_id,
                    Evidence.document_index_set_id
                    == DocumentChunk.document_index_set_id,
                    Evidence.file_id == DocumentVersion.file_id,
                ),
            )
            .join(
                ContextArtifact,
                and_(
                    ContextArtifact.tenant_id == Evidence.tenant_id,
                    ContextArtifact.id == Evidence.context_artifact_id,
                ),
            )
            .where(
                Evidence.id == evidence_id,
                Evidence.evidence_schema_version == "m2-document-evidence-v1",
                Evidence.source_type.in_(("knowledge", "user_file")),
                Evidence.source_name == "document_chunk",
                Evidence.trust_level == "document_snapshot",
                Evidence.synthetic_data.is_(True),
                Evidence.title == Document.title,
                Evidence.source_content_sha256 == DocumentChunk.content_sha256,
                ContextArtifact.requested_by_user_id == current_user.user_id,
                ContextArtifact.contract_version == "m2-context-bundle-v1",
                ContextArtifact.token_counter_version == "m2-unicode-token-counter-v1",
                Evidence.citation_ordinal <= ContextArtifact.segment_count,
            )
            .with_only_columns(
                Evidence,
                Document,
                DocumentVersion,
                DocumentIndexSet,
                DocumentChunk,
                StoredFile,
            )
        )
        row = self._session.execute(statement).one_or_none()
        if row is None:
            return None
        evidence, document, version, index_set, chunk, _file_row = row
        if not all(
            (
                isinstance(evidence.id, UUID),
                isinstance(evidence.file_id, UUID),
                isinstance(evidence.context_artifact_id, UUID),
                isinstance(evidence.citation_ordinal, int),
                isinstance(evidence.document_id, UUID),
                isinstance(evidence.document_version_id, UUID),
                isinstance(evidence.document_index_set_id, UUID),
                isinstance(evidence.document_chunk_id, UUID),
                isinstance(evidence.source_locator_json, dict),
                isinstance(evidence.source_content_sha256, str),
                isinstance(evidence.context_text_sha256, str),
            )
        ):
            return None
        return AuthorizedDocumentEvidence(
            id=evidence.id,
            source_type=evidence.source_type,
            file_id=evidence.file_id,
            context_id=evidence.context_artifact_id,
            citation_ordinal=evidence.citation_ordinal,
            document_id=document.id,
            document_version_id=version.id,
            document_index_set_id=index_set.id,
            document_chunk_id=chunk.id,
            title=evidence.title,
            excerpt=evidence.excerpt,
            observed_at=evidence.observed_at,
            document_title=document.title,
            document_type=document.document_type,
            language=document.language,
            market=document.market,
            source_locator=evidence.source_locator_json,
            source_content_sha256=evidence.source_content_sha256,
            context_text_sha256=evidence.context_text_sha256,
            created_at=evidence.created_at,
        )
