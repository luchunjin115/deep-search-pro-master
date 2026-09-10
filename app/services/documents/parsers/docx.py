"""Bounded DOCX extraction with headers, footers, and in-place image OCR."""

from __future__ import annotations

import hashlib
import io
import re
import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Annotated, BinaryIO, Literal, Self
from xml.etree import ElementTree
from zipfile import ZipFile, ZipInfo

import docx
from docx.drawing import Drawing
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.table import Table
from docx.text.hyperlink import Hyperlink
from docx.text.paragraph import Paragraph
from docx.text.run import Run
from PIL import Image, UnidentifiedImageError
from pydantic import Field, model_validator

from app.schemas.common import M1Schema
from app.services.documents.parsers.base import (
    DocumentEncryptedError,
    DocumentEnhancementError,
    DocumentLimitError,
    DocumentParseError,
    ParserWarning,
    SourceLocator,
)
from app.services.documents.parsers.docx_ocr import (
    DocxImageOcrOutput,
    DocxImageOcrProvider,
    LocalRapidOcrProvider,
)

if TYPE_CHECKING:
    from app.core.config import Settings

PARSER_NAME: Literal["python-docx"] = "python-docx"
PARSER_VERSION = f"m2-docx-v2+python-docx-{docx.__version__}"
_READ_CHUNK_BYTES = 1024 * 1024
_REQUIRED_MEMBERS = frozenset(
    {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
)
_HEADING_STYLE = re.compile(r"^(?:heading|标题)\s*([1-9])$", re.IGNORECASE)


class DocxTextSegment(M1Schema):
    """A text slice before or after an inline image in one paragraph."""

    kind: Literal["text"] = "text"
    segment_number: int = Field(ge=1)
    run_number: int = Field(ge=1)
    text: str
    locator: SourceLocator


class DocxImageOcrSegment(M1Schema):
    """OCR output anchored to one physical inline-image occurrence."""

    kind: Literal["image_ocr"] = "image_ocr"
    segment_number: int = Field(ge=1)
    run_number: int = Field(ge=1)
    image_number: int = Field(ge=1)
    text: str
    image_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    image_size_bytes: int = Field(gt=0)
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    content_type: str = Field(min_length=1, max_length=100)
    provider_name: str = Field(min_length=1, max_length=100)
    provider_version: str = Field(min_length=1, max_length=200)
    mean_confidence: float | None = Field(default=None, ge=0, le=1)
    locator: SourceLocator


DocxParagraphSegment = Annotated[
    DocxTextSegment | DocxImageOcrSegment,
    Field(discriminator="kind"),
]


class DocxRegionTextBlock(M1Schema):
    """One non-empty paragraph or table flattened from a header/footer part."""

    region: Literal["header", "footer"]
    section_number: int = Field(ge=1)
    region_block_number: int = Field(ge=1)
    content_kind: Literal["paragraph", "table"]
    text: str = Field(min_length=1)
    locator: SourceLocator = Field(default_factory=SourceLocator)


class DocxParagraphBlock(M1Schema):
    """One top-level Word paragraph, including intentional blank paragraphs."""

    kind: Literal["paragraph"] = "paragraph"
    block_number: int = Field(ge=1)
    paragraph_number: int = Field(ge=1)
    text: str
    style_name: str | None = Field(default=None, max_length=200)
    heading_level: int | None = Field(default=None, ge=1, le=9)
    heading_path: list[str] = Field(max_length=9)
    locator: SourceLocator
    segments: list[DocxParagraphSegment] = Field(default_factory=list, max_length=3000)

    @model_validator(mode="after")
    def validate_locator(self) -> DocxParagraphBlock:
        if (
            self.locator.block_number != self.block_number
            or self.locator.paragraph_number != self.paragraph_number
            or self.locator.table_number is not None
            or self.locator.heading_path != self.heading_path
        ):
            raise ValueError("paragraph locator does not match block")
        if self.segments:
            if [item.segment_number for item in self.segments] != list(
                range(1, len(self.segments) + 1)
            ):
                raise ValueError("paragraph segments must be a one-based sequence")
            if not any(isinstance(item, DocxImageOcrSegment) for item in self.segments):
                raise ValueError(
                    "paragraph segments are only used for image paragraphs"
                )
            if any(
                item.locator.block_number != self.block_number
                or item.locator.paragraph_number != self.paragraph_number
                or item.locator.heading_path != self.heading_path
                for item in self.segments
            ):
                raise ValueError("paragraph segment locator does not match block")
        return self


class DocxTableCell(M1Schema):
    """One table grid cell with a stable one-based row and column location."""

    row_number: int = Field(ge=1)
    column_number: int = Field(ge=1)
    text: str
    locator: SourceLocator

    @model_validator(mode="after")
    def validate_locator(self) -> DocxTableCell:
        if (
            self.locator.table_number is None
            or self.locator.row_number != self.row_number
            or self.locator.column_number != self.column_number
        ):
            raise ValueError("cell locator does not match cell")
        return self


class DocxTableRow(M1Schema):
    """One table row in source order."""

    row_number: int = Field(ge=1)
    cells: list[DocxTableCell] = Field(max_length=500_000)

    @model_validator(mode="after")
    def validate_cell_sequence(self) -> DocxTableRow:
        if [cell.column_number for cell in self.cells] != list(
            range(1, len(self.cells) + 1)
        ) or any(cell.row_number != self.row_number for cell in self.cells):
            raise ValueError("cells must match their row in one-based order")
        return self


class DocxTableBlock(M1Schema):
    """One top-level Word table in its original body position."""

    kind: Literal["table"] = "table"
    block_number: int = Field(ge=1)
    table_number: int = Field(ge=1)
    heading_path: list[str] = Field(max_length=9)
    rows: list[DocxTableRow] = Field(max_length=100_000)
    locator: SourceLocator

    @model_validator(mode="after")
    def validate_locator_and_rows(self) -> DocxTableBlock:
        if (
            self.locator.block_number != self.block_number
            or self.locator.table_number != self.table_number
            or self.locator.paragraph_number is not None
            or self.locator.heading_path != self.heading_path
        ):
            raise ValueError("table locator does not match block")
        if [row.row_number for row in self.rows] != list(range(1, len(self.rows) + 1)):
            raise ValueError("rows must be a complete one-based sequence")
        for row in self.rows:
            for cell in row.cells:
                if (
                    cell.locator.block_number != self.block_number
                    or cell.locator.table_number != self.table_number
                    or cell.locator.heading_path != self.heading_path
                ):
                    raise ValueError("cell locator does not match table")
        return self


DocxBlock = Annotated[
    DocxParagraphBlock | DocxTableBlock,
    Field(discriminator="kind"),
]


class DocxParseResult(M1Schema):
    """Safe DOCX parser output without filesystem paths or Storage keys."""

    parser_name: Literal["python-docx"] = PARSER_NAME
    parser_version: str = Field(min_length=1, max_length=64)
    source_type: Literal["docx"] = "docx"
    block_count: int = Field(ge=0, le=100_000)
    paragraph_count: int = Field(ge=0, le=100_000)
    table_count: int = Field(ge=0, le=100_000)
    table_cell_count: int = Field(ge=0, le=500_000)
    region_block_count: int = Field(default=0, ge=0, le=100_000)
    image_ocr_count: int = Field(default=0, ge=0, le=1000)
    image_bytes_total: int = Field(default=0, ge=0, le=100_000_000)
    character_count: int = Field(ge=0, le=20_000_000)
    blocks: list[DocxBlock] = Field(max_length=100_000)
    region_blocks: list[DocxRegionTextBlock] = Field(
        default_factory=list,
        max_length=100_000,
    )
    warnings: list[ParserWarning] = Field(max_length=100)

    @model_validator(mode="after")
    def validate_sequences_and_counts(self) -> DocxParseResult:
        if self.block_count != len(self.blocks):
            raise ValueError("block_count does not match blocks")
        if [block.block_number for block in self.blocks] != list(
            range(1, self.block_count + 1)
        ):
            raise ValueError("blocks must be a complete one-based sequence")

        paragraphs = [
            block for block in self.blocks if isinstance(block, DocxParagraphBlock)
        ]
        tables = [block for block in self.blocks if isinstance(block, DocxTableBlock)]
        if self.paragraph_count != len(paragraphs):
            raise ValueError("paragraph_count does not match blocks")
        if self.table_count != len(tables):
            raise ValueError("table_count does not match blocks")
        if [block.paragraph_number for block in paragraphs] != list(
            range(1, self.paragraph_count + 1)
        ):
            raise ValueError("paragraphs must be a complete one-based sequence")
        if [block.table_number for block in tables] != list(
            range(1, self.table_count + 1)
        ):
            raise ValueError("tables must be a complete one-based sequence")

        cells = [cell for table in tables for row in table.rows for cell in row.cells]
        if self.table_cell_count != len(cells):
            raise ValueError("table_cell_count does not match blocks")
        if self.region_block_count != len(self.region_blocks):
            raise ValueError("region_block_count does not match region blocks")
        if [block.region_block_number for block in self.region_blocks] != list(
            range(1, self.region_block_count + 1)
        ):
            raise ValueError("region blocks must be a complete one-based sequence")
        image_segments = [
            segment
            for paragraph in paragraphs
            for segment in paragraph.segments
            if isinstance(segment, DocxImageOcrSegment)
        ]
        if self.image_ocr_count != len(image_segments):
            raise ValueError("image_ocr_count does not match paragraph segments")
        if [segment.image_number for segment in image_segments] != list(
            range(1, self.image_ocr_count + 1)
        ):
            raise ValueError("image OCR occurrences must be a one-based sequence")
        if self.image_bytes_total != sum(
            segment.image_size_bytes for segment in image_segments
        ):
            raise ValueError("image_bytes_total does not match paragraph segments")
        actual_characters = sum(
            _character_count(block.text) for block in self.region_blocks
        )
        for block in self.blocks:
            if isinstance(block, DocxParagraphBlock):
                actual_characters += (
                    sum(_character_count(segment.text) for segment in block.segments)
                    if block.segments
                    else _character_count(block.text)
                )
            else:
                actual_characters += sum(
                    _character_count(cell.text)
                    for row in block.rows
                    for cell in row.cells
                )
        if self.character_count != actual_characters:
            raise ValueError("character_count does not match blocks")
        return self


@dataclass(slots=True)
class _ImageExtractionState:
    image_count: int = 0
    image_bytes_total: int = 0
    ocr_cache: dict[str, DocxImageOcrOutput] = field(default_factory=dict)


class DocxParser:
    """Extract bounded DOCX structure and optional offline inline-image OCR."""

    def __init__(
        self,
        *,
        max_source_bytes: int = 25 * 1024 * 1024,
        max_archive_members: int = 5000,
        max_uncompressed_bytes: int = 100 * 1024 * 1024,
        max_compression_ratio: int = 200,
        max_blocks: int = 50_000,
        max_table_cells: int = 200_000,
        max_extracted_characters: int = 5_000_000,
        image_ocr_provider: DocxImageOcrProvider | None = None,
        max_images: int = 100,
        max_image_bytes: int = 10 * 1024 * 1024,
        max_total_image_bytes: int = 25 * 1024 * 1024,
        max_image_pixels: int = 20_000_000,
    ) -> None:
        limits = (
            max_source_bytes,
            max_archive_members,
            max_uncompressed_bytes,
            max_compression_ratio,
            max_blocks,
            max_table_cells,
            max_extracted_characters,
            max_images,
            max_image_bytes,
            max_total_image_bytes,
            max_image_pixels,
        )
        if any(limit <= 0 for limit in limits):
            raise ValueError("DOCX parser limits must be positive and bounded")
        if (
            max_archive_members > 20_000
            or max_uncompressed_bytes > 500 * 1024 * 1024
            or max_compression_ratio > 1000
            or max_blocks > 100_000
            or max_table_cells > 500_000
            or max_extracted_characters > 20_000_000
            or max_images > 1000
            or max_image_bytes > 25 * 1024 * 1024
            or max_total_image_bytes > 100 * 1024 * 1024
            or max_total_image_bytes < max_image_bytes
            or max_image_pixels > 100_000_000
        ):
            raise ValueError("DOCX parser limits must be positive and bounded")
        self._max_source_bytes = max_source_bytes
        self._max_archive_members = max_archive_members
        self._max_uncompressed_bytes = max_uncompressed_bytes
        self._max_compression_ratio = max_compression_ratio
        self._max_blocks = max_blocks
        self._max_table_cells = max_table_cells
        self._max_extracted_characters = max_extracted_characters
        self._image_ocr_provider = image_ocr_provider
        self._max_images = max_images
        self._max_image_bytes = max_image_bytes
        self._max_total_image_bytes = max_total_image_bytes
        self._max_image_pixels = max_image_pixels

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        """Build one parser from the process-wide validated M2 limits."""

        image_ocr_provider = (
            LocalRapidOcrProvider(
                model_cache_root=settings.docling_model_cache_root,
                num_threads=settings.docx_image_ocr_threads,
            )
            if settings.docx_image_ocr_backend == "rapidocr"
            else None
        )
        return cls(
            max_source_bytes=settings.upload_max_file_size_bytes,
            max_archive_members=settings.docx_max_archive_members,
            max_uncompressed_bytes=settings.docx_max_uncompressed_bytes,
            max_compression_ratio=settings.docx_max_compression_ratio,
            max_blocks=settings.docx_max_blocks,
            max_table_cells=settings.docx_max_table_cells,
            max_extracted_characters=settings.docx_max_extracted_characters,
            image_ocr_provider=image_ocr_provider,
            max_images=settings.docx_max_images,
            max_image_bytes=settings.docx_max_image_bytes,
            max_total_image_bytes=settings.docx_max_total_image_bytes,
            max_image_pixels=settings.docx_max_image_pixels,
        )

    @property
    def parser_name(self) -> str:
        return PARSER_NAME

    @property
    def parser_version(self) -> str:
        return PARSER_VERSION

    def parse(self, stream: BinaryIO) -> DocxParseResult:
        source = self._read_bounded(stream)
        self._validate_archive(source)
        try:
            document = docx.Document(io.BytesIO(source))
            return self._extract(document)
        except (DocumentEnhancementError, DocumentLimitError):
            raise
        except Exception:  # noqa: BLE001 - malformed OOXML internals stay private.
            raise DocumentParseError from None

    def _read_bounded(self, stream: BinaryIO) -> bytes:
        chunks: list[bytes] = []
        total = 0
        try:
            stream.seek(0)
            while True:
                remaining = self._max_source_bytes + 1 - total
                chunk = stream.read(min(_READ_CHUNK_BYTES, remaining))
                if chunk == b"":
                    break
                if not isinstance(chunk, (bytes, bytearray, memoryview)):
                    raise TypeError("binary stream required")
                binary = bytes(chunk)
                chunks.append(binary)
                total += len(binary)
                if total > self._max_source_bytes:
                    raise DocumentLimitError
        except DocumentLimitError:
            raise
        except Exception:  # noqa: BLE001 - arbitrary stream failures stay private.
            raise DocumentParseError from None
        return b"".join(chunks)

    def _validate_archive(self, source: bytes) -> None:
        try:
            with ZipFile(io.BytesIO(source)) as archive:
                members = archive.infolist()
                if len(members) > self._max_archive_members:
                    raise DocumentLimitError
                names: set[str] = set()
                total_uncompressed = 0
                for member in members:
                    self._validate_member(member, names)
                    total_uncompressed += member.file_size
                    if total_uncompressed > self._max_uncompressed_bytes:
                        raise DocumentLimitError
                if not _REQUIRED_MEMBERS.issubset(names):
                    raise DocumentParseError
                self._validate_image_relationships(archive, members)
        except (DocumentEncryptedError, DocumentLimitError, DocumentParseError):
            raise
        except Exception:  # noqa: BLE001 - ZIP implementation details stay private.
            raise DocumentParseError from None

    def _validate_member(self, member: ZipInfo, names: set[str]) -> None:
        name = member.filename
        parts = name.split("/")
        if (
            not name
            or "\\" in name
            or name.startswith("/")
            or any(part in {"", ".", ".."} for part in parts[:-1])
            or name in names
        ):
            raise DocumentParseError
        names.add(name)
        if member.flag_bits & 0x1:
            raise DocumentEncryptedError
        if member.file_size < 0 or member.compress_size < 0:
            raise DocumentParseError
        if member.file_size == 0:
            return
        if member.compress_size == 0:
            raise DocumentLimitError
        if member.file_size > member.compress_size * self._max_compression_ratio:
            raise DocumentLimitError

    def _extract(self, document: docx.document.Document) -> DocxParseResult:
        blocks: list[DocxBlock] = []
        headings: dict[int, str] = {}
        image_state = _ImageExtractionState()
        paragraph_number = 0
        table_number = 0
        table_cell_count = 0
        region_table_cell_count = 0
        header_blocks, header_cells = self._extract_region_blocks(document, "header")
        footer_blocks, footer_cells = self._extract_region_blocks(document, "footer")
        region_blocks = [
            block.model_copy(update={"region_block_number": number})
            for number, block in enumerate([*header_blocks, *footer_blocks], start=1)
        ]
        region_table_cell_count += header_cells + footer_cells
        character_count = sum(_character_count(block.text) for block in region_blocks)

        if len(region_blocks) > self._max_blocks:
            raise DocumentLimitError
        if region_table_cell_count > self._max_table_cells:
            raise DocumentLimitError

        for block_number, content in enumerate(document.iter_inner_content(), start=1):
            if block_number + len(region_blocks) > self._max_blocks:
                raise DocumentLimitError
            if isinstance(content, Paragraph):
                paragraph_number += 1
                text = _normalize_text(content.text)
                heading_level = _heading_level(content)
                if heading_level is not None and text:
                    headings = {
                        level: value
                        for level, value in headings.items()
                        if level < heading_level
                    }
                    headings[heading_level] = text
                heading_path = [headings[level] for level in sorted(headings)]
                locator = SourceLocator(
                    block_number=block_number,
                    paragraph_number=paragraph_number,
                    heading_path=heading_path,
                )
                segments = self._extract_paragraph_segments(
                    content,
                    block_number=block_number,
                    paragraph_number=paragraph_number,
                    heading_path=heading_path,
                    state=image_state,
                )
                if (
                    block_number + len(region_blocks) + image_state.image_count
                    > self._max_blocks
                ):
                    raise DocumentLimitError
                blocks.append(
                    DocxParagraphBlock(
                        block_number=block_number,
                        paragraph_number=paragraph_number,
                        text=text,
                        style_name=_style_name(content),
                        heading_level=heading_level,
                        heading_path=heading_path,
                        locator=locator,
                        segments=segments,
                    )
                )
                character_count += (
                    sum(_character_count(segment.text) for segment in segments)
                    if segments
                    else _character_count(text)
                )
            elif isinstance(content, Table):
                table_number += 1
                heading_path = [headings[level] for level in sorted(headings)]
                table_locator = SourceLocator(
                    block_number=block_number,
                    table_number=table_number,
                    heading_path=heading_path,
                )
                rows: list[DocxTableRow] = []
                for row_number, row in enumerate(content.rows, start=1):
                    cells: list[DocxTableCell] = []
                    for column_number, cell in enumerate(row.cells, start=1):
                        table_cell_count += 1
                        if (
                            table_cell_count + region_table_cell_count
                            > self._max_table_cells
                        ):
                            raise DocumentLimitError
                        text = _normalize_text(cell.text)
                        character_count += _character_count(text)
                        cells.append(
                            DocxTableCell(
                                row_number=row_number,
                                column_number=column_number,
                                text=text,
                                locator=SourceLocator(
                                    block_number=block_number,
                                    table_number=table_number,
                                    row_number=row_number,
                                    column_number=column_number,
                                    heading_path=heading_path,
                                ),
                            )
                        )
                    rows.append(DocxTableRow(row_number=row_number, cells=cells))
                blocks.append(
                    DocxTableBlock(
                        block_number=block_number,
                        table_number=table_number,
                        heading_path=heading_path,
                        rows=rows,
                        locator=table_locator,
                    )
                )

            if character_count > self._max_extracted_characters:
                raise DocumentLimitError

        warnings = []
        if character_count == 0:
            warnings.append(
                ParserWarning(
                    code="empty_document",
                    message="文档没有可提取的文字",
                    locator=SourceLocator(),
                )
            )
        return DocxParseResult(
            parser_version=self.parser_version,
            block_count=len(blocks),
            paragraph_count=paragraph_number,
            table_count=table_number,
            table_cell_count=table_cell_count,
            region_block_count=len(region_blocks),
            image_ocr_count=image_state.image_count,
            image_bytes_total=image_state.image_bytes_total,
            character_count=character_count,
            blocks=blocks,
            region_blocks=region_blocks,
            warnings=warnings,
        )

    def _extract_region_blocks(
        self,
        document: docx.document.Document,
        region: Literal["header", "footer"],
    ) -> tuple[list[DocxRegionTextBlock], int]:
        blocks: list[DocxRegionTextBlock] = []
        seen_parts: set[str] = set()
        table_cell_count = 0
        for section_number, section in enumerate(document.sections, start=1):
            container = section.header if region == "header" else section.footer
            part_name = str(container.part.partname)
            if part_name in seen_parts:
                continue
            seen_parts.add(part_name)
            for content in container.iter_inner_content():
                content_kind: Literal["paragraph", "table"]
                if isinstance(content, Paragraph):
                    content_kind = "paragraph"
                    text = _normalize_text(content.text)
                elif isinstance(content, Table):
                    content_kind = "table"
                    rows: list[str] = []
                    for row in content.rows:
                        table_cell_count += len(row.cells)
                        rows.append(
                            " | ".join(_normalize_text(cell.text) for cell in row.cells)
                        )
                    text = _normalize_text("\n".join(rows))
                else:
                    continue
                if not text:
                    continue
                blocks.append(
                    DocxRegionTextBlock(
                        region=region,
                        section_number=section_number,
                        region_block_number=len(blocks) + 1,
                        content_kind=content_kind,
                        text=text,
                    )
                )
        return blocks, table_cell_count

    def _extract_paragraph_segments(
        self,
        paragraph: Paragraph,
        *,
        block_number: int,
        paragraph_number: int,
        heading_path: list[str],
        state: _ImageExtractionState,
    ) -> list[DocxParagraphSegment]:
        pending_text: list[str] = []
        pending_run_number = 1
        segments: list[DocxParagraphSegment] = []
        saw_inline_image = False
        run_number = 0

        def append_text() -> None:
            text = _normalize_text("".join(pending_text))
            pending_text.clear()
            if not text:
                return
            segments.append(
                DocxTextSegment(
                    segment_number=len(segments) + 1,
                    run_number=pending_run_number,
                    text=text,
                    locator=SourceLocator(
                        block_number=block_number,
                        paragraph_number=paragraph_number,
                        heading_path=heading_path,
                    ),
                )
            )

        for item in paragraph.iter_inner_content():
            runs = item.runs if isinstance(item, Hyperlink) else (item,)
            for run in runs:
                if not isinstance(run, Run):
                    continue
                run_number += 1
                for inner in run.iter_inner_content():
                    if isinstance(inner, str):
                        if not pending_text:
                            pending_run_number = run_number
                        pending_text.append(inner)
                        continue
                    if not isinstance(inner, Drawing):
                        continue
                    image_refs = self._inline_image_relationship_ids(inner)
                    if not image_refs:
                        continue
                    saw_inline_image = True
                    append_text()
                    for relationship_id in image_refs:
                        segments.append(
                            self._extract_image_segment(
                                paragraph,
                                relationship_id=relationship_id,
                                segment_number=len(segments) + 1,
                                run_number=run_number,
                                block_number=block_number,
                                paragraph_number=paragraph_number,
                                heading_path=heading_path,
                                state=state,
                            )
                        )
        if not saw_inline_image:
            return []
        append_text()
        return segments

    def _inline_image_relationship_ids(self, drawing: Drawing) -> list[str]:
        linked = drawing._drawing.xpath("./wp:inline//a:blip/@r:link")
        if linked:
            raise DocumentParseError
        return [
            str(relationship_id)
            for relationship_id in drawing._drawing.xpath(
                "./wp:inline//pic:blipFill/a:blip/@r:embed"
            )
        ]

    def _extract_image_segment(
        self,
        paragraph: Paragraph,
        *,
        relationship_id: str,
        segment_number: int,
        run_number: int,
        block_number: int,
        paragraph_number: int,
        heading_path: list[str],
        state: _ImageExtractionState,
    ) -> DocxImageOcrSegment:
        relationship = paragraph.part.rels.get(relationship_id)
        if (
            relationship is None
            or relationship.is_external
            or relationship.reltype != RT.IMAGE
        ):
            raise DocumentParseError
        image_part = relationship.target_part
        image_bytes = bytes(image_part.blob)
        content_type = str(image_part.content_type)
        if not image_bytes or not content_type.startswith("image/"):
            raise DocumentParseError

        state.image_count += 1
        state.image_bytes_total += len(image_bytes)
        if (
            state.image_count > self._max_images
            or len(image_bytes) > self._max_image_bytes
            or state.image_bytes_total > self._max_total_image_bytes
        ):
            raise DocumentLimitError
        width, height = self._validate_image(image_bytes)
        image_sha256 = hashlib.sha256(image_bytes).hexdigest()
        output = state.ocr_cache.get(image_sha256)
        if output is None:
            output = (
                self._image_ocr_provider.extract(image_bytes)
                if self._image_ocr_provider is not None
                else DocxImageOcrOutput(
                    text="",
                    provider_name="disabled",
                    provider_version="m2-docx-image-ocr-disabled-v1",
                )
            )
            state.ocr_cache[image_sha256] = output
        return DocxImageOcrSegment(
            segment_number=segment_number,
            run_number=run_number,
            image_number=state.image_count,
            text=_normalize_text(output.text),
            image_sha256=image_sha256,
            image_size_bytes=len(image_bytes),
            image_width=width,
            image_height=height,
            content_type=content_type,
            provider_name=output.provider_name,
            provider_version=output.provider_version,
            mean_confidence=output.mean_confidence,
            locator=SourceLocator(
                block_number=block_number,
                paragraph_number=paragraph_number,
                heading_path=heading_path,
            ),
        )

    def _validate_image(self, image_bytes: bytes) -> tuple[int, int]:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(image_bytes)) as image:
                    width, height = image.size
                    if width <= 0 or height <= 0:
                        raise DocumentParseError
                    if width * height > self._max_image_pixels:
                        raise DocumentLimitError
                    image.verify()
            return width, height
        except DocumentLimitError:
            raise
        except (Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise DocumentLimitError from None
        except (OSError, UnidentifiedImageError, ValueError):
            raise DocumentParseError from None

    def _validate_image_relationships(
        self,
        archive: ZipFile,
        members: list[ZipInfo],
    ) -> None:
        for member in members:
            if not member.filename.lower().endswith(".rels"):
                continue
            payload = archive.read(member)
            upper_payload = payload.upper()
            if b"<!DOCTYPE" in upper_payload or b"<!ENTITY" in upper_payload:
                raise DocumentParseError
            try:
                root = ElementTree.fromstring(payload)
            except ElementTree.ParseError:
                raise DocumentParseError from None
            for relationship in root.iter():
                if not relationship.tag.endswith("Relationship"):
                    continue
                relation_type = relationship.attrib.get("Type", "")
                target_mode = relationship.attrib.get("TargetMode", "")
                if (
                    relation_type.endswith("/image")
                    and target_mode.casefold() == "external"
                ):
                    raise DocumentParseError


def _normalize_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


def _character_count(value: str) -> int:
    return sum(not character.isspace() for character in value)


def _style_name(paragraph: Paragraph) -> str | None:
    try:
        style = paragraph.style
        if style is None:
            return None
        name = style.name
    except (AttributeError, KeyError, ValueError):
        return None
    normalized = str(name).strip()
    return normalized[:200] or None


def _heading_level(paragraph: Paragraph) -> int | None:
    try:
        style = paragraph.style
        visited: set[str] = set()
        while style is not None and style.style_id not in visited:
            visited.add(style.style_id)
            for candidate in (style.style_id, style.name):
                match = _HEADING_STYLE.fullmatch(str(candidate).strip())
                if match:
                    return int(match.group(1))
            paragraph_properties = style._element.pPr
            if paragraph_properties is not None:
                outline_level = paragraph_properties.outlineLvl
                if outline_level is not None:
                    value = int(outline_level.val) + 1
                    if 1 <= value <= 9:
                        return value
            style = style.base_style
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
    return None
