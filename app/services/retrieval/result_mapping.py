"""Shared safe source-locator mapping for retrieval candidates."""

from __future__ import annotations

from typing import Protocol, cast

from app.schemas.retrieval import (
    CsvRetrievalSourceLocator,
    DocxRetrievalSourceLocator,
    PdfRetrievalSourceLocator,
    RetrievalSourceLocator,
    XlsxRetrievalSourceLocator,
)
from app.services.documents.parsers.base import SourceLocator


class RetrievalSourceCandidate(Protocol):
    @property
    def file_extension(self) -> str: ...

    @property
    def heading_path(self) -> list[object]: ...

    @property
    def page_numbers(self) -> list[object]: ...

    @property
    def source_spans(self) -> list[object]: ...

    @property
    def table_json(self) -> dict[str, object] | None: ...


def source_locator_from_candidate(
    candidate: RetrievalSourceCandidate,
) -> RetrievalSourceLocator:
    """Map persisted coordinates without exposing Storage implementation details."""

    source = _first_source_locator(candidate.source_spans)
    headings = _string_list(candidate.heading_path)
    pages = _positive_int_list(candidate.page_numbers)
    extension = candidate.file_extension.lower()
    if extension == ".pdf":
        if source.page_number is not None and source.page_number not in pages:
            pages = sorted({*pages, source.page_number})
        return PdfRetrievalSourceLocator(
            page_number=source.page_number,
            page_numbers=pages,
            block_number=source.block_number,
            paragraph_number=source.paragraph_number,
            table_number=source.table_number,
            heading_path=headings,
        )
    if extension == ".docx":
        return DocxRetrievalSourceLocator(
            page_number=source.page_number,
            page_numbers=pages,
            block_number=source.block_number,
            paragraph_number=source.paragraph_number,
            table_number=source.table_number,
            heading_path=headings,
        )
    if extension == ".xlsx":
        table = candidate.table_json or {}
        return XlsxRetrievalSourceLocator(
            sheet_name=_required_string(table.get("sheet_name", source.sheet_name)),
            cell_range=_optional_string(table.get("cell_range", source.cell_range)),
            row_start=_optional_positive_int(
                table.get("row_start", source.row_start or source.row_number)
            ),
            row_end=_optional_positive_int(
                table.get("row_end", source.row_end or source.row_number)
            ),
            heading_path=headings,
        )
    if extension == ".csv":
        table = candidate.table_json or {}
        return CsvRetrievalSourceLocator(
            row_start=_required_positive_int(
                table.get("row_start", source.row_start or source.row_number)
            ),
            row_end=_required_positive_int(
                table.get("row_end", source.row_end or source.row_number)
            ),
        )
    raise ValueError("unsupported stored file extension")


def _first_source_locator(source_spans: list[object]) -> SourceLocator:
    if not source_spans or not isinstance(source_spans[0], dict):
        raise ValueError("source span is missing")
    raw_locator = source_spans[0].get("start_locator")
    return SourceLocator.model_validate(raw_locator)


def _string_list(values: list[object]) -> list[str]:
    if any(not isinstance(value, str) for value in values):
        raise ValueError("heading path is invalid")
    return [str(value) for value in values]


def _positive_int_list(values: list[object]) -> list[int]:
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value < 1
        for value in values
    ):
        raise ValueError("page numbers are invalid")
    return sorted({cast(int, value) for value in values})


def _required_string(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("required source string is missing")
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return _required_string(value)


def _required_positive_int(value: object) -> int:
    result = _optional_positive_int(value)
    if result is None:
        raise ValueError("required source integer is missing")
    return result


def _optional_positive_int(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError("source integer is invalid")
    return value
