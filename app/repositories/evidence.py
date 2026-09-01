"""Tenant-scoped Evidence reads and idempotent M2 Context persistence."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.knowledge import DocumentChunk
from app.models.runtime import ContextArtifact, Evidence
from app.repositories.common import apply_statement_timeout
from app.repositories.retrieval import ContextChunkRecord, RetrievalRepository
from app.schemas.auth import CurrentUser


@dataclass(frozen=True, slots=True)
class AuthorizedCitationContext:
    """Minimal current-user allow-list consumed by citation validation."""

    context_id: UUID
    evidence_ids: tuple[UUID, ...]


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
