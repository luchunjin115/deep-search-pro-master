from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, replace
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.core.errors import EmbeddingProviderError
from app.repositories.retrieval import DenseCandidateRecord
from app.schemas.auth import CurrentUser
from app.schemas.retrieval import RetrievalRequest
from app.services.retrieval import (
    EmbeddingBatch,
    EmbeddingIdentity,
    EmbeddingPurpose,
    FakeEmbeddingProvider,
    RetrievalDatabaseTimeoutError,
    RetrievalDatabaseUnavailableError,
    RetrievalEmbeddingIdentityMismatchError,
    RetrievalEmbeddingProviderUnavailableError,
    RetrievalInputError,
)
from app.services.retrieval.dense import DenseRetrievalService

_USER = CurrentUser(
    user_id=UUID("11111111-1111-4111-8111-111111111111"),
    tenant_id=UUID("22222222-2222-4222-8222-222222222222"),
    email="dense-reader@example.com",
    display_name="Dense Reader",
    roles=["amazon_operator"],
    market_scopes=["DE"],
    synthetic_data=True,
)


class RecordingProvider:
    def __init__(self) -> None:
        self._identity = FakeEmbeddingProvider().identity
        self.calls: list[tuple[tuple[str, ...], EmbeddingPurpose]] = []

    @property
    def identity(self) -> EmbeddingIdentity:
        return self._identity

    def embed(
        self,
        texts: Sequence[str],
        *,
        purpose: EmbeddingPurpose,
    ) -> EmbeddingBatch:
        self.calls.append((tuple(texts), purpose))
        return EmbeddingBatch(
            vectors=((1.0,) + (0.0,) * 1023,),
            cache_keys=("sha256:" + "a" * 64,),
            purpose=purpose,
            identity=self.identity,
            effective_batch_size=1,
        )


class FailingProvider(RecordingProvider):
    def embed(
        self,
        texts: Sequence[str],
        *,
        purpose: EmbeddingPurpose,
    ) -> EmbeddingBatch:
        raise EmbeddingProviderError


class StubRepository:
    def __init__(
        self,
        identity: EmbeddingIdentity,
        *,
        candidates: list[DenseCandidateRecord] | None = None,
        identities: list[dict[str, object]] | None = None,
        identity_error: Exception | None = None,
        search_error: Exception | None = None,
    ) -> None:
        self._identity = identity
        self._candidates = candidates or []
        self._identities = identities
        self._identity_error = identity_error
        self._search_error = search_error
        self.search_calls: list[tuple[tuple[float, ...], EmbeddingIdentity, int]] = []

    def list_authorized_embedding_identities(
        self,
        current_user: CurrentUser,
    ) -> list[dict[str, object]]:
        assert current_user is _USER
        if self._identity_error is not None:
            raise self._identity_error
        if self._identities is not None:
            return self._identities
        return [asdict(self._identity)]

    def search_dense(
        self,
        current_user: CurrentUser,
        *,
        query_vector: tuple[float, ...],
        embedding_identity: EmbeddingIdentity,
        limit: int,
    ) -> list[DenseCandidateRecord]:
        assert current_user is _USER
        self.search_calls.append((query_vector, embedding_identity, limit))
        if self._search_error is not None:
            raise self._search_error
        return self._candidates


def _candidate(*, distance: float = 0.25) -> DenseCandidateRecord:
    return DenseCandidateRecord(
        chunk_id=UUID("33333333-3333-4333-8333-333333333333"),
        document_id=UUID("44444444-4444-4444-8444-444444444444"),
        version_id=UUID("55555555-5555-4555-8555-555555555555"),
        index_set_id=UUID("66666666-6666-4666-8666-666666666666"),
        title="合成蘑菇灯说明书",
        document_type="product_manual",
        language="zh-CN",
        market="DE",
        body_text="蘑菇灯额定功率为12W。",
        file_extension=".pdf",
        heading_path=["产品参数"],
        page_numbers=[2],
        source_spans=[
            {
                "block_id": "b000001",
                "start_locator": {
                    "page_number": 2,
                    "heading_path": ["产品参数"],
                },
                "end_locator": {
                    "page_number": 2,
                    "heading_path": ["产品参数"],
                },
            }
        ],
        table_json=None,
        distance=distance,
    )


def test_dense_service_embeds_query_and_returns_safe_ranked_response() -> None:
    provider = RecordingProvider()
    repository = StubRepository(provider.identity, candidates=[_candidate()])
    service = DenseRetrievalService(
        repository,
        provider,
        query_max_characters=2000,
        candidate_count=7,
    )

    response = service.retrieve(_USER, RetrievalRequest(query="  额定功率  "))

    assert provider.calls == [(("额定功率",), EmbeddingPurpose.QUERY)]
    assert len(repository.search_calls) == 1
    vector, identity, limit = repository.search_calls[0]
    assert vector == (1.0,) + (0.0,) * 1023
    assert identity == provider.identity
    assert limit == 7
    assert response.mode == "dense"
    assert response.embedding_identity is not None
    assert response.embedding_identity.revision == provider.identity.revision
    assert len(response.results) == 1
    result = response.results[0]
    assert result.final_rank == 1
    assert result.scores.dense is not None
    assert result.scores.dense.rank == 1
    assert result.scores.dense.distance == pytest.approx(0.25)
    assert result.scores.dense.similarity == pytest.approx(0.75)
    assert result.source_locator.source_type == "pdf"
    assert result.source_locator.page_numbers == [2]
    serialized = response.model_dump(mode="json")
    assert "tenant_id" not in str(serialized)
    assert "embedding" not in serialized["results"][0]


def test_dense_service_returns_empty_without_loading_provider_when_scope_is_empty() -> (
    None
):
    provider = RecordingProvider()
    repository = StubRepository(provider.identity, identities=[])
    service = DenseRetrievalService(repository, provider)

    response = service.retrieve(_USER, RetrievalRequest(query="亮度"))

    assert response.results == []
    assert provider.calls == []
    assert repository.search_calls == []


def test_dense_service_rejects_incompatible_active_embedding_identity() -> None:
    provider = RecordingProvider()
    incompatible = asdict(provider.identity)
    incompatible["revision"] = "other-revision"
    repository = StubRepository(provider.identity, identities=[incompatible])
    service = DenseRetrievalService(repository, provider)

    with pytest.raises(RetrievalEmbeddingIdentityMismatchError):
        service.retrieve(_USER, RetrievalRequest(query="亮度"))

    assert provider.calls == []
    assert repository.search_calls == []


def test_dense_service_maps_provider_failure_to_safe_retrieval_error() -> None:
    provider = FailingProvider()
    repository = StubRepository(provider.identity)
    service = DenseRetrievalService(repository, provider)

    with pytest.raises(RetrievalEmbeddingProviderUnavailableError) as captured:
        service.retrieve(_USER, RetrievalRequest(query="亮度"))

    assert "FlagEmbedding" not in captured.value.message


def test_dense_service_enforces_runtime_query_limit() -> None:
    provider = RecordingProvider()
    repository = StubRepository(provider.identity)
    service = DenseRetrievalService(
        repository,
        provider,
        query_max_characters=5,
    )

    with pytest.raises(RetrievalInputError):
        service.retrieve(_USER, RetrievalRequest(query="123456"))

    assert provider.calls == []


@pytest.mark.parametrize(
    ("candidate", "source_type"),
    [
        (
            replace(
                _candidate(),
                file_extension=".docx",
                page_numbers=[],
                source_spans=[
                    {
                        "block_id": "b000001",
                        "start_locator": {
                            "paragraph_number": 3,
                            "heading_path": ["操作步骤"],
                        },
                        "end_locator": {
                            "paragraph_number": 3,
                            "heading_path": ["操作步骤"],
                        },
                    }
                ],
            ),
            "docx",
        ),
        (
            replace(
                _candidate(),
                file_extension=".xlsx",
                page_numbers=[],
                source_spans=[
                    {
                        "block_id": "b000001",
                        "start_locator": {
                            "sheet_name": "报价",
                            "cell_range": "A2:D3",
                            "row_start": 2,
                            "row_end": 3,
                        },
                        "end_locator": {
                            "sheet_name": "报价",
                            "cell_range": "A2:D3",
                            "row_start": 2,
                            "row_end": 3,
                        },
                    }
                ],
                table_json={
                    "source_kind": "worksheet",
                    "sheet_name": "报价",
                    "cell_range": "A2:D3",
                    "row_start": 2,
                    "row_end": 3,
                    "rows": [],
                },
            ),
            "xlsx",
        ),
        (
            replace(
                _candidate(),
                file_extension=".csv",
                page_numbers=[],
                source_spans=[
                    {
                        "block_id": "b000001",
                        "start_locator": {"row_start": 4, "row_end": 6},
                        "end_locator": {"row_start": 4, "row_end": 6},
                    }
                ],
                table_json={
                    "source_kind": "csv",
                    "row_start": 4,
                    "row_end": 6,
                    "rows": [],
                },
            ),
            "csv",
        ),
    ],
)
def test_dense_service_maps_all_existing_public_source_types(
    candidate: DenseCandidateRecord,
    source_type: str,
) -> None:
    provider = RecordingProvider()
    repository = StubRepository(provider.identity, candidates=[candidate])
    service = DenseRetrievalService(repository, provider)

    response = service.retrieve(_USER, RetrievalRequest(query="定位"))

    assert response.results[0].source_locator.source_type == source_type


def test_dense_service_maps_search_database_failure_after_query_embedding() -> None:
    provider = RecordingProvider()
    repository = StubRepository(
        provider.identity,
        search_error=SQLAlchemyError("SELECT vector FROM private_table"),
    )
    service = DenseRetrievalService(repository, provider)

    with pytest.raises(RetrievalDatabaseUnavailableError) as captured:
        service.retrieve(_USER, RetrievalRequest(query="亮度"))

    assert provider.calls == [(("亮度",), EmbeddingPurpose.QUERY)]
    assert "private_table" not in captured.value.message


class TimeoutDriverError(Exception):
    sqlstate = "57014"


@pytest.mark.parametrize(
    ("error", "expected_error"),
    [
        (
            OperationalError("SELECT private", {}, TimeoutDriverError()),
            RetrievalDatabaseTimeoutError,
        ),
        (
            SQLAlchemyError("postgresql://secret@localhost/private"),
            RetrievalDatabaseUnavailableError,
        ),
    ],
)
def test_dense_service_maps_database_failures_without_leaking_details(
    error: Exception,
    expected_error: type[Exception],
) -> None:
    provider = RecordingProvider()
    repository = StubRepository(provider.identity, identity_error=error)
    service = DenseRetrievalService(repository, provider)

    with pytest.raises(expected_error) as captured:
        service.retrieve(_USER, RetrievalRequest(query="亮度"))

    public_error = cast(
        RetrievalDatabaseTimeoutError | RetrievalDatabaseUnavailableError,
        captured.value,
    )
    assert "private" not in public_error.message
    assert "postgresql" not in public_error.message
