"""Project-owned parsed-document contract and deterministic Markdown view."""

from __future__ import annotations

import hashlib
import json
from itertools import pairwise
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import Field, model_validator

from app.schemas.common import M1Schema
from app.services.documents.parsers.base import SourceLocator

ARTIFACT_SCHEMA_VERSION: Literal["m2-canonical-parsed-artifact-v1"] = (
    "m2-canonical-parsed-artifact-v1"
)
NATIVE_ADAPTER_VERSION: Literal["m2-native-adapter-v1"] = "m2-native-adapter-v1"
NATIVE_PDF_ADAPTER_VERSION: Literal["m2-native-pdf-adapter-v2"] = (
    "m2-native-pdf-adapter-v2"
)
DOCLING_ADAPTER_VERSION: Literal["m2-docling-adapter-v1"] = "m2-docling-adapter-v1"
CONTENT_HASH_VERSION: Literal["m2-canonical-content-v1"] = "m2-canonical-content-v1"

ArtifactSourceType = Literal["pdf", "docx", "xlsx", "csv"]
ArtifactScalar: TypeAlias = str | int | float | bool | None
ArtifactCellType = Literal[
    "empty",
    "text",
    "number",
    "boolean",
    "date",
    "formula",
    "error",
]


class ArtifactParser(M1Schema):
    """Parser and adapter provenance without a path or runtime secret."""

    provider: Literal["native", "docling"]
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=200)
    adapter_version: str = Field(
        pattern=r"^m2-[a-z0-9-]+-adapter-v[0-9]+$",
        max_length=100,
    )


class ArtifactWarning(M1Schema):
    """Parser-independent warning that remains safe and source-located."""

    code: str = Field(pattern=r"^[a-z][a-z0-9_]{0,99}$")
    message: str = Field(min_length=1, max_length=300)
    locator: SourceLocator


class ArtifactBoundingBox(M1Schema):
    """Optional top-left coordinates measured in the declared page dimensions."""

    page_number: int = Field(ge=1, le=2000)
    left: float = Field(ge=0)
    top: float = Field(ge=0)
    right: float = Field(gt=0)
    bottom: float = Field(gt=0)
    page_width: float = Field(gt=0)
    page_height: float = Field(gt=0)
    coordinate_system: Literal["top_left"] = "top_left"

    @model_validator(mode="after")
    def validate_geometry(self) -> ArtifactBoundingBox:
        if self.left >= self.right or self.top >= self.bottom:
            raise ValueError("bounding box must have positive area")
        if self.right > self.page_width or self.bottom > self.page_height:
            raise ValueError("bounding box must stay inside the page")
        return self


class ArtifactHeadingHint(M1Schema):
    """A source heading clue retained without promoting it to guaranteed truth."""

    text: str = Field(min_length=1, max_length=200)
    level: int = Field(ge=1, le=9)
    font_size: float | None = Field(default=None, gt=0, le=1000)
    locator: SourceLocator
    layout_line_number: int | None = Field(
        default=None,
        ge=1,
        le=100_000,
        exclude_if=lambda value: value is None,
    )
    bounding_box: ArtifactBoundingBox | None = None

    @model_validator(mode="after")
    def validate_location(self) -> ArtifactHeadingHint:
        if self.layout_line_number is not None and self.bounding_box is None:
            raise ValueError("heading layout line reference requires a bounding box")
        if self.bounding_box is not None and (
            self.locator.page_number != self.bounding_box.page_number
        ):
            raise ValueError("heading bounding box page does not match its locator")
        return self


class ArtifactPdfLayoutLine(M1Schema):
    """One physical PDF line located within its parent page text and page."""

    line_number: int = Field(ge=1, le=100_000)
    text: str = Field(min_length=1, max_length=1_000_000)
    character_start: int | None = Field(default=None, ge=0, le=5_000_000)
    character_end: int | None = Field(default=None, gt=0, le=5_000_000)
    locator: SourceLocator
    bounding_box: ArtifactBoundingBox

    @model_validator(mode="after")
    def validate_location(self) -> ArtifactPdfLayoutLine:
        if (self.character_start is None) != (self.character_end is None):
            raise ValueError("PDF layout line range must be complete or absent")
        if (
            self.character_start is not None
            and self.character_end is not None
            and self.character_start >= self.character_end
        ):
            raise ValueError("PDF layout line range must have positive length")
        if self.locator.page_number != self.bounding_box.page_number:
            raise ValueError("PDF layout line bounding box page does not match locator")
        return self


class ArtifactPageProperties(M1Schema):
    """Native PDF page signals used later by the quality gate."""

    page_number: int = Field(ge=1, le=2000)
    character_count: int = Field(ge=0, le=20_000_000)
    image_count: int = Field(ge=0, le=100_000)
    low_text: bool


class ArtifactDocxSource(M1Schema):
    """Versioned DOCX-only provenance for a header, footer, or inline image."""

    contract_version: Literal["m2-docx-source-v1"] = "m2-docx-source-v1"
    section_number: int | None = Field(default=None, ge=1)
    region_block_number: int | None = Field(default=None, ge=1)
    content_kind: Literal["paragraph", "table"] | None = None
    run_number: int | None = Field(default=None, ge=1)
    image_number: int | None = Field(default=None, ge=1)
    image_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    image_size_bytes: int | None = Field(default=None, gt=0)
    image_width: int | None = Field(default=None, gt=0)
    image_height: int | None = Field(default=None, gt=0)
    content_type: str | None = Field(default=None, min_length=1, max_length=100)
    ocr_provider_name: str | None = Field(default=None, min_length=1, max_length=100)
    ocr_provider_version: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )
    ocr_mean_confidence: float | None = Field(default=None, ge=0, le=1)


class ArtifactTextBlock(M1Schema):
    """One ordered page or document paragraph."""

    kind: Literal["text"] = "text"
    block_id: str = Field(pattern=r"^b[0-9]{6}$")
    source_kind: Literal[
        "document_text",
        "docx_header",
        "docx_footer",
        "docx_image_ocr",
    ] = Field(
        default="document_text", exclude_if=lambda value: value == "document_text"
    )
    docx_source: ArtifactDocxSource | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    text: str
    locator: SourceLocator
    heading_level: int | None = Field(default=None, ge=1, le=9)
    heading_path: list[str] = Field(default_factory=list, max_length=9)
    style_name: str | None = Field(default=None, max_length=200)
    page: ArtifactPageProperties | None = None
    heading_hints: list[ArtifactHeadingHint] = Field(
        default_factory=list,
        max_length=100,
    )
    pdf_layout_lines: list[ArtifactPdfLayoutLine] = Field(
        default_factory=list,
        max_length=100_000,
        exclude_if=lambda value: not value,
    )
    bounding_box: ArtifactBoundingBox | None = None

    @model_validator(mode="after")
    def validate_location(self) -> ArtifactTextBlock:
        if self.source_kind == "document_text":
            if self.docx_source is not None:
                raise ValueError("ordinary text cannot declare DOCX source metadata")
        elif self.docx_source is None:
            raise ValueError("special DOCX text requires source metadata")
        elif self.source_kind in {"docx_header", "docx_footer"}:
            if (
                self.docx_source.section_number is None
                or self.docx_source.region_block_number is None
                or self.docx_source.content_kind is None
                or any(
                    value is not None
                    for value in (
                        self.docx_source.run_number,
                        self.docx_source.image_number,
                        self.docx_source.image_sha256,
                        self.docx_source.image_size_bytes,
                        self.docx_source.image_width,
                        self.docx_source.image_height,
                        self.docx_source.content_type,
                        self.docx_source.ocr_provider_name,
                        self.docx_source.ocr_provider_version,
                        self.docx_source.ocr_mean_confidence,
                    )
                )
                or self.locator != SourceLocator()
            ):
                raise ValueError("DOCX header/footer metadata is inconsistent")
        elif (
            self.docx_source.section_number is not None
            or self.docx_source.region_block_number is not None
            or self.docx_source.content_kind is not None
            or any(
                value is None
                for value in (
                    self.docx_source.run_number,
                    self.docx_source.image_number,
                    self.docx_source.image_sha256,
                    self.docx_source.image_size_bytes,
                    self.docx_source.image_width,
                    self.docx_source.image_height,
                    self.docx_source.content_type,
                    self.docx_source.ocr_provider_name,
                    self.docx_source.ocr_provider_version,
                )
            )
            or self.locator.block_number is None
            or self.locator.paragraph_number is None
            or self.locator.table_number is not None
            or self.locator.page_number is not None
        ):
            raise ValueError("DOCX image OCR metadata is inconsistent")
        if self.page is not None and self.locator.page_number != self.page.page_number:
            raise ValueError("text block page does not match its locator")
        if self.locator.heading_path != self.heading_path:
            raise ValueError("text block heading path does not match its locator")
        if self.bounding_box is not None and (
            self.locator.page_number != self.bounding_box.page_number
        ):
            raise ValueError("text bounding box page does not match its locator")
        if [line.line_number for line in self.pdf_layout_lines] != list(
            range(1, len(self.pdf_layout_lines) + 1)
        ):
            raise ValueError("PDF layout lines must be a complete one-based sequence")
        lines_by_number = {line.line_number: line for line in self.pdf_layout_lines}
        mapped_ranges: list[tuple[int, int]] = []
        for line in self.pdf_layout_lines:
            if (
                self.locator.page_number is None
                or line.locator.page_number != self.locator.page_number
                or line.bounding_box.page_number != self.locator.page_number
            ):
                raise ValueError("PDF layout line belongs to a different text page")
            if line.character_start is None or line.character_end is None:
                continue
            if line.character_end > len(self.text):
                raise ValueError("PDF layout line range exceeds text block")
            if _locator_text(self.text[line.character_start : line.character_end]) != (
                _locator_text(line.text)
            ):
                raise ValueError("PDF layout line text does not match its range")
            mapped_ranges.append((line.character_start, line.character_end))
        ordered_ranges = sorted(mapped_ranges)
        for previous, current in pairwise(ordered_ranges):
            if current[0] < previous[1]:
                raise ValueError("PDF layout line ranges cannot overlap")
        for hint in self.heading_hints:
            if hint.layout_line_number is None:
                continue
            referenced_line = lines_by_number.get(hint.layout_line_number)
            if referenced_line is None:
                raise ValueError("heading hint references a missing PDF layout line")
            if hint.text != referenced_line.text or (
                hint.bounding_box is not None
                and hint.bounding_box != referenced_line.bounding_box
            ):
                raise ValueError("heading hint does not match its PDF layout line")
        return self


class ArtifactTableCell(M1Schema):
    """One lossless table cell, including optional spreadsheet formula state."""

    column_number: int = Field(ge=1, le=16_384)
    coordinate: str | None = Field(
        default=None,
        pattern=r"^[A-Z]{1,3}[1-9][0-9]{0,6}$",
        max_length=10,
    )
    value: ArtifactScalar
    display_text: str
    data_type: ArtifactCellType
    formula: str | None = Field(default=None, max_length=8192)
    cached_value: ArtifactScalar = None
    row_span: int = Field(default=1, ge=1, le=1_048_576)
    column_span: int = Field(default=1, ge=1, le=16_384)
    row_header: bool = False
    column_header: bool = False
    locator: SourceLocator
    bounding_box: ArtifactBoundingBox | None = None

    @model_validator(mode="after")
    def validate_formula(self) -> ArtifactTableCell:
        if self.data_type == "formula":
            if self.formula is None or not self.formula.startswith("="):
                raise ValueError("formula cells require an Excel formula")
            if self.value != self.cached_value:
                raise ValueError("formula cell value must equal cached value")
        elif self.formula is not None or self.cached_value is not None:
            raise ValueError("non-formula cells cannot contain formula state")
        if self.bounding_box is not None and (
            self.locator.page_number != self.bounding_box.page_number
        ):
            raise ValueError("cell bounding box page does not match its locator")
        return self


class ArtifactTableRow(M1Schema):
    """One physical or logical row with its original one-based number."""

    row_number: int = Field(ge=1, le=1_048_576)
    is_empty: bool
    locator: SourceLocator
    cells: list[ArtifactTableCell] = Field(max_length=16_384)

    @model_validator(mode="after")
    def validate_cells(self) -> ArtifactTableRow:
        if [cell.column_number for cell in self.cells] != list(
            range(1, len(self.cells) + 1)
        ):
            raise ValueError("artifact cells must be a complete one-based sequence")
        if self.is_empty != all(not cell.display_text.strip() for cell in self.cells):
            raise ValueError("artifact row empty flag does not match cells")
        return self


class ArtifactTableBlock(M1Schema):
    """One Word table, worksheet, or delimited table in source order."""

    kind: Literal["table"] = "table"
    block_id: str = Field(pattern=r"^b[0-9]{6}$")
    source_kind: Literal["docx_table", "worksheet", "csv", "document_table"]
    title: str | None = Field(default=None, max_length=200)
    locator: SourceLocator
    heading_path: list[str] = Field(default_factory=list, max_length=9)
    headers: list[str] = Field(default_factory=list, max_length=16_384)
    header_row_number: int | None = Field(default=None, ge=1, le=1_048_576)
    sheet_state: Literal["visible", "hidden", "veryHidden"] | None = None
    encoding: Literal["utf-8-sig", "utf-8", "gb18030"] | None = None
    delimiter: Literal[",", ";", "\t", "|"] | None = None
    rows: list[ArtifactTableRow] = Field(max_length=1_048_576)
    bounding_box: ArtifactBoundingBox | None = None

    @model_validator(mode="after")
    def validate_source_contract(self) -> ArtifactTableBlock:
        if [row.row_number for row in self.rows] != list(range(1, len(self.rows) + 1)):
            raise ValueError("artifact rows must be a complete one-based sequence")
        if self.header_row_number is not None and self.header_row_number > len(
            self.rows
        ):
            raise ValueError("artifact header row must exist")
        if self.source_kind == "worksheet":
            if (
                self.title is None
                or self.locator.sheet_name != self.title
                or self.sheet_state is None
                or self.encoding is not None
                or self.delimiter is not None
            ):
                raise ValueError("worksheet metadata does not match its source")
        elif self.source_kind == "csv":
            if (
                self.encoding is None
                or self.delimiter is None
                or self.sheet_state is not None
                or self.locator.sheet_name is not None
            ):
                raise ValueError("CSV metadata does not match its source")
        elif self.source_kind in {"docx_table", "document_table"} and (
            self.locator.table_number is None
            or self.sheet_state is not None
            or self.encoding is not None
            or self.delimiter is not None
        ):
            raise ValueError("document table metadata does not match its source")
        if self.locator.heading_path != self.heading_path:
            raise ValueError("table heading path does not match its locator")
        if self.bounding_box is not None and (
            self.locator.page_number != self.bounding_box.page_number
        ):
            raise ValueError("table bounding box page does not match its locator")
        return self


ArtifactBlock = Annotated[
    ArtifactTextBlock | ArtifactTableBlock,
    Field(discriminator="kind"),
]


class ArtifactStatistics(M1Schema):
    """Validated counts used for audit and later quality rules."""

    block_count: int = Field(ge=0, le=1_100_000)
    text_block_count: int = Field(ge=0, le=1_100_000)
    table_count: int = Field(ge=0, le=100_000)
    row_count: int = Field(ge=0, le=2_000_000)
    cell_count: int = Field(ge=0, le=2_000_000)
    formula_count: int = Field(ge=0, le=2_000_000)
    character_count: int = Field(ge=0, le=20_000_000)
    page_count: int | None = Field(default=None, ge=1, le=2000)
    sheet_count: int | None = Field(default=None, ge=1, le=1000)


class CanonicalParsedArtifact(M1Schema):
    """Stable project-owned document facts, independent of parser libraries."""

    schema_version: Literal["m2-canonical-parsed-artifact-v1"] = ARTIFACT_SCHEMA_VERSION
    content_hash_version: Literal["m2-canonical-content-v1"] = CONTENT_HASH_VERSION
    source_type: ArtifactSourceType
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parser: ArtifactParser
    blocks: list[ArtifactBlock] = Field(max_length=1_100_000)
    warnings: list[ArtifactWarning] = Field(max_length=6000)
    statistics: ArtifactStatistics
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_counts_and_hash(self) -> CanonicalParsedArtifact:
        if [block.block_id for block in self.blocks] != [
            f"b{number:06d}" for number in range(1, len(self.blocks) + 1)
        ]:
            raise ValueError("artifact block IDs must be stable and sequential")
        text_blocks = [
            block for block in self.blocks if isinstance(block, ArtifactTextBlock)
        ]
        if self.source_type != "docx" and any(
            block.source_kind != "document_text" for block in text_blocks
        ):
            raise ValueError("DOCX source text can only appear in DOCX artifacts")
        if self.source_type != "pdf" and any(
            block.pdf_layout_lines for block in text_blocks
        ):
            raise ValueError("PDF layout lines can only appear in PDF artifacts")
        tables = [
            block for block in self.blocks if isinstance(block, ArtifactTableBlock)
        ]
        rows = [row for table in tables for row in table.rows]
        cells = [cell for row in rows for cell in row.cells]
        expected = {
            "block_count": len(self.blocks),
            "text_block_count": len(text_blocks),
            "table_count": len(tables),
            "row_count": len(rows),
            "cell_count": len(cells),
            "formula_count": sum(cell.formula is not None for cell in cells),
            "character_count": sum(
                _text_character_count(block.text) for block in text_blocks
            )
            + sum(_cell_character_count(cell) for cell in cells),
            "page_count": self.statistics.page_count,
            "sheet_count": (
                sum(table.source_kind == "worksheet" for table in tables)
                if self.source_type == "xlsx" and self.parser.provider == "native"
                else None
            ),
        }
        if self.source_type == "pdf":
            if self.statistics.page_count is None:
                raise ValueError("PDF artifacts require a physical page count")
            located_pages = [
                block.locator.page_number
                for block in self.blocks
                if block.locator.page_number is not None
            ]
            if located_pages and max(located_pages) > self.statistics.page_count:
                raise ValueError("artifact locator exceeds its physical page count")
        elif self.statistics.page_count is not None:
            raise ValueError("only PDF artifacts may declare a page count")
        if self.statistics.model_dump() != expected:
            raise ValueError("artifact statistics do not match its blocks")
        expected_hash = calculate_artifact_content_sha256(
            self.model_dump(mode="json", exclude={"content_sha256"})
        )
        if self.content_sha256 != expected_hash:
            raise ValueError("artifact content hash does not match its content")
        return self


def calculate_artifact_content_sha256(payload: dict[str, Any]) -> str:
    """Hash canonical JSON bytes; callers must exclude content_sha256 itself."""

    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def build_canonical_artifact(
    *,
    source_type: ArtifactSourceType,
    source_sha256: str,
    parser_name: str,
    parser_version: str,
    blocks: list[ArtifactBlock],
    warnings: list[ArtifactWarning],
    source_character_count: int,
    provider: Literal["native", "docling"] = "native",
    adapter_version: str = NATIVE_ADAPTER_VERSION,
    page_count: int | None = None,
    sheet_count: int | None = None,
) -> CanonicalParsedArtifact:
    """Build and self-validate one deterministic artifact."""

    text_blocks = [block for block in blocks if isinstance(block, ArtifactTextBlock)]
    tables = [block for block in blocks if isinstance(block, ArtifactTableBlock)]
    rows = [row for table in tables for row in table.rows]
    cells = [cell for row in rows for cell in row.cells]
    statistics = ArtifactStatistics(
        block_count=len(blocks),
        text_block_count=len(text_blocks),
        table_count=len(tables),
        row_count=len(rows),
        cell_count=len(cells),
        formula_count=sum(cell.formula is not None for cell in cells),
        character_count=source_character_count,
        page_count=(
            page_count
            if page_count is not None
            else (len(text_blocks) if source_type == "pdf" else None)
        ),
        sheet_count=(
            sheet_count
            if sheet_count is not None
            else (
                sum(table.source_kind == "worksheet" for table in tables)
                if source_type == "xlsx" and provider == "native"
                else None
            )
        ),
    )
    payload: dict[str, Any] = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "content_hash_version": CONTENT_HASH_VERSION,
        "source_type": source_type,
        "source_sha256": source_sha256,
        "parser": ArtifactParser(
            provider=provider,
            name=parser_name,
            version=parser_version,
            adapter_version=adapter_version,
        ).model_dump(mode="json"),
        "blocks": [block.model_dump(mode="json") for block in blocks],
        "warnings": [warning.model_dump(mode="json") for warning in warnings],
        "statistics": statistics.model_dump(mode="json"),
    }
    return CanonicalParsedArtifact.model_validate(
        {
            **payload,
            "content_sha256": calculate_artifact_content_sha256(payload),
        }
    )


def artifact_to_markdown(artifact: CanonicalParsedArtifact) -> str:
    """Derive a deterministic view; Markdown is never the source of truth."""

    sections: list[str] = []
    for block in artifact.blocks:
        if isinstance(block, ArtifactTextBlock):
            if artifact.source_type == "pdf" and block.locator.page_number is not None:
                sections.append(f"<!-- page:{block.locator.page_number} -->")
            if block.source_kind == "docx_header":
                sections.append(f"[页眉]\n{block.text}\n[/页眉]")
                continue
            if block.source_kind == "docx_footer":
                sections.append(f"[页脚]\n{block.text}\n[/页脚]")
                continue
            if block.source_kind == "docx_image_ocr":
                sections.append(f"[图片内容]\n{block.text}\n[/图片内容]")
                continue
            if block.heading_level is not None and block.text:
                sections.append(f"{'#' * block.heading_level} {block.text}")
            elif block.text:
                sections.append(block.text)
            continue

        if block.title:
            sections.append(f"## {_escape_markdown_cell(block.title)}")
        table = _table_to_markdown(block)
        if table:
            sections.append(table)
    return "\n\n".join(sections).rstrip() + ("\n" if sections else "")


def _table_to_markdown(block: ArtifactTableBlock) -> str:
    if not block.rows:
        return ""
    width = max((len(row.cells) for row in block.rows), default=0)
    if width == 0:
        return ""
    rows = [
        [_escape_markdown_cell(_cell_markdown_text(cell)) for cell in row.cells]
        for row in block.rows
    ]
    header_index = (
        block.header_row_number - 1 if block.header_row_number is not None else 0
    )
    header = rows[header_index]
    body = [row for index, row in enumerate(rows) if index != header_index]
    lines = [
        f"| {' | '.join(header)} |",
        f"| {' | '.join('---' for _ in range(width))} |",
    ]
    lines.extend(f"| {' | '.join(row)} |" for row in body)
    return "\n".join(lines)


def _cell_markdown_text(cell: ArtifactTableCell) -> str:
    if cell.formula is None:
        return cell.display_text
    if cell.cached_value is None:
        return cell.formula
    return f"{cell.display_text} ({cell.formula})"


def _escape_markdown_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def _text_character_count(value: str) -> int:
    return sum(not character.isspace() for character in value)


def _locator_text(value: str) -> str:
    return " ".join(value.split())


def _cell_character_count(cell: ArtifactTableCell) -> int:
    values = (
        (cell.formula, _scalar_text(cell.cached_value))
        if cell.formula is not None
        else (cell.display_text,)
    )
    return sum(
        not character.isspace()
        for value in values
        if value is not None
        for character in value
    )


def _scalar_text(value: ArtifactScalar) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return str(value)
