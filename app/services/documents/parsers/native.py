"""Lossless adapters from the four M2 Native parser results."""

from __future__ import annotations

from typing import TypeAlias, assert_never

from app.services.documents.artifacts import (
    ArtifactBlock,
    ArtifactHeadingHint,
    ArtifactPageProperties,
    ArtifactTableBlock,
    ArtifactTableCell,
    ArtifactTableRow,
    ArtifactTextBlock,
    ArtifactWarning,
    CanonicalParsedArtifact,
    build_canonical_artifact,
)
from app.services.documents.parsers.base import SourceLocator
from app.services.documents.parsers.csv import CsvParseResult
from app.services.documents.parsers.docx import (
    DocxParagraphBlock,
    DocxParseResult,
    DocxTableBlock,
)
from app.services.documents.parsers.pdf import PdfParseResult
from app.services.documents.parsers.xlsx import (
    SpreadsheetScalar,
    XlsxCell,
    XlsxParseResult,
)

NativeParseResult: TypeAlias = (
    PdfParseResult | DocxParseResult | XlsxParseResult | CsvParseResult
)


def adapt_native_parse_result(
    result: NativeParseResult,
    *,
    source_sha256: str,
) -> CanonicalParsedArtifact:
    """Dispatch one already-safe Native result into the canonical contract."""

    if isinstance(result, PdfParseResult):
        blocks = _adapt_pdf(result)
        source_character_count = sum(page.character_count for page in result.pages)
    elif isinstance(result, DocxParseResult):
        blocks = _adapt_docx(result)
        source_character_count = result.character_count
    elif isinstance(result, XlsxParseResult):
        blocks = _adapt_xlsx(result)
        source_character_count = result.character_count
    elif isinstance(result, CsvParseResult):
        blocks = _adapt_csv(result)
        source_character_count = result.character_count
    else:
        assert_never(result)
    return build_canonical_artifact(
        source_type=result.source_type,
        source_sha256=source_sha256,
        parser_name=result.parser_name,
        parser_version=result.parser_version,
        blocks=blocks,
        warnings=[
            ArtifactWarning(
                code=warning.code,
                message=warning.message,
                locator=warning.locator,
            )
            for warning in result.warnings
        ],
        source_character_count=source_character_count,
        page_count=(result.page_count if isinstance(result, PdfParseResult) else None),
        sheet_count=(
            result.sheet_count if isinstance(result, XlsxParseResult) else None
        ),
    )


def _adapt_pdf(result: PdfParseResult) -> list[ArtifactBlock]:
    return [
        ArtifactTextBlock(
            block_id=_block_id(page.page_number),
            text=page.text,
            locator=SourceLocator(page_number=page.page_number),
            page=ArtifactPageProperties(
                page_number=page.page_number,
                character_count=page.character_count,
                image_count=page.image_count,
                low_text=page.low_text,
            ),
            heading_hints=[
                ArtifactHeadingHint(
                    text=hint.text,
                    level=hint.level,
                    font_size=hint.font_size,
                    locator=hint.locator,
                )
                for hint in page.heading_hints
            ],
        )
        for page in result.pages
    ]


def _adapt_docx(result: DocxParseResult) -> list[ArtifactBlock]:
    blocks: list[ArtifactBlock] = []
    for source in result.blocks:
        if isinstance(source, DocxParagraphBlock):
            blocks.append(
                ArtifactTextBlock(
                    block_id=_block_id(source.block_number),
                    text=source.text,
                    locator=source.locator,
                    heading_level=source.heading_level,
                    heading_path=source.heading_path,
                    style_name=source.style_name,
                )
            )
            continue
        if isinstance(source, DocxTableBlock):
            blocks.append(
                ArtifactTableBlock(
                    block_id=_block_id(source.block_number),
                    source_kind="docx_table",
                    locator=source.locator,
                    heading_path=source.heading_path,
                    rows=[
                        ArtifactTableRow(
                            row_number=row.row_number,
                            is_empty=all(not cell.text.strip() for cell in row.cells),
                            locator=source.locator,
                            cells=[
                                ArtifactTableCell(
                                    column_number=cell.column_number,
                                    value=cell.text,
                                    display_text=cell.text,
                                    data_type=("text" if cell.text else "empty"),
                                    locator=cell.locator,
                                )
                                for cell in row.cells
                            ],
                        )
                        for row in source.rows
                    ],
                )
            )
            continue
        assert_never(source)
    return blocks


def _adapt_xlsx(result: XlsxParseResult) -> list[ArtifactBlock]:
    return [
        ArtifactTableBlock(
            block_id=_block_id(sheet.sheet_number),
            source_kind="worksheet",
            title=sheet.sheet_name,
            locator=sheet.locator,
            headers=sheet.headers,
            header_row_number=sheet.header_row_number,
            sheet_state=sheet.state,
            rows=[
                ArtifactTableRow(
                    row_number=row.row_number,
                    is_empty=row.is_empty,
                    locator=row.locator,
                    cells=[_adapt_xlsx_cell(cell) for cell in row.cells],
                )
                for row in sheet.rows
            ],
        )
        for sheet in result.sheets
    ]


def _adapt_xlsx_cell(cell: XlsxCell) -> ArtifactTableCell:
    display_text = (
        _scalar_text(cell.cached_value) or cell.formula or ""
        if cell.formula is not None
        else _scalar_text(cell.value)
    )
    return ArtifactTableCell(
        column_number=cell.column_number,
        coordinate=cell.coordinate,
        value=cell.value,
        display_text=display_text,
        data_type=cell.data_type,
        formula=cell.formula,
        cached_value=cell.cached_value,
        locator=cell.locator,
    )


def _adapt_csv(result: CsvParseResult) -> list[ArtifactBlock]:
    return [
        ArtifactTableBlock(
            block_id=_block_id(1),
            source_kind="csv",
            locator=SourceLocator(),
            headers=result.headers,
            header_row_number=result.header_row_number,
            encoding=result.encoding,
            delimiter=result.delimiter,
            rows=[
                ArtifactTableRow(
                    row_number=row.row_number,
                    is_empty=row.is_empty,
                    locator=row.locator,
                    cells=[
                        ArtifactTableCell(
                            column_number=column_number,
                            value=value,
                            display_text=value,
                            data_type=("text" if value else "empty"),
                            locator=row.locator,
                        )
                        for column_number, value in enumerate(row.values, start=1)
                    ],
                )
                for row in result.rows
            ],
        )
    ]


def _block_id(number: int) -> str:
    return f"b{number:06d}"


def _scalar_text(value: SpreadsheetScalar) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return str(value)
