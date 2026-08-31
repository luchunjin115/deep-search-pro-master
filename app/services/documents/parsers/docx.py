"""Bounded DOCX extraction with stable body, heading, and table locators."""

from __future__ import annotations

import io
import re
from typing import TYPE_CHECKING, Annotated, BinaryIO, Literal, Self
from zipfile import ZipFile, ZipInfo

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph
from pydantic import Field, model_validator

from app.schemas.common import M1Schema
from app.services.documents.parsers.base import (
    DocumentEncryptedError,
    DocumentLimitError,
    DocumentParseError,
    ParserWarning,
    SourceLocator,
)

if TYPE_CHECKING:
    from app.core.config import Settings

PARSER_NAME: Literal["python-docx"] = "python-docx"
PARSER_VERSION = f"m2-docx-v1+python-docx-{docx.__version__}"
_READ_CHUNK_BYTES = 1024 * 1024
_REQUIRED_MEMBERS = frozenset(
    {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}
)
_HEADING_STYLE = re.compile(r"^(?:heading|标题)\s*([1-9])$", re.IGNORECASE)


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

    @model_validator(mode="after")
    def validate_locator(self) -> DocxParagraphBlock:
        if (
            self.locator.block_number != self.block_number
            or self.locator.paragraph_number != self.paragraph_number
            or self.locator.table_number is not None
            or self.locator.heading_path != self.heading_path
        ):
            raise ValueError("paragraph locator does not match block")
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
    character_count: int = Field(ge=0, le=20_000_000)
    blocks: list[DocxBlock] = Field(max_length=100_000)
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
        actual_characters = sum(
            _character_count(block.text)
            if isinstance(block, DocxParagraphBlock)
            else sum(
                _character_count(cell.text) for row in block.rows for cell in row.cells
            )
            for block in self.blocks
        )
        if self.character_count != actual_characters:
            raise ValueError("character_count does not match blocks")
        return self


class DocxParser:
    """Extract top-level DOCX paragraphs and tables without running macros or OCR."""

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
    ) -> None:
        limits = (
            max_source_bytes,
            max_archive_members,
            max_uncompressed_bytes,
            max_compression_ratio,
            max_blocks,
            max_table_cells,
            max_extracted_characters,
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
        ):
            raise ValueError("DOCX parser limits must be positive and bounded")
        self._max_source_bytes = max_source_bytes
        self._max_archive_members = max_archive_members
        self._max_uncompressed_bytes = max_uncompressed_bytes
        self._max_compression_ratio = max_compression_ratio
        self._max_blocks = max_blocks
        self._max_table_cells = max_table_cells
        self._max_extracted_characters = max_extracted_characters

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        """Build one parser from the process-wide validated M2 limits."""

        return cls(
            max_source_bytes=settings.upload_max_file_size_bytes,
            max_archive_members=settings.docx_max_archive_members,
            max_uncompressed_bytes=settings.docx_max_uncompressed_bytes,
            max_compression_ratio=settings.docx_max_compression_ratio,
            max_blocks=settings.docx_max_blocks,
            max_table_cells=settings.docx_max_table_cells,
            max_extracted_characters=settings.docx_max_extracted_characters,
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
        except DocumentLimitError:
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
        paragraph_number = 0
        table_number = 0
        table_cell_count = 0
        character_count = 0

        for block_number, content in enumerate(document.iter_inner_content(), start=1):
            if block_number > self._max_blocks:
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
                blocks.append(
                    DocxParagraphBlock(
                        block_number=block_number,
                        paragraph_number=paragraph_number,
                        text=text,
                        style_name=_style_name(content),
                        heading_level=heading_level,
                        heading_path=heading_path,
                        locator=locator,
                    )
                )
                character_count += _character_count(text)
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
                        if table_cell_count > self._max_table_cells:
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
            character_count=character_count,
            blocks=blocks,
            warnings=warnings,
        )


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
