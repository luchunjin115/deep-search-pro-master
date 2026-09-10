from __future__ import annotations

import hashlib
import io
from collections.abc import Sequence

import pytest

from app.services.documents.artifacts import (
    ArtifactBoundingBox,
    ArtifactHeadingHint,
    ArtifactPdfLayoutLine,
    ArtifactTableBlock,
    ArtifactTextBlock,
    build_canonical_artifact,
)
from app.services.documents.chunking import (
    ChunkingConfig,
    DocumentChunkingError,
    StructureAwareTextChunker,
    normalize_source_text,
)
from app.services.documents.parsers.base import SourceLocator
from app.services.documents.parsers.docx import DocxParser
from app.services.documents.parsers.native import adapt_native_parse_result
from app.services.documents.parsers.pdf import PdfParser
from tests.fixtures.docx_factory import make_structured_docx
from tests.fixtures.pdf_factory import make_text_pdf, make_two_column_text_pdf

_SOURCE_HASH = "1" * 64


def _artifact(
    source_type: str,
    blocks: Sequence[ArtifactTextBlock | ArtifactTableBlock],
    *,
    page_count: int | None = None,
):  # type: ignore[no-untyped-def]
    return build_canonical_artifact(
        source_type=source_type,  # type: ignore[arg-type]
        source_sha256=_SOURCE_HASH,
        parser_name="test_parser",
        parser_version="1.0",
        blocks=list(blocks),
        warnings=[],
        source_character_count=sum(
            sum(not character.isspace() for character in block.text)
            for block in blocks
            if isinstance(block, ArtifactTextBlock)
        ),
        page_count=page_count,
    )


def _docx_text(
    block_number: int,
    text: str,
    *,
    heading_path: list[str] | None = None,
    heading_level: int | None = None,
) -> ArtifactTextBlock:
    path = heading_path or []
    return ArtifactTextBlock(
        block_id=f"b{block_number:06d}",
        text=text,
        locator=SourceLocator(
            block_number=block_number,
            paragraph_number=block_number,
            heading_path=path,
        ),
        heading_level=heading_level,
        heading_path=path,
    )


def _pdf_text(
    block_number: int,
    page_number: int,
    text: str,
    *,
    heading_hints: list[ArtifactHeadingHint] | None = None,
) -> ArtifactTextBlock:
    return ArtifactTextBlock(
        block_id=f"b{block_number:06d}",
        text=text,
        locator=SourceLocator(page_number=page_number),
        heading_hints=heading_hints or [],
    )


def test_normalization_is_deterministic_and_retains_original_offsets() -> None:
    source = "  e\u0301\r\n正文 \t\r\n\r\n\r\n尾部  "

    first = normalize_source_text(source)
    second = normalize_source_text(source)

    assert first == second
    assert first.text == "é\n正文\n\n尾部"
    assert first.source_range(0, 1) == (2, 4)
    assert source[slice(*first.source_range(2, 4))] == "正文"


def test_docx_preserves_heading_list_marker_and_table_barrier() -> None:
    blocks: list[ArtifactTextBlock | ArtifactTableBlock] = [
        _docx_text(
            1,
            "操作指南",
            heading_path=["操作指南"],
            heading_level=1,
        ),
        _docx_text(2, "开始操作前请检查设备。", heading_path=["操作指南"]),
        _docx_text(3, "- 断开电源", heading_path=["操作指南"]),
        ArtifactTableBlock(
            block_id="b000004",
            source_kind="docx_table",
            locator=SourceLocator(
                block_number=4,
                table_number=1,
                heading_path=["操作指南"],
            ),
            heading_path=["操作指南"],
            rows=[],
        ),
        _docx_text(5, "表格之后的检查说明。", heading_path=["操作指南"]),
    ]

    result = StructureAwareTextChunker().chunk(_artifact("docx", blocks))

    assert result.deferred_table_block_ids == ["b000004"]
    assert len(result.chunks) == 2
    assert result.chunks[0].heading_path == ["操作指南"]
    assert "- 断开电源" in result.chunks[0].body_text
    assert result.chunks[0].source_block_ids == [
        "b000001",
        "b000002",
        "b000003",
    ]
    assert result.chunks[1].source_block_ids == ["b000005"]
    assert result.chunks[1].overlap is None


def test_pdf_repeated_headers_and_footers_are_audited_not_indexed() -> None:
    blocks = [
        _pdf_text(
            page,
            page,
            f"公司内部资料\n第{page}页正文内容\n仅供内部使用",
        )
        for page in range(1, 4)
    ]

    result = StructureAwareTextChunker().chunk(_artifact("pdf", blocks, page_count=3))

    assert [span.reason for span in result.excluded_spans] == [
        "repeated_header",
        "repeated_footer",
        "repeated_header",
        "repeated_footer",
        "repeated_header",
        "repeated_footer",
    ]
    assert all("公司内部资料" not in chunk.body_text for chunk in result.chunks)
    assert all("仅供内部使用" not in chunk.body_text for chunk in result.chunks)
    assert result.chunks[0].page_numbers == [1, 2, 3]


def test_pdf_exact_heading_hint_creates_path_and_cross_page_chunk() -> None:
    heading = ArtifactHeadingHint(
        text="安全规范",
        level=1,
        locator=SourceLocator(page_number=1),
    )
    artifact = _artifact(
        "pdf",
        [
            _pdf_text(1, 1, "安全规范\n第一页内容", heading_hints=[heading]),
            _pdf_text(2, 2, "第二页延续内容"),
        ],
        page_count=2,
    )

    result = StructureAwareTextChunker().chunk(artifact)

    assert len(result.chunks) == 1
    assert result.chunks[0].heading_path == ["安全规范"]
    assert result.chunks[0].page_numbers == [1, 2]
    assert "安全规范" in result.chunks[0].retrieval_text
    assert "安全规范" not in result.chunks[0].body_text
    heading_source = result.chunks[0].heading_sources[0]
    heading_exclusion = next(
        span for span in result.excluded_spans if span.reason == "heading_metadata"
    )
    assert heading_source.heading_path_index == 0
    assert heading_source.heading_text == "安全规范"
    assert heading_source.source_text == "安全规范"
    assert heading_source.source_span.block_id == "b000001"
    assert heading_source.source_span.character_start == 0
    assert heading_source.source_span.character_end == len("安全规范")
    assert heading_exclusion.block_id == "b000001"
    assert heading_exclusion.character_start == 0
    assert heading_exclusion.character_end == len("安全规范")


def test_pdf_numbered_heading_becomes_metadata_not_chunk_body() -> None:
    heading = ArtifactHeadingHint(
        text="IOSS适用范围",
        level=1,
        locator=SourceLocator(page_number=1),
    )
    artifact = _artifact(
        "pdf",
        [
            _pdf_text(
                1,
                1,
                "2. IOSS适用范围\n该特殊安排适用于不超过150欧元的进口货物。",
                heading_hints=[heading],
            )
        ],
        page_count=1,
    )

    result = StructureAwareTextChunker().chunk(artifact)

    assert len(result.chunks) == 1
    assert result.chunks[0].heading_path == ["IOSS适用范围"]
    assert result.chunks[0].body_text == "该特殊安排适用于不超过150欧元的进口货物。"
    assert result.chunks[0].retrieval_text == (
        "IOSS适用范围\n\n该特殊安排适用于不超过150欧元的进口货物。"
    )


def test_pdf_heading_metadata_keeps_parent_child_path_without_title_only_chunk() -> (
    None
):
    artifact = _artifact(
        "pdf",
        [
            _pdf_text(
                1,
                1,
                "VAT\n2. IOSS适用范围\n申报人必须保存相关交易记录。",
                heading_hints=[
                    ArtifactHeadingHint(
                        text="VAT",
                        level=1,
                        locator=SourceLocator(page_number=1),
                    ),
                    ArtifactHeadingHint(
                        text="IOSS适用范围",
                        level=2,
                        locator=SourceLocator(page_number=1),
                    ),
                ],
            )
        ],
        page_count=1,
    )

    result = StructureAwareTextChunker().chunk(artifact)

    assert len(result.chunks) == 1
    assert result.chunks[0].heading_path == ["VAT", "IOSS适用范围"]
    assert result.chunks[0].body_text == "申报人必须保存相关交易记录。"
    assert result.chunks[0].retrieval_text == (
        "VAT > IOSS适用范围\n\n申报人必须保存相关交易记录。"
    )


def test_pdf_masthead_consumed_by_main_title_keeps_exact_noise_audit() -> None:
    source = (
        "CONSUMER PROTECTION\n"
        "THE NEW GENERAL PRODUCT\n"
        "SAFETY REGULATION\n"
        "The regulation protects consumers."
    )
    line_texts = [
        "CONSUMER PROTECTION",
        "THE NEW GENERAL PRODUCT",
        "SAFETY REGULATION",
        "The regulation protects consumers.",
    ]
    starts = [source.index(text) for text in line_texts]
    boxes = [
        ArtifactBoundingBox(
            page_number=1,
            left=40,
            top=10 + index * 10,
            right=300,
            bottom=20 + index * 10,
            page_width=600,
            page_height=800,
        )
        for index in range(4)
    ]
    block = ArtifactTextBlock(
        block_id="b000001",
        text=source,
        locator=SourceLocator(page_number=1),
        pdf_layout_lines=[
            ArtifactPdfLayoutLine(
                line_number=index + 1,
                text=text,
                character_start=starts[index],
                character_end=starts[index] + len(text),
                locator=SourceLocator(page_number=1),
                bounding_box=boxes[index],
            )
            for index, text in enumerate(line_texts)
        ],
        heading_hints=[
            ArtifactHeadingHint(
                text=text,
                level=1 if index == 0 else 3,
                locator=SourceLocator(page_number=1),
                layout_line_number=index + 1,
                bounding_box=boxes[index],
            )
            for index, text in enumerate(line_texts[:3])
        ],
    )
    artifact = _artifact("pdf", [block], page_count=1)

    result = StructureAwareTextChunker().chunk(artifact)

    assert result.chunks[0].heading_path == [
        "THE NEW GENERAL PRODUCT SAFETY REGULATION"
    ]
    assert result.chunks[0].body_text == "The regulation protects consumers."
    masthead = next(span for span in result.excluded_spans if span.reason == "noise")
    assert masthead.text == "CONSUMER PROTECTION"
    assert masthead.character_start == 0
    assert masthead.character_end == len("CONSUMER PROTECTION")


def test_pdf_heading_hint_inside_prose_is_not_promoted_to_metadata() -> None:
    artifact = _artifact(
        "pdf",
        [
            _pdf_text(
                1,
                1,
                "本文讨论IOSS适用范围的变化。",
                heading_hints=[
                    ArtifactHeadingHint(
                        text="IOSS适用范围",
                        level=1,
                        locator=SourceLocator(page_number=1),
                    )
                ],
            )
        ],
        page_count=1,
    )

    result = StructureAwareTextChunker().chunk(artifact)

    assert len(result.chunks) == 1
    assert result.chunks[0].heading_path == []
    assert result.chunks[0].body_text == "本文讨论IOSS适用范围的变化。"


def test_pdf_inline_numbered_heading_keeps_body_and_exact_source_range() -> None:
    source = "2. IOSS适用范围 该特殊安排适用于不超过150欧元的进口货物。"
    artifact = _artifact(
        "pdf",
        [
            _pdf_text(
                1,
                1,
                source,
                heading_hints=[
                    ArtifactHeadingHint(
                        text="IOSS适用范围",
                        level=1,
                        locator=SourceLocator(page_number=1),
                    )
                ],
            )
        ],
        page_count=1,
    )

    result = StructureAwareTextChunker().chunk(artifact)

    assert len(result.chunks) == 1
    chunk = result.chunks[0]
    assert chunk.heading_path == ["IOSS适用范围"]
    assert chunk.body_text == "该特殊安排适用于不超过150欧元的进口货物。"
    assert chunk.source_spans[0].character_start == source.index("该")
    assert chunk.source_spans[0].character_end == len(source)
    assert len(chunk.heading_sources) == 1
    assert chunk.heading_sources[0].heading_text == "IOSS适用范围"
    assert chunk.heading_sources[0].source_text == "2. IOSS适用范围"
    assert chunk.heading_sources[0].source_span.character_start == 0
    assert chunk.heading_sources[0].source_span.character_end == source.index(" 该")


def test_pdf_two_column_body_uses_heading_from_its_own_physical_column() -> None:
    source = make_two_column_text_pdf()
    parsed = PdfParser().parse(io.BytesIO(source))
    artifact = adapt_native_parse_result(
        parsed,
        source_sha256=hashlib.sha256(source).hexdigest(),
    )

    first = StructureAwareTextChunker().chunk(artifact)
    second = StructureAwareTextChunker().chunk(artifact)

    by_body = {chunk.body_text: chunk for chunk in first.chunks}
    assert by_body["Units sold: 139"].heading_path == [
        "Two Column Brief",
        "Left Sales",
    ]
    assert by_body["Daily budget: 18 EUR"].heading_path == [
        "Two Column Brief",
        "Right Actions",
    ]
    assert all(
        heading not in chunk.body_text
        for chunk in first.chunks
        for heading in ("Two Column Brief", "Left Sales", "Right Actions")
    )
    assert first == second


def test_long_paragraph_uses_hard_limit_and_auditable_same_section_overlap() -> None:
    text = "安全说明必须逐项确认。" * 500
    artifact = _artifact(
        "docx",
        [
            _docx_text(
                1,
                "安全规范",
                heading_path=["安全规范"],
                heading_level=1,
            ),
            _docx_text(2, text, heading_path=["安全规范"]),
        ],
    )
    config = ChunkingConfig(target_tokens=400, max_tokens=450, overlap_tokens=80)

    result = StructureAwareTextChunker(config=config).chunk(artifact)

    assert len(result.chunks) > 2
    assert all(chunk.token_count <= 450 for chunk in result.chunks)
    assert all(chunk.heading_path == ["安全规范"] for chunk in result.chunks)
    for previous, current in zip(result.chunks, result.chunks[1:]):
        assert current.overlap is not None
        assert current.overlap.previous_chunk_id == previous.chunk_id
        assert current.overlap.token_count <= 80
        assert current.source_spans[0].character_start is not None
        assert current.source_spans[0].character_end is not None


def test_same_input_is_byte_stable_and_other_sources_are_rejected() -> None:
    artifact = _artifact("docx", [_docx_text(1, "稳定生成同一份结果。")])
    chunker = StructureAwareTextChunker()

    first = chunker.chunk(artifact)
    second = chunker.chunk(artifact)

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()

    unsupported = _artifact(
        "csv",
        [
            ArtifactTableBlock(
                block_id="b000001",
                source_kind="csv",
                locator=SourceLocator(),
                encoding="utf-8",
                delimiter=",",
                rows=[],
            )
        ],
    )
    with pytest.raises(DocumentChunkingError, match="PDF/DOCX"):
        chunker.chunk(unsupported)


def test_different_heading_paths_never_merge_and_blank_blocks_are_audited() -> None:
    artifact = _artifact(
        "docx",
        [
            _docx_text(1, "第一章", heading_path=["第一章"], heading_level=1),
            _docx_text(2, "第一章正文。", heading_path=["第一章"]),
            _docx_text(3, "   ", heading_path=["第一章"]),
            _docx_text(4, "第二章", heading_path=["第二章"], heading_level=1),
            _docx_text(5, "第二章正文。", heading_path=["第二章"]),
        ],
    )

    result = StructureAwareTextChunker().chunk(artifact)

    assert [chunk.heading_path for chunk in result.chunks] == [
        ["第一章"],
        ["第二章"],
    ]
    assert "第二章正文" not in result.chunks[0].body_text
    assert "第一章正文" not in result.chunks[1].body_text
    assert [(span.block_id, span.reason) for span in result.excluded_spans] == [
        ("b000003", "blank")
    ]


@pytest.mark.parametrize(
    ("source", "parser"),
    (
        (make_text_pdf(include_empty_page=True), PdfParser()),
        (make_structured_docx(), DocxParser()),
    ),
    ids=("native-pdf", "native-docx"),
)
def test_native_parser_artifacts_flow_into_text_chunker(
    source: bytes, parser: object
) -> None:
    parsed = parser.parse(io.BytesIO(source))  # type: ignore[attr-defined]
    artifact = adapt_native_parse_result(
        parsed,
        source_sha256=hashlib.sha256(source).hexdigest(),
    )

    result = StructureAwareTextChunker().chunk(artifact)

    assert result.chunks
    assert all(chunk.source_spans for chunk in result.chunks)
    assert all(chunk.token_count <= 700 for chunk in result.chunks)
    assert result == StructureAwareTextChunker().chunk(artifact)
