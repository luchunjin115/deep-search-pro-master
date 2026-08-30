"""Shared parser contracts, safe failures, and source locators for M2."""

from __future__ import annotations

from typing import BinaryIO, Generic, Literal, Protocol, TypeVar

from pydantic import Field, model_validator

from app.schemas.common import M1Schema

ParserWarningCode = Literal[
    "empty_page",
    "low_text_page",
    "scanned_page_suspected",
    "empty_document",
    "empty_sheet",
    "empty_csv",
]


class SourceLocator(M1Schema):
    """Stable user-facing location inside text and tabular documents."""

    page_number: int | None = Field(default=None, ge=1)
    block_number: int | None = Field(default=None, ge=1)
    paragraph_number: int | None = Field(default=None, ge=1)
    table_number: int | None = Field(default=None, ge=1)
    row_number: int | None = Field(default=None, ge=1)
    column_number: int | None = Field(default=None, ge=1)
    heading_path: list[str] = Field(default_factory=list, max_length=9)
    sheet_name: str | None = Field(default=None, min_length=1, max_length=31)
    cell_range: str | None = Field(default=None, min_length=1, max_length=50)
    row_start: int | None = Field(default=None, ge=1)
    row_end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_docx_location(self) -> SourceLocator:
        if self.paragraph_number is not None and self.table_number is not None:
            raise ValueError("paragraph and table locations are mutually exclusive")
        if (self.row_number is not None or self.column_number is not None) and not (
            self.table_number is not None or self.sheet_name is not None
        ):
            raise ValueError("row and column locations require a table or sheet")
        if (self.row_number is None) != (self.column_number is None):
            raise ValueError("row and column locations must be provided together")
        if (self.row_start is None) != (self.row_end is None):
            raise ValueError("row range bounds must be provided together")
        if (
            self.row_start is not None
            and self.row_end is not None
            and self.row_start > self.row_end
        ):
            raise ValueError("row range start cannot exceed end")
        if self.cell_range is not None and self.sheet_name is None:
            raise ValueError("cell ranges require a sheet name")
        return self


class ParserWarning(M1Schema):
    """Safe, structured warning that never contains paths or library errors."""

    code: ParserWarningCode
    message: str = Field(min_length=1, max_length=200)
    locator: SourceLocator


class DocumentParseError(Exception):
    """A malformed or unsupported source could not be safely parsed."""

    def __init__(self, message: str = "文档解析失败") -> None:
        super().__init__(message)


class DocumentEncryptedError(DocumentParseError):
    """The source requires a password and is outside the M2 text boundary."""

    def __init__(self) -> None:
        super().__init__("文档已加密，无法解析")


class DocumentLimitError(DocumentParseError):
    """The source exceeds one configured parser resource limit."""

    def __init__(self) -> None:
        super().__init__("文档超过解析安全限制")


class DocumentEnhancementError(DocumentParseError):
    """A complex-document provider failed without exposing private details."""

    def __init__(self) -> None:
        super().__init__("复杂文档增强解析失败")


ParseResultT_co = TypeVar("ParseResultT_co", covariant=True)


class DocumentParser(Protocol, Generic[ParseResultT_co]):
    """One deterministic parser that consumes a managed binary stream."""

    @property
    def parser_name(self) -> str: ...

    @property
    def parser_version(self) -> str: ...

    def parse(self, stream: BinaryIO) -> ParseResultT_co: ...
