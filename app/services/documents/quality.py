"""Deterministic quality gate between safe Native parsing and Docling."""

from __future__ import annotations

import io
import zipfile
from typing import Literal

import pymupdf
from pydantic import Field

from app.schemas.common import M1Schema
from app.services.documents.artifacts import ArtifactSourceType, CanonicalParsedArtifact
from app.services.documents.parsers.base import DocumentParseError

ParseRoute = Literal["native", "docling", "hybrid"]

_PDF_COMPLEXITY_TAGS = frozenset(
    {
        "image_only",
        "scanned_pdf",
        "ocr_required",
        "two_column",
        "reading_order",
        "repeated_header_footer",
        "merged_header",
        "borderless_table",
        "table_semantics",
        "detected_two_column",
        "detected_document_table",
    }
)
_DOCX_COMPLEXITY_TAGS = frozenset(
    {
        "header_footer",
        "image_text",
        "body_visual",
        "detected_embedded_media",
    }
)
_XLSX_COMPLEXITY_TAGS = frozenset(
    {
        "merged_multilevel_header",
        "multiple_regions",
        "formulas",
        "detected_merged_cells",
    }
)


class ParseQualityDecision(M1Schema):
    """Auditable decision made only after Native safety checks pass."""

    route: ParseRoute
    reasons: list[str] = Field(min_length=1, max_length=30)
    complexity_tags: list[str] = Field(default_factory=list, max_length=30)
    native_warning_codes: list[str] = Field(default_factory=list, max_length=6000)
    native_character_count: int = Field(ge=0, le=20_000_000)


def infer_complexity_tags(
    source_type: ArtifactSourceType,
    content: bytes,
) -> tuple[str, ...]:
    """Inspect bounded, Native-approved bytes for deterministic format features."""

    try:
        if source_type == "pdf":
            return _inspect_pdf(content)
        if source_type == "docx":
            return _inspect_docx(content)
        if source_type == "xlsx":
            return _inspect_xlsx(content)
        return ()
    except Exception:  # noqa: BLE001 - inspection details stay private.
        raise DocumentParseError from None


def decide_parse_route(
    native_artifact: CanonicalParsedArtifact,
    *,
    complexity_tags: tuple[str, ...] = (),
) -> ParseQualityDecision:
    """Choose enhancement deterministically; tags never bypass Native parsing."""

    tags = sorted(set(complexity_tags))
    warning_codes = sorted({warning.code for warning in native_artifact.warnings})
    source_type = native_artifact.source_type
    reasons: list[str] = []

    if source_type == "csv":
        route: ParseRoute = "native"
        reasons.append("csv_native_deterministic")
    elif source_type == "pdf":
        low_text_codes = {
            "empty_page",
            "low_text_page",
            "scanned_page_suspected",
            "empty_document",
        }
        if low_text_codes.intersection(warning_codes):
            reasons.append("native_low_text_or_scan_signal")
        matching_tags = sorted(_PDF_COMPLEXITY_TAGS.intersection(tags))
        reasons.extend(f"complexity_{tag}" for tag in matching_tags)
        route = "docling" if reasons else "native"
    elif source_type == "docx":
        matching_tags = sorted(_DOCX_COMPLEXITY_TAGS.intersection(tags))
        reasons.extend(f"complexity_{tag}" for tag in matching_tags)
        route = "hybrid" if reasons else "native"
    else:
        matching_tags = sorted(_XLSX_COMPLEXITY_TAGS.intersection(tags))
        reasons.extend(f"complexity_{tag}" for tag in matching_tags)
        route = "hybrid" if reasons else "native"

    if not reasons:
        reasons.append("native_quality_sufficient")
    return ParseQualityDecision(
        route=route,
        reasons=reasons,
        complexity_tags=tags,
        native_warning_codes=warning_codes,
        native_character_count=native_artifact.statistics.character_count,
    )


def _inspect_pdf(content: bytes) -> tuple[str, ...]:
    tags: set[str] = set()
    document = pymupdf.open(stream=content, filetype="pdf")  # type: ignore[no-untyped-call]
    try:
        for page_number in range(document.page_count):
            page = document.load_page(page_number)  # type: ignore[no-untyped-call]
            width = float(page.rect.width)
            blocks = [
                block
                for block in page.get_text("blocks", sort=True)  # type: ignore[no-untyped-call]
                if str(block[4]).strip()
            ]
            centers = [(float(block[0]) + float(block[2])) / 2 for block in blocks]
            left_count = sum(center < width * 0.42 for center in centers)
            right_count = sum(
                width * 0.55 < center < width * 0.85 for center in centers
            )
            if left_count >= 3 and right_count >= 3:
                tags.add("detected_two_column")
            if len(page.get_drawings()) >= 4:  # type: ignore[no-untyped-call]
                tags.add("detected_document_table")
    finally:
        document.close()  # type: ignore[no-untyped-call]
    return tuple(sorted(tags))


def _inspect_docx(content: bytes) -> tuple[str, ...]:
    tags: set[str] = set()
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = archive.namelist()
        furniture = [
            name
            for name in names
            if name.startswith(("word/header", "word/footer")) and name.endswith(".xml")
        ]
        if any(b"<w:t" in archive.read(name) for name in furniture):
            tags.add("detected_header_footer")
        if any(name.startswith("word/media/") for name in names):
            tags.add("detected_embedded_media")
    return tuple(sorted(tags))


def _inspect_xlsx(content: bytes) -> tuple[str, ...]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        worksheet_names = [
            name
            for name in archive.namelist()
            if name.startswith("xl/worksheets/") and name.endswith(".xml")
        ]
        if any(b"<mergeCells" in archive.read(name) for name in worksheet_names):
            return ("detected_merged_cells",)
    return ()
