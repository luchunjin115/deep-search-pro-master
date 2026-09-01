from __future__ import annotations

import math
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, select

from app.models.knowledge import Document, DocumentChunk, DocumentVersion
from app.repositories.retrieval import (
    ContextChunkRehydrationError,
    RetrievalRepository,
)
from app.schemas.common import MarketCode
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
    RetrievalRequest,
    RetrievalRerankerIdentity,
    RetrievalRerankerScore,
    RetrievalScoreBreakdown,
)
from app.services.retrieval.context import ContextBuilderService
from tests.integration import test_retrieval_repository_scope as scope_support
from tests.integration.test_retrieval_repository_scope import RetrievalScopeFixture

retrieval_scope_fixture = scope_support.retrieval_scope_fixture


def _sigmoid(value: float) -> float:
    return 1 / (1 + math.exp(-value))


def _response_for_chunks(
    fixture: RetrievalScopeFixture,
    chunk_ids: list[UUID],
) -> RerankedRetrievalResponse:
    results: list[RerankedRetrievalResult] = []
    for rank, chunk_id in enumerate(chunk_ids, start=1):
        chunk = fixture.session.get(DocumentChunk, chunk_id)
        assert chunk is not None
        document = fixture.session.get(Document, chunk.document_id)
        assert document is not None
        raw_score = float(10 - rank)
        results.append(
            RerankedRetrievalResult(
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
                        rank=rank,
                        distance=0.2,
                        similarity=0.8,
                    ),
                    lexical=LexicalRetrievalScore(rank=rank, score=0.75),
                ),
                rrf_score=1 / (60 + rank),
                hybrid_rank=rank,
                reranker=RetrievalRerankerScore(
                    rank=rank,
                    raw_score=raw_score,
                    normalized_score=_sigmoid(raw_score),
                ),
                final_rank=rank,
            )
        )
    return RerankedRetrievalResponse(
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
        reranker_identity=RetrievalRerankerIdentity(
            contract_version="m2-reranker-provider-v1",
            provider="fake",
            model_id="fake/m2-reranker-deterministic",
            revision="m2-fake-reranker-v1",
            max_length=8192,
            precision="float32",
            score_transform="sigmoid",
        ),
        input_candidate_count=len(results),
        top_k=5,
        results=results,
    )


def _add_neighbor(
    fixture: RetrievalScopeFixture,
    anchor: DocumentChunk,
    *,
    chunk_index: int,
    body_text: str,
) -> DocumentChunk:
    digest = scope_support._sha256(
        f"neighbor:{anchor.document_index_set_id}:{chunk_index}:{body_text}"
    )
    neighbor = DocumentChunk(
        id=uuid4(),
        tenant_id=anchor.tenant_id,
        document_id=anchor.document_id,
        document_version_id=anchor.document_version_id,
        document_chunk_set_id=anchor.document_chunk_set_id,
        document_index_set_id=anchor.document_index_set_id,
        chunk_id=f"c{chunk_index:06d}",
        chunk_index=chunk_index,
        kind="text",
        body_text=body_text,
        retrieval_text=body_text,
        fts_text=body_text,
        token_count=4,
        content_sha256=digest,
        heading_path=["neighbor"],
        page_numbers=[chunk_index],
        source_block_ids=[f"b{chunk_index:06d}"],
        source_spans=[{"block_id": f"b{chunk_index:06d}"}],
        bounding_boxes=[],
        overlap_json={"neighbor": True},
        table_json=None,
        warnings=[],
        embedding=[1.0] + [0.0] * 1023,
        embedding_model="fake/m2-deterministic",
        embedding_version="m2-fake-v1",
        embedding_cache_key=f"sha256:{digest}",
        created_at=scope_support._BASE_TIME,
    )
    fixture.session.add(neighbor)
    fixture.session.flush()
    return neighbor


def test_rehydrates_anchor_and_plus_minus_one_neighbors_from_trusted_rows(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(
        RetrievalScopeFixture,
        request.getfixturevalue("retrieval_scope_fixture"),
    )
    anchor = fixture.session.get(DocumentChunk, fixture.expected["owner"])
    assert anchor is not None
    anchor.chunk_id = "c000002"
    anchor.chunk_index = 2
    fixture.session.flush()
    previous = _add_neighbor(
        fixture,
        anchor,
        chunk_index=1,
        body_text="trusted previous neighbor",
    )
    next_chunk = _add_neighbor(
        fixture,
        anchor,
        chunk_index=3,
        body_text="trusted next neighbor",
    )
    response = _response_for_chunks(fixture, [anchor.id])

    context_selects: list[str] = []

    def capture_context_selects(*args: object) -> None:
        statement = cast(str, args[2])
        if (
            statement.lstrip().upper().startswith("SELECT")
            and "document_chunks" in statement
        ):
            context_selects.append(statement)

    event.listen(
        fixture.runtime.engine,
        "before_cursor_execute",
        capture_context_selects,
    )
    try:
        windows = RetrievalRepository(fixture.session).rehydrate_context_windows(
            fixture.users["reader"],
            response,
            neighbor_window=1,
        )
    finally:
        event.remove(
            fixture.runtime.engine,
            "before_cursor_execute",
            capture_context_selects,
        )

    assert len(context_selects) == 2
    assert len(windows) == 1
    window = windows[0]
    assert window.anchor.chunk_id == anchor.id
    assert window.anchor.canonical_chunk_id == "c000002"
    assert window.anchor.chunk_set_id == anchor.document_chunk_set_id
    assert window.anchor.file_id == fixture.session.scalar(
        select(DocumentVersion.file_id).where(
            DocumentVersion.id == anchor.document_version_id
        )
    )
    assert window.anchor.access_level == "restricted"
    assert window.previous is not None
    assert window.previous.chunk_id == previous.id
    assert window.previous.chunk_index == 1
    assert window.previous.body_text == "trusted previous neighbor"
    assert window.next is not None
    assert window.next.chunk_id == next_chunk.id
    assert window.next.chunk_index == 3
    assert window.next.body_text == "trusted next neighbor"
    assert window.next.overlap_json == {"neighbor": True}


def test_neighbor_query_stays_in_the_same_active_index_generation(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(
        RetrievalScopeFixture,
        request.getfixturevalue("retrieval_scope_fixture"),
    )
    active = fixture.session.get(
        DocumentChunk,
        fixture.expected["active_index_set"],
    )
    stale = fixture.session.get(DocumentChunk, fixture.expected["old_index_set"])
    assert active is not None
    assert stale is not None
    active_neighbor = _add_neighbor(
        fixture,
        active,
        chunk_index=2,
        body_text="active generation neighbor",
    )
    _add_neighbor(
        fixture,
        stale,
        chunk_index=2,
        body_text="stale generation neighbor must never leak",
    )
    response = _response_for_chunks(fixture, [active.id])

    window = RetrievalRepository(fixture.session).rehydrate_context_windows(
        fixture.users["company_owner"],
        response,
        neighbor_window=1,
    )[0]

    assert window.previous is None
    assert window.next is not None
    assert window.next.chunk_id == active_neighbor.id
    assert window.next.body_text == "active generation neighbor"


@pytest.mark.parametrize(
    ("user_label", "chunk_label"),
    (
        ("reader", "no_acl"),
        ("reader", "cross_tenant"),
        ("company_owner", "old_version"),
        ("company_owner", "old_index_set"),
        ("company_owner", "soft_deleted_document"),
        ("company_owner", "soft_deleted_file"),
    ),
)
def test_rejects_inaccessible_stale_or_deleted_anchor_without_leaking_which_one(
    request: pytest.FixtureRequest,
    user_label: str,
    chunk_label: str,
) -> None:
    fixture = cast(
        RetrievalScopeFixture,
        request.getfixturevalue("retrieval_scope_fixture"),
    )
    response = _response_for_chunks(fixture, [fixture.expected[chunk_label]])

    with pytest.raises(ContextChunkRehydrationError) as caught:
        RetrievalRepository(fixture.session).rehydrate_context_windows(
            fixture.users[user_label],
            response,
            neighbor_window=1,
        )

    assert str(caught.value) == "reranked context source is unavailable"
    assert chunk_label not in str(caught.value)


def test_rejects_tampered_identity_body_or_document_metadata(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(
        RetrievalScopeFixture,
        request.getfixturevalue("retrieval_scope_fixture"),
    )
    response = _response_for_chunks(fixture, [fixture.expected["owner"]])
    original = response.results[0]
    tampered_results = (
        original.model_copy(
            update={
                "identity": original.identity.model_copy(update={"version_id": uuid4()})
            }
        ),
        original.model_copy(update={"body_text": "tampered body"}),
        original.model_copy(
            update={
                "document": original.document.model_copy(
                    update={"title": "tampered title"}
                )
            }
        ),
    )

    for tampered in tampered_results:
        with pytest.raises(ContextChunkRehydrationError):
            RetrievalRepository(fixture.session).rehydrate_context_windows(
                fixture.users["reader"],
                response.model_copy(update={"results": [tampered]}),
                neighbor_window=1,
            )


def test_rejects_duplicate_anchor_and_untrusted_arguments(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(
        RetrievalScopeFixture,
        request.getfixturevalue("retrieval_scope_fixture"),
    )
    response = _response_for_chunks(fixture, [fixture.expected["owner"]])
    first = response.results[0]
    duplicate = first.model_copy(
        update={
            "hybrid_rank": 2,
            "final_rank": 2,
            "reranker": RetrievalRerankerScore(
                rank=2,
                raw_score=8.0,
                normalized_score=_sigmoid(8.0),
            ),
        }
    )
    duplicate_response = response.model_copy(update={"results": [first, duplicate]})
    repository = RetrievalRepository(fixture.session)

    with pytest.raises(ContextChunkRehydrationError):
        repository.rehydrate_context_windows(
            fixture.users["reader"],
            duplicate_response,
            neighbor_window=1,
        )
    with pytest.raises(TypeError):
        repository.rehydrate_context_windows(
            {"tenant_id": fixture.users["reader"].tenant_id},  # type: ignore[arg-type]
            response,
            neighbor_window=1,
        )
    with pytest.raises(TypeError):
        repository.rehydrate_context_windows(
            fixture.users["reader"],
            {"results": []},  # type: ignore[arg-type]
            neighbor_window=1,
        )
    with pytest.raises(ValueError, match="neighbor window"):
        repository.rehydrate_context_windows(
            fixture.users["reader"],
            response,
            neighbor_window=2,
        )


def test_empty_reranked_response_needs_no_database_rows(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(
        RetrievalScopeFixture,
        request.getfixturevalue("retrieval_scope_fixture"),
    )
    response = _response_for_chunks(fixture, [])

    assert (
        RetrievalRepository(fixture.session).rehydrate_context_windows(
            fixture.users["reader"],
            response,
            neighbor_window=1,
        )
        == []
    )


def test_context_builder_consumes_the_real_authorized_postgresql_snapshot(
    request: pytest.FixtureRequest,
) -> None:
    fixture = cast(
        RetrievalScopeFixture,
        request.getfixturevalue("retrieval_scope_fixture"),
    )
    anchor = fixture.session.get(DocumentChunk, fixture.expected["owner"])
    assert anchor is not None
    anchor.body_text = "清洁蘑菇灯前必须断开电源。"
    anchor.retrieval_text = anchor.body_text
    anchor.token_count = 20
    anchor.heading_path = ["维护", "清洁"]
    anchor.page_numbers = [2]
    anchor.source_spans = [
        {
            "block_id": "b000001",
            "start_locator": {"page_number": 2, "block_number": 1},
            "end_locator": {"page_number": 2, "block_number": 1},
            "character_start": 0,
            "character_end": len(anchor.body_text),
            "bounding_boxes": [],
        }
    ]
    fixture.session.flush()
    response = _response_for_chunks(fixture, [anchor.id])

    built = ContextBuilderService(
        RetrievalRepository(fixture.session),
        neighbor_window=1,
    ).build(
        fixture.users["reader"],
        RetrievalRequest(query="清洁前要做什么？"),
        response,
    )

    assert built.bundle.supported is True
    assert len(built.bundle.segments) == 1
    assert built.bundle.segments[0].identity.chunk_id == anchor.id
    assert built.bundle.segments[0].text == anchor.body_text
    assert isinstance(
        built.bundle.segments[0].source_locator,
        PdfRetrievalSourceLocator,
    )
    assert built.bundle.segments[0].source_locator.page_number == 2
    assert built.sources[0].file_id == fixture.session.scalar(
        select(DocumentVersion.file_id).where(
            DocumentVersion.id == anchor.document_version_id
        )
    )
