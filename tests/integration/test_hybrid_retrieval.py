from __future__ import annotations

from typing import cast

import pytest

from app.repositories.retrieval import RetrievalRepository
from app.schemas.retrieval import RetrievalRequest
from app.services.retrieval import FakeEmbeddingProvider
from app.services.retrieval.dense import DenseRetrievalService
from app.services.retrieval.hybrid import HybridRetrievalService
from app.services.retrieval.lexical import LexicalRetrievalService
from tests.integration import test_lexical_retrieval as lexical_test_support
from tests.integration.test_dense_retrieval import FixedQueryProvider
from tests.integration.test_lexical_retrieval import LexicalFixture

lexical_fixture = lexical_test_support.lexical_fixture


def test_hybrid_runs_both_real_postgresql_routes_and_keeps_authorized_union(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(LexicalFixture, request.getfixturevalue("lexical_fixture"))
    repository = RetrievalRepository(fixture.session, statement_timeout_ms=2000)
    provider = FixedQueryProvider(
        fixture_identity := FakeEmbeddingProvider().identity,
        (1.0,) + (0.0,) * 1023,
    )
    dense = DenseRetrievalService(repository, provider, candidate_count=10)
    lexical = LexicalRetrievalService(repository, candidate_count=10)
    hybrid = HybridRetrievalService(dense, lexical, rrf_k=60, candidate_count=10)

    response = hybrid.retrieve(
        fixture.reader,
        RetrievalRequest(query="亮度"),
    )

    returned_ids = {item.identity.chunk_id for item in response.results}
    assert fixture.expected_ids["denied"] not in returned_ids
    assert returned_ids == {
        fixture.expected_ids["rank_high"],
        fixture.expected_ids["rank_mid"],
        fixture.expected_ids["tie_low"],
        fixture.expected_ids["tie_high"],
        fixture.expected_ids["identifiers"],
        fixture.expected_ids["old_builder"],
    }
    assert provider.identity == fixture_identity
    assert len(provider.calls) == 1
    assert any(
        item.scores.dense is not None and item.scores.lexical is not None
        for item in response.results
    )
    assert all(item.rrf_score is not None for item in response.results)
    assert [item.rrf_score for item in response.results] == sorted(
        (item.rrf_score for item in response.results),
        reverse=True,
    )


def test_hybrid_final_count_is_applied_after_cross_route_deduplication(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(LexicalFixture, request.getfixturevalue("lexical_fixture"))
    repository = RetrievalRepository(fixture.session, statement_timeout_ms=2000)
    provider = FixedQueryProvider(
        FakeEmbeddingProvider().identity,
        (1.0,) + (0.0,) * 1023,
    )
    hybrid = HybridRetrievalService(
        DenseRetrievalService(repository, provider, candidate_count=10),
        LexicalRetrievalService(repository, candidate_count=10),
        candidate_count=3,
    )

    response = hybrid.retrieve(fixture.reader, RetrievalRequest(query="亮度"))

    assert len(response.results) == 3
    assert [item.final_rank for item in response.results] == [1, 2, 3]
