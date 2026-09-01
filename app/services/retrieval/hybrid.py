"""Deterministic Hybrid fusion over the authorized Dense and Lexical lists."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from pydantic import ValidationError

from app.schemas.auth import CurrentUser
from app.schemas.retrieval import (
    DenseRetrievalScore,
    LexicalRetrievalScore,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalResult,
    RetrievalScoreBreakdown,
)
from app.services.retrieval.errors import RetrievalInternalError


class RetrievalRoute(Protocol):
    def retrieve(
        self,
        current_user: CurrentUser,
        request: RetrievalRequest,
    ) -> RetrievalResponse: ...


@dataclass(slots=True)
class _MergedCandidate:
    result: RetrievalResult
    dense: DenseRetrievalScore | None = None
    lexical: LexicalRetrievalScore | None = None


class HybridRetrievalService:
    """Fuse both complete route responses without inventing partial success."""

    def __init__(
        self,
        dense_retrieval: RetrievalRoute,
        lexical_retrieval: RetrievalRoute,
        *,
        rrf_k: int = 60,
        candidate_count: int = 30,
    ) -> None:
        if not 1 <= rrf_k <= 200:
            raise ValueError("rrf_k must be between 1 and 200")
        if not 1 <= candidate_count <= 100:
            raise ValueError("candidate_count must be between 1 and 100")
        self._dense_retrieval = dense_retrieval
        self._lexical_retrieval = lexical_retrieval
        self._rrf_k = rrf_k
        self._candidate_count = candidate_count

    def retrieve(
        self,
        current_user: CurrentUser,
        request: RetrievalRequest,
    ) -> RetrievalResponse:
        """Run both safe routes and return one stable, reproducible RRF list."""

        dense_response = self._dense_retrieval.retrieve(current_user, request)
        lexical_response = self._lexical_retrieval.retrieve(current_user, request)
        try:
            return _fuse_responses(
                dense_response,
                lexical_response,
                rrf_k=self._rrf_k,
                candidate_count=self._candidate_count,
            )
        except (TypeError, ValueError, ValidationError):
            raise RetrievalInternalError from None


def _fuse_responses(
    dense_response: RetrievalResponse,
    lexical_response: RetrievalResponse,
    *,
    rrf_k: int,
    candidate_count: int,
) -> RetrievalResponse:
    if dense_response.mode != "dense" or dense_response.embedding_identity is None:
        raise ValueError("Dense route returned an invalid response mode")
    if lexical_response.mode != "lexical" or lexical_response.fts_identity is None:
        raise ValueError("Lexical route returned an invalid response mode")

    merged: dict[UUID, _MergedCandidate] = {}
    for expected_rank, result in enumerate(dense_response.results, start=1):
        dense_score = result.scores.dense
        if dense_score is None or dense_score.rank != expected_rank:
            raise ValueError("Dense route ranks are not contiguous")
        candidate = _merge_candidate(merged, result)
        if candidate.dense is not None:
            raise ValueError("Dense route returned a duplicate Chunk")
        candidate.dense = dense_score

    for expected_rank, result in enumerate(lexical_response.results, start=1):
        lexical_score = result.scores.lexical
        if lexical_score is None or lexical_score.rank != expected_rank:
            raise ValueError("Lexical route ranks are not contiguous")
        candidate = _merge_candidate(merged, result)
        if candidate.lexical is not None:
            raise ValueError("Lexical route returned a duplicate Chunk")
        candidate.lexical = lexical_score

    _validate_one_generation_per_document(merged.values())
    ranked = sorted(
        (
            (_rrf_score(candidate, rrf_k=rrf_k), candidate)
            for candidate in merged.values()
        ),
        key=lambda item: (-item[0], item[1].result.identity.chunk_id),
    )[:candidate_count]
    results = [
        _hybrid_result(candidate, rrf_score=score, final_rank=final_rank)
        for final_rank, (score, candidate) in enumerate(ranked, start=1)
    ]
    return RetrievalResponse(
        mode="hybrid",
        embedding_identity=dense_response.embedding_identity,
        fts_identity=lexical_response.fts_identity,
        rrf_k=rrf_k,
        results=results,
    )


def _merge_candidate(
    merged: dict[UUID, _MergedCandidate],
    result: RetrievalResult,
) -> _MergedCandidate:
    chunk_id = result.identity.chunk_id
    candidate = merged.get(chunk_id)
    if candidate is None:
        candidate = _MergedCandidate(result=result)
        merged[chunk_id] = candidate
        return candidate
    if not _same_public_candidate(candidate.result, result):
        raise ValueError("Routes returned conflicting facts for one Chunk")
    return candidate


def _same_public_candidate(left: RetrievalResult, right: RetrievalResult) -> bool:
    return (
        left.identity == right.identity
        and left.document == right.document
        and left.body_text == right.body_text
        and left.source_locator == right.source_locator
    )


def _validate_one_generation_per_document(
    candidates: Iterable[_MergedCandidate],
) -> None:
    generations: dict[UUID, tuple[UUID, UUID]] = {}
    for candidate in candidates:
        identity = candidate.result.identity
        generation = (identity.version_id, identity.index_set_id)
        existing = generations.setdefault(identity.document_id, generation)
        if existing != generation:
            raise ValueError("Routes observed conflicting active document generations")


def _rrf_score(candidate: _MergedCandidate, *, rrf_k: int) -> float:
    score = 0.0
    if candidate.dense is not None:
        score += 1 / (rrf_k + candidate.dense.rank)
    if candidate.lexical is not None:
        score += 1 / (rrf_k + candidate.lexical.rank)
    if score <= 0:
        raise ValueError("RRF requires at least one route hit")
    return score


def _hybrid_result(
    candidate: _MergedCandidate,
    *,
    rrf_score: float,
    final_rank: int,
) -> RetrievalResult:
    original = candidate.result
    return RetrievalResult(
        identity=original.identity,
        document=original.document,
        body_text=original.body_text,
        source_locator=original.source_locator,
        scores=RetrievalScoreBreakdown(
            dense=candidate.dense,
            lexical=candidate.lexical,
        ),
        rrf_score=rrf_score,
        final_rank=final_rank,
    )
