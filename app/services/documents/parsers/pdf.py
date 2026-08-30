"""Bounded text-layer PDF extraction with one-based page locators."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING, BinaryIO, Literal, Self

import pymupdf
from pydantic import Field, ValidationError, model_validator

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

PARSER_NAME: Literal["pymupdf"] = "pymupdf"
PARSER_VERSION = f"m2-pdf-v1+pymupdf-{pymupdf.VersionBind}"
_READ_CHUNK_BYTES = 1024 * 1024


class PdfHeadingHint(M1Schema):
    """A font-size-based heading clue, not a guaranteed semantic heading."""

    text: str = Field(min_length=1, max_length=200)
    level: int = Field(ge=1, le=6)
    font_size: float = Field(gt=0, le=1000)
    locator: SourceLocator


class PdfPageText(M1Schema):
    """Text and stable metadata extracted from one physical PDF page."""

    page_number: int = Field(ge=1)
    text: str
    character_count: int = Field(ge=0)
    image_count: int = Field(ge=0)
    low_text: bool
    heading_hints: list[PdfHeadingHint] = Field(max_length=100)

    @model_validator(mode="after")
    def validate_character_count(self) -> PdfPageText:
        actual = sum(not character.isspace() for character in self.text)
        if self.character_count != actual:
            raise ValueError("character_count does not match text")
        return self


class PdfParseResult(M1Schema):
    """Safe PDF parser output without filesystem paths or Storage keys."""

    parser_name: Literal["pymupdf"] = PARSER_NAME
    parser_version: str = Field(min_length=1, max_length=64)
    source_type: Literal["pdf"] = "pdf"
    page_count: int = Field(ge=1, le=2000)
    pages: list[PdfPageText] = Field(min_length=1, max_length=2000)
    warnings: list[ParserWarning] = Field(max_length=6000)

    @model_validator(mode="after")
    def validate_page_sequence(self) -> PdfParseResult:
        expected = list(range(1, self.page_count + 1))
        if [page.page_number for page in self.pages] != expected:
            raise ValueError("pages must be a complete one-based sequence")
        return self


@dataclass(frozen=True, slots=True)
class _LineCandidate:
    page_number: int
    text: str
    font_size: float


@dataclass(frozen=True, slots=True)
class _PageDraft:
    page_number: int
    text: str
    character_count: int
    image_count: int
    lines: tuple[_LineCandidate, ...]


class PdfParser:
    """Extract only embedded text; low-text image pages are warned, never OCR'd."""

    def __init__(
        self,
        *,
        max_source_bytes: int = 25 * 1024 * 1024,
        max_pages: int = 500,
        max_extracted_characters: int = 5_000_000,
        low_text_character_threshold: int = 20,
    ) -> None:
        limits = (
            max_source_bytes,
            max_pages,
            max_extracted_characters,
            low_text_character_threshold,
        )
        if any(limit <= 0 for limit in limits) or max_pages > 2000:
            raise ValueError("PDF parser limits must be positive and bounded")
        self._max_source_bytes = max_source_bytes
        self._max_pages = max_pages
        self._max_extracted_characters = max_extracted_characters
        self._low_text_character_threshold = low_text_character_threshold

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        """Build one parser from the process-wide validated M2 limits."""

        return cls(
            max_source_bytes=settings.upload_max_file_size_bytes,
            max_pages=settings.pdf_max_pages,
            max_extracted_characters=settings.pdf_max_extracted_characters,
            low_text_character_threshold=settings.pdf_low_text_character_threshold,
        )

    @property
    def parser_name(self) -> str:
        return PARSER_NAME

    @property
    def parser_version(self) -> str:
        return PARSER_VERSION

    def parse(self, stream: BinaryIO) -> PdfParseResult:
        source = self._read_bounded(stream)
        try:
            document = pymupdf.open(  # type: ignore[no-untyped-call]
                stream=source,
                filetype="pdf",
            )
        except Exception:  # noqa: BLE001 - PyMuPDF errors must not escape.
            raise DocumentParseError from None

        try:
            if document.needs_pass:
                raise DocumentEncryptedError
            if document.page_count <= 0:
                raise DocumentParseError
            if document.page_count > self._max_pages:
                raise DocumentLimitError

            drafts: list[_PageDraft] = []
            total_characters = 0
            for index in range(document.page_count):
                draft = self._extract_page(document[index], index + 1)
                total_characters += draft.character_count
                if total_characters > self._max_extracted_characters:
                    raise DocumentLimitError
                drafts.append(draft)
        except (DocumentEncryptedError, DocumentLimitError, DocumentParseError):
            raise
        except Exception:  # noqa: BLE001 - malformed page internals stay private.
            raise DocumentParseError from None
        finally:
            document.close()  # type: ignore[no-untyped-call]

        try:
            headings = self._heading_hints(drafts)
            pages = [
                PdfPageText(
                    page_number=draft.page_number,
                    text=draft.text,
                    character_count=draft.character_count,
                    image_count=draft.image_count,
                    low_text=(
                        draft.character_count < self._low_text_character_threshold
                    ),
                    heading_hints=headings.get(draft.page_number, []),
                )
                for draft in drafts
            ]
            return PdfParseResult(
                parser_version=self.parser_version,
                page_count=len(pages),
                pages=pages,
                warnings=self._warnings(pages),
            )
        except ValidationError:
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

    @staticmethod
    def _extract_page(page: pymupdf.Page, page_number: int) -> _PageDraft:
        raw_text = page.get_text("text", sort=True)  # type: ignore[no-untyped-call]
        normalized_lines = [line.rstrip() for line in raw_text.splitlines()]
        text = "\n".join(normalized_lines).strip()
        character_count = sum(not character.isspace() for character in text)
        raw_dict = page.get_text("dict", sort=True)  # type: ignore[no-untyped-call]
        lines: list[_LineCandidate] = []
        for block in raw_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                line_text = "".join(str(span.get("text", "")) for span in spans).strip()
                sizes = [
                    float(span.get("size", 0))
                    for span in spans
                    if isfinite(float(span.get("size", 0)))
                ]
                if line_text and sizes:
                    lines.append(
                        _LineCandidate(
                            page_number=page_number,
                            text=line_text,
                            font_size=max(sizes),
                        )
                    )
        return _PageDraft(
            page_number=page_number,
            text=text,
            character_count=character_count,
            image_count=len(page.get_images(full=True)),  # type: ignore[no-untyped-call]
            lines=tuple(lines),
        )

    @staticmethod
    def _heading_hints(
        drafts: list[_PageDraft],
    ) -> dict[int, list[PdfHeadingHint]]:
        all_lines = [line for draft in drafts for line in draft.lines]
        if not all_lines:
            return {}
        weighted_sizes: Counter[float] = Counter()
        for line in all_lines:
            weighted_sizes[round(line.font_size, 1)] += max(1, len(line.text))
        body_size = weighted_sizes.most_common(1)[0][0]
        minimum_heading_size = max(body_size + 1.0, body_size * 1.2)
        candidates = [
            line
            for line in all_lines
            if line.font_size >= minimum_heading_size
            and line.font_size <= 1000
            and 1 < len(line.text) <= 200
            and any(character.isalnum() for character in line.text)
        ]
        heading_sizes = sorted(
            {round(line.font_size, 1) for line in candidates},
            reverse=True,
        )
        levels = {size: min(index + 1, 6) for index, size in enumerate(heading_sizes)}
        by_page: dict[int, list[PdfHeadingHint]] = {}
        for line in candidates:
            page_headings = by_page.setdefault(line.page_number, [])
            if len(page_headings) >= 100:
                continue
            page_headings.append(
                PdfHeadingHint(
                    text=line.text,
                    level=levels[round(line.font_size, 1)],
                    font_size=round(line.font_size, 2),
                    locator=SourceLocator(page_number=line.page_number),
                )
            )
        return by_page

    @staticmethod
    def _warnings(pages: list[PdfPageText]) -> list[ParserWarning]:
        warnings: list[ParserWarning] = []
        for page in pages:
            locator = SourceLocator(page_number=page.page_number)
            if page.character_count == 0:
                warnings.append(
                    ParserWarning(
                        code="empty_page",
                        message="该页没有可提取的文字",
                        locator=locator,
                    )
                )
            elif page.low_text:
                warnings.append(
                    ParserWarning(
                        code="low_text_page",
                        message="该页可提取文字很少",
                        locator=locator,
                    )
                )
            if page.low_text and page.image_count > 0:
                warnings.append(
                    ParserWarning(
                        code="scanned_page_suspected",
                        message="该页疑似扫描图片，M2不会执行OCR",
                        locator=locator,
                    )
                )
        return warnings
