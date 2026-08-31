from __future__ import annotations

import hashlib
import io
from collections.abc import Sequence
from uuid import UUID

import pytest

from app.services.documents.artifacts import (
    ArtifactBoundingBox,
    ArtifactTableBlock,
    ArtifactTableCell,
    ArtifactTableRow,
    ArtifactTextBlock,
    build_canonical_artifact,
)
from app.services.documents.chunking import (
    ChunkerIdentity,
    ChunkingConfig,
    ChunkInputProvenance,
    DocumentChunkingError,
    StructureAwareDocumentChunker,
    StructureAwareTableChunker,
    UnicodeMixedTokenCounter,
    build_chunk_artifact,
)
from app.services.documents.parsers.base import SourceLocator
from app.services.documents.parsers.csv import CsvParser
from app.services.documents.parsers.docx import DocxParser
from app.services.documents.parsers.native import adapt_native_parse_result
from app.services.documents.parsers.xlsx import XlsxParser
from tests.fixtures.docx_factory import make_structured_docx
from tests.fixtures.spreadsheet_factory import (
    make_structured_xlsx,
    make_utf8_sig_semicolon_csv,
)

_SOURCE_HASH = "1" * 64


def _artifact(
    source_type: str,
    blocks: Sequence[ArtifactTextBlock | ArtifactTableBlock],
    *,
    page_count: int | None = None,
):  # type: ignore[no-untyped-def]
    character_count = 0
    for block in blocks:
        if isinstance(block, ArtifactTextBlock):
            character_count += sum(not character.isspace() for character in block.text)
            continue
        for row in block.rows:
            for cell in row.cells:
                values = (
                    (
                        cell.formula,
                        "" if cell.cached_value is None else str(cell.cached_value),
                    )
                    if cell.formula is not None
                    else (cell.display_text,)
                )
                character_count += sum(
                    not character.isspace()
                    for value in values
                    if value is not None
                    for character in value
                )
    return build_canonical_artifact(
        source_type=source_type,  # type: ignore[arg-type]
        source_sha256=_SOURCE_HASH,
        parser_name="test_parser",
        parser_version="1.0",
        blocks=list(blocks),
        warnings=[],
        source_character_count=character_count,
        page_count=page_count,
    )


def _table(
    block_number: int,
    source_kind: str,
    values: Sequence[Sequence[str]],
    *,
    header_row_number: int | None = 1,
    title: str | None = None,
    heading_path: list[str] | None = None,
    page_number: int | None = None,
    table_number: int = 1,
    sheet_state: str | None = None,
    encoding: str | None = None,
    delimiter: str | None = None,
) -> ArtifactTableBlock:
    path = heading_path or []
    sheet_name = title if source_kind == "worksheet" else None
    rows: list[ArtifactTableRow] = []
    for row_number, row_values in enumerate(values, start=1):
        cells: list[ArtifactTableCell] = []
        for column_number, value in enumerate(row_values, start=1):
            locator = _cell_locator(
                source_kind=source_kind,
                row_number=row_number,
                column_number=column_number,
                sheet_name=sheet_name,
                page_number=page_number,
                table_number=table_number,
                heading_path=path,
            )
            cells.append(
                ArtifactTableCell(
                    column_number=column_number,
                    coordinate=(
                        f"{_column_label(column_number)}{row_number}"
                        if source_kind == "worksheet"
                        else None
                    ),
                    value=value,
                    display_text=value,
                    data_type="text" if value else "empty",
                    column_header=row_number == header_row_number,
                    locator=locator,
                )
            )
        rows.append(
            ArtifactTableRow(
                row_number=row_number,
                is_empty=all(not value.strip() for value in row_values),
                locator=_row_locator(
                    source_kind=source_kind,
                    row_number=row_number,
                    sheet_name=sheet_name,
                    page_number=page_number,
                    table_number=table_number,
                    heading_path=path,
                ),
                cells=cells,
            )
        )
    locator = SourceLocator(
        page_number=page_number,
        block_number=(block_number if source_kind == "docx_table" else None),
        table_number=(
            table_number if source_kind in {"docx_table", "document_table"} else None
        ),
        heading_path=path,
        sheet_name=sheet_name,
    )
    return ArtifactTableBlock(
        block_id=f"b{block_number:06d}",
        source_kind=source_kind,  # type: ignore[arg-type]
        title=title,
        locator=locator,
        heading_path=path,
        headers=(list(values[header_row_number - 1]) if header_row_number else []),
        header_row_number=header_row_number,
        sheet_state=sheet_state,  # type: ignore[arg-type]
        encoding=encoding,  # type: ignore[arg-type]
        delimiter=delimiter,  # type: ignore[arg-type]
        rows=rows,
    )


def _cell_locator(
    *,
    source_kind: str,
    row_number: int,
    column_number: int,
    sheet_name: str | None,
    page_number: int | None,
    table_number: int,
    heading_path: list[str],
) -> SourceLocator:
    if source_kind == "worksheet":
        coordinate = f"{_column_label(column_number)}{row_number}"
        return SourceLocator(
            sheet_name=sheet_name,
            cell_range=coordinate,
            row_number=row_number,
            column_number=column_number,
        )
    if source_kind == "csv":
        return SourceLocator(row_start=row_number, row_end=row_number)
    return SourceLocator(
        page_number=page_number,
        table_number=table_number,
        row_number=row_number,
        column_number=column_number,
        heading_path=heading_path,
    )


def _row_locator(
    *,
    source_kind: str,
    row_number: int,
    sheet_name: str | None,
    page_number: int | None,
    table_number: int,
    heading_path: list[str],
) -> SourceLocator:
    if source_kind == "worksheet":
        return SourceLocator(
            sheet_name=sheet_name,
            cell_range=f"A{row_number}:A{row_number}",
            row_start=row_number,
            row_end=row_number,
        )
    if source_kind == "csv":
        return SourceLocator(row_start=row_number, row_end=row_number)
    return SourceLocator(
        page_number=page_number,
        table_number=table_number,
        heading_path=heading_path,
    )


def _column_label(number: int) -> str:
    label = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        label = chr(65 + remainder) + label
    return label


def test_docx_rows_repeat_header_and_overlap_without_becoming_new_data() -> None:
    values = [["检查项", "要求"]] + [
        [f"步骤{row}", "必须逐项确认安全要求。" * 12] for row in range(1, 9)
    ]
    block = _table(
        1,
        "docx_table",
        values,
        title="安全检查表",
        heading_path=["安全规范"],
    )
    config = ChunkingConfig(target_tokens=400, max_tokens=450, overlap_tokens=80)

    result = StructureAwareTableChunker(config=config).chunk(_artifact("docx", [block]))

    assert len(result.chunks) >= 2
    assert all(chunk.token_count <= 450 for chunk in result.chunks)
    assert result.chunks[0].table is not None
    assert result.chunks[0].table.rows[0].repeated_as_context is False
    for chunk in result.chunks[1:]:
        assert chunk.table is not None
        assert chunk.table.rows[0].role == "header"
        assert chunk.table.rows[0].repeated_as_context is True
        assert any(
            row.role == "data" and row.repeated_as_context for row in chunk.table.rows
        )
        assert chunk.overlap is not None
    original_data_rows = [
        row.source_row_number
        for chunk in result.chunks
        if chunk.table is not None
        for row in chunk.table.rows
        if row.role == "data" and not row.repeated_as_context
    ]
    assert original_data_rows == list(range(2, 10))


def test_pdf_document_table_retains_title_page_box_source_and_merged_spans() -> None:
    box = ArtifactBoundingBox(
        page_number=2,
        left=10,
        top=20,
        right=190,
        bottom=120,
        page_width=200,
        page_height=300,
    )
    block = _table(
        1,
        "document_table",
        [["成本汇总", ""], ["德国", "125"]],
        title="区域成本表",
        heading_path=["成本分析"],
        page_number=2,
    )
    first_cell = (
        block.rows[0]
        .cells[0]
        .model_copy(update={"row_span": 2, "column_span": 2, "bounding_box": box})
    )
    block = block.model_copy(
        update={
            "rows": [
                block.rows[0].model_copy(
                    update={"cells": [first_cell, block.rows[0].cells[1]]}
                ),
                block.rows[1],
            ],
            "bounding_box": box,
        }
    )
    artifact = _artifact("pdf", [block], page_count=2)

    result = StructureAwareTableChunker().chunk(artifact)

    assert len(result.chunks) == 1
    chunk = result.chunks[0]
    assert chunk.heading_path == ["成本分析"]
    assert chunk.page_numbers == [2]
    assert chunk.bounding_boxes == [box]
    assert chunk.source_block_ids == ["b000001"]
    assert chunk.table is not None
    assert chunk.table.source_kind == "document_table"
    assert chunk.table.title == "区域成本表"
    assert chunk.table.rows[0].cells[0].row_span == 2
    assert chunk.table.rows[0].cells[0].column_span == 2


def test_native_docx_tables_flow_through_canonical_document_order() -> None:
    source = make_structured_docx()
    artifact = adapt_native_parse_result(
        DocxParser().parse(io.BytesIO(source)),
        source_sha256=hashlib.sha256(source).hexdigest(),
    )

    result = StructureAwareDocumentChunker().chunk(artifact)

    table_chunks = [chunk for chunk in result.chunks if chunk.kind == "table"]
    assert len(table_chunks) == 2
    assert all(
        chunk.table and chunk.table.source_kind == "docx_table"
        for chunk in table_chunks
    )
    source_positions = {
        block.block_id: index for index, block in enumerate(artifact.blocks)
    }
    assert [
        min(source_positions[block_id] for block_id in chunk.source_block_ids)
        for chunk in result.chunks
    ] == sorted(
        min(source_positions[block_id] for block_id in chunk.source_block_ids)
        for chunk in result.chunks
    )


def test_native_xlsx_preserves_sheet_formula_ranges_and_hidden_sheet_policy() -> None:
    source = make_structured_xlsx()
    artifact = adapt_native_parse_result(
        XlsxParser().parse(io.BytesIO(source)),
        source_sha256=hashlib.sha256(source).hexdigest(),
    )

    result = StructureAwareTableChunker().chunk(artifact)

    quote_chunks = [
        chunk
        for chunk in result.chunks
        if chunk.table and chunk.table.sheet_name == "合成报价"
    ]
    assert quote_chunks
    assert all(
        chunk.table and chunk.table.sheet_state == "visible" for chunk in quote_chunks
    )
    assert quote_chunks[0].table is not None
    assert quote_chunks[0].table.cell_range == "A1:E4"
    formulas = [
        cell.formula
        for chunk in quote_chunks
        if chunk.table is not None
        for row in chunk.table.rows
        for cell in row.cells
        if cell.formula is not None
    ]
    assert formulas == ["=C2*D2", "=C4*D4"]
    assert [(item.block_id, item.reason) for item in result.skipped_tables] == [
        ("b000003", "empty_table")
    ]

    excluded = StructureAwareTableChunker(
        config=ChunkingConfig(include_hidden_sheets=False)
    ).chunk(artifact)
    assert excluded.skipped_tables[-1].block_id == "b000003"


def test_formula_cell_keeps_raw_display_type_formula_and_cached_value() -> None:
    block = _table(
        1,
        "worksheet",
        [["项目", "合计"], ["库存", "125"]],
        title="公式表",
        sheet_state="visible",
    )
    original = block.rows[1].cells[1]
    formula = original.model_copy(
        update={
            "value": 125,
            "display_text": "125",
            "data_type": "formula",
            "formula": "=C2-D2",
            "cached_value": 125,
        }
    )
    block = block.model_copy(
        update={
            "rows": [
                block.rows[0],
                block.rows[1].model_copy(
                    update={"cells": [block.rows[1].cells[0], formula]}
                ),
            ]
        }
    )

    result = StructureAwareTableChunker().chunk(_artifact("xlsx", [block]))

    assert result.chunks[0].table is not None
    retained = result.chunks[0].table.rows[1].cells[1]
    assert retained.value == 125
    assert retained.display_text == "125"
    assert retained.data_type == "formula"
    assert retained.formula == "=C2-D2"
    assert retained.cached_value == 125
    assert "=C2-D2" in result.chunks[0].retrieval_text


def test_native_csv_preserves_encoding_delimiter_header_and_row_range() -> None:
    source = make_utf8_sig_semicolon_csv()
    artifact = adapt_native_parse_result(
        CsvParser().parse(io.BytesIO(source)),
        source_sha256=hashlib.sha256(source).hexdigest(),
    )

    result = StructureAwareTableChunker().chunk(artifact)

    assert len(result.chunks) == 1
    table = result.chunks[0].table
    assert table is not None
    assert table.source_kind == "csv"
    assert table.encoding == "utf-8-sig"
    assert table.delimiter == ";"
    assert table.row_start == 1
    assert table.row_end == 4
    assert table.rows[0].role == "header"
    assert table.rows[2].cells[0].display_text == ""


def test_wide_row_uses_lossless_column_windows_and_keeps_merged_group() -> None:
    headers = [f"字段{column}" for column in range(1, 25)]
    values = [f"第{column}列完整内容" * 20 for column in range(1, 25)]
    block = _table(
        1,
        "worksheet",
        [headers, values],
        title="超宽表",
        sheet_state="visible",
    )
    merged = block.rows[1].cells[1].model_copy(update={"column_span": 3})
    block = block.model_copy(
        update={
            "rows": [
                block.rows[0],
                block.rows[1].model_copy(
                    update={
                        "cells": [
                            block.rows[1].cells[0],
                            merged,
                            *block.rows[1].cells[2:],
                        ]
                    }
                ),
            ]
        }
    )

    result = StructureAwareTableChunker().chunk(_artifact("xlsx", [block]))

    assert len(result.chunks) > 1
    assert all(chunk.token_count <= 700 for chunk in result.chunks)
    assert all(
        "table_row_split_by_columns" in chunk.warnings for chunk in result.chunks
    )
    data_columns = [
        cell.column_number
        for chunk in result.chunks
        if chunk.table is not None
        for row in chunk.table.rows
        if row.role == "data" and not row.repeated_as_context
        for cell in row.cells
    ]
    assert data_columns == list(range(1, 25))
    merged_chunk = next(
        chunk
        for chunk in result.chunks
        if chunk.table
        and any(
            cell.column_number == 2
            for row in chunk.table.rows
            if row.role == "data"
            for cell in row.cells
        )
    )
    assert merged_chunk.table is not None
    merged_columns = [
        cell.column_number
        for row in merged_chunk.table.rows
        if row.role == "data"
        for cell in row.cells
    ]
    assert {2, 3, 4}.issubset(merged_columns)


def test_unsplittable_long_cell_fails_without_truncating_source() -> None:
    value = "不可截断的完整单元格" * 100
    block = _table(
        1,
        "csv",
        [["字段"], [value]],
        encoding="utf-8",
        delimiter=",",
    )

    with pytest.raises(DocumentChunkingError, match="单元格"):
        StructureAwareTableChunker().chunk(_artifact("csv", [block]))

    assert block.rows[1].cells[0].display_text == value


def test_empty_header_only_and_hidden_tables_have_explicit_policies() -> None:
    header_only = _table(
        1,
        "worksheet",
        [["字段", "说明"]],
        title="仅表头",
        sheet_state="visible",
    )
    hidden = _table(
        2,
        "worksheet",
        [["字段"], ["隐藏事实"]],
        title="隐藏表",
        sheet_state="hidden",
    )
    empty = _table(
        3,
        "worksheet",
        [],
        header_row_number=None,
        title="空表",
        sheet_state="visible",
    )
    artifact = _artifact("xlsx", [header_only, hidden, empty])

    included = StructureAwareTableChunker().chunk(artifact)
    assert [chunk.table.title for chunk in included.chunks if chunk.table] == [
        "仅表头",
        "隐藏表",
    ]
    assert included.chunks[0].table is not None
    assert included.chunks[0].table.rows[0].repeated_as_context is False
    assert included.skipped_tables[0].reason == "empty_table"

    excluded = StructureAwareTableChunker(
        config=ChunkingConfig(include_hidden_sheets=False)
    ).chunk(artifact)
    assert [(item.block_id, item.reason) for item in excluded.skipped_tables] == [
        ("b000002", "hidden_sheet"),
        ("b000003", "empty_table"),
    ]


def test_document_merge_order_and_complete_hash_are_deterministic() -> None:
    path = ["操作指南"]
    blocks: list[ArtifactTextBlock | ArtifactTableBlock] = [
        ArtifactTextBlock(
            block_id="b000001",
            text="表格前说明。",
            locator=SourceLocator(
                block_number=1,
                paragraph_number=1,
                heading_path=path,
            ),
            heading_path=path,
        ),
        _table(
            2,
            "docx_table",
            [["字段", "值"], ["电压", "220 V"]],
            heading_path=path,
            table_number=1,
        ),
        ArtifactTextBlock(
            block_id="b000003",
            text="表格后说明。",
            locator=SourceLocator(
                block_number=3,
                paragraph_number=2,
                heading_path=path,
            ),
            heading_path=path,
        ),
    ]
    artifact = _artifact("docx", blocks)
    chunker = StructureAwareDocumentChunker()

    first = chunker.chunk(artifact)
    second = chunker.chunk(artifact)

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
    assert [chunk.source_block_ids for chunk in first.chunks] == [
        ["b000001"],
        ["b000002"],
        ["b000003"],
    ]
    counter = UnicodeMixedTokenCounter()
    identity = ChunkerIdentity(
        token_counter_name=counter.name,
        token_counter_version=counter.version,
    )
    provenance = ChunkInputProvenance(
        document_id=UUID("11111111-1111-4111-8111-111111111111"),
        document_version_id=UUID("22222222-2222-4222-8222-222222222222"),
        source_sha256=artifact.source_sha256,
        parsed_publication_sha256="2" * 64,
        selected_artifact_content_sha256=artifact.content_sha256,
    )
    first_artifact = build_chunk_artifact(
        input_provenance=provenance,
        chunker=identity,
        config=chunker.config,
        chunks=first.chunks,
        excluded_spans=first.excluded_spans,
    )
    second_artifact = build_chunk_artifact(
        input_provenance=provenance,
        chunker=identity,
        config=chunker.config,
        chunks=second.chunks,
        excluded_spans=second.excluded_spans,
    )
    assert first_artifact.output_sha256 == second_artifact.output_sha256
    assert first_artifact.model_dump_json() == second_artifact.model_dump_json()
