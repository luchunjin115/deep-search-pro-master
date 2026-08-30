"""Bounded CSV extraction with deterministic encoding and delimiter metadata."""

from __future__ import annotations

import csv
import io
from typing import TYPE_CHECKING, BinaryIO, Literal, Self, TypeAlias

import pandas as pd  # type: ignore[import-untyped]
from pydantic import Field, model_validator

from app.schemas.common import M1Schema
from app.services.documents.parsers.base import (
    DocumentLimitError,
    DocumentParseError,
    ParserWarning,
    SourceLocator,
)

if TYPE_CHECKING:
    from app.core.config import Settings

PARSER_NAME: Literal["pandas"] = "pandas"
PARSER_VERSION = f"m2-csv-v1+pandas-{pd.__version__}"
_READ_CHUNK_BYTES = 1024 * 1024
_DELIMITERS = (",", ";", "\t", "|")

CsvEncoding: TypeAlias = Literal["utf-8-sig", "utf-8", "gb18030"]
CsvDelimiter: TypeAlias = Literal[",", ";", "\t", "|"]


class CsvRow(M1Schema):
    """One logical CSV record, including records whose fields are all empty."""

    row_number: int = Field(ge=1, le=1_000_000)
    is_empty: bool
    values: list[str] = Field(max_length=10_000)
    locator: SourceLocator

    @model_validator(mode="after")
    def validate_values_and_locator(self) -> CsvRow:
        if self.is_empty != all(not value.strip() for value in self.values):
            raise ValueError("CSV row empty flag does not match values")
        if (
            self.locator.row_start != self.row_number
            or self.locator.row_end != self.row_number
        ):
            raise ValueError("CSV row locator does not match row")
        return self


class CsvParseResult(M1Schema):
    """Safe CSV result with encoding, delimiter, rows, and stable row ranges."""

    parser_name: Literal["pandas"] = PARSER_NAME
    parser_version: str = Field(min_length=1, max_length=64)
    source_type: Literal["csv"] = "csv"
    encoding: CsvEncoding
    delimiter: CsvDelimiter
    row_count: int = Field(ge=0, le=1_000_000)
    column_count: int = Field(ge=0, le=10_000)
    non_empty_row_count: int = Field(ge=0, le=1_000_000)
    header_row_number: int | None = Field(default=None, ge=1, le=1_000_000)
    headers: list[str] = Field(max_length=10_000)
    character_count: int = Field(ge=0, le=20_000_000)
    rows: list[CsvRow] = Field(max_length=1_000_000)
    warnings: list[ParserWarning] = Field(max_length=10)

    @model_validator(mode="after")
    def validate_shape_and_counts(self) -> CsvParseResult:
        if self.row_count != len(self.rows):
            raise ValueError("CSV row_count does not match rows")
        if [row.row_number for row in self.rows] != list(
            range(1, self.row_count + 1)
        ):
            raise ValueError("CSV rows must be a complete one-based sequence")
        if any(len(row.values) != self.column_count for row in self.rows):
            raise ValueError("CSV rows must match column_count")
        if self.non_empty_row_count != sum(not row.is_empty for row in self.rows):
            raise ValueError("CSV non_empty_row_count does not match rows")
        expected_header = next(
            (row.row_number for row in self.rows if not row.is_empty),
            None,
        )
        if self.header_row_number != expected_header:
            raise ValueError("CSV header row must be the first non-empty row")
        if self.headers and len(self.headers) != self.column_count:
            raise ValueError("CSV headers must match column_count")
        actual_characters = sum(
            not character.isspace()
            for row in self.rows
            for value in row.values
            for character in value
        )
        if self.character_count != actual_characters:
            raise ValueError("CSV character_count does not match rows")
        return self


class CsvParser:
    """Decode a small supported encoding set, then parse logical rows with Pandas."""

    def __init__(
        self,
        *,
        max_source_bytes: int = 25 * 1024 * 1024,
        max_rows: int = 200_000,
        max_columns: int = 500,
        max_cells: int = 500_000,
        max_extracted_characters: int = 5_000_000,
    ) -> None:
        limits = (
            max_source_bytes,
            max_rows,
            max_columns,
            max_cells,
            max_extracted_characters,
        )
        if any(limit <= 0 for limit in limits) or (
            max_rows > 1_000_000
            or max_columns > 10_000
            or max_cells > 2_000_000
            or max_extracted_characters > 20_000_000
        ):
            raise ValueError("CSV parser limits must be positive and bounded")
        self._max_source_bytes = max_source_bytes
        self._max_rows = max_rows
        self._max_columns = max_columns
        self._max_cells = max_cells
        self._max_extracted_characters = max_extracted_characters

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        return cls(
            max_source_bytes=settings.upload_max_file_size_bytes,
            max_rows=settings.csv_max_rows,
            max_columns=settings.csv_max_columns,
            max_cells=settings.csv_max_cells,
            max_extracted_characters=settings.csv_max_extracted_characters,
        )

    @property
    def parser_name(self) -> str:
        return PARSER_NAME

    @property
    def parser_version(self) -> str:
        return PARSER_VERSION

    def parse(self, stream: BinaryIO) -> CsvParseResult:
        source = self._read_bounded(stream)
        text, encoding = _decode(source)
        if "\x00" in text:
            raise DocumentParseError
        if sum(not character.isspace() for character in text) > (
            self._max_extracted_characters
        ):
            raise DocumentLimitError
        delimiter = _detect_delimiter(text)
        frame = self._read_frame(text, delimiter)
        row_count, column_count = frame.shape
        if (
            row_count > self._max_rows
            or column_count > self._max_columns
            or row_count * column_count > self._max_cells
        ):
            raise DocumentLimitError

        rows: list[CsvRow] = []
        character_count = 0
        for row_number, values in enumerate(frame.itertuples(index=False, name=None), 1):
            normalized = [_normalize_csv_value(value) for value in values]
            character_count += sum(
                not character.isspace()
                for value in normalized
                for character in value
            )
            if character_count > self._max_extracted_characters:
                raise DocumentLimitError
            rows.append(
                CsvRow(
                    row_number=row_number,
                    is_empty=all(not value.strip() for value in normalized),
                    values=normalized,
                    locator=SourceLocator(
                        row_start=row_number,
                        row_end=row_number,
                    ),
                )
            )

        header_row = next((row for row in rows if not row.is_empty), None)
        warnings = []
        if character_count == 0:
            warnings.append(
                ParserWarning(
                    code="empty_csv",
                    message="CSV没有可提取的字段内容",
                    locator=SourceLocator(),
                )
            )
        return CsvParseResult(
            parser_version=self.parser_version,
            encoding=encoding,
            delimiter=delimiter,
            row_count=row_count,
            column_count=column_count,
            non_empty_row_count=sum(not row.is_empty for row in rows),
            header_row_number=(header_row.row_number if header_row is not None else None),
            headers=(header_row.values if header_row is not None else []),
            character_count=character_count,
            rows=rows,
            warnings=warnings,
        )

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

    @staticmethod
    def _read_frame(text: str, delimiter: CsvDelimiter) -> pd.DataFrame:
        if not text:
            return pd.DataFrame()
        try:
            return pd.read_csv(
                io.StringIO(text),
                sep=delimiter,
                header=None,
                dtype=str,
                keep_default_na=False,
                na_filter=False,
                skip_blank_lines=False,
                engine="python",
                on_bad_lines="error",
            )
        except pd.errors.EmptyDataError:
            return pd.DataFrame()
        except Exception:  # noqa: BLE001 - parser details stay private.
            raise DocumentParseError from None


def _decode(source: bytes) -> tuple[str, CsvEncoding]:
    if source.startswith(b"\xef\xbb\xbf"):
        try:
            return source.decode("utf-8-sig"), "utf-8-sig"
        except UnicodeDecodeError:
            raise DocumentParseError from None
    try:
        return source.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        return source.decode("gb18030"), "gb18030"
    except UnicodeDecodeError:
        raise DocumentParseError from None


def _detect_delimiter(text: str) -> CsvDelimiter:
    sample = text[:65_536]
    try:
        detected = csv.Sniffer().sniff(sample, delimiters="".join(_DELIMITERS))
        if detected.delimiter in _DELIMITERS:
            return detected.delimiter  # type: ignore[return-value]
    except csv.Error:
        pass
    counts = {delimiter: sample.count(delimiter) for delimiter in _DELIMITERS}
    selected = max(_DELIMITERS, key=counts.__getitem__)
    return selected  # type: ignore[return-value]


def _normalize_csv_value(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)
