"""Strict file metadata, lifecycle, and public response contracts for M2."""

from __future__ import annotations

import re
from typing import Annotated, Literal, TypeAlias
from uuid import UUID

from pydantic import (
    AwareDatetime,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.schemas.common import M1Schema

FileExtension = Literal[".pdf", ".docx", ".xlsx", ".csv"]
FileStatus = Literal[
    "uploaded",
    "validating",
    "parsing",
    "indexing",
    "ready",
    "failed",
    "soft_deleted",
]
Sha256 = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$"),
]
FileReadSourceType = Literal["pdf", "docx", "xlsx", "csv"]
_CELL_RANGE_PATTERN = re.compile(
    r"^(?P<start_column>[A-Z]{1,3})(?P<start_row>[1-9][0-9]{0,6})"
    r"(?::(?P<end_column>[A-Z]{1,3})(?P<end_row>[1-9][0-9]{0,6}))?$"
)
_MAX_PDF_READ_PAGES = 3
_MAX_TABULAR_READ_ROWS = 50
_MAX_XLSX_READ_CELLS = 1_000


class PdfFileReadLocator(M1Schema):
    """One caller-selected PDF window whose size cannot exceed server policy."""

    source_type: Literal["pdf"] = "pdf"
    page_start: int = Field(strict=True, ge=1, le=2000)
    page_end: int | None = Field(default=None, strict=True, ge=1, le=2000)

    @model_validator(mode="after")
    def validate_page_window(self) -> PdfFileReadLocator:
        end = self.page_end if self.page_end is not None else self.page_start
        if end < self.page_start or end - self.page_start + 1 > _MAX_PDF_READ_PAGES:
            raise ValueError("PDF read window must contain at most three ordered pages")
        return self


class DocxFileReadLocator(M1Schema):
    """One exact DOCX structural coordinate, never a path or broad text query."""

    source_type: Literal["docx"] = "docx"
    block_number: int | None = Field(default=None, strict=True, ge=1, le=1_100_000)
    paragraph_number: int | None = Field(
        default=None,
        strict=True,
        ge=1,
        le=1_100_000,
    )
    table_number: int | None = Field(default=None, strict=True, ge=1, le=100_000)

    @model_validator(mode="after")
    def require_one_coordinate(self) -> DocxFileReadLocator:
        if (
            sum(
                value is not None
                for value in (
                    self.block_number,
                    self.paragraph_number,
                    self.table_number,
                )
            )
            != 1
        ):
            raise ValueError("DOCX read locator requires exactly one coordinate")
        return self


class XlsxFileReadLocator(M1Schema):
    """One bounded worksheet cell rectangle or physical row window."""

    source_type: Literal["xlsx"] = "xlsx"
    sheet_name: str = Field(strict=True, min_length=1, max_length=31)
    cell_range: str | None = Field(
        default=None,
        strict=True,
        max_length=64,
        pattern=r"^[A-Z]{1,3}[1-9][0-9]{0,6}(?::[A-Z]{1,3}[1-9][0-9]{0,6})?$",
    )
    row_start: int | None = Field(
        default=None,
        strict=True,
        ge=1,
        le=1_048_576,
    )
    row_end: int | None = Field(
        default=None,
        strict=True,
        ge=1,
        le=1_048_576,
    )

    @model_validator(mode="after")
    def validate_selection(self) -> XlsxFileReadLocator:
        has_cells = self.cell_range is not None
        has_rows = self.row_start is not None or self.row_end is not None
        if has_cells == has_rows:
            raise ValueError("XLSX read locator requires cells or rows, not both")
        if has_rows:
            if self.row_start is None or self.row_end is None:
                raise ValueError("XLSX row window requires both boundaries")
            if (
                self.row_end < self.row_start
                or self.row_end - self.row_start + 1 > _MAX_TABULAR_READ_ROWS
            ):
                raise ValueError("XLSX row window must contain at most fifty rows")
            return self

        if self.cell_range is None:
            raise ValueError("XLSX cell range is required")
        match = _CELL_RANGE_PATTERN.fullmatch(self.cell_range)
        if match is None:
            raise ValueError("XLSX cell range is invalid")
        start_column = _excel_column_number(match.group("start_column"))
        end_column = _excel_column_number(
            match.group("end_column") or match.group("start_column")
        )
        start_row = int(match.group("start_row"))
        end_row = int(match.group("end_row") or match.group("start_row"))
        if (
            start_column > end_column
            or start_row > end_row
            or end_column > 16_384
            or end_row > 1_048_576
            or end_row - start_row + 1 > _MAX_TABULAR_READ_ROWS
            or (end_column - start_column + 1) * (end_row - start_row + 1)
            > _MAX_XLSX_READ_CELLS
        ):
            raise ValueError("XLSX cell range exceeds the bounded worksheet window")
        return self


class CsvFileReadLocator(M1Schema):
    """One bounded CSV physical-row window."""

    source_type: Literal["csv"] = "csv"
    row_start: int = Field(strict=True, ge=1, le=1_048_576)
    row_end: int = Field(strict=True, ge=1, le=1_048_576)

    @model_validator(mode="after")
    def validate_row_window(self) -> CsvFileReadLocator:
        if (
            self.row_end < self.row_start
            or self.row_end - self.row_start + 1 > _MAX_TABULAR_READ_ROWS
        ):
            raise ValueError("CSV read window must contain at most fifty rows")
        return self


FileReadLocator: TypeAlias = Annotated[
    PdfFileReadLocator | DocxFileReadLocator | XlsxFileReadLocator | CsvFileReadLocator,
    Field(discriminator="source_type"),
]


class ReadUploadedFileInput(M1Schema):
    """Only public file identity and an optional bounded structural locator."""

    file_id: UUID = Field(
        description="当前用户获权的公开文件ID；不得填写路径或Storage Key"
    )
    locator: FileReadLocator | None = Field(
        default=None,
        description="可选的PDF、DOCX、XLSX或CSV有界定位；省略时只返回有限预览",
    )


def _excel_column_number(value: str) -> int:
    number = 0
    for character in value:
        number = number * 26 + ord(character) - ord("A") + 1
    return number


class FileRegistrationInput(M1Schema):
    """Safe metadata accepted after Storage has produced trusted object facts."""

    original_name: str = Field(min_length=1, max_length=255)
    extension: FileExtension
    category: Literal["uploads"] = "uploads"

    @field_validator("original_name")
    @classmethod
    def reject_path_like_original_name(cls, value: str) -> str:
        if (
            value != value.strip()
            or "/" in value
            or "\\" in value
            or value in {".", ".."}
            or any(ord(character) < 32 for character in value)
        ):
            raise ValueError("original_name must be a base filename")
        return value

    @model_validator(mode="after")
    def require_matching_extension(self) -> FileRegistrationInput:
        if not self.original_name.lower().endswith(self.extension):
            raise ValueError("original_name extension does not match extension")
        return self


class FileStateUpdate(M1Schema):
    """One requested transition; failure details are bounded and optional elsewhere."""

    status: FileStatus
    error_message: str | None = Field(default=None, min_length=1, max_length=1000)

    @field_validator("error_message")
    @classmethod
    def reject_control_characters(cls, value: str | None) -> str | None:
        if value is not None and any(ord(character) < 32 for character in value):
            raise ValueError("error_message must not contain control characters")
        return value

    @model_validator(mode="after")
    def validate_error_for_target_state(self) -> FileStateUpdate:
        if self.status == "failed" and self.error_message is None:
            raise ValueError("failed status requires error_message")
        if self.status not in {"failed", "soft_deleted"} and self.error_message:
            raise ValueError("error_message is only valid for failed or soft_deleted")
        return self


class FileResponse(M1Schema):
    """Authorized file metadata without Storage keys or filesystem paths."""

    file_id: UUID
    owner_user_id: UUID
    original_name: str = Field(min_length=1, max_length=255)
    extension: FileExtension
    mime_type: str = Field(min_length=3, max_length=127)
    size_bytes: int = Field(ge=0)
    sha256: Sha256
    category: Literal["uploads"]
    status: FileStatus
    error_message: str | None = Field(default=None, min_length=1, max_length=1000)
    created_at: AwareDatetime
    deleted_at: AwareDatetime | None = None


class FileListResponse(M1Schema):
    """A bounded file list prepared for the later HTTP endpoint."""

    items: list[FileResponse] = Field(max_length=100)


class FileUploadResponse(M1Schema):
    """Atomic multipart upload result for a bounded batch."""

    items: list[FileResponse] = Field(min_length=1, max_length=10)
