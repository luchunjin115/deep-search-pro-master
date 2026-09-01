from __future__ import annotations

from typing import cast

import pytest

from app.repositories.retrieval import RetrievalRepository
from app.schemas.retrieval import RetrievalRequest
from app.services.retrieval import FakeEmbeddingProvider, FakeRerankerProvider
from app.services.retrieval.dense import DenseRetrievalService
from app.services.retrieval.hybrid import HybridRetrievalService
from app.services.retrieval.lexical import LexicalRetrievalService
from app.services.retrieval.reranker import RerankerRetrievalService
from tests.integration import test_lexical_retrieval as lexical_test_support
from tests.integration.test_dense_retrieval import FixedQueryProvider
from tests.integration.test_lexical_retrieval import LexicalFixture

lexical_fixture = lexical_test_support.lexical_fixture


def test_reranker_only_returns_the_real_postgresql_authorized_hybrid_subset(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(LexicalFixture, request.getfixturevalue("lexical_fixture"))
    repository = RetrievalRepository(fixture.session, statement_timeout_ms=2000)
    query_provider = FixedQueryProvider(
        FakeEmbeddingProvider().identity,
        (1.0,) + (0.0,) * 1023,
    )
    hybrid = HybridRetrievalService(
        DenseRetrievalService(repository, query_provider, candidate_count=10),
        LexicalRetrievalService(repository, candidate_count=10),
        rrf_k=60,
        candidate_count=10,
    )
    service = RerankerRetrievalService(
        hybrid,
        FakeRerankerProvider(),
        top_k=8,
    )

    response = service.retrieve(
        fixture.reader,
        RetrievalRequest(query="亮度"),
    )

    returned_ids = {item.identity.chunk_id for item in response.results}
    authorized_hybrid_ids = {
        fixture.expected_ids["rank_high"],
        fixture.expected_ids["rank_mid"],
        fixture.expected_ids["tie_low"],
        fixture.expected_ids["tie_high"],
        fixture.expected_ids["identifiers"],
        fixture.expected_ids["old_builder"],
    }
    assert fixture.expected_ids["denied"] not in returned_ids
    assert returned_ids == authorized_hybrid_ids
    assert response.input_candidate_count == len(authorized_hybrid_ids)
    assert all(item.rrf_score is not None for item in response.results)
    assert all(item.scores.dense is not None for item in response.results)
    assert [item.final_rank for item in response.results] == list(
        range(1, len(response.results) + 1)
    )
