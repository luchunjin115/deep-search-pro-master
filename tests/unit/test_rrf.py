from __future__ import annotations

from uuid import UUID

import pytest

from app.schemas.auth import CurrentUser
from app.schemas.retrieval import (
    DenseRetrievalScore,
    LexicalRetrievalScore,
    PdfRetrievalSourceLocator,
    RetrievalCandidateIdentity,
    RetrievalDocumentMetadata,
    RetrievalEmbeddingIdentity,
    RetrievalFtsIdentity,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalResult,
    RetrievalScoreBreakdown,
)
from app.services.retrieval import RetrievalInternalError
from app.services.retrieval.hybrid import HybridRetrievalService

_USER = CurrentUser(
    user_id=UUID("11111111-1111-4111-8111-111111111111"),
    tenant_id=UUID("22222222-2222-4222-8222-222222222222"),
    email="hybrid-reader@example.com",
    display_name="Hybrid Reader",
    roles=["amazon_operator"],
    market_scopes=["DE"],
    synthetic_data=True,
)
_EMBEDDING_IDENTITY = RetrievalEmbeddingIdentity(
    contract_version="m2-embedding-provider-v1",
    provider="fake",
    model_id="fake/m2-deterministic",
    revision="m2-fake-v1",
    pooling="sha256-shake-v1",
    max_length=8192,
    normalize=True,
    precision="float32",
    dimensions=1024,
)
_FTS_IDENTITY = RetrievalFtsIdentity(builder_version="m2-fts-jieba-search-v1")


class StubRetriever:
    def __init__(
        self,
        response: RetrievalResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self._response = response
        self._error = error
        self.calls: list[tuple[CurrentUser, RetrievalRequest]] = []

    def retrieve(
        self,
        current_user: CurrentUser,
        request: RetrievalRequest,
    ) -> RetrievalResponse:
        self.calls.append((current_user, request))
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


def _result(
    chunk_id: UUID,
    *,
    mode: str,
    rank: int,
    body_text: str = "蘑菇灯亮度调节说明。",
) -> RetrievalResult:
    dense = (
        DenseRetrievalScore(
            rank=rank,
            distance=min(1.0, rank / 10),
            similarity=1 - min(1.0, rank / 10),
        )
        if mode == "dense"
        else None
    )
    lexical = (
        LexicalRetrievalScore(rank=rank, score=1 / rank) if mode == "lexical" else None
    )
    return RetrievalResult(
        identity=RetrievalCandidateIdentity(
            document_id=UUID(int=chunk_id.int + 100),
            version_id=UUID(int=chunk_id.int + 200),
            index_set_id=UUID(int=chunk_id.int + 300),
            chunk_id=chunk_id,
        ),
        document=RetrievalDocumentMetadata(
            title=f"合成文档-{chunk_id}",
            document_type="product_manual",
            language="zh-CN",
            market="DE",
        ),
        body_text=body_text,
        source_locator=PdfRetrievalSourceLocator(page_number=1),
        scores=RetrievalScoreBreakdown(dense=dense, lexical=lexical),
        final_rank=rank,
    )


def _dense_response(chunk_ids: list[UUID]) -> RetrievalResponse:
    return RetrievalResponse(
        mode="dense",
        embedding_identity=_EMBEDDING_IDENTITY,
        results=[
            _result(chunk_id, mode="dense", rank=rank)
            for rank, chunk_id in enumerate(chunk_ids, start=1)
        ],
    )


def _lexical_response(chunk_ids: list[UUID]) -> RetrievalResponse:
    return RetrievalResponse(
        mode="lexical",
        fts_identity=_FTS_IDENTITY,
        results=[
            _result(chunk_id, mode="lexical", rank=rank)
            for rank, chunk_id in enumerate(chunk_ids, start=1)
        ],
    )


def test_hybrid_rrf_deduplicates_and_preserves_both_score_breakdowns() -> None:
    chunk_a = UUID(int=1)
    chunk_b = UUID(int=2)
    chunk_c = UUID(int=3)
    chunk_d = UUID(int=4)
    dense = StubRetriever(_dense_response([chunk_a, chunk_b, chunk_d]))
    lexical = StubRetriever(_lexical_response([chunk_b, chunk_c, chunk_d]))
    service = HybridRetrievalService(dense, lexical, rrf_k=60, candidate_count=10)
    request = RetrievalRequest(query="蘑菇灯亮度")

    response = service.retrieve(_USER, request)

    assert dense.calls == [(_USER, request)]
    assert lexical.calls == [(_USER, request)]
    assert [item.identity.chunk_id for item in response.results] == [
        chunk_b,
        chunk_d,
        chunk_a,
        chunk_c,
    ]
    assert response.mode == "hybrid"
    assert response.embedding_identity == _EMBEDDING_IDENTITY
    assert response.fts_identity == _FTS_IDENTITY
    assert response.rrf_k == 60
    first = response.results[0]
    assert first.scores.dense is not None
    assert first.scores.dense.rank == 2
    assert first.scores.lexical is not None
    assert first.scores.lexical.rank == 1
    assert first.rrf_score == pytest.approx((1 / 62) + (1 / 61))
    assert [item.final_rank for item in response.results] == [1, 2, 3, 4]


def test_hybrid_rrf_uses_chunk_uuid_for_equal_score_and_limits_after_merge() -> None:
    chunk_low = UUID(int=10)
    chunk_high = UUID(int=20)
    dense = StubRetriever(_dense_response([chunk_high]))
    lexical = StubRetriever(_lexical_response([chunk_low]))
    service = HybridRetrievalService(dense, lexical, rrf_k=60, candidate_count=1)

    response = service.retrieve(_USER, RetrievalRequest(query="亮度"))

    assert [item.identity.chunk_id for item in response.results] == [chunk_low]
    assert response.results[0].rrf_score == pytest.approx(1 / 61)


def test_hybrid_returns_empty_with_both_reproducibility_identities() -> None:
    service = HybridRetrievalService(
        StubRetriever(_dense_response([])),
        StubRetriever(_lexical_response([])),
    )

    response = service.retrieve(_USER, RetrievalRequest(query="没有结果"))

    assert response.results == []
    assert response.embedding_identity == _EMBEDDING_IDENTITY
    assert response.fts_identity == _FTS_IDENTITY
    assert response.rrf_k == 60


def test_hybrid_rejects_conflicting_facts_for_the_same_chunk() -> None:
    chunk_id = UUID(int=30)
    dense_response = _dense_response([chunk_id])
    lexical_response = _lexical_response([chunk_id])
    lexical_response.results[0].body_text = "冲突正文"
    service = HybridRetrievalService(
        StubRetriever(dense_response),
        StubRetriever(lexical_response),
    )

    with pytest.raises(RetrievalInternalError):
        service.retrieve(_USER, RetrievalRequest(query="亮度"))


def test_hybrid_does_not_disguise_one_route_failure_as_success() -> None:
    failure = RetrievalInternalError()
    dense = StubRetriever(_dense_response([UUID(int=40)]))
    lexical = StubRetriever(error=failure)
    service = HybridRetrievalService(dense, lexical)

    with pytest.raises(RetrievalInternalError) as captured:
        service.retrieve(_USER, RetrievalRequest(query="亮度"))

    assert captured.value is failure
    assert len(dense.calls) == 1
    assert len(lexical.calls) == 1


@pytest.mark.parametrize(
    ("rrf_k", "candidate_count"),
    [(0, 30), (201, 30), (60, 0), (60, 101)],
)
def test_hybrid_constructor_rejects_out_of_contract_limits(
    rrf_k: int,
    candidate_count: int,
) -> None:
    with pytest.raises(ValueError):
        HybridRetrievalService(
            StubRetriever(_dense_response([])),
            StubRetriever(_lexical_response([])),
            rrf_k=rrf_k,
            candidate_count=candidate_count,
        )
