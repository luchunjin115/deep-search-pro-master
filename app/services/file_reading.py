"""Authorized, bounded reads from validated parsed-file artifacts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Protocol, cast
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import (
    FileNotFoundError,
    FileReadError,
    FileReadLocatorError,
    FileStateConflictError,
)
from app.repositories.files import ReadableParsedFile
from app.schemas.auth import CurrentUser
from app.schemas.file_reading import (
    FILE_READ_MAX_CHARACTERS,
    FileReadSection,
    ReadUploadedFileResult,
)
from app.schemas.files import (
    CsvFileReadLocator,
    DocxFileReadLocator,
    FileReadSourceType,
    PdfFileReadLocator,
    ReadUploadedFileInput,
    XlsxFileReadLocator,
)
from app.schemas.retrieval import (
    CsvRetrievalSourceLocator,
    DocxRetrievalSourceLocator,
    PdfRetrievalSourceLocator,
    RetrievalSourceLocator,
    XlsxRetrievalSourceLocator,
)
from app.services.documents.artifacts import (
    ArtifactBlock,
    ArtifactTableBlock,
    ArtifactTableRow,
    ArtifactTextBlock,
    CanonicalParsedArtifact,
)
from app.services.documents.parsers.base import SourceLocator
from app.services.documents.routing import RoutedParseResult
from app.services.storage import StorageBackend, StorageError, validate_storage_key

_SOURCE_TYPE_BY_EXTENSION: dict[str, FileReadSourceType] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".csv": "csv",
}
_CELL_RANGE_PATTERN = re.compile(
    r"^(?P<start_column>[A-Z]{1,3})(?P<start_row>[1-9][0-9]{0,6})"
    r"(?::(?P<end_column>[A-Z]{1,3})(?P<end_row>[1-9][0-9]{0,6}))?$"
)
_MAX_SECTIONS = 12
_MAX_PDF_PAGES = 3
_MAX_TABLE_ROWS = 50
_MAX_XLSX_CELLS = 1_000


class ParsedFileReader(Protocol):
    """One fixed authorization-aware metadata read required by this service."""

    def find_readable_parsed_file(
        self,
        *,
        tenant_id: UUID,
        user_id: UUID,
        role_names: tuple[str, ...],
        market_scopes: tuple[str, ...],
        file_id: UUID,
    ) -> ReadableParsedFile | None: ...


@dataclass(frozen=True, slots=True)
class _SelectedSection:
    kind: Literal["text", "table"]
    locator: RetrievalSourceLocator
    content: str
    truncated: bool = False


class FileReadingService:
    """Re-authorize a file ID and expose only a small deterministic artifact view."""

    def __init__(
        self,
        repository: ParsedFileReader,
        storage: StorageBackend,
        *,
        maximum_artifact_bytes: int,
    ) -> None:
        if maximum_artifact_bytes < 1:
            raise ValueError("maximum_artifact_bytes must be positive")
        self._repository = repository
        self._storage = storage
        self._maximum_artifact_bytes = maximum_artifact_bytes

    def read_uploaded_file(
        self,
        current_user: CurrentUser,
        request: ReadUploadedFileInput,
    ) -> ReadUploadedFileResult:
        """Return one authorized bounded preview without exposing private metadata."""

        try:
            row = self._repository.find_readable_parsed_file(
                tenant_id=current_user.tenant_id,
                user_id=current_user.user_id,
                role_names=tuple(current_user.roles),
                market_scopes=tuple(current_user.market_scopes),
                file_id=request.file_id,
            )
        except SQLAlchemyError:
            raise FileReadError from None
        if row is None:
            raise FileNotFoundError

        source_type = _SOURCE_TYPE_BY_EXTENSION.get(row.extension)
        if source_type is None:
            raise FileReadError
        if request.locator is not None and request.locator.source_type != source_type:
            raise FileReadLocatorError
        if row.parse_status != "ready" or row.parsed_storage_key is None:
            raise FileStateConflictError

        storage_key = self._validate_artifact_key(row, current_user.tenant_id)
        routed = self._load_routed_artifact(storage_key)
        artifact = routed.selected_artifact
        if (
            artifact.source_type != source_type
            or artifact.source_sha256 != row.sha256
            or artifact.source_sha256 != row.content_hash
        ):
            raise FileReadError

        try:
            selected, more_available = _select_sections(artifact, request)
            sections, truncated = _bound_sections(
                selected, more_available=more_available
            )
            if not sections:
                raise FileReadLocatorError
            return ReadUploadedFileResult(
                file_id=row.file_id,
                document_id=row.document_id,
                version_id=row.version_id,
                version_no=row.version_no,
                original_name=row.original_name,
                source_type=source_type,
                is_active_version=row.is_active_version,
                sections=sections,
                total_characters=sum(len(section.content) for section in sections),
                truncated=truncated,
                synthetic_data=True,
            )
        except (FileReadError, FileReadLocatorError):
            raise
        except (ValidationError, ValueError, TypeError):
            raise FileReadError from None

    @staticmethod
    def _validate_artifact_key(row: ReadableParsedFile, tenant_id: UUID) -> str:
        try:
            key = validate_storage_key(row.parsed_storage_key or "")
        except StorageError:
            raise FileReadError from None
        parts = key.split("/")
        if (
            parts[0] != str(tenant_id)
            or parts[1] != "parsed"
            or parts[4] != f"{row.version_id}.json"
        ):
            raise FileReadError
        return key

    def _load_routed_artifact(self, storage_key: str) -> RoutedParseResult:
        try:
            with self._storage.open(storage_key) as stream:
                payload = stream.read(self._maximum_artifact_bytes + 1)
            if (
                not isinstance(payload, bytes)
                or len(payload) > self._maximum_artifact_bytes
            ):
                raise FileReadError
            return RoutedParseResult.model_validate_json(payload)
        except FileReadError:
            raise
        except (StorageError, ValidationError, ValueError, TypeError, UnicodeError):
            raise FileReadError from None


def _select_sections(
    artifact: CanonicalParsedArtifact,
    request: ReadUploadedFileInput,
) -> tuple[list[_SelectedSection], bool]:
    locator = request.locator
    if locator is None:
        return _select_preview(artifact)
    if isinstance(locator, PdfFileReadLocator):
        return _select_pdf(artifact, locator), False
    if isinstance(locator, DocxFileReadLocator):
        return _select_docx(artifact, locator), False
    if isinstance(locator, XlsxFileReadLocator):
        return _select_xlsx(artifact, locator), False
    if isinstance(locator, CsvFileReadLocator):
        return _select_csv(artifact, locator), False
    raise FileReadLocatorError


def _select_preview(
    artifact: CanonicalParsedArtifact,
) -> tuple[list[_SelectedSection], bool]:
    sections: list[_SelectedSection] = []
    more_available = False
    for block in artifact.blocks:
        if artifact.source_type == "pdf" and len(sections) >= _MAX_PDF_PAGES:
            more_available = True
            break
        if len(sections) >= _MAX_SECTIONS:
            more_available = True
            break
        selected = _preview_block(artifact.source_type, block)
        if selected is not None:
            sections.append(selected)
    return sections, more_available


def _preview_block(
    source_type: FileReadSourceType,
    block: ArtifactBlock,
) -> _SelectedSection | None:
    if isinstance(block, ArtifactTextBlock):
        if not block.text.strip():
            return None
        return _SelectedSection(
            kind="text",
            locator=_public_locator(source_type, block.locator),
            content=block.text,
        )
    rows = block.rows[:_MAX_TABLE_ROWS]
    column_start = 1
    column_end: int | None = None
    truncated = len(rows) < len(block.rows)
    if source_type == "xlsx" and rows:
        maximum_columns = max(1, _MAX_XLSX_CELLS // len(rows))
        widest = max((len(row.cells) for row in rows), default=0)
        column_end = min(widest, maximum_columns)
        truncated = truncated or column_end < widest
    content = _render_rows(rows, column_start=column_start, column_end=column_end)
    if not content:
        return None
    if source_type == "xlsx":
        locator: RetrievalSourceLocator = XlsxRetrievalSourceLocator(
            sheet_name=block.locator.sheet_name or block.title or "Sheet",
            row_start=rows[0].row_number,
            row_end=rows[-1].row_number,
            heading_path=block.heading_path,
        )
    elif source_type == "csv":
        locator = CsvRetrievalSourceLocator(
            row_start=rows[0].row_number,
            row_end=rows[-1].row_number,
        )
    else:
        locator = _public_locator(source_type, block.locator)
    return _SelectedSection(
        kind="table",
        locator=locator,
        content=content,
        truncated=truncated,
    )


def _select_pdf(
    artifact: CanonicalParsedArtifact,
    locator: PdfFileReadLocator,
) -> list[_SelectedSection]:
    page_end = locator.page_end or locator.page_start
    sections = [
        _SelectedSection(
            kind="text" if isinstance(block, ArtifactTextBlock) else "table",
            locator=_public_locator("pdf", block.locator),
            content=(
                block.text
                if isinstance(block, ArtifactTextBlock)
                else _render_rows(block.rows)
            ),
        )
        for block in artifact.blocks
        if block.locator.page_number is not None
        and locator.page_start <= block.locator.page_number <= page_end
    ]
    return [section for section in sections if section.content.strip()]


def _select_docx(
    artifact: CanonicalParsedArtifact,
    locator: DocxFileReadLocator,
) -> list[_SelectedSection]:
    def matches(block: ArtifactBlock) -> bool:
        return (
            (
                locator.block_number is not None
                and block.locator.block_number == locator.block_number
            )
            or (
                locator.paragraph_number is not None
                and isinstance(block, ArtifactTextBlock)
                and block.locator.paragraph_number == locator.paragraph_number
            )
            or (
                locator.table_number is not None
                and isinstance(block, ArtifactTableBlock)
                and block.locator.table_number == locator.table_number
            )
        )

    sections: list[_SelectedSection] = []
    for block in artifact.blocks:
        if not matches(block):
            continue
        content = (
            block.text
            if isinstance(block, ArtifactTextBlock)
            else _render_rows(block.rows)
        )
        if content.strip():
            sections.append(
                _SelectedSection(
                    kind=block.kind,
                    locator=_public_locator("docx", block.locator),
                    content=content,
                )
            )
    return sections


def _select_xlsx(
    artifact: CanonicalParsedArtifact,
    locator: XlsxFileReadLocator,
) -> list[_SelectedSection]:
    table = next(
        (
            block
            for block in artifact.blocks
            if isinstance(block, ArtifactTableBlock)
            and block.source_kind == "worksheet"
            and block.locator.sheet_name == locator.sheet_name
        ),
        None,
    )
    if table is None:
        return []
    if locator.cell_range is not None:
        column_start, row_start, column_end, row_end = _parse_cell_range(
            locator.cell_range
        )
        public_locator: RetrievalSourceLocator = XlsxRetrievalSourceLocator(
            sheet_name=locator.sheet_name,
            cell_range=locator.cell_range,
        )
    else:
        row_start = cast(int, locator.row_start)
        row_end = cast(int, locator.row_end)
        column_start = 1
        column_end = None
        public_locator = XlsxRetrievalSourceLocator(
            sheet_name=locator.sheet_name,
            row_start=row_start,
            row_end=row_end,
        )
    rows = [row for row in table.rows if row_start <= row.row_number <= row_end]
    truncated = False
    if locator.cell_range is None and rows:
        widest = max((len(row.cells) for row in rows), default=0)
        maximum_columns = max(1, _MAX_XLSX_CELLS // len(rows))
        column_end = min(widest, maximum_columns)
        truncated = column_end < widest
    content = _render_rows(
        rows,
        column_start=column_start,
        column_end=column_end,
    )
    if not content:
        return []
    return [
        _SelectedSection(
            kind="table",
            locator=public_locator,
            content=content,
            truncated=truncated,
        )
    ]


def _select_csv(
    artifact: CanonicalParsedArtifact,
    locator: CsvFileReadLocator,
) -> list[_SelectedSection]:
    table = next(
        (
            block
            for block in artifact.blocks
            if isinstance(block, ArtifactTableBlock) and block.source_kind == "csv"
        ),
        None,
    )
    if table is None:
        return []
    rows = [
        row
        for row in table.rows
        if locator.row_start <= row.row_number <= locator.row_end
    ]
    content = _render_rows(rows)
    if not content:
        return []
    return [
        _SelectedSection(
            kind="table",
            locator=CsvRetrievalSourceLocator(
                row_start=locator.row_start,
                row_end=locator.row_end,
            ),
            content=content,
        )
    ]


def _bound_sections(
    selected: list[_SelectedSection],
    *,
    more_available: bool,
) -> tuple[list[FileReadSection], bool]:
    sections: list[FileReadSection] = []
    remaining = FILE_READ_MAX_CHARACTERS
    truncated = more_available
    for index, candidate in enumerate(selected):
        if remaining == 0 or len(sections) == _MAX_SECTIONS:
            truncated = True
            break
        content = candidate.content[:remaining]
        if not content:
            continue
        section_truncated = candidate.truncated or len(content) < len(candidate.content)
        sections.append(
            FileReadSection(
                kind=candidate.kind,
                locator=candidate.locator,
                content=content,
                truncated=section_truncated,
            )
        )
        remaining -= len(content)
        truncated = truncated or section_truncated
        if index < len(selected) - 1 and remaining == 0:
            truncated = True
    return sections, truncated


def _public_locator(
    source_type: FileReadSourceType,
    locator: SourceLocator,
) -> RetrievalSourceLocator:
    if source_type == "pdf":
        return PdfRetrievalSourceLocator(
            page_number=locator.page_number,
            block_number=locator.block_number,
            paragraph_number=locator.paragraph_number,
            table_number=locator.table_number,
            heading_path=locator.heading_path,
        )
    if source_type == "docx":
        return DocxRetrievalSourceLocator(
            page_number=locator.page_number,
            block_number=locator.block_number,
            paragraph_number=locator.paragraph_number,
            table_number=locator.table_number,
            heading_path=locator.heading_path,
        )
    raise FileReadError


def _render_rows(
    rows: list[ArtifactTableRow],
    *,
    column_start: int = 1,
    column_end: int | None = None,
) -> str:
    if not rows:
        return ""
    end = column_end or max((len(row.cells) for row in rows), default=0)
    if end < column_start:
        return ""
    labels = [f"C{column}" for column in range(column_start, end + 1)]
    lines = [
        f"| row | {' | '.join(labels)} |",
        f"| --- | {' | '.join('---' for _ in labels)} |",
    ]
    for row in rows:
        values = [_cell_text(row, column) for column in range(column_start, end + 1)]
        lines.append(
            f"| {row.row_number} | {' | '.join(_escape_cell(value) for value in values)} |"
        )
    return "\n".join(lines)


def _cell_text(row: ArtifactTableRow, column: int) -> str:
    if column > len(row.cells):
        return ""
    cell = row.cells[column - 1]
    if cell.formula is None or cell.cached_value is not None:
        return cell.display_text
    return cell.formula


def _escape_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def _parse_cell_range(value: str) -> tuple[int, int, int, int]:
    match = _CELL_RANGE_PATTERN.fullmatch(value)
    if match is None:
        raise FileReadLocatorError
    start_column = _excel_column_number(match.group("start_column"))
    start_row = int(match.group("start_row"))
    end_column = _excel_column_number(
        match.group("end_column") or match.group("start_column")
    )
    end_row = int(match.group("end_row") or match.group("start_row"))
    return start_column, start_row, end_column, end_row


def _excel_column_number(value: str) -> int:
    number = 0
    for character in value:
        number = number * 26 + ord(character) - ord("A") + 1
    return number
