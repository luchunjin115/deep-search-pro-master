from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import replace
from uuid import UUID

import pytest

from app.core.errors import RerankerProviderError
from app.core.rag_trace import RagReviewTrace, rag_review_trace
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
from app.services.retrieval import (
    FakeRerankerProvider,
    RetrievalInternalError,
    RetrievalRerankerProviderUnavailableError,
)
from app.services.retrieval.reranker import RerankerRetrievalService
from app.services.retrieval.reranker_provider import (
    RerankerBatch,
    RerankerIdentity,
    RerankerPairScore,
    build_reranker_pair_key,
)

_USER = CurrentUser(
    user_id=UUID("11111111-1111-4111-8111-111111111111"),
    tenant_id=UUID("22222222-2222-4222-8222-222222222222"),
    email="reranker-reader@example.com",
    display_name="Reranker reader",
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


class StubHybridRetrieval:
    def __init__(self, response: RetrievalResponse) -> None:
        self.response = response
        self.calls: list[tuple[CurrentUser, RetrievalRequest]] = []

    def retrieve(
        self,
        current_user: CurrentUser,
        request: RetrievalRequest,
    ) -> RetrievalResponse:
        self.calls.append((current_user, request))
        return self.response


BatchTransform = Callable[
    [RerankerBatch, str, tuple[str, ...]],
    RerankerBatch,
]


class ScriptedRerankerProvider:
    def __init__(
        self,
        raw_scores: Sequence[float],
        *,
        transform: BatchTransform | None = None,
    ) -> None:
        self._identity = FakeRerankerProvider().identity
        self._raw_scores = tuple(raw_scores)
        self._transform = transform
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    @property
    def identity(self) -> RerankerIdentity:
        return self._identity

    def score(self, query: str, passages: Sequence[str]) -> RerankerBatch:
        passage_tuple = tuple(passages)
        self.calls.append((query, passage_tuple))
        scores = tuple(
            RerankerPairScore(
                pair_key=build_reranker_pair_key(
                    self.identity,
                    query,
                    passage,
                    position,
                ),
                raw_score=raw_score,
                normalized_score=_sigmoid(raw_score),
            )
            for position, (passage, raw_score) in enumerate(
                zip(passage_tuple, self._raw_scores, strict=True)
            )
        )
        batch = RerankerBatch(
            scores=scores,
            identity=self.identity,
            effective_batch_size=len(passage_tuple),
        )
        if self._transform is not None:
            return self._transform(batch, query, passage_tuple)
        return batch


class FailingRerankerProvider:
    identity = FakeRerankerProvider().identity

    def score(self, query: str, passages: Sequence[str]) -> RerankerBatch:
        del query, passages
        raise RerankerProviderError(retryable=True)


def _hybrid_result(rank: int, *, body_text: str | None = None) -> RetrievalResult:
    return RetrievalResult(
        identity=RetrievalCandidateIdentity(
            document_id=UUID(int=100 + rank),
            version_id=UUID(int=200 + rank),
            index_set_id=UUID(int=300 + rank),
            chunk_id=UUID(int=rank),
        ),
        document=RetrievalDocumentMetadata(
            title=f"合成手册-{rank}",
            document_type="product_manual",
            language="zh-CN",
            market="DE",
        ),
        body_text=body_text or f"第{rank}段获权Hybrid正文",
        source_locator=PdfRetrievalSourceLocator(
            page_number=rank,
            block_number=rank,
        ),
        scores=RetrievalScoreBreakdown(
            dense=DenseRetrievalScore(
                rank=rank,
                distance=min(rank / 100, 1),
                similarity=1 - min(rank / 100, 1),
            ),
            lexical=LexicalRetrievalScore(rank=rank, score=1 / rank),
        ),
        rrf_score=2 / (60 + rank),
        final_rank=rank,
    )


def _hybrid_response(count: int) -> RetrievalResponse:
    return RetrievalResponse(
        mode="hybrid",
        embedding_identity=_EMBEDDING_IDENTITY,
        fts_identity=_FTS_IDENTITY,
        rrf_k=60,
        results=[_hybrid_result(rank) for rank in range(1, count + 1)],
    )


def test_reranker_calls_trusted_hybrid_then_reorders_without_changing_facts() -> None:
    hybrid_response = _hybrid_response(3)
    hybrid = StubHybridRetrieval(hybrid_response)
    provider = ScriptedRerankerProvider([0.0, 3.0, 1.0])
    service = RerankerRetrievalService(hybrid, provider, top_k=8)
    request = RetrievalRequest(query="哪段最相关？")

    trace = RagReviewTrace()
    with rag_review_trace(trace):
        response = service.retrieve(_USER, request)
    assert trace.retrieval == hybrid_response.model_dump(mode="json")
    assert trace.reranked == response.model_dump(mode="json")

    assert hybrid.calls == [(_USER, request)]
    assert provider.calls == [
        (request.query, tuple(item.body_text for item in hybrid_response.results))
    ]
    assert response.mode == "reranked"
    assert response.embedding_identity == hybrid_response.embedding_identity
    assert response.fts_identity == hybrid_response.fts_identity
    assert response.rrf_k == hybrid_response.rrf_k
    assert response.input_candidate_count == 3
    assert response.top_k == 8
    assert [item.hybrid_rank for item in response.results] == [2, 3, 1]
    assert [item.final_rank for item in response.results] == [1, 2, 3]
    assert [item.reranker.rank for item in response.results] == [1, 2, 3]

    originals = {
        item.identity.chunk_id: item.model_dump(exclude={"final_rank"})
        for item in hybrid_response.results
    }
    for item in response.results:
        actual = item.model_dump(exclude={"final_rank", "hybrid_rank", "reranker"})
        assert actual == originals[item.identity.chunk_id]
    assert [item.final_rank for item in hybrid_response.results] == [1, 2, 3]


def test_reranker_keeps_hybrid_order_for_equal_scores() -> None:
    hybrid = StubHybridRetrieval(_hybrid_response(3))
    service = RerankerRetrievalService(
        hybrid,
        ScriptedRerankerProvider([1.0, 1.0, 1.0]),
    )

    response = service.retrieve(_USER, RetrievalRequest(query="同分"))

    assert [item.hybrid_rank for item in response.results] == [1, 2, 3]


def test_reranker_applies_server_top_eight_after_scoring_all_candidates() -> None:
    hybrid_response = _hybrid_response(10)
    provider = ScriptedRerankerProvider(list(range(10)))
    service = RerankerRetrievalService(
        StubHybridRetrieval(hybrid_response),
        provider,
        top_k=8,
    )

    response = service.retrieve(_USER, RetrievalRequest(query="选前八条"))

    assert len(provider.calls[0][1]) == 10
    assert len(response.results) == 8
    assert [item.hybrid_rank for item in response.results] == [10, 9, 8, 7, 6, 5, 4, 3]
    assert {item.identity.chunk_id for item in response.results}.issubset(
        {item.identity.chunk_id for item in hybrid_response.results}
    )


def test_empty_hybrid_response_does_not_call_provider() -> None:
    provider = ScriptedRerankerProvider([])
    service = RerankerRetrievalService(
        StubHybridRetrieval(_hybrid_response(0)),
        provider,
    )

    response = service.retrieve(_USER, RetrievalRequest(query="没有候选"))

    assert response.results == []
    assert response.input_candidate_count == 0
    assert provider.calls == []


def test_provider_failure_is_mapped_to_one_safe_retrieval_error() -> None:
    service = RerankerRetrievalService(
        StubHybridRetrieval(_hybrid_response(1)),
        FailingRerankerProvider(),
    )

    with pytest.raises(RetrievalRerankerProviderUnavailableError) as captured:
        service.retrieve(_USER, RetrievalRequest(query="秘密问题"))

    rendered = captured.value.to_detail().model_dump_json()
    assert "秘密问题" not in rendered
    assert "CUDA" not in rendered


def _drop_score(
    batch: RerankerBatch,
    _query: str,
    _passages: tuple[str, ...],
) -> RerankerBatch:
    return replace(batch, scores=batch.scores[:-1])


def _reverse_scores(
    batch: RerankerBatch,
    _query: str,
    _passages: tuple[str, ...],
) -> RerankerBatch:
    return replace(batch, scores=tuple(reversed(batch.scores)))


def _change_identity(
    batch: RerankerBatch,
    _query: str,
    _passages: tuple[str, ...],
) -> RerankerBatch:
    return replace(batch, identity=replace(batch.identity, revision="wrong"))


def _bind_first_score_to_tampered_body(
    batch: RerankerBatch,
    query: str,
    passages: tuple[str, ...],
) -> RerankerBatch:
    tampered = replace(
        batch.scores[0],
        pair_key=build_reranker_pair_key(
            batch.identity,
            query,
            "被Provider替换的正文",
            0,
        ),
    )
    return replace(batch, scores=(tampered, *batch.scores[1:]))


@pytest.mark.parametrize(
    "transform",
    [
        _drop_score,
        _reverse_scores,
        _change_identity,
        _bind_first_score_to_tampered_body,
    ],
)
def test_service_rejects_provider_count_order_identity_or_fact_tampering(
    transform: BatchTransform,
) -> None:
    service = RerankerRetrievalService(
        StubHybridRetrieval(_hybrid_response(2)),
        ScriptedRerankerProvider([2.0, 1.0], transform=transform),
    )

    with pytest.raises(RetrievalRerankerProviderUnavailableError):
        service.retrieve(_USER, RetrievalRequest(query="防篡改"))


@pytest.mark.parametrize("kind", ["wrong_mode", "duplicate", "invalid_body"])
def test_service_rejects_malformed_hybrid_response_before_provider(
    kind: str,
) -> None:
    valid = _hybrid_response(2)
    if kind == "wrong_mode":
        malformed = valid.model_copy(update={"mode": "dense"})
    elif kind == "duplicate":
        malformed = valid.model_copy(update={"results": [valid.results[0]] * 2})
    else:
        bad_result = valid.results[0].model_copy(update={"body_text": ""})
        malformed = valid.model_copy(update={"results": [bad_result, valid.results[1]]})
    provider = ScriptedRerankerProvider([2.0, 1.0])
    service = RerankerRetrievalService(StubHybridRetrieval(malformed), provider)

    with pytest.raises(RetrievalInternalError):
        service.retrieve(_USER, RetrievalRequest(query="检查Hybrid"))

    assert provider.calls == []


@pytest.mark.parametrize("top_k", [4, 9])
def test_reranker_constructor_rejects_caller_controlled_top_k(top_k: int) -> None:
    with pytest.raises(ValueError):
        RerankerRetrievalService(
            StubHybridRetrieval(_hybrid_response(0)),
            FakeRerankerProvider(),
            top_k=top_k,
        )


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1 / (1 + math.exp(-value))
    exponential = math.exp(value)
    return exponential / (1 + exponential)
