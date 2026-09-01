from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field, replace
from uuid import UUID, uuid4

import pytest

from app.repositories.retrieval import (
    ContextChunkRecord,
    ContextChunkRehydrationError,
    ContextChunkWindowRecord,
)
from app.schemas.auth import CurrentUser
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
from app.services.documents.artifacts import ArtifactTableCell
from app.services.documents.chunking.contracts import (
    ChunkOverlap,
    ChunkSourceSpan,
    ChunkTableData,
    ChunkTableRow,
)
from app.services.documents.chunking.token_counting import UnicodeMixedTokenCounter
from app.services.documents.parsers.base import SourceLocator
from app.services.retrieval.context import (
    CONTEXT_BUILDER_VERSION,
    BuiltContext,
    ContextBuilderService,
)
from app.services.retrieval.errors import (
    ContextBuildError,
    ContextDataContractError,
    ContextInputError,
)

_COUNTER = UnicodeMixedTokenCounter()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _user() -> CurrentUser:
    return CurrentUser(
        user_id=uuid4(),
        tenant_id=uuid4(),
        email="reader@context.example.com",
        display_name="Context reader",
        roles=["amazon_operator"],
        market_scopes=["DE"],
        synthetic_data=True,
    )


def _source_span(
    *,
    page_number: int = 1,
    character_start: int = 0,
    character_end: int = 10,
) -> dict[str, object]:
    return ChunkSourceSpan(
        block_id="b000001",
        start_locator=SourceLocator(page_number=page_number),
        end_locator=SourceLocator(page_number=page_number),
        character_start=character_start,
        character_end=character_end,
    ).model_dump(mode="json")


def _chunk(
    index: int,
    body_text: str,
    *,
    document_id: UUID | None = None,
    version_id: UUID | None = None,
    chunk_set_id: UUID | None = None,
    index_set_id: UUID | None = None,
    file_id: UUID | None = None,
    access_level: str = "tenant",
    overlap: ChunkOverlap | None = None,
    kind: str = "text",
    table_json: dict[str, object] | None = None,
    file_extension: str = ".pdf",
) -> ContextChunkRecord:
    return ContextChunkRecord(
        chunk_id=uuid4(),
        canonical_chunk_id=f"c{index:06d}",
        chunk_index=index,
        kind=kind,
        document_id=document_id or uuid4(),
        version_id=version_id or uuid4(),
        chunk_set_id=chunk_set_id or uuid4(),
        index_set_id=index_set_id or uuid4(),
        file_id=file_id or uuid4(),
        title="蘑菇灯安全手册",
        document_type="product_manual",
        language="zh-CN",
        market="DE",
        access_level=access_level,
        file_extension=file_extension,
        body_text=body_text,
        token_count=_COUNTER.count(body_text) + 10,
        content_sha256=_sha256(f"source:{index}:{body_text}"),
        heading_path=["安全说明"],
        page_numbers=[index],
        source_block_ids=["b000001"],
        source_spans=[_source_span(page_number=index)],
        bounding_boxes=[],
        overlap_json=(overlap.model_dump(mode="json") if overlap else None),
        table_json=table_json,
        warnings=[],
    )


def _same_generation_chunks(*bodies: str) -> list[ContextChunkRecord]:
    document_id = uuid4()
    version_id = uuid4()
    chunk_set_id = uuid4()
    index_set_id = uuid4()
    file_id = uuid4()
    return [
        _chunk(
            index,
            body,
            document_id=document_id,
            version_id=version_id,
            chunk_set_id=chunk_set_id,
            index_set_id=index_set_id,
            file_id=file_id,
        )
        for index, body in enumerate(bodies, start=1)
    ]


def _sigmoid(value: float) -> float:
    return 1 / (1 + math.exp(-value))


def _response(*anchors: ContextChunkRecord) -> RerankedRetrievalResponse:
    results: list[RerankedRetrievalResult] = []
    for rank, anchor in enumerate(anchors, start=1):
        raw_score = float(10 - rank)
        results.append(
            RerankedRetrievalResult(
                identity=RetrievalCandidateIdentity(
                    document_id=anchor.document_id,
                    version_id=anchor.version_id,
                    index_set_id=anchor.index_set_id,
                    chunk_id=anchor.chunk_id,
                ),
                document=RetrievalDocumentMetadata(
                    title=anchor.title,
                    document_type=anchor.document_type,
                    language=anchor.language,
                    market="DE",
                ),
                body_text=anchor.body_text,
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
        top_k=8,
        results=results,
    )


@dataclass(slots=True)
class FakeContextReader:
    windows: list[ContextChunkWindowRecord] = field(default_factory=list)
    failure: Exception | None = None
    calls: list[tuple[CurrentUser, RerankedRetrievalResponse, int]] = field(
        default_factory=list
    )

    def rehydrate_context_windows(
        self,
        current_user: CurrentUser,
        response: RerankedRetrievalResponse,
        *,
        neighbor_window: int,
    ) -> list[ContextChunkWindowRecord]:
        self.calls.append((current_user, response, neighbor_window))
        if self.failure is not None:
            raise self.failure
        return self.windows


def _build(
    windows: list[ContextChunkWindowRecord],
    response: RerankedRetrievalResponse,
    *,
    query: str = "蘑菇灯清洁前需要做什么？",
    max_tokens: int = 4000,
    max_segments: int = 12,
) -> tuple[BuiltContext, FakeContextReader, CurrentUser]:
    reader = FakeContextReader(windows=windows)
    user = _user()
    result = ContextBuilderService(
        reader,
        max_tokens=max_tokens,
        max_segments=max_segments,
        neighbor_window=1,
    ).build(user, RetrievalRequest(query=query), response)
    return result, reader, user


def test_builds_stable_natural_window_with_server_owned_identity_and_hashes() -> None:
    previous, anchor, next_chunk = _same_generation_chunks(
        "上一段安全背景。",
        "清洁前必须断开电源。",
        "清洁后等待完全干燥。",
    )
    anchor = _chunk(
        2,
        anchor.body_text,
        document_id=anchor.document_id,
        version_id=anchor.version_id,
        chunk_set_id=anchor.chunk_set_id,
        index_set_id=anchor.index_set_id,
        file_id=anchor.file_id,
        access_level="private",
    )
    windows = [
        ContextChunkWindowRecord(
            anchor=anchor,
            previous=previous,
            next=next_chunk,
        )
    ]
    response = _response(anchor)

    result, reader, user = _build(windows, response)
    repeated = ContextBuilderService(reader).build(
        user,
        RetrievalRequest(query="蘑菇灯清洁前需要做什么？"),
        response,
    )

    assert result == repeated
    assert result.config["builder_version"] == CONTEXT_BUILDER_VERSION
    assert reader.calls == [(user, response, 1), (user, response, 1)]
    assert result.bundle.supported is True
    assert [segment.identity.chunk_id for segment in result.bundle.segments] == [
        previous.chunk_id,
        anchor.chunk_id,
        next_chunk.chunk_id,
    ]
    assert [segment.role for segment in result.bundle.segments] == [
        "previous_neighbor",
        "anchor",
        "next_neighbor",
    ]
    assert [segment.citation_label for segment in result.bundle.segments] == [
        "[E1]",
        "[E2]",
        "[E3]",
    ]
    assert result.bundle.segments[0].neighbor_of_chunk_id == anchor.chunk_id
    assert result.bundle.segments[1].neighbor_of_chunk_id is None
    assert result.bundle.segments[1].source_type == "user_file"
    assert result.bundle.segments[2].source_type == "knowledge"
    assert result.bundle.total_tokens == sum(
        segment.token_count for segment in result.bundle.segments
    )
    assert result.sources == (previous, anchor, next_chunk)
    for value in (
        result.bundle.query_sha256,
        result.bundle.context_sha256,
        result.retrieval_snapshot_sha256,
        result.config_sha256,
        result.identity_sha256,
    ):
        assert len(value) == 64
        int(value, 16)
    rendered = result.bundle.model_dump_json()
    for forbidden in ("tenant_id", "storage_key", "owner_user_id", "sql"):
        assert forbidden not in rendered.lower()

    changed_query = ContextBuilderService(reader).build(
        user,
        RetrievalRequest(query="另一条问题"),
        response,
    )
    assert changed_query.bundle.context_id != result.bundle.context_id
    assert changed_query.bundle.query_sha256 != result.bundle.query_sha256


def test_adjacent_anchors_dominate_neighbor_roles_and_exact_text_is_deduplicated() -> (
    None
):
    first, second, duplicate_neighbor = _same_generation_chunks(
        "第一条锚点事实。",
        "第二条锚点事实。",
        "第一条锚点事实。",
    )
    response = _response(first, second)
    windows = [
        ContextChunkWindowRecord(anchor=first, previous=None, next=second),
        ContextChunkWindowRecord(
            anchor=second,
            previous=first,
            next=duplicate_neighbor,
        ),
    ]

    result, _reader, _user_record = _build(windows, response)

    assert [segment.identity.chunk_id for segment in result.bundle.segments] == [
        first.chunk_id,
        second.chunk_id,
    ]
    assert [segment.role for segment in result.bundle.segments] == [
        "anchor",
        "anchor",
    ]
    assert [segment.reranker_rank for segment in result.bundle.segments] == [1, 2]


def test_text_overlap_is_trimmed_only_when_the_previous_chunk_is_selected() -> None:
    overlap_text = "重复背景"
    previous_body = f"前段新内容 {overlap_text}"
    anchor_body = f"{overlap_text} 当前关键事实"
    previous, initial_anchor = _same_generation_chunks(previous_body, anchor_body)
    overlap = ChunkOverlap(
        previous_chunk_id=previous.canonical_chunk_id,
        token_count=_COUNTER.count(overlap_text),
        source_spans=[ChunkSourceSpan.model_validate(_source_span())],
    )
    anchor = _chunk(
        2,
        anchor_body,
        document_id=initial_anchor.document_id,
        version_id=initial_anchor.version_id,
        chunk_set_id=initial_anchor.chunk_set_id,
        index_set_id=initial_anchor.index_set_id,
        file_id=initial_anchor.file_id,
        overlap=overlap,
    )
    response = _response(anchor)

    with_neighbor, _reader, _user_record = _build(
        [ContextChunkWindowRecord(anchor=anchor, previous=previous, next=None)],
        response,
    )
    without_neighbor, _reader, _user_record = _build(
        [ContextChunkWindowRecord(anchor=anchor, previous=None, next=None)],
        response,
    )

    trimmed_anchor = with_neighbor.bundle.segments[1]
    assert trimmed_anchor.identity.chunk_id == anchor.chunk_id
    assert trimmed_anchor.text == "当前关键事实"
    assert trimmed_anchor.overlap_trimmed is True
    assert without_neighbor.bundle.segments[0].text == anchor_body
    assert without_neighbor.bundle.segments[0].overlap_trimmed is False


def _cell(row: int, value: str) -> ArtifactTableCell:
    return ArtifactTableCell(
        column_number=1,
        value=value,
        display_text=value,
        data_type="text",
        locator=SourceLocator(table_number=1, row_number=row, column_number=1),
    )


def test_table_overlap_removes_only_rows_marked_as_repeated_context() -> None:
    previous, initial_anchor = _same_generation_chunks(
        "[data row 1] 检查项",
        "placeholder",
    )
    table = ChunkTableData(
        source_kind="docx_table",
        title="安全检查表",
        row_start=2,
        row_end=2,
        rows=[
            ChunkTableRow(
                source_row_number=1,
                role="header",
                repeated_as_context=True,
                cells=[_cell(1, "检查项")],
            ),
            ChunkTableRow(
                source_row_number=2,
                role="data",
                repeated_as_context=False,
                cells=[_cell(2, "断开电源")],
            ),
        ],
    )
    body = "[header context row 1] 检查项\n[data row 2] 断开电源"
    overlap = ChunkOverlap(
        previous_chunk_id=previous.canonical_chunk_id,
        token_count=_COUNTER.count("[header context row 1] 检查项"),
        source_spans=[ChunkSourceSpan.model_validate(_source_span())],
    )
    anchor = _chunk(
        2,
        body,
        document_id=initial_anchor.document_id,
        version_id=initial_anchor.version_id,
        chunk_set_id=initial_anchor.chunk_set_id,
        index_set_id=initial_anchor.index_set_id,
        file_id=initial_anchor.file_id,
        overlap=overlap,
        kind="table",
        table_json=table.model_dump(mode="json"),
        file_extension=".docx",
    )

    result, _reader, _user_record = _build(
        [ContextChunkWindowRecord(anchor=anchor, previous=previous, next=None)],
        _response(anchor),
    )

    assert result.bundle.segments[1].text == "[data row 2] 断开电源"
    assert result.bundle.segments[1].overlap_trimmed is True


def test_anchors_take_budget_before_neighbors_and_limits_are_exact() -> None:
    anchors = [_chunk(index, "事实" * 100 + str(index)) for index in range(1, 9)]
    neighbors = [
        _chunk(
            anchor.chunk_index + 1,
            "邻居" * 100 + str(anchor.chunk_index),
            document_id=anchor.document_id,
            version_id=anchor.version_id,
            chunk_set_id=anchor.chunk_set_id,
            index_set_id=anchor.index_set_id,
            file_id=anchor.file_id,
        )
        for anchor in anchors
    ]
    windows = [
        ContextChunkWindowRecord(anchor=anchor, previous=None, next=neighbor)
        for anchor, neighbor in zip(anchors, neighbors, strict=True)
    ]

    token_limited, _reader, _user_record = _build(
        windows,
        _response(*anchors),
        max_tokens=700,
    )
    segment_limited, _reader, _user_record = _build(
        windows,
        _response(*anchors),
        max_segments=5,
    )

    assert [item.identity.chunk_id for item in token_limited.bundle.segments] == [
        anchors[0].chunk_id,
        anchors[1].chunk_id,
        anchors[2].chunk_id,
    ]
    assert token_limited.bundle.total_tokens == 603
    assert len(segment_limited.bundle.segments) == 5
    assert all(item.role == "anchor" for item in segment_limited.bundle.segments)


def test_empty_reranked_input_returns_stable_explicit_unsupported_context() -> None:
    response = _response()

    first, _reader, user = _build([], response)
    second = ContextBuilderService(FakeContextReader()).build(
        user,
        RetrievalRequest(query="蘑菇灯清洁前需要做什么？"),
        response,
    )

    assert first == second
    assert first.bundle.supported is False
    assert first.bundle.total_tokens == 0
    assert first.bundle.segments == []
    assert first.sources == ()


def test_maps_stale_input_bad_trusted_data_and_unknown_failures_safely() -> None:
    anchor = _chunk(1, "可信事实")
    response = _response(anchor)
    user = _user()
    request = RetrievalRequest(query="问题")

    with pytest.raises(ContextInputError):
        ContextBuilderService(
            FakeContextReader(failure=ContextChunkRehydrationError())
        ).build(user, request, response)
    with pytest.raises(ContextBuildError):
        ContextBuilderService(
            FakeContextReader(failure=RuntimeError("SQL secret"))
        ).build(
            user,
            request,
            response,
        )

    malformed = _chunk(1, "可信事实")
    malformed = replace(
        malformed,
        source_spans=[{"storage_key": "secret"}],
    )
    with pytest.raises(ContextDataContractError):
        ContextBuilderService(
            FakeContextReader(
                windows=[
                    ContextChunkWindowRecord(
                        anchor=malformed,
                        previous=None,
                        next=None,
                    )
                ]
            )
        ).build(user, request, _response(malformed))

    neighbor = _chunk(
        2,
        "不应返回的邻居",
        document_id=anchor.document_id,
        version_id=anchor.version_id,
        chunk_set_id=anchor.chunk_set_id,
        index_set_id=anchor.index_set_id,
        file_id=anchor.file_id,
    )
    with pytest.raises(ContextDataContractError):
        ContextBuilderService(
            FakeContextReader(
                windows=[
                    ContextChunkWindowRecord(
                        anchor=anchor,
                        previous=None,
                        next=neighbor,
                    )
                ]
            ),
            neighbor_window=0,
        ).build(user, request, response)


@pytest.mark.parametrize(
    "overrides",
    (
        {"max_tokens": 699},
        {"max_tokens": 16_001},
        {"max_segments": 4},
        {"max_segments": 13},
        {"neighbor_window": -1},
        {"neighbor_window": 2},
    ),
)
def test_builder_rejects_non_server_bounds(overrides: dict[str, int]) -> None:
    arguments = {
        "max_tokens": 4000,
        "max_segments": 12,
        "neighbor_window": 1,
    }
    arguments.update(overrides)
    with pytest.raises(ValueError):
        ContextBuilderService(
            FakeContextReader(),
            max_tokens=arguments["max_tokens"],
            max_segments=arguments["max_segments"],
            neighbor_window=arguments["neighbor_window"],
        )
