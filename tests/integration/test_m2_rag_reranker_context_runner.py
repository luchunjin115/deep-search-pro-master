from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import timedelta
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy import delete, select, update

from app.core.config import Settings
from app.evals.rag_runner import _chunk_formal_baseline, _cleanup_chunk_evaluation
from app.evals.reranker_context_corpus import ensure_m2_reranker_context_corpus
from app.evals.reranker_context_runner import (
    build_m2_database_probe_context,
    rerank_m2_database_probe_candidates,
    run_m2_reranker_context_database_probe,
)
from app.models.knowledge import (
    Document,
    DocumentAcl,
    DocumentChunk,
    DocumentIndexSet,
    DocumentVersion,
)
from app.repositories.retrieval import RetrievalRepository
from app.schemas.common import MarketCode
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
    DenseRetrievalService,
    EmbeddingIdentity,
    FakeEmbeddingProvider,
    FakeRerankerProvider,
    HybridRetrievalService,
    LexicalRetrievalService,
)
from app.services.retrieval.errors import ContextInputError
from tests.integration import test_m2_rag_retrieval_runner as runner_support
from tests.integration import test_retrieval_repository_scope as scope_support
from tests.integration.test_retrieval_repository_scope import RetrievalScopeFixture

retrieval_scope_fixture = scope_support.retrieval_scope_fixture
retrieval_runner_settings = runner_support.retrieval_runner_settings


def _hybrid_for_chunk(
    fixture: RetrievalScopeFixture,
    chunk_id: UUID,
) -> RetrievalResponse:
    chunk = fixture.session.get(DocumentChunk, chunk_id)
    assert chunk is not None
    document = fixture.session.get(Document, chunk.document_id)
    assert document is not None
    return RetrievalResponse(
        mode="hybrid",
        embedding_identity=RetrievalEmbeddingIdentity(
            contract_version="m2-embedding-provider-v1",
            provider="fake",
            model_id="fake/m2-deterministic",
            revision="m2-fake-v1",
            pooling="sha256-shake-v1",
            max_length=8192,
            normalize=True,
            precision="float32",
            dimensions=1024,
        ),
        fts_identity=RetrievalFtsIdentity(builder_version="m2-fts-jieba-search-v1"),
        rrf_k=60,
        results=[
            RetrievalResult(
                identity=RetrievalCandidateIdentity(
                    document_id=chunk.document_id,
                    version_id=chunk.document_version_id,
                    index_set_id=chunk.document_index_set_id,
                    chunk_id=chunk.id,
                ),
                document=RetrievalDocumentMetadata(
                    title=document.title,
                    document_type=document.document_type,
                    language=document.language,
                    market=cast(MarketCode | None, document.market),
                ),
                body_text=chunk.body_text,
                source_locator=PdfRetrievalSourceLocator(page_number=1),
                scores=RetrievalScoreBreakdown(
                    dense=DenseRetrievalScore(
                        rank=1,
                        distance=0.2,
                        similarity=0.8,
                    ),
                    lexical=LexicalRetrievalScore(rank=1, score=0.75),
                ),
                rrf_score=2 / 61,
                final_rank=1,
            )
        ],
    )


def _tenant_chunk_ids(fixture: RetrievalScopeFixture) -> tuple[UUID, ...]:
    return tuple(
        fixture.session.scalars(
            select(DocumentChunk.id)
            .where(DocumentChunk.tenant_id == fixture.users["reader"].tenant_id)
            .order_by(DocumentChunk.id)
        )
    )


def test_real_routes_fake_reranker_and_context_reuse_one_unchanged_chunk_snapshot(
    retrieval_scope_fixture: RetrievalScopeFixture,
) -> None:
    fixture = retrieval_scope_fixture
    user = fixture.users["reader"]
    request = RetrievalRequest(query="owner candidate content")
    embedding_provider = FakeEmbeddingProvider()
    embedding_identity = asdict(embedding_provider.identity)
    embedding_identity_sha256 = hashlib.sha256(
        json.dumps(
            embedding_identity,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    for index_set in fixture.session.scalars(
        select(DocumentIndexSet)
        .join(
            DocumentVersion,
            DocumentVersion.active_index_set_id == DocumentIndexSet.id,
        )
        .where(
            DocumentIndexSet.tenant_id == user.tenant_id,
            DocumentIndexSet.status == "ready",
        )
    ):
        index_set.embedding_identity_json = embedding_identity
        index_set.embedding_identity_sha256 = embedding_identity_sha256
    for chunk in fixture.session.scalars(
        select(DocumentChunk).where(DocumentChunk.tenant_id == user.tenant_id)
    ):
        chunk.source_spans = [
            {
                "block_id": "b000001",
                "start_locator": {"page_number": 1, "block_number": 1},
                "end_locator": {"page_number": 1, "block_number": 1},
                "character_start": 0,
                "character_end": len(chunk.body_text),
                "bounding_boxes": [],
            }
        ]
    fixture.session.flush()
    repository = RetrievalRepository(fixture.session, statement_timeout_ms=2000)
    dense = DenseRetrievalService(
        repository,
        embedding_provider,
        candidate_count=10,
    )
    lexical = LexicalRetrievalService(repository, candidate_count=10)
    hybrid = HybridRetrievalService(
        dense,
        lexical,
        rrf_k=60,
        candidate_count=20,
    )
    before_chunk_ids = _tenant_chunk_ids(fixture)

    result = run_m2_reranker_context_database_probe(
        current_user=user,
        request=request,
        hybrid_route=hybrid,
        context_reader=repository,
        reranker_provider=FakeRerankerProvider(),
        top_k=5,
        neighbor_window=0,
        max_tokens=2000,
        logical_document_ids={},
        evidence_ids_by_chunk={},
    )

    assert result.hybrid_response.mode == "hybrid"
    assert result.hybrid_response.rrf_k == 60
    assert 0 < len(result.hybrid_candidate_ids) <= 20
    assert all(
        score.rank <= 10
        for candidate in result.hybrid_response.results
        for score in (candidate.scores.dense, candidate.scores.lexical)
        if score is not None
    )
    assert result.reranked_response.input_candidate_count == len(
        result.hybrid_candidate_ids
    )
    assert set(result.reranked_candidate_ids) <= set(result.hybrid_candidate_ids)
    assert result.built_context.bundle.supported is True
    assert {UUID(segment.segment_id) for segment in result.context_metric_segments} == {
        segment.identity.chunk_id for segment in result.built_context.bundle.segments
    }
    assert _tenant_chunk_ids(fixture) == before_chunk_ids


def _revoke_acl(fixture: RetrievalScopeFixture, chunk: DocumentChunk) -> None:
    fixture.session.execute(
        delete(DocumentAcl).where(DocumentAcl.document_id == chunk.document_id)
    )


def _soft_delete_document(
    fixture: RetrievalScopeFixture,
    chunk: DocumentChunk,
) -> None:
    document = fixture.session.get(Document, chunk.document_id)
    assert document is not None
    document.deleted_at = document.created_at + timedelta(minutes=1)


def _switch_active_index(
    fixture: RetrievalScopeFixture,
    chunk: DocumentChunk,
) -> None:
    stale_chunk = fixture.session.get(
        DocumentChunk,
        fixture.expected["old_index_set"],
    )
    assert stale_chunk is not None
    version = fixture.session.get(DocumentVersion, chunk.document_version_id)
    assert version is not None
    stale_index = fixture.session.get(
        DocumentIndexSet,
        stale_chunk.document_index_set_id,
    )
    assert stale_index is not None
    version.active_index_set_id = stale_index.id


def _switch_active_version(
    fixture: RetrievalScopeFixture,
    chunk: DocumentChunk,
) -> None:
    stale_chunk = fixture.session.get(
        DocumentChunk,
        fixture.expected["old_version"],
    )
    assert stale_chunk is not None
    document = fixture.session.get(Document, chunk.document_id)
    assert document is not None
    document.active_version_id = stale_chunk.document_version_id


@pytest.mark.parametrize(
    ("user_label", "chunk_label", "mutate"),
    (
        ("reader", "role_acl", _revoke_acl),
        ("reader", "owner", _soft_delete_document),
        ("company_owner", "active_version", _switch_active_version),
        ("company_owner", "active_index_set", _switch_active_index),
        ("reader", "cross_tenant", None),
    ),
)
def test_context_rechecks_current_database_state_after_fake_reranking(
    retrieval_scope_fixture: RetrievalScopeFixture,
    user_label: str,
    chunk_label: str,
    mutate: Callable[[RetrievalScopeFixture, DocumentChunk], None] | None,
) -> None:
    fixture = retrieval_scope_fixture
    chunk = fixture.session.get(DocumentChunk, fixture.expected[chunk_label])
    assert chunk is not None
    hybrid = _hybrid_for_chunk(fixture, chunk.id)
    source_user = (
        fixture.users["other_tenant"]
        if chunk_label == "cross_tenant"
        else fixture.users[user_label]
    )
    reranked = rerank_m2_database_probe_candidates(
        current_user=source_user,
        request=RetrievalRequest(query="current authorization probe"),
        hybrid_response=hybrid,
        reranker_provider=FakeRerankerProvider(),
        top_k=5,
    )
    if mutate is not None:
        mutate(fixture, chunk)
        fixture.session.flush()

    with pytest.raises(ContextInputError):
        build_m2_database_probe_context(
            current_user=fixture.users[user_label],
            request=RetrievalRequest(query="current authorization probe"),
            reranked_response=reranked,
            context_reader=RetrievalRepository(fixture.session),
            neighbor_window=1,
            max_tokens=4000,
            logical_document_ids={},
            evidence_ids_by_chunk={},
        )


def test_context_rejects_a_tampered_reranker_source_body(
    retrieval_scope_fixture: RetrievalScopeFixture,
) -> None:
    fixture = retrieval_scope_fixture
    user = fixture.users["reader"]
    request = RetrievalRequest(query="tampered source probe")
    reranked = rerank_m2_database_probe_candidates(
        current_user=user,
        request=request,
        hybrid_response=_hybrid_for_chunk(fixture, fixture.expected["owner"]),
        reranker_provider=FakeRerankerProvider(),
        top_k=5,
    )
    original = reranked.results[0]
    tampered = reranked.model_copy(
        update={
            "results": [
                original.model_copy(update={"body_text": "tampered source body"})
            ]
        }
    )

    with pytest.raises(ContextInputError):
        build_m2_database_probe_context(
            current_user=user,
            request=request,
            reranked_response=tampered,
            context_reader=RetrievalRepository(fixture.session),
            neighbor_window=1,
            max_tokens=4000,
            logical_document_ids={},
            evidence_ids_by_chunk={},
        )


def test_database_probe_rejects_non_fake_reranker_provider(
    retrieval_scope_fixture: RetrievalScopeFixture,
) -> None:
    fixture = retrieval_scope_fixture
    fake = FakeRerankerProvider()
    identity = fake.identity
    real_identity = replace(
        identity,
        provider="bge",
        model_id="BAAI/bge-reranker-v2-m3",
        revision="953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e",
    )

    class NonFakeProvider(FakeRerankerProvider):
        @property
        def identity(self):  # type: ignore[no-untyped-def]
            return real_identity

    with pytest.raises(TypeError, match="Fake Reranker"):
        rerank_m2_database_probe_candidates(
            current_user=fixture.users["reader"],
            request=RetrievalRequest(query="fake-only probe"),
            hybrid_response=_hybrid_for_chunk(
                fixture,
                fixture.expected["owner"],
            ),
            reranker_provider=NonFakeProvider(),
            top_k=5,
        )


def test_frozen_corpus_is_built_once_then_reused_without_rechunking(
    retrieval_runner_settings: Settings,
) -> None:
    from app.db.session import create_database_runtime
    from app.services.storage import LocalStorageBackend

    settings = retrieval_runner_settings
    storage = LocalStorageBackend(settings.local_storage_root)
    runtime = create_database_runtime(settings)
    baseline = _chunk_formal_baseline(runtime, storage)
    runtime.engine.dispose()
    first = None

    class AlternateFakeEmbeddingProvider(FakeEmbeddingProvider):
        @property
        def identity(self) -> EmbeddingIdentity:
            return replace(super().identity, revision="m2-fake-v2-index-only")

    try:
        first = ensure_m2_reranker_context_corpus(
            settings,
            project_root=runner_support.ROOT,
            source_ids={"m2-v1-mushroom-lamp-manual"},
            storage=storage,
            embedding_provider=FakeEmbeddingProvider(),
        )
        second = ensure_m2_reranker_context_corpus(
            settings,
            project_root=runner_support.ROOT,
            source_ids={"m2-v1-mushroom-lamp-manual"},
            storage=storage,
            embedding_provider=FakeEmbeddingProvider(),
        )

        assert first.created is True
        assert second.created is False
        assert second.corpus_sha256 == first.corpus_sha256
        assert second.snapshot_sha256 == first.snapshot_sha256
        assert second.tenant_id == first.tenant_id
        assert second.document_ids == first.document_ids
        assert second.chunk_set_ids == first.chunk_set_ids
        assert second.index_set_ids == first.index_set_ids
        assert second.chunk_ids == first.chunk_ids
        assert first.document_count == 1
        assert first.chunk_set_count == 1
        assert first.index_set_count == 1
        assert first.chunk_count > 0

        reindexed = ensure_m2_reranker_context_corpus(
            settings,
            project_root=runner_support.ROOT,
            source_ids={"m2-v1-mushroom-lamp-manual"},
            storage=storage,
            embedding_provider=AlternateFakeEmbeddingProvider(),
        )
        reindexed_again = ensure_m2_reranker_context_corpus(
            settings,
            project_root=runner_support.ROOT,
            source_ids={"m2-v1-mushroom-lamp-manual"},
            storage=storage,
            embedding_provider=AlternateFakeEmbeddingProvider(),
        )

        assert reindexed.created is False
        assert reindexed.corpus_sha256 == first.corpus_sha256
        assert reindexed.document_ids == first.document_ids
        assert reindexed.chunk_set_ids == first.chunk_set_ids
        assert reindexed.index_sha256 != first.index_sha256
        assert reindexed.index_set_ids != first.index_set_ids
        assert reindexed.index_set_count == 2
        assert reindexed_again.index_set_ids == reindexed.index_set_ids
        assert reindexed_again.chunk_ids == reindexed.chunk_ids
    finally:
        if first is not None:
            cleanup_runtime = create_database_runtime(settings)
            try:
                with cleanup_runtime.session_factory.begin() as session:
                    session.execute(
                        update(DocumentVersion)
                        .where(DocumentVersion.tenant_id == first.tenant_id)
                        .values(active_index_set_id=None)
                    )
                    session.execute(
                        update(Document)
                        .where(Document.tenant_id == first.tenant_id)
                        .values(active_version_id=None)
                    )
                    session.execute(
                        delete(DocumentChunk).where(
                            DocumentChunk.tenant_id == first.tenant_id
                        )
                    )
                    session.execute(
                        delete(DocumentIndexSet).where(
                            DocumentIndexSet.tenant_id == first.tenant_id
                        )
                    )
                cleanup = _cleanup_chunk_evaluation(
                    runtime=cleanup_runtime,
                    storage=storage,
                    tenant_id=first.tenant_id,
                    baseline_before=baseline,
                )
                assert cleanup.evaluation_database_rows_remaining == 0
                assert cleanup.evaluation_storage_objects_remaining == 0
            finally:
                cleanup_runtime.engine.dispose()
