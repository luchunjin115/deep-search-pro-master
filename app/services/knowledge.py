"""Application orchestration for one authorized knowledge search."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from pydantic import ValidationError

from app.core.errors import KnowledgeEvidencePersistenceError
from app.core.rag_trace import record_rag_stage
from app.schemas.auth import CurrentUser
from app.schemas.evidence import DocumentEvidenceDetail
from app.schemas.knowledge import SearchKnowledgeInput, SearchKnowledgeResult
from app.schemas.retrieval import RerankedRetrievalResponse, RetrievalRequest
from app.services.evidence import (
    EvidenceWriteContext,
    PersistedDocumentContext,
)
from app.services.retrieval.context import BuiltContext
from app.services.retrieval.errors import (
    ContextDataContractError,
    RetrievalInputError,
    RetrievalInternalError,
)


class RerankedKnowledgeRoute(Protocol):
    """The existing permission-first Hybrid and Reranker route."""

    def retrieve(
        self,
        current_user: CurrentUser,
        request: RetrievalRequest,
    ) -> RerankedRetrievalResponse: ...


class KnowledgeContextBuilder(Protocol):
    """Build one bounded Context from a freshly authorized reranked response."""

    def build(
        self,
        current_user: CurrentUser,
        request: RetrievalRequest,
        response: RerankedRetrievalResponse,
    ) -> BuiltContext: ...


class KnowledgeEvidenceWriter(Protocol):
    """Persist Context, Evidence, and an optional ToolCall association atomically."""

    def persist_document_context(
        self,
        current_user: CurrentUser,
        built: BuiltContext,
        *,
        runtime_context: EvidenceWriteContext | None = None,
    ) -> PersistedDocumentContext: ...


@dataclass(frozen=True, slots=True)
class KnowledgeSearchOutcome:
    """Public Tool data plus the minimal internal persistence reuse signal."""

    result: SearchKnowledgeResult
    reused: bool

    @property
    def evidence_ids(self) -> tuple[UUID, ...]:
        """Return the exact ordered Evidence allow-list derived from Context."""

        return self.result.evidence_ids


class KnowledgeSearchService:
    """Run Reranker, Context Builder, and Evidence persistence in one fixed order."""

    def __init__(
        self,
        reranker: RerankedKnowledgeRoute,
        context_builder: KnowledgeContextBuilder,
        evidence_writer: KnowledgeEvidenceWriter,
    ) -> None:
        self._reranker = reranker
        self._context_builder = context_builder
        self._evidence_writer = evidence_writer

    def search(
        self,
        current_user: CurrentUser,
        request: SearchKnowledgeInput,
        *,
        runtime_context: EvidenceWriteContext | None = None,
    ) -> KnowledgeSearchOutcome:
        """Return one persisted, public-safe knowledge Context."""

        if not isinstance(current_user, CurrentUser) or not isinstance(
            request, SearchKnowledgeInput
        ):
            raise RetrievalInputError
        if runtime_context is not None and not isinstance(
            runtime_context, EvidenceWriteContext
        ):
            raise KnowledgeEvidencePersistenceError

        try:
            retrieval_request = RetrievalRequest(query=request.query)
        except ValidationError:
            raise RetrievalInputError from None

        reranked = self._reranker.retrieve(current_user, retrieval_request)
        if not isinstance(reranked, RerankedRetrievalResponse):
            raise RetrievalInternalError
        try:
            reranked = RerankedRetrievalResponse.model_validate(
                reranked.model_dump(mode="python")
            )
        except (TypeError, ValueError, ValidationError):
            raise RetrievalInternalError from None

        built = self._context_builder.build(
            current_user,
            retrieval_request,
            reranked,
        )
        if not isinstance(built, BuiltContext):
            raise ContextDataContractError

        persisted = self._evidence_writer.persist_document_context(
            current_user,
            built,
            runtime_context=runtime_context,
        )
        try:
            outcome = _outcome_from_persisted(built, persisted)
        except (AttributeError, TypeError, ValueError, ValidationError):
            raise KnowledgeEvidencePersistenceError from None
        record_rag_stage("context", outcome.result.context)
        return outcome


def _outcome_from_persisted(
    built: BuiltContext,
    persisted: object,
) -> KnowledgeSearchOutcome:
    if not isinstance(persisted, PersistedDocumentContext):
        raise TypeError("Evidence writer returned an invalid result type")
    if persisted.bundle != built.bundle:
        raise ValueError("persisted Context differs from the built Context")

    segments = persisted.bundle.segments
    if len(persisted.evidences) != len(segments):
        raise ValueError("persisted Evidence count differs from Context")
    for segment, evidence in zip(segments, persisted.evidences, strict=True):
        if not isinstance(evidence, DocumentEvidenceDetail) or (
            evidence.id != segment.evidence_id
            or evidence.context_id != persisted.bundle.context_id
            or evidence.citation_label != segment.citation_label
            or evidence.source_type != segment.source_type
            or evidence.identity != segment.identity
            or evidence.document != segment.document
            or evidence.source_locator != segment.source_locator
            or evidence.context_text_sha256 != segment.text_sha256
        ):
            raise ValueError("persisted Evidence differs from Context")

    return KnowledgeSearchOutcome(
        result=SearchKnowledgeResult(context=persisted.bundle),
        reused=persisted.reused,
    )
