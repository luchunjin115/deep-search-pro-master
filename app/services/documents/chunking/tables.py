"""Deterministic structured-table chunking over Canonical Parsed Artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.common import M1Schema
from app.services.documents.artifacts import (
    ArtifactBoundingBox,
    ArtifactTableBlock,
    ArtifactTableCell,
    ArtifactTableRow,
    CanonicalParsedArtifact,
)
from app.services.documents.chunking.chunker import (
    DocumentChunkingError,
    StructureAwareTextChunker,
)
from app.services.documents.chunking.contracts import (
    ChunkingConfig,
    ChunkOverlap,
    ChunkSourceSpan,
    ChunkTableData,
    ChunkTableRow,
    DocumentChunk,
    ExcludedChunkSpan,
    SkippedTableBlock,
    build_document_chunk,
)
from app.services.documents.chunking.token_counting import (
    TokenCounter,
    UnicodeMixedTokenCounter,
)
from app.services.documents.parsers.base import SourceLocator


class TableChunkingResult(M1Schema):
    """Structured table Chunks plus explicit empty/hidden-table decisions."""

    chunks: list[DocumentChunk] = Field(max_length=1_100_000)
    skipped_tables: list[SkippedTableBlock] = Field(max_length=100_000)

    @model_validator(mode="after")
    def validate_table_result(self) -> TableChunkingResult:
        if any(chunk.kind != "table" for chunk in self.chunks):
            raise ValueError("table chunking result cannot contain text chunks")
        block_ids = [item.block_id for item in self.skipped_tables]
        if block_ids != list(dict.fromkeys(block_ids)):
            raise ValueError("skipped table block IDs must be unique and ordered")
        return self


class DocumentChunkingResult(M1Schema):
    """M2-12.3 document output ordered by Canonical Block position."""

    chunks: list[DocumentChunk] = Field(max_length=1_100_000)
    excluded_spans: list[ExcludedChunkSpan] = Field(max_length=1_100_000)
    skipped_tables: list[SkippedTableBlock] = Field(max_length=100_000)

    @model_validator(mode="after")
    def validate_chunk_sequence(self) -> DocumentChunkingResult:
        expected_ids = [f"c{index:06d}" for index in range(1, len(self.chunks) + 1)]
        if [chunk.chunk_id for chunk in self.chunks] != expected_ids or [
            chunk.chunk_index for chunk in self.chunks
        ] != list(range(1, len(self.chunks) + 1)):
            raise ValueError("document chunks must have stable sequential identities")
        return self


@dataclass(frozen=True, slots=True)
class _TableRowView:
    row_number: int
    locator: SourceLocator
    cells: tuple[ArtifactTableCell, ...]


@dataclass(frozen=True, slots=True)
class _RowSelection:
    row: _TableRowView
    role: Literal["header", "data"]
    repeated_as_context: bool


@dataclass(frozen=True, slots=True)
class _ChunkDraft:
    rows: tuple[_RowSelection, ...]
    primary_rows: tuple[ArtifactTableRow, ...]
    column_start: int
    column_end: int
    body_text: str
    retrieval_text: str
    token_count: int


class StructureAwareTableChunker:
    """Convert Canonical DOCX/PDF/XLSX/CSV tables to structured Chunks."""

    def __init__(
        self,
        *,
        config: ChunkingConfig | None = None,
        token_counter: TokenCounter | None = None,
    ) -> None:
        self._config = config or ChunkingConfig()
        self._counter = token_counter or UnicodeMixedTokenCounter()

    @property
    def config(self) -> ChunkingConfig:
        return self._config

    @property
    def token_counter(self) -> TokenCounter:
        return self._counter

    def chunk(self, artifact: CanonicalParsedArtifact) -> TableChunkingResult:
        chunks: list[DocumentChunk] = []
        skipped: list[SkippedTableBlock] = []
        for block in artifact.blocks:
            if not isinstance(block, ArtifactTableBlock):
                continue
            self._validate_source_kind(artifact, block)
            if (
                block.source_kind == "worksheet"
                and block.sheet_state in {"hidden", "veryHidden"}
                and not self._config.include_hidden_sheets
            ):
                skipped.append(
                    SkippedTableBlock(block_id=block.block_id, reason="hidden_sheet")
                )
                continue
            if _is_empty_table(block):
                skipped.append(
                    SkippedTableBlock(block_id=block.block_id, reason="empty_table")
                )
                continue
            chunks.extend(self._chunk_table(block, first_chunk_index=len(chunks) + 1))
        return TableChunkingResult(chunks=chunks, skipped_tables=skipped)

    def _validate_source_kind(
        self,
        artifact: CanonicalParsedArtifact,
        block: ArtifactTableBlock,
    ) -> None:
        allowed = {
            "pdf": {"document_table"},
            "docx": {"docx_table", "document_table"},
            "xlsx": {"worksheet"},
            "csv": {"csv"},
        }[artifact.source_type]
        if block.source_kind not in allowed:
            raise DocumentChunkingError("Canonical表格类型与源文档格式不一致")

    def _chunk_table(
        self,
        block: ArtifactTableBlock,
        *,
        first_chunk_index: int,
    ) -> list[DocumentChunk]:
        header_numbers = _header_row_numbers(block)
        header_rows = [row for row in block.rows if row.row_number in header_numbers]
        data_rows = [row for row in block.rows if row.row_number not in header_numbers]
        max_column = _max_column(block.rows)
        if max_column == 0:
            raise DocumentChunkingError("Canonical表格缺少可保留的单元格")

        chunks: list[DocumentChunk] = []
        if not data_rows:
            selections = tuple(
                _RowSelection(row=row, role="header", repeated_as_context=False)
                for row in map(_row_view, header_rows)
            )
            chunks.extend(
                self._emit_or_split_columns(
                    block,
                    selections=selections,
                    primary_rows=tuple(header_rows),
                    first_chunk_index=first_chunk_index,
                    max_column=max_column,
                    allow_overlap=False,
                )
            )
            return chunks

        cursor = 0
        previous_primary_rows: list[ArtifactTableRow] = []
        first_window = True
        while cursor < len(data_rows):
            overlap_rows = previous_primary_rows[-self._config.table_row_overlap :]
            if first_window or self._config.table_row_overlap == 0:
                overlap_rows = []
            new_rows: list[ArtifactTableRow] = []
            overlap_reduced = False

            while cursor + len(new_rows) < len(data_rows):
                candidate_new = [*new_rows, data_rows[cursor + len(new_rows)]]
                draft = self._draft(
                    block,
                    selections=self._row_selections(
                        header_rows=header_rows,
                        overlap_rows=overlap_rows,
                        new_rows=candidate_new,
                        repeat_headers=not first_window,
                    ),
                    primary_rows=tuple(
                        [*header_rows, *candidate_new]
                        if first_window
                        else candidate_new
                    ),
                    column_start=1,
                    column_end=max_column,
                )
                if draft.token_count > self._config.max_tokens:
                    if new_rows:
                        break
                    if overlap_rows:
                        overlap_rows = overlap_rows[1:]
                        overlap_reduced = True
                        continue
                    break
                new_rows = candidate_new
                if draft.token_count >= self._config.target_tokens:
                    break

            if not new_rows:
                row = data_rows[cursor]
                selections = self._row_selections(
                    header_rows=header_rows,
                    overlap_rows=[],
                    new_rows=[row],
                    repeat_headers=not first_window,
                )
                split_chunks = self._emit_or_split_columns(
                    block,
                    selections=selections,
                    primary_rows=tuple([*header_rows, row] if first_window else [row]),
                    first_chunk_index=first_chunk_index + len(chunks),
                    max_column=max_column,
                    allow_overlap=False,
                )
                chunks.extend(split_chunks)
                cursor += 1
                previous_primary_rows = [row]
                first_window = False
                continue

            selections = self._row_selections(
                header_rows=header_rows,
                overlap_rows=overlap_rows,
                new_rows=new_rows,
                repeat_headers=not first_window,
            )
            draft = self._draft(
                block,
                selections=selections,
                primary_rows=tuple(
                    [*header_rows, *new_rows] if first_window else new_rows
                ),
                column_start=1,
                column_end=max_column,
            )
            warnings = ["table_row_overlap_reduced"] if overlap_reduced else []
            chunks.append(
                self._build_chunk(
                    block,
                    draft=draft,
                    chunk_index=first_chunk_index + len(chunks),
                    previous_chunk=(chunks[-1] if chunks else None),
                    warnings=warnings,
                    allow_overlap=True,
                )
            )
            cursor += len(new_rows)
            previous_primary_rows = new_rows
            first_window = False
        return chunks

    def _row_selections(
        self,
        *,
        header_rows: list[ArtifactTableRow],
        overlap_rows: list[ArtifactTableRow],
        new_rows: list[ArtifactTableRow],
        repeat_headers: bool,
    ) -> tuple[_RowSelection, ...]:
        headers = (
            header_rows
            if self._config.repeat_table_headers or not repeat_headers
            else []
        )
        return tuple(
            [
                _RowSelection(
                    row=_row_view(row),
                    role="header",
                    repeated_as_context=repeat_headers,
                )
                for row in headers
            ]
            + [
                _RowSelection(
                    row=_row_view(row),
                    role="data",
                    repeated_as_context=True,
                )
                for row in overlap_rows
            ]
            + [
                _RowSelection(
                    row=_row_view(row),
                    role="data",
                    repeated_as_context=False,
                )
                for row in new_rows
            ]
        )

    def _emit_or_split_columns(
        self,
        block: ArtifactTableBlock,
        *,
        selections: tuple[_RowSelection, ...],
        primary_rows: tuple[ArtifactTableRow, ...],
        first_chunk_index: int,
        max_column: int,
        allow_overlap: bool,
    ) -> list[DocumentChunk]:
        full = self._draft(
            block,
            selections=selections,
            primary_rows=primary_rows,
            column_start=1,
            column_end=max_column,
        )
        if full.token_count <= self._config.max_tokens:
            return [
                self._build_chunk(
                    block,
                    draft=full,
                    chunk_index=first_chunk_index,
                    previous_chunk=None,
                    warnings=[],
                    allow_overlap=allow_overlap,
                )
            ]

        chunks: list[DocumentChunk] = []
        groups = _atomic_column_groups(selections, max_column)
        group_index = 0
        while group_index < len(groups):
            band_start, band_end = groups[group_index]
            next_index = group_index + 1
            accepted: _ChunkDraft | None = None
            while True:
                candidate = self._draft(
                    block,
                    selections=selections,
                    primary_rows=primary_rows,
                    column_start=band_start,
                    column_end=band_end,
                )
                if candidate.token_count <= self._config.max_tokens:
                    accepted = candidate
                    if candidate.token_count >= self._config.target_tokens:
                        break
                    if next_index >= len(groups):
                        break
                    band_end = groups[next_index][1]
                    next_index += 1
                    continue
                if accepted is not None:
                    next_index -= 1
                    break
                raise DocumentChunkingError("表格单元格无法在Token硬上限内完整保留")
            if accepted is None:
                raise DocumentChunkingError("表格列窗口无法安全生成")
            chunks.append(
                self._build_chunk(
                    block,
                    draft=accepted,
                    chunk_index=first_chunk_index + len(chunks),
                    previous_chunk=(chunks[-1] if chunks else None),
                    warnings=["table_row_split_by_columns"],
                    allow_overlap=False,
                )
            )
            group_index = next_index
        return chunks

    def _draft(
        self,
        block: ArtifactTableBlock,
        *,
        selections: tuple[_RowSelection, ...],
        primary_rows: tuple[ArtifactTableRow, ...],
        column_start: int,
        column_end: int,
    ) -> _ChunkDraft:
        selected = tuple(
            _RowSelection(
                row=_TableRowView(
                    row_number=item.row.row_number,
                    locator=item.row.locator,
                    cells=tuple(
                        cell
                        for cell in item.row.cells
                        if column_start <= cell.column_number <= column_end
                    ),
                ),
                role=item.role,
                repeated_as_context=item.repeated_as_context,
            )
            for item in selections
        )
        if any(not item.row.cells for item in selected):
            raise DocumentChunkingError("表格列窗口缺少完整单元格")
        body_text = "\n".join(_render_row(item) for item in selected)
        row_start = min(row.row_number for row in primary_rows)
        row_end = max(row.row_number for row in primary_rows)
        cell_range = (
            f"{_column_label(column_start)}{row_start}:"
            f"{_column_label(column_end)}{row_end}"
            if block.source_kind == "worksheet"
            else None
        )
        retrieval_text = _retrieval_text(
            block,
            body_text=body_text,
            row_start=row_start,
            row_end=row_end,
            cell_range=cell_range,
        )
        return _ChunkDraft(
            rows=selected,
            primary_rows=primary_rows,
            column_start=column_start,
            column_end=column_end,
            body_text=body_text,
            retrieval_text=retrieval_text,
            token_count=self._counter.count(retrieval_text),
        )

    def _build_chunk(
        self,
        block: ArtifactTableBlock,
        *,
        draft: _ChunkDraft,
        chunk_index: int,
        previous_chunk: DocumentChunk | None,
        warnings: list[str],
        allow_overlap: bool,
    ) -> DocumentChunk:
        table_rows = [
            ChunkTableRow(
                source_row_number=item.row.row_number,
                role=item.role,
                repeated_as_context=item.repeated_as_context,
                cells=list(item.row.cells),
            )
            for item in draft.rows
        ]
        source_spans = _source_spans(block, draft.rows)
        repeated = tuple(item for item in draft.rows if item.repeated_as_context)
        overlap = None
        if allow_overlap and previous_chunk is not None and repeated:
            overlap_text = "\n".join(_render_row(item) for item in repeated)
            overlap = ChunkOverlap(
                previous_chunk_id=previous_chunk.chunk_id,
                token_count=self._counter.count(overlap_text),
                source_spans=_source_spans(block, repeated),
            )
        row_start = min(row.row_number for row in draft.primary_rows)
        row_end = max(row.row_number for row in draft.primary_rows)
        cell_range = (
            f"{_column_label(draft.column_start)}{row_start}:"
            f"{_column_label(draft.column_end)}{row_end}"
            if block.source_kind == "worksheet"
            else None
        )
        boxes = _bounding_boxes(block, draft.rows)
        return build_document_chunk(
            chunk_id=f"c{chunk_index:06d}",
            chunk_index=chunk_index,
            kind="table",
            body_text=draft.body_text,
            retrieval_text=draft.retrieval_text,
            token_count=draft.token_count,
            heading_path=block.heading_path,
            source_block_ids=[block.block_id],
            source_spans=source_spans,
            page_numbers=_page_numbers(block, draft.rows),
            bounding_boxes=boxes,
            table=ChunkTableData(
                source_kind=block.source_kind,
                title=block.title,
                sheet_name=(block.title if block.source_kind == "worksheet" else None),
                sheet_state=block.sheet_state,
                encoding=block.encoding,
                delimiter=block.delimiter,
                cell_range=cell_range,
                row_start=row_start,
                row_end=row_end,
                rows=table_rows,
            ),
            overlap=overlap,
            warnings=warnings,
        )


class StructureAwareDocumentChunker:
    """Merge text and table Chunks in the Canonical Block order."""

    def __init__(
        self,
        *,
        config: ChunkingConfig | None = None,
        token_counter: TokenCounter | None = None,
    ) -> None:
        shared_config = config or ChunkingConfig()
        shared_counter = token_counter or UnicodeMixedTokenCounter()
        self._text = StructureAwareTextChunker(
            config=shared_config,
            token_counter=shared_counter,
        )
        self._tables = StructureAwareTableChunker(
            config=shared_config,
            token_counter=shared_counter,
        )

    @property
    def config(self) -> ChunkingConfig:
        return self._tables.config

    @property
    def token_counter(self) -> TokenCounter:
        return self._tables.token_counter

    def chunk(self, artifact: CanonicalParsedArtifact) -> DocumentChunkingResult:
        text_chunks: list[DocumentChunk] = []
        excluded: list[ExcludedChunkSpan] = []
        if artifact.source_type in {"pdf", "docx"}:
            text_result = self._text.chunk(artifact)
            text_chunks = text_result.chunks
            excluded = text_result.excluded_spans
        table_result = self._tables.chunk(artifact)
        block_order = {
            block.block_id: index for index, block in enumerate(artifact.blocks)
        }
        ordered = sorted(
            [*text_chunks, *table_result.chunks],
            key=lambda chunk: min(block_order[item] for item in chunk.source_block_ids),
        )
        renumbered = [
            _renumber_chunk(
                chunk, index=index, previous=ordered[index - 2] if index > 1 else None
            )
            for index, chunk in enumerate(ordered, start=1)
        ]
        return DocumentChunkingResult(
            chunks=renumbered,
            excluded_spans=excluded,
            skipped_tables=table_result.skipped_tables,
        )


def _renumber_chunk(
    chunk: DocumentChunk,
    *,
    index: int,
    previous: DocumentChunk | None,
) -> DocumentChunk:
    overlap = chunk.overlap
    if overlap is not None:
        if previous is None:
            raise DocumentChunkingError("切块重叠缺少前一Canonical Chunk")
        overlap = ChunkOverlap(
            previous_chunk_id=f"c{index - 1:06d}",
            token_count=overlap.token_count,
            source_spans=overlap.source_spans,
        )
    return build_document_chunk(
        chunk_id=f"c{index:06d}",
        chunk_index=index,
        kind=chunk.kind,
        body_text=chunk.body_text,
        retrieval_text=chunk.retrieval_text,
        token_count=chunk.token_count,
        heading_path=chunk.heading_path,
        source_block_ids=chunk.source_block_ids,
        source_spans=chunk.source_spans,
        page_numbers=chunk.page_numbers,
        bounding_boxes=chunk.bounding_boxes,
        table=chunk.table,
        overlap=overlap,
        warnings=chunk.warnings,
    )


def _is_empty_table(block: ArtifactTableBlock) -> bool:
    return not block.rows or not any(
        cell.display_text.strip() or cell.formula is not None
        for row in block.rows
        for cell in row.cells
    )


def _row_view(row: ArtifactTableRow) -> _TableRowView:
    return _TableRowView(
        row_number=row.row_number,
        locator=row.locator,
        cells=tuple(row.cells),
    )


def _header_row_numbers(block: ArtifactTableBlock) -> set[int]:
    numbers = {
        row.row_number
        for row in block.rows
        if any(cell.column_header for cell in row.cells)
    }
    if block.header_row_number is not None:
        numbers.add(block.header_row_number)
    return numbers


def _max_column(rows: list[ArtifactTableRow]) -> int:
    return max(
        (
            cell.column_number + cell.column_span - 1
            for row in rows
            for cell in row.cells
        ),
        default=0,
    )


def _atomic_column_groups(
    selections: tuple[_RowSelection, ...],
    max_column: int,
) -> list[tuple[int, int]]:
    cells = [cell for item in selections for cell in item.row.cells]
    groups: list[tuple[int, int]] = []
    start = 1
    while start <= max_column:
        end = start
        changed = True
        while changed:
            changed = False
            for cell in cells:
                if start <= cell.column_number <= end:
                    span_end = cell.column_number + cell.column_span - 1
                    if span_end > end:
                        end = span_end
                        changed = True
        groups.append((start, min(end, max_column)))
        start = end + 1
    return groups


def _render_row(item: _RowSelection) -> str:
    context = " context" if item.repeated_as_context else ""
    cells = " | ".join(_cell_text(cell) for cell in item.row.cells)
    # M1Schema strips outer string whitespace during full validation.  Do that
    # before hashing too, while the structured cells continue to retain every
    # trailing empty value and column position losslessly.
    return f"[{item.role}{context} row {item.row.row_number}] {cells}".rstrip()


def _cell_text(cell: ArtifactTableCell) -> str:
    value = cell.display_text
    if cell.formula is not None and cell.formula not in value:
        value = f"{value} ({cell.formula})" if value else cell.formula
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def _retrieval_text(
    block: ArtifactTableBlock,
    *,
    body_text: str,
    row_start: int,
    row_end: int,
    cell_range: str | None,
) -> str:
    metadata = [f"table_source: {block.source_kind}"]
    if block.title:
        metadata.append(f"table_title: {block.title}")
    if block.heading_path:
        metadata.append(f"heading_path: {' > '.join(block.heading_path)}")
    if block.source_kind == "worksheet":
        metadata.append(f"sheet: {block.title} ({block.sheet_state})")
    if block.source_kind == "csv":
        delimiter = "TAB" if block.delimiter == "\t" else block.delimiter
        metadata.append(f"csv: {block.encoding} delimiter={delimiter}")
    metadata.append(f"rows: {row_start}-{row_end}")
    if cell_range is not None:
        metadata.append(f"cells: {cell_range}")
    return "\n".join([*metadata, body_text])


def _source_spans(
    block: ArtifactTableBlock,
    selections: tuple[_RowSelection, ...],
) -> list[ChunkSourceSpan]:
    spans: list[ChunkSourceSpan] = []
    for item in selections:
        boxes = _deduplicate_boxes(
            [
                cell.bounding_box
                for cell in item.row.cells
                if cell.bounding_box is not None
            ]
        )
        spans.append(
            ChunkSourceSpan(
                block_id=block.block_id,
                start_locator=item.row.cells[0].locator,
                end_locator=item.row.cells[-1].locator,
                bounding_boxes=boxes,
            )
        )
    return spans


def _page_numbers(
    block: ArtifactTableBlock,
    selections: tuple[_RowSelection, ...],
) -> list[int]:
    pages = {
        page
        for page in [
            block.locator.page_number,
            *[
                cell.locator.page_number
                for item in selections
                for cell in item.row.cells
            ],
        ]
        if page is not None
    }
    return sorted(pages)


def _bounding_boxes(
    block: ArtifactTableBlock,
    selections: tuple[_RowSelection, ...],
) -> list[ArtifactBoundingBox]:
    return _deduplicate_boxes(
        [
            box
            for box in [
                block.bounding_box,
                *[cell.bounding_box for item in selections for cell in item.row.cells],
            ]
            if box is not None
        ]
    )


def _deduplicate_boxes(
    boxes: list[ArtifactBoundingBox],
) -> list[ArtifactBoundingBox]:
    output: list[ArtifactBoundingBox] = []
    seen: set[tuple[object, ...]] = set()
    for box in boxes:
        identity = (
            box.page_number,
            box.left,
            box.top,
            box.right,
            box.bottom,
            box.page_width,
            box.page_height,
            box.coordinate_system,
        )
        if identity not in seen:
            seen.add(identity)
            output.append(box)
    return output


def _column_label(number: int) -> str:
    label = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        label = chr(65 + remainder) + label
    return label
