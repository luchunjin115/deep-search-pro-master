from __future__ import annotations

import math
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.errors import ApplicationError
from app.schemas.retrieval import (
    CsvRetrievalSourceLocator,
    DenseRetrievalScore,
    DocxRetrievalSourceLocator,
    LexicalRetrievalScore,
    PdfRetrievalSourceLocator,
    RetrievalCandidateFailure,
    RetrievalCandidateIdentity,
    RetrievalDocumentMetadata,
    RetrievalEmbeddingIdentity,
    RetrievalFtsIdentity,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalResult,
    RetrievalScoreBreakdown,
    XlsxRetrievalSourceLocator,
)
from app.services.retrieval.errors import (
    RetrievalDatabaseTimeoutError,
    RetrievalDatabaseUnavailableError,
    RetrievalEmbeddingIdentityMismatchError,
    RetrievalEmbeddingProviderUnavailableError,
    RetrievalInputError,
    RetrievalInternalError,
)


def candidate_identity() -> RetrievalCandidateIdentity:
    return RetrievalCandidateIdentity(
        document_id=uuid4(),
        version_id=uuid4(),
        index_set_id=uuid4(),
        chunk_id=uuid4(),
    )


def document_metadata() -> RetrievalDocumentMetadata:
    return RetrievalDocumentMetadata(
        title="蘑菇灯使用手册",
        document_type="product_manual",
        language="zh-CN",
        market="DE",
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


def fts_identity() -> RetrievalFtsIdentity:
    return RetrievalFtsIdentity(builder_version="m2-fts-raw-retrieval-v1")


def result_with_scores(
    scores: RetrievalScoreBreakdown,
    *,
    final_rank: int = 1,
    rrf_score: float | None = None,
) -> RetrievalResult:
    return RetrievalResult(
        identity=candidate_identity(),
        document=document_metadata(),
        body_text="蘑菇灯清洁前请先断开电源。",
        source_locator=PdfRetrievalSourceLocator(
            page_number=2,
            heading_path=["维护", "清洁"],
            block_number=4,
        ),
        scores=scores,
        rrf_score=rrf_score,
        final_rank=final_rank,
    )


@pytest.mark.parametrize(
    "forged_field",
    (
        "tenant_id",
        "user_id",
        "role",
        "market",
        "acl",
        "version_id",
        "index_set_id",
        "vector",
        "sql",
        "model_path",
        "candidate_count",
    ),
)
def test_retrieval_request_only_accepts_one_bounded_query(
    forged_field: str,
) -> None:
    assert RetrievalRequest(query="  德国仓蘑菇灯库存  ").query == "德国仓蘑菇灯库存"

    with pytest.raises(ValidationError, match="extra_forbidden"):
        RetrievalRequest(query="蘑菇灯", **{forged_field: "forged"})


@pytest.mark.parametrize("query", ("", "  \t\r\n  ", "查" * 2001))
def test_retrieval_request_rejects_blank_or_oversized_query(query: str) -> None:
    with pytest.raises(ValidationError):
        RetrievalRequest(query=query)


def test_retrieval_request_accepts_the_hard_maximum_after_trimming() -> None:
    request = RetrievalRequest(query=f"  {'查' * 2000}  ")

    assert len(request.query) == 2000


def test_four_document_source_locators_preserve_public_coordinates() -> None:
    locators = (
        PdfRetrievalSourceLocator(
            page_number=3,
            block_number=7,
            heading_path=["安装"],
        ),
        DocxRetrievalSourceLocator(
            page_number=2,
            paragraph_number=5,
            table_number=1,
            heading_path=["售后", "保修"],
        ),
        XlsxRetrievalSourceLocator(
            sheet_name="德国库存",
            cell_range="B2:F8",
            row_start=2,
            row_end=8,
        ),
        CsvRetrievalSourceLocator(row_start=10, row_end=20),
    )

    assert [item.source_type for item in locators] == [
        "pdf",
        "docx",
        "xlsx",
        "csv",
    ]


def test_source_locators_reject_mismatched_ranges_and_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="row_end"):
        CsvRetrievalSourceLocator(row_start=10, row_end=9)
    with pytest.raises(ValidationError, match="extra_forbidden"):
        PdfRetrievalSourceLocator(  # type: ignore[call-arg]
            page_number=1,
            storage_key="private/object.pdf",
        )


def test_score_breakdown_can_express_a_hit_from_only_one_ranking_list() -> None:
    dense_only = RetrievalScoreBreakdown(
        dense=DenseRetrievalScore(rank=1, distance=0.21, similarity=0.79)
    )
    lexical_only = RetrievalScoreBreakdown(
        lexical=LexicalRetrievalScore(rank=2, score=3.7)
    )

    assert dense_only.lexical is None
    assert lexical_only.dense is None
    assert dense_only.dense is not None and dense_only.dense.rank == 1
    assert lexical_only.lexical is not None and lexical_only.lexical.rank == 2


def test_score_breakdown_requires_one_real_hit_and_dense_measurement() -> None:
    with pytest.raises(ValidationError, match="dense or lexical"):
        RetrievalScoreBreakdown()
    with pytest.raises(ValidationError, match="distance or similarity"):
        DenseRetrievalScore(rank=1)


@pytest.mark.parametrize("rank", (0, -1))
def test_all_ranks_must_be_positive_integers(rank: int) -> None:
    with pytest.raises(ValidationError):
        DenseRetrievalScore(rank=rank, distance=0.2)
    with pytest.raises(ValidationError):
        LexicalRetrievalScore(rank=rank, score=1.0)
    with pytest.raises(ValidationError):
        result_with_scores(
            RetrievalScoreBreakdown(dense=DenseRetrievalScore(rank=1, distance=0.2)),
            final_rank=rank,
        )


@pytest.mark.parametrize("score", (math.nan, math.inf, -math.inf))
def test_all_public_scores_reject_non_finite_values(score: float) -> None:
    with pytest.raises(ValidationError):
        DenseRetrievalScore(rank=1, distance=score)
    with pytest.raises(ValidationError):
        DenseRetrievalScore(rank=1, similarity=score)
    with pytest.raises(ValidationError):
        LexicalRetrievalScore(rank=1, score=score)
    with pytest.raises(ValidationError):
        result_with_scores(
            RetrievalScoreBreakdown(dense=DenseRetrievalScore(rank=1, distance=0.2)),
            rrf_score=score,
        )


def test_dense_and_lexical_scores_only_apply_definition_based_limits() -> None:
    dense = DenseRetrievalScore(rank=1, distance=1.75, similarity=-0.75)
    lexical = LexicalRetrievalScore(rank=1, score=125.0)

    assert dense.distance == 1.75
    assert dense.similarity == -0.75
    assert lexical.score == 125.0

    with pytest.raises(ValidationError, match="less than or equal to 2"):
        DenseRetrievalScore(rank=1, distance=2.01)
    with pytest.raises(ValidationError, match="greater than or equal to -1"):
        DenseRetrievalScore(rank=1, similarity=-1.01)
    with pytest.raises(ValidationError, match="one minus"):
        DenseRetrievalScore(rank=1, distance=0.25, similarity=0.5)


def test_retrieval_response_enforces_mode_specific_score_shape() -> None:
    dense_result = result_with_scores(
        RetrievalScoreBreakdown(dense=DenseRetrievalScore(rank=1, distance=0.2))
    )
    RetrievalResponse(
        mode="dense",
        embedding_identity=embedding_identity(),
        fts_identity=fts_identity(),
        results=[dense_result],
    )

    with pytest.raises(ValidationError, match="hybrid"):
        RetrievalResponse(
            mode="hybrid",
            embedding_identity=embedding_identity(),
            fts_identity=fts_identity(),
            rrf_k=60,
            results=[dense_result],
        )


def test_hybrid_response_accepts_one_list_hits_and_requires_contiguous_final_ranks() -> (
    None
):
    dense_hit = result_with_scores(
        RetrievalScoreBreakdown(dense=DenseRetrievalScore(rank=1, distance=0.2)),
        final_rank=1,
        rrf_score=1 / 61,
    )
    lexical_hit = result_with_scores(
        RetrievalScoreBreakdown(lexical=LexicalRetrievalScore(rank=1, score=4.5)),
        final_rank=2,
        rrf_score=1 / 61,
    )
    response = RetrievalResponse(
        mode="hybrid",
        embedding_identity=embedding_identity(),
        fts_identity=fts_identity(),
        rrf_k=60,
        results=[dense_hit, lexical_hit],
    )

    assert response.results[0].scores.lexical is None
    assert response.results[1].scores.dense is None

    with pytest.raises(ValidationError, match="contiguous"):
        RetrievalResponse(
            mode="hybrid",
            embedding_identity=embedding_identity(),
            fts_identity=fts_identity(),
            rrf_k=60,
            results=[
                dense_hit,
                result_with_scores(
                    lexical_hit.scores,
                    final_rank=3,
                    rrf_score=1 / 61,
                ),
            ],
        )


def test_single_route_rank_gap_requires_a_safe_candidate_failure() -> None:
    failed_chunk_id = uuid4()
    second = result_with_scores(
        RetrievalScoreBreakdown(dense=DenseRetrievalScore(rank=2, distance=0.2)),
        final_rank=2,
    )
    response = RetrievalResponse(
        mode="dense",
        embedding_identity=embedding_identity(),
        results=[second],
        candidate_failures=[
            RetrievalCandidateFailure(
                source_mode="dense",
                rank=1,
                chunk_id=failed_chunk_id,
                stage="source_locator_mapping",
                reason="invalid_source_locator",
            )
        ],
    )

    assert response.results[0].final_rank == 2
    assert response.candidate_failures[0].chunk_id == failed_chunk_id
    rendered = response.model_dump_json()
    assert "invalid_source_locator" in rendered
    assert "start_locator" not in rendered

    with pytest.raises(ValidationError, match="account for every route rank"):
        RetrievalResponse(
            mode="dense",
            embedding_identity=embedding_identity(),
            results=[second],
        )


def test_public_retrieval_result_has_no_sensitive_internal_fields() -> None:
    response = RetrievalResponse(
        mode="hybrid",
        embedding_identity=embedding_identity(),
        fts_identity=fts_identity(),
        rrf_k=60,
        results=[
            result_with_scores(
                RetrievalScoreBreakdown(
                    dense=DenseRetrievalScore(rank=1, distance=0.2),
                    lexical=LexicalRetrievalScore(rank=2, score=3.1),
                ),
                rrf_score=(1 / 61) + (1 / 62),
            )
        ],
    )
    dumped = response.model_dump(mode="json")
    rendered = response.model_dump_json()

    forbidden_fields = {
        "tenant_id",
        "owner_user_id",
        "acl",
        "storage_key",
        "parsed_storage_key",
        "local_path",
        "model_path",
        "embedding",
        "vector",
        "sql",
        "database_error",
    }

    def nested_keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {
                key for child in value.values() for key in nested_keys(child)
            }
        if isinstance(value, list):
            return {key for child in value for key in nested_keys(child)}
        return set()

    assert forbidden_fields.isdisjoint(nested_keys(dumped))
    assert "D:/private/model-cache" not in rendered
    assert "private/storage/object-key" not in rendered


@pytest.mark.parametrize(
    ("error", "code", "retryable", "field"),
    (
        (RetrievalInputError(), "VALIDATION_ERROR", False, "query"),
        (
            RetrievalEmbeddingProviderUnavailableError(),
            "PROVIDER_ERROR",
            True,
            None,
        ),
        (RetrievalEmbeddingIdentityMismatchError(), "INTERNAL_ERROR", False, None),
        (RetrievalDatabaseUnavailableError(), "DATABASE_UNAVAILABLE", True, None),
        (RetrievalDatabaseTimeoutError(), "DATABASE_TIMEOUT", True, None),
        (RetrievalInternalError(), "INTERNAL_ERROR", True, None),
    ),
)
def test_retrieval_errors_have_typed_safe_public_details(
    error: ApplicationError,
    code: str,
    retryable: bool,
    field: str | None,
) -> None:
    hostile_cause = RuntimeError(
        "SQL=SELECT * FROM secrets; storage_key=tenant/private; "
        "D:/model-cache/snapshot; DATABASE_URL=postgresql://secret"
    )
    try:
        raise error from hostile_cause
    except ApplicationError as captured:
        detail = captured.to_detail()

    assert detail.code == code
    assert detail.retryable is retryable
    assert detail.field == field
    rendered = detail.model_dump_json()
    for secret in ("SELECT", "storage_key", "model-cache", "DATABASE_URL", "secret"):
        assert secret not in rendered
