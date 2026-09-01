from __future__ import annotations

import math
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.core.config import (
    BGE_RERANKER_MODEL_ID,
    BGE_RERANKER_REVISION,
    Settings,
)
from app.schemas.retrieval import (
    DenseRetrievalScore,
    LexicalRetrievalScore,
    PdfRetrievalSourceLocator,
    RerankedRetrievalResponse,
    RerankedRetrievalResult,
    RetrievalCandidateIdentity,
    RetrievalDocumentMetadata,
    RetrievalEmbeddingIdentity,
    RetrievalFtsIdentity,
    RetrievalRerankerIdentity,
    RetrievalRerankerScore,
    RetrievalScoreBreakdown,
)
from app.services.retrieval.errors import (
    RetrievalRerankerProviderUnavailableError,
)


def settings_without_env(**overrides: object) -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        **overrides,  # type: ignore[arg-type]
    )


def embedding_identity() -> RetrievalEmbeddingIdentity:
    return RetrievalEmbeddingIdentity(
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


def reranker_identity() -> RetrievalRerankerIdentity:
    return RetrievalRerankerIdentity(
        contract_version="m2-reranker-provider-v1",
        provider="fake",
        model_id="fake/m2-reranker-deterministic",
        revision="m2-fake-reranker-v1",
        max_length=8192,
        precision="float32",
        score_transform="sigmoid",
    )


def sigmoid(value: float) -> float:
    if value >= 0:
        return 1 / (1 + math.exp(-value))
    exponential = math.exp(value)
    return exponential / (1 + exponential)


def reranked_result(
    *,
    hybrid_rank: int,
    final_rank: int,
    raw_score: float,
    chunk_id: UUID | None = None,
    score_rank: int | None = None,
) -> RerankedRetrievalResult:
    return RerankedRetrievalResult(
        identity=RetrievalCandidateIdentity(
            document_id=uuid4(),
            version_id=uuid4(),
            index_set_id=uuid4(),
            chunk_id=chunk_id or uuid4(),
        ),
        document=RetrievalDocumentMetadata(
            title="蘑菇灯使用手册",
            document_type="product_manual",
            language="zh-CN",
            market="DE",
        ),
        body_text="额定电压为220 V。",
        source_locator=PdfRetrievalSourceLocator(page_number=2, block_number=4),
        scores=RetrievalScoreBreakdown(
            dense=DenseRetrievalScore(rank=2, distance=0.2, similarity=0.8),
            lexical=LexicalRetrievalScore(rank=1, score=0.75),
        ),
        rrf_score=(1 / 62) + (1 / 61),
        hybrid_rank=hybrid_rank,
        reranker=RetrievalRerankerScore(
            rank=score_rank or final_rank,
            raw_score=raw_score,
            normalized_score=sigmoid(raw_score),
        ),
        final_rank=final_rank,
    )


def reranked_response(
    results: list[RerankedRetrievalResult],
    *,
    input_candidate_count: int = 30,
    top_k: int = 8,
) -> RerankedRetrievalResponse:
    return RerankedRetrievalResponse(
        embedding_identity=embedding_identity(),
        fts_identity=RetrievalFtsIdentity(builder_version="m2-fts-jieba-search-v1"),
        rrf_k=60,
        reranker_identity=reranker_identity(),
        input_candidate_count=input_candidate_count,
        top_k=top_k,
        results=results,
    )


def test_reranked_response_preserves_hybrid_evidence_and_adds_reranker_scores() -> None:
    result = reranked_result(hybrid_rank=7, final_rank=1, raw_score=2.0)
    response = reranked_response([result])

    assert response.mode == "reranked"
    assert response.results[0].hybrid_rank == 7
    assert response.results[0].scores.dense is not None
    assert response.results[0].scores.lexical is not None
    assert response.results[0].rrf_score == pytest.approx((1 / 62) + (1 / 61))
    assert response.results[0].reranker.raw_score == 2.0
    assert response.results[0].reranker.normalized_score == pytest.approx(sigmoid(2.0))
    assert response.reranker_identity.score_transform == "sigmoid"


@pytest.mark.parametrize("score", (math.nan, math.inf, -math.inf))
def test_reranker_score_rejects_non_finite_values(score: float) -> None:
    with pytest.raises(ValidationError):
        RetrievalRerankerScore(rank=1, raw_score=score, normalized_score=0.5)
    with pytest.raises(ValidationError):
        RetrievalRerankerScore(rank=1, raw_score=0.0, normalized_score=score)


def test_reranker_score_requires_sigmoid_value_and_positive_rank() -> None:
    with pytest.raises(ValidationError, match="sigmoid"):
        RetrievalRerankerScore(rank=1, raw_score=0.0, normalized_score=0.75)
    with pytest.raises(ValidationError):
        RetrievalRerankerScore(rank=0, raw_score=0.0, normalized_score=0.5)


def test_reranked_response_requires_contiguous_stable_score_order() -> None:
    first = reranked_result(hybrid_rank=5, final_rank=1, raw_score=3.0)
    second = reranked_result(hybrid_rank=2, final_rank=2, raw_score=1.0)

    response = reranked_response([first, second])

    assert [result.final_rank for result in response.results] == [1, 2]

    with pytest.raises(ValidationError, match="contiguous"):
        reranked_response(
            [
                first,
                reranked_result(hybrid_rank=2, final_rank=3, raw_score=1.0),
            ]
        )
    with pytest.raises(ValidationError, match="score rank"):
        reranked_response(
            [reranked_result(hybrid_rank=5, final_rank=1, raw_score=3.0, score_rank=2)]
        )
    with pytest.raises(ValidationError, match="score order"):
        reranked_response(
            [
                reranked_result(hybrid_rank=2, final_rank=1, raw_score=1.0),
                reranked_result(hybrid_rank=5, final_rank=2, raw_score=3.0),
            ]
        )


def test_reranked_response_rejects_duplicate_or_out_of_range_hybrid_ranks() -> None:
    with pytest.raises(ValidationError, match="Hybrid ranks"):
        reranked_response(
            [
                reranked_result(hybrid_rank=2, final_rank=1, raw_score=2.0),
                reranked_result(hybrid_rank=2, final_rank=2, raw_score=1.0),
            ]
        )
    with pytest.raises(ValidationError, match="input candidate count"):
        reranked_response(
            [reranked_result(hybrid_rank=4, final_rank=1, raw_score=2.0)],
            input_candidate_count=3,
        )


def test_reranked_response_enforces_server_top_k_and_hybrid_shape() -> None:
    results = [
        reranked_result(hybrid_rank=index, final_rank=index, raw_score=10 - index)
        for index in range(1, 9)
    ]

    assert len(reranked_response(results).results) == 8
    assert reranked_response([], input_candidate_count=0).results == []

    with pytest.raises(ValidationError):
        reranked_response(results, top_k=9)
    with pytest.raises(ValidationError, match="top k"):
        reranked_response(results, top_k=5)

    invalid = reranked_result(hybrid_rank=1, final_rank=1, raw_score=2.0)
    invalid = invalid.model_copy(update={"rrf_score": None})
    with pytest.raises(ValidationError, match="Hybrid RRF"):
        reranked_response([invalid])


def test_reranker_contract_rejects_sensitive_or_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        RetrievalRerankerIdentity(  # type: ignore[call-arg]
            contract_version="m2-reranker-provider-v1",
            provider="bge-reranker-local",
            model_id=BGE_RERANKER_MODEL_ID,
            revision=BGE_RERANKER_REVISION,
            max_length=8192,
            precision="float32",
            score_transform="sigmoid",
            snapshot_path="D:/private/model-cache",
        )
    with pytest.raises(ValidationError, match="extra_forbidden"):
        RerankedRetrievalResponse(  # type: ignore[call-arg]
            embedding_identity=embedding_identity(),
            fts_identity=RetrievalFtsIdentity(builder_version="m2-fts-jieba-search-v1"),
            rrf_k=60,
            reranker_identity=reranker_identity(),
            input_candidate_count=0,
            top_k=8,
            results=[],
            tenant_id=str(uuid4()),
        )


def test_reranker_settings_keep_fake_default_and_pin_real_identity() -> None:
    settings = settings_without_env()

    assert settings.reranker_backend == "fake"
    assert settings.reranker_model == BGE_RERANKER_MODEL_ID
    assert settings.reranker_revision == BGE_RERANKER_REVISION
    assert settings.reranker_max_length == 8192
    assert settings.reranker_precision == "float32"
    assert settings.reranker_batch_size == 2
    assert settings.reranker_top_k == 8
    assert settings.model_local_files_only is True

    real = settings_without_env(reranker_backend="bge")
    assert real.reranker_revision == BGE_RERANKER_REVISION

    for overrides in (
        {"reranker_backend": "bge", "reranker_model": "other/reranker"},
        {"reranker_backend": "bge", "reranker_revision": "main"},
        {"reranker_backend": "bge", "model_local_files_only": False},
        {"reranker_max_length": 4096},
    ):
        with pytest.raises(ValidationError):
            settings_without_env(**overrides)


def test_reranker_provider_error_is_retryable_and_never_leaks_raw_cause() -> None:
    error = RetrievalRerankerProviderUnavailableError()
    hostile = RuntimeError(
        "D:/private/reranker; token=secret; query passage; CUDA out of memory"
    )
    try:
        raise error from hostile
    except RetrievalRerankerProviderUnavailableError as captured:
        detail = captured.to_detail()

    assert detail.code == "PROVIDER_ERROR"
    assert detail.retryable is True
    assert detail.field is None
    rendered = detail.model_dump_json()
    for secret in ("private", "secret", "query passage", "CUDA"):
        assert secret not in rendered
