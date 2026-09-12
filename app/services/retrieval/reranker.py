"""Safe Reranker orchestration over server-built authorized Hybrid candidates."""

from __future__ import annotations

from dataclasses import asdict
from typing import Protocol
from uuid import UUID

from pydantic import ValidationError

from app.core.errors import RerankerInputError, RerankerProviderError
from app.core.rag_trace import record_rag_stage
from app.schemas.auth import CurrentUser
from app.schemas.retrieval import (
    RerankedRetrievalResponse,
    RerankedRetrievalResult,
    RetrievalRequest,
    RetrievalRerankerIdentity,
    RetrievalRerankerScore,
    RetrievalResponse,
)
from app.services.retrieval.errors import (
    RetrievalInternalError,
    RetrievalRerankerProviderUnavailableError,
)
from app.services.retrieval.reranker_provider import (
    RerankerBatch,
    RerankerProvider,
    validate_reranker_batch,
)


class HybridRetrievalRoute(Protocol):
    """Trusted server-side route that produces authorized Hybrid candidates."""

    def retrieve(
        self,
        current_user: CurrentUser,
        request: RetrievalRequest,
    ) -> RetrievalResponse: ...


class RerankerRetrievalService:
    """Score and reorder only the exact candidates returned by Hybrid retrieval."""

    def __init__(
        self,
        hybrid_retrieval: HybridRetrievalRoute,
        provider: RerankerProvider,
        *,
        top_k: int = 8,
    ) -> None:
        if not 5 <= top_k <= 8:
            raise ValueError("top_k must be between 5 and 8")
        self._hybrid_retrieval = hybrid_retrieval
        self._provider = provider
        self._top_k = top_k

    def retrieve(
        self,
        current_user: CurrentUser,
        request: RetrievalRequest,
    ) -> RerankedRetrievalResponse:
        """Run trusted Hybrid retrieval, then return its stable scored subset."""

        hybrid_response = self._hybrid_retrieval.retrieve(current_user, request)
        try:
            validated_hybrid = _validated_hybrid_response(hybrid_response)
            provider_identity = self._provider.identity
            public_identity = RetrievalRerankerIdentity.model_validate(
                asdict(provider_identity)
            )
        except (TypeError, ValueError, ValidationError):
            raise RetrievalInternalError from None

        record_rag_stage("retrieval", validated_hybrid)
        if not validated_hybrid.results:
            response = _empty_response(
                validated_hybrid,
                public_identity=public_identity,
                top_k=self._top_k,
            )
            record_rag_stage("reranked", response)
            return response

        passages = tuple(result.body_text for result in validated_hybrid.results)
        try:
            batch = self._provider.score(request.query, passages)
            batch = validate_reranker_batch(
                batch,
                query=request.query,
                passages=passages,
                expected_identity=provider_identity,
            )
        except RerankerInputError:
            raise RetrievalInternalError from None
        except RerankerProviderError:
            raise RetrievalRerankerProviderUnavailableError from None

        try:
            response = _reranked_response(
                validated_hybrid,
                batch=batch,
                public_identity=public_identity,
                top_k=self._top_k,
            )
        except (TypeError, ValueError, ValidationError):
            raise RetrievalInternalError from None
        record_rag_stage("reranked", response)
        return response


def _validated_hybrid_response(response: object) -> RetrievalResponse:
    if not isinstance(response, RetrievalResponse):
        raise TypeError("Hybrid route returned an invalid response type")
    validated = RetrievalResponse.model_validate(response.model_dump(mode="python"))
    if (
        validated.mode != "hybrid"
        or validated.embedding_identity is None
        or validated.fts_identity is None
        or validated.rrf_k is None
    ):
        raise ValueError("Reranker requires a complete Hybrid response")

    chunk_ids: set[UUID] = set()
    generations: dict[UUID, tuple[UUID, UUID]] = {}
    for result in validated.results:
        identity = result.identity
        if identity.chunk_id in chunk_ids:
            raise ValueError("Hybrid response contains a duplicate Chunk")
        chunk_ids.add(identity.chunk_id)
        generation = (identity.version_id, identity.index_set_id)
        existing = generations.setdefault(identity.document_id, generation)
        if existing != generation:
            raise ValueError("Hybrid response mixes active document generations")
    return validated


def _empty_response(
    hybrid: RetrievalResponse,
    *,
    public_identity: RetrievalRerankerIdentity,
    top_k: int,
) -> RerankedRetrievalResponse:
    assert hybrid.embedding_identity is not None
    assert hybrid.fts_identity is not None
    assert hybrid.rrf_k is not None
    return RerankedRetrievalResponse(
        embedding_identity=hybrid.embedding_identity,
        fts_identity=hybrid.fts_identity,
        rrf_k=hybrid.rrf_k,
        reranker_identity=public_identity,
        input_candidate_count=0,
        top_k=top_k,
        results=[],
    )


def _reranked_response(
    hybrid: RetrievalResponse,
    *,
    batch: RerankerBatch,
    public_identity: RetrievalRerankerIdentity,
    top_k: int,
) -> RerankedRetrievalResponse:
    assert hybrid.embedding_identity is not None
    assert hybrid.fts_identity is not None
    assert hybrid.rrf_k is not None
    scored = sorted(
        zip(hybrid.results, batch.scores, strict=True),
        key=lambda item: (
            -item[1].normalized_score,
            item[0].final_rank,
            item[0].identity.chunk_id,
        ),
    )[:top_k]
    results = [
        RerankedRetrievalResult(
            identity=original.identity,
            document=original.document,
            body_text=original.body_text,
            source_locator=original.source_locator,
            scores=original.scores,
            rrf_score=original.rrf_score,
            hybrid_rank=original.final_rank,
            reranker=RetrievalRerankerScore(
                rank=final_rank,
                raw_score=score.raw_score,
                normalized_score=score.normalized_score,
            ),
            final_rank=final_rank,
        )
        for final_rank, (original, score) in enumerate(scored, start=1)
    ]
    return RerankedRetrievalResponse(
        embedding_identity=hybrid.embedding_identity,
        fts_identity=hybrid.fts_identity,
        rrf_k=hybrid.rrf_k,
        reranker_identity=public_identity,
        input_candidate_count=len(hybrid.results),
        top_k=top_k,
        results=results,
    )
