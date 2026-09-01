from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.repositories.retrieval import LexicalCandidateRecord
from app.schemas.auth import CurrentUser
from app.schemas.retrieval import RetrievalRequest
from app.services.retrieval import (
    FTS_BUILDER_VERSION,
    RetrievalDatabaseTimeoutError,
    RetrievalDatabaseUnavailableError,
    RetrievalInputError,
)
from app.services.retrieval.lexical import LexicalRetrievalService

_USER = CurrentUser(
    user_id=UUID("11111111-1111-4111-8111-111111111111"),
    tenant_id=UUID("22222222-2222-4222-8222-222222222222"),
    email="lexical-reader@example.com",
    display_name="Lexical Reader",
    roles=["amazon_operator"],
    market_scopes=["DE"],
    synthetic_data=True,
)


class StubRepository:
    def __init__(
        self,
        *,
        candidates: list[LexicalCandidateRecord] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._candidates = candidates or []
        self._error = error
        self.calls: list[tuple[str, str, int]] = []

    def search_lexical(
        self,
        current_user: CurrentUser,
        *,
        lexical_tsquery: str,
        fts_builder_version: str,
        limit: int,
    ) -> list[LexicalCandidateRecord]:
        assert current_user is _USER
        self.calls.append((lexical_tsquery, fts_builder_version, limit))
        if self._error is not None:
            raise self._error
        return self._candidates


def _candidate(*, score: float = 0.5) -> LexicalCandidateRecord:
    return LexicalCandidateRecord(
        chunk_id=UUID("33333333-3333-4333-8333-333333333333"),
        document_id=UUID("44444444-4444-4444-8444-444444444444"),
        version_id=UUID("55555555-5555-4555-8555-555555555555"),
        index_set_id=UUID("66666666-6666-4666-8666-666666666666"),
        title="合成蘑菇灯说明书",
        document_type="product_manual",
        language="zh-CN",
        market="DE",
        body_text="蘑菇灯支持亮度调节。",
        file_extension=".pdf",
        heading_path=["亮度调节"],
        page_numbers=[3],
        source_spans=[
            {
                "block_id": "b000001",
                "start_locator": {
                    "page_number": 3,
                    "heading_path": ["亮度调节"],
                },
                "end_locator": {
                    "page_number": 3,
                    "heading_path": ["亮度调节"],
                },
            }
        ],
        table_json=None,
        score=score,
    )


def test_lexical_service_builds_or_tsquery_and_returns_safe_response() -> None:
    repository = StubRepository(candidates=[_candidate()])
    service = LexicalRetrievalService(
        repository,
        query_max_characters=2000,
        candidate_count=9,
    )

    response = service.retrieve(
        _USER,
        RetrievalRequest(query="  蘑菇灯 如何 调节亮度  "),
    )

    assert len(repository.calls) == 1
    lexical_tsquery, builder_version, limit = repository.calls[0]
    assert " | " in lexical_tsquery
    assert "亮度" in lexical_tsquery
    assert builder_version == FTS_BUILDER_VERSION
    assert limit == 9
    assert response.mode == "lexical"
    assert response.embedding_identity is None
    assert response.fts_identity is not None
    assert response.fts_identity.builder_version == FTS_BUILDER_VERSION
    result = response.results[0]
    assert result.final_rank == 1
    assert result.scores.lexical is not None
    assert result.scores.lexical.rank == 1
    assert result.scores.lexical.score == pytest.approx(0.5)
    assert result.scores.dense is None
    assert result.source_locator.source_type == "pdf"
    serialized = response.model_dump(mode="json")
    assert "tenant_id" not in str(serialized)
    assert "search_vector" not in str(serialized)


def test_lexical_service_returns_empty_without_embedding_or_fake_scores() -> None:
    repository = StubRepository()
    service = LexicalRetrievalService(repository)

    response = service.retrieve(_USER, RetrievalRequest(query="不存在词条"))

    assert response.mode == "lexical"
    assert response.results == []
    assert response.fts_identity is not None


def test_lexical_service_enforces_runtime_query_limit() -> None:
    repository = StubRepository()
    service = LexicalRetrievalService(repository, query_max_characters=5)

    with pytest.raises(RetrievalInputError):
        service.retrieve(_USER, RetrievalRequest(query="123456"))

    assert repository.calls == []


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
def test_lexical_service_maps_database_failures_without_leaking_details(
    error: Exception,
    expected_error: type[Exception],
) -> None:
    repository = StubRepository(error=error)
    service = LexicalRetrievalService(repository)

    with pytest.raises(expected_error) as captured:
        service.retrieve(_USER, RetrievalRequest(query="亮度"))

    public_error = captured.value
    assert "private" not in str(public_error)
    assert "postgresql" not in str(public_error)
