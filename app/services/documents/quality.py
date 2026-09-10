"""Deterministic quality gate between safe Native parsing and Docling."""

from __future__ import annotations

import io
import unicodedata
import zipfile
from collections.abc import Iterator
from typing import Literal

import pymupdf
from pydantic import Field, model_validator

from app.schemas.common import M1Schema
from app.services.documents.artifacts import (
    ArtifactSourceType,
    ArtifactTableBlock,
    ArtifactTextBlock,
    CanonicalParsedArtifact,
)
from app.services.documents.parsers.base import DocumentParseError

ParseRoute = Literal["native", "docling", "hybrid"]
NativeTextHealthStatus = Literal["healthy", "suspect", "unusable"]
NATIVE_TEXT_HEALTH_POLICY_VERSION: Literal["m2-native-text-health-v1"] = (
    "m2-native-text-health-v1"
)
POST_PARSE_QUALITY_POLICY_VERSION: Literal["m2-post-parse-quality-v1"] = (
    "m2-post-parse-quality-v1"
)

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
    native_text_health: NativeTextHealthAssessment | None = None


class NativeTextHealthAssessment(M1Schema):
    """Versioned, deterministic signals explaining Native text usability."""

    policy_version: Literal["m2-native-text-health-v1"] = (
        NATIVE_TEXT_HEALTH_POLICY_VERSION
    )
    status: NativeTextHealthStatus
    reasons: list[str] = Field(min_length=1, max_length=20)
    character_count: int = Field(ge=0, le=20_000_000)
    valid_character_count: int = Field(ge=0, le=20_000_000)
    valid_character_ratio: float = Field(ge=0, le=1)
    content_page_count: int | None = Field(default=None, ge=0, le=2000)
    healthy_page_count: int | None = Field(default=None, ge=0, le=2000)
    healthy_page_ratio: float | None = Field(default=None, ge=0, le=1)
    minimum_character_count: int = Field(ge=1, le=500)
    minimum_page_character_count: int = Field(ge=1, le=500)
    minimum_valid_character_ratio: float = Field(ge=0.5, le=1)
    minimum_healthy_page_ratio: float = Field(ge=0.5, le=1)


class PostParsePageAssessment(M1Schema):
    """One PDF page comparison used by the post-parse release gate."""

    page_number: int = Field(ge=1, le=2000)
    native_character_count: int = Field(ge=0, le=20_000_000)
    final_character_count: int = Field(ge=0, le=20_000_000)
    native_image_count: int = Field(ge=0, le=100_000)
    status: Literal["accepted", "rejected", "ignored_blank", "not_evaluated"]
    reason: Literal[
        "final_page_text_sufficient",
        "native_text_missing_from_final_page",
        "image_page_ocr_unrecovered",
        "native_page_has_no_text_or_images",
        "native_page_baseline_inconclusive",
    ]


class PostParseDocxImageAssessment(M1Schema):
    """One DOCX inline-image OCR result and its deterministic consequence."""

    block_id: str = Field(pattern=r"^b[0-9]{6}$")
    image_number: int = Field(ge=1, le=1000)
    image_size_bytes: int = Field(gt=0, le=100 * 1024 * 1024)
    ocr_character_count: int = Field(ge=0, le=20_000_000)
    paragraph_character_count: int = Field(ge=0, le=20_000_000)
    status: Literal["accepted", "warning", "rejected", "below_threshold"]
    reason: Literal[
        "ocr_text_present",
        "empty_ocr_image_below_warning_threshold",
        "large_image_ocr_empty",
        "image_only_paragraph_ocr_empty",
        "document_body_insufficient_after_empty_ocr",
    ]


class PostParseQualityDecision(M1Schema):
    """Versioned release decision made after the final artifact is selected."""

    policy_version: Literal["m2-post-parse-quality-v1"] = (
        POST_PARSE_QUALITY_POLICY_VERSION
    )
    status: Literal["accepted", "rejected"]
    rejection_codes: list[str] = Field(default_factory=list, max_length=100)
    warning_codes: list[str] = Field(default_factory=list, max_length=100)
    native_character_count: int = Field(ge=0, le=20_000_000)
    final_character_count: int = Field(ge=0, le=20_000_000)
    character_retention_ratio: float | None = Field(default=None, ge=0)
    minimum_final_native_ratio: float = Field(ge=0.5, le=1)
    minimum_page_character_count: int = Field(ge=1, le=500)
    native_page_baseline_character_count: int = Field(ge=1, le=500)
    docx_empty_ocr_min_image_bytes: int = Field(
        ge=1024,
        le=25 * 1024 * 1024,
    )
    minimum_docx_body_character_count: int = Field(ge=1, le=500)
    native_page_count: int | None = Field(default=None, ge=1, le=2000)
    final_page_count: int | None = Field(default=None, ge=1, le=2000)
    page_assessments: list[PostParsePageAssessment] = Field(
        default_factory=list,
        max_length=2000,
    )
    docx_image_assessments: list[PostParseDocxImageAssessment] = Field(
        default_factory=list,
        max_length=1000,
    )

    @model_validator(mode="after")
    def validate_status(self) -> PostParseQualityDecision:
        expected_rejections: list[str] = []
        if (
            self.character_retention_ratio is not None
            and self.character_retention_ratio < self.minimum_final_native_ratio
        ):
            expected_rejections.append("final_text_retention_below_threshold")
        if self.native_page_count != self.final_page_count:
            expected_rejections.append("pdf_page_count_mismatch")
        for page in self.page_assessments:
            if page.reason == "native_text_missing_from_final_page":
                expected_rejections.append("pdf_page_text_regression")
            elif page.reason == "image_page_ocr_unrecovered":
                expected_rejections.append("pdf_image_page_ocr_unrecovered")
        for image in self.docx_image_assessments:
            if image.reason == "image_only_paragraph_ocr_empty":
                expected_rejections.append("docx_image_only_paragraph_ocr_empty")
            elif image.reason == "document_body_insufficient_after_empty_ocr":
                expected_rejections.append("docx_document_body_ocr_empty")
        expected_rejections = list(dict.fromkeys(expected_rejections))
        expected_warnings = (
            ["ocr_possible_failure"]
            if any(
                image.reason == "large_image_ocr_empty"
                for image in self.docx_image_assessments
            )
            else []
        )
        if self.rejection_codes != expected_rejections:
            raise ValueError("post-parse rejection codes do not match assessments")
        if self.warning_codes != expected_warnings:
            raise ValueError("post-parse warning codes do not match assessments")
        if (self.native_page_count is None) != (self.final_page_count is None):
            raise ValueError("post-parse PDF page counts must be paired")
        if self.page_assessments and self.native_page_count != len(
            self.page_assessments
        ):
            raise ValueError("post-parse page assessment count is incomplete")
        if (self.status == "rejected") != bool(expected_rejections):
            raise ValueError("post-parse status must match its rejection codes")
        if len(self.rejection_codes) != len(set(self.rejection_codes)):
            raise ValueError("post-parse rejection codes must be unique")
        if len(self.warning_codes) != len(set(self.warning_codes)):
            raise ValueError("post-parse warning codes must be unique")
        return self


def evaluate_post_parse_quality(
    *,
    native_artifact: CanonicalParsedArtifact,
    selected_artifact: CanonicalParsedArtifact,
    native_text_health: NativeTextHealthAssessment,
    minimum_final_native_ratio: float = 0.7,
    minimum_page_character_count: int = 10,
    native_page_baseline_character_count: int = 50,
    docx_empty_ocr_min_image_bytes: int = 5 * 1024,
    minimum_docx_body_character_count: int = 20,
) -> PostParseQualityDecision:
    """Reject deterministic truncation while retaining source-located warnings."""

    if (
        native_artifact.source_type != selected_artifact.source_type
        or native_artifact.source_sha256 != selected_artifact.source_sha256
        or native_text_health.character_count
        != native_artifact.statistics.character_count
    ):
        raise ValueError("post-parse inputs do not describe the same Native source")

    native_character_count = native_artifact.statistics.character_count
    final_character_count = selected_artifact.statistics.character_count
    retention_ratio = (
        round(final_character_count / native_character_count, 6)
        if native_text_health.status == "healthy" and native_character_count > 0
        else None
    )
    rejection_codes: list[str] = []
    warning_codes: list[str] = []
    if retention_ratio is not None and retention_ratio < minimum_final_native_ratio:
        rejection_codes.append("final_text_retention_below_threshold")

    page_assessments = _assess_pdf_pages(
        native_artifact,
        selected_artifact,
        minimum_page_character_count=minimum_page_character_count,
        native_page_baseline_character_count=(native_page_baseline_character_count),
        rejection_codes=rejection_codes,
    )
    docx_image_assessments = _assess_docx_images(
        selected_artifact,
        docx_empty_ocr_min_image_bytes=docx_empty_ocr_min_image_bytes,
        minimum_docx_body_character_count=minimum_docx_body_character_count,
        rejection_codes=rejection_codes,
        warning_codes=warning_codes,
    )
    rejection_codes = list(dict.fromkeys(rejection_codes))
    warning_codes = list(dict.fromkeys(warning_codes))
    return PostParseQualityDecision(
        status="rejected" if rejection_codes else "accepted",
        rejection_codes=rejection_codes,
        warning_codes=warning_codes,
        native_character_count=native_character_count,
        final_character_count=final_character_count,
        character_retention_ratio=retention_ratio,
        minimum_final_native_ratio=minimum_final_native_ratio,
        minimum_page_character_count=minimum_page_character_count,
        native_page_baseline_character_count=native_page_baseline_character_count,
        docx_empty_ocr_min_image_bytes=docx_empty_ocr_min_image_bytes,
        minimum_docx_body_character_count=minimum_docx_body_character_count,
        native_page_count=native_artifact.statistics.page_count,
        final_page_count=selected_artifact.statistics.page_count,
        page_assessments=page_assessments,
        docx_image_assessments=docx_image_assessments,
    )


def _assess_pdf_pages(
    native_artifact: CanonicalParsedArtifact,
    selected_artifact: CanonicalParsedArtifact,
    *,
    minimum_page_character_count: int,
    native_page_baseline_character_count: int,
    rejection_codes: list[str],
) -> list[PostParsePageAssessment]:
    if native_artifact.source_type != "pdf":
        return []
    if native_artifact.statistics.page_count != selected_artifact.statistics.page_count:
        rejection_codes.append("pdf_page_count_mismatch")

    native_pages = {
        block.page.page_number: block.page
        for block in native_artifact.blocks
        if isinstance(block, ArtifactTextBlock) and block.page is not None
    }
    final_page_characters = _page_character_counts(selected_artifact)
    assessments: list[PostParsePageAssessment] = []
    for page_number in range(1, (native_artifact.statistics.page_count or 0) + 1):
        native_page = native_pages.get(page_number)
        if native_page is None:
            raise ValueError("Native PDF page properties are incomplete")
        final_count = final_page_characters.get(page_number, 0)
        if final_count >= minimum_page_character_count:
            status = "accepted"
            reason = "final_page_text_sufficient"
        elif native_page.character_count >= native_page_baseline_character_count:
            status = "rejected"
            reason = "native_text_missing_from_final_page"
            rejection_codes.append("pdf_page_text_regression")
        elif (
            native_page.character_count < minimum_page_character_count
            and native_page.image_count > 0
        ):
            status = "rejected"
            reason = "image_page_ocr_unrecovered"
            rejection_codes.append("pdf_image_page_ocr_unrecovered")
        elif (
            native_page.character_count < minimum_page_character_count
            and native_page.image_count == 0
        ):
            status = "ignored_blank"
            reason = "native_page_has_no_text_or_images"
        else:
            status = "not_evaluated"
            reason = "native_page_baseline_inconclusive"
        assessments.append(
            PostParsePageAssessment(
                page_number=page_number,
                native_character_count=native_page.character_count,
                final_character_count=final_count,
                native_image_count=native_page.image_count,
                status=status,  # type: ignore[arg-type]
                reason=reason,  # type: ignore[arg-type]
            )
        )
    return assessments


def _page_character_counts(artifact: CanonicalParsedArtifact) -> dict[int, int]:
    counts: dict[int, int] = {}
    for block in artifact.blocks:
        if isinstance(block, ArtifactTextBlock):
            page_number = block.locator.page_number
            if page_number is not None:
                counts[page_number] = counts.get(page_number, 0) + _text_count(
                    block.text
                )
            continue
        for row in block.rows:
            for cell in row.cells:
                page_number = cell.locator.page_number or block.locator.page_number
                if page_number is not None:
                    counts[page_number] = counts.get(page_number, 0) + _text_count(
                        cell.display_text
                    )
    return counts


def _assess_docx_images(
    artifact: CanonicalParsedArtifact,
    *,
    docx_empty_ocr_min_image_bytes: int,
    minimum_docx_body_character_count: int,
    rejection_codes: list[str],
    warning_codes: list[str],
) -> list[PostParseDocxImageAssessment]:
    if artifact.source_type != "docx":
        return []
    paragraph_characters: dict[tuple[int | None, int | None], int] = {}
    for block in artifact.blocks:
        if (
            not isinstance(block, ArtifactTextBlock)
            or block.source_kind != "document_text"
        ):
            continue
        key = (block.locator.block_number, block.locator.paragraph_number)
        paragraph_characters[key] = paragraph_characters.get(key, 0) + _text_count(
            block.text
        )
    body_character_count = _docx_body_character_count(artifact)

    assessments: list[PostParseDocxImageAssessment] = []
    for block in artifact.blocks:
        if (
            not isinstance(block, ArtifactTextBlock)
            or block.source_kind != "docx_image_ocr"
        ):
            continue
        source = block.docx_source
        if (
            source is None
            or source.image_number is None
            or source.image_size_bytes is None
        ):
            raise ValueError("DOCX image source metadata is incomplete")
        ocr_character_count = _text_count(block.text)
        key = (block.locator.block_number, block.locator.paragraph_number)
        paragraph_character_count = paragraph_characters.get(key, 0)
        if ocr_character_count > 0:
            status = "accepted"
            reason = "ocr_text_present"
        elif source.image_size_bytes <= docx_empty_ocr_min_image_bytes:
            status = "below_threshold"
            reason = "empty_ocr_image_below_warning_threshold"
        elif paragraph_character_count == 0:
            status = "rejected"
            reason = "image_only_paragraph_ocr_empty"
            rejection_codes.append("docx_image_only_paragraph_ocr_empty")
        elif body_character_count < minimum_docx_body_character_count:
            status = "rejected"
            reason = "document_body_insufficient_after_empty_ocr"
            rejection_codes.append("docx_document_body_ocr_empty")
        else:
            status = "warning"
            reason = "large_image_ocr_empty"
            warning_codes.append("ocr_possible_failure")
        assessments.append(
            PostParseDocxImageAssessment(
                block_id=block.block_id,
                image_number=source.image_number,
                image_size_bytes=source.image_size_bytes,
                ocr_character_count=ocr_character_count,
                paragraph_character_count=paragraph_character_count,
                status=status,  # type: ignore[arg-type]
                reason=reason,  # type: ignore[arg-type]
            )
        )
    return assessments


def _docx_body_character_count(artifact: CanonicalParsedArtifact) -> int:
    count = 0
    for block in artifact.blocks:
        if isinstance(block, ArtifactTextBlock):
            if block.source_kind == "document_text":
                count += _text_count(block.text)
            continue
        for row in block.rows:
            for cell in row.cells:
                count += _text_count(cell.display_text)
    return count


def _text_count(value: str) -> int:
    return sum(not character.isspace() for character in value)


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
    minimum_character_count: int = 20,
    minimum_page_character_count: int = 20,
    minimum_valid_character_ratio: float = 0.9,
    minimum_healthy_page_ratio: float = 0.8,
) -> ParseQualityDecision:
    """Choose enhancement deterministically; tags never bypass Native parsing."""

    tags = sorted(set(complexity_tags))
    warning_codes = sorted({warning.code for warning in native_artifact.warnings})
    source_type = native_artifact.source_type
    reasons: list[str] = []
    health = assess_native_text_health(
        native_artifact,
        minimum_character_count=minimum_character_count,
        minimum_page_character_count=minimum_page_character_count,
        minimum_valid_character_ratio=minimum_valid_character_ratio,
        minimum_healthy_page_ratio=minimum_healthy_page_ratio,
    )

    if source_type == "csv":
        route: ParseRoute = "native"
        reasons.append("csv_native_deterministic")
    elif source_type == "pdf":
        matching_tags = sorted(_PDF_COMPLEXITY_TAGS.intersection(tags))
        reasons.append(f"native_text_{health.status}")
        if health.status == "healthy":
            reasons.extend(f"complexity_{tag}_advisory" for tag in matching_tags)
            route = "native"
        else:
            reasons.extend(health.reasons)
            reasons.extend(f"complexity_{tag}" for tag in matching_tags)
            route = "docling"
    elif source_type == "docx":
        matching_tags = sorted(_DOCX_COMPLEXITY_TAGS.intersection(tags))
        reasons.extend(
            f"complexity_{tag}_native_visual_extraction" for tag in matching_tags
        )
        route = "native"
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
        native_text_health=health,
    )


def assess_native_text_health(
    native_artifact: CanonicalParsedArtifact,
    *,
    minimum_character_count: int = 20,
    minimum_page_character_count: int = 20,
    minimum_valid_character_ratio: float = 0.9,
    minimum_healthy_page_ratio: float = 0.8,
) -> NativeTextHealthAssessment:
    """Classify Native text without semantic models or unbounded work."""

    character_count = 0
    valid_character_count = 0
    for value in _artifact_text_values(native_artifact):
        for character in value:
            if character.isspace():
                continue
            character_count += 1
            valid_character_count += _is_valid_text_character(character)
    valid_character_ratio = (
        round(valid_character_count / character_count, 6) if character_count else 0.0
    )

    content_page_count: int | None = None
    healthy_page_count: int | None = None
    healthy_page_ratio: float | None = None
    pages = [
        block.page
        for block in native_artifact.blocks
        if isinstance(block, ArtifactTextBlock) and block.page is not None
    ]
    if native_artifact.source_type == "pdf":
        content_pages = [
            page for page in pages if page.character_count > 0 or page.image_count > 0
        ]
        content_page_count = len(content_pages)
        healthy_page_count = sum(
            page.character_count >= minimum_page_character_count
            for page in content_pages
        )
        healthy_page_ratio = (
            round(healthy_page_count / content_page_count, 6)
            if content_page_count
            else 0.0
        )

    warning_codes = {warning.code for warning in native_artifact.warnings}
    reasons: list[str] = []
    if character_count == 0:
        status: NativeTextHealthStatus = "unusable"
        reasons.append("native_text_empty")
    elif valid_character_count == 0:
        status = "unusable"
        reasons.append("native_text_no_valid_characters")
    else:
        if character_count < minimum_character_count:
            reasons.append("native_text_character_count_low")
        if valid_character_ratio < minimum_valid_character_ratio:
            reasons.append("native_valid_character_ratio_low")
        if (
            healthy_page_ratio is not None
            and healthy_page_ratio < minimum_healthy_page_ratio
        ):
            reasons.append("native_text_page_coverage_low")
        if "scanned_page_suspected" in warning_codes:
            reasons.append("native_scanned_page_signal")
        if "low_text_page" in warning_codes:
            reasons.append("native_low_text_page_signal")
        status = "suspect" if reasons else "healthy"

    if status == "unusable":
        if "scanned_page_suspected" in warning_codes:
            reasons.append("native_scanned_page_signal")
        if any(page.character_count == 0 and page.image_count > 0 for page in pages):
            reasons.append("native_image_page_without_text")
    if not reasons:
        reasons.append("native_text_readable")

    return NativeTextHealthAssessment(
        status=status,
        reasons=list(dict.fromkeys(reasons)),
        character_count=character_count,
        valid_character_count=valid_character_count,
        valid_character_ratio=valid_character_ratio,
        content_page_count=content_page_count,
        healthy_page_count=healthy_page_count,
        healthy_page_ratio=healthy_page_ratio,
        minimum_character_count=minimum_character_count,
        minimum_page_character_count=minimum_page_character_count,
        minimum_valid_character_ratio=minimum_valid_character_ratio,
        minimum_healthy_page_ratio=minimum_healthy_page_ratio,
    )


def _artifact_text_values(artifact: CanonicalParsedArtifact) -> Iterator[str]:
    for block in artifact.blocks:
        if isinstance(block, ArtifactTextBlock):
            yield block.text
            continue
        if isinstance(block, ArtifactTableBlock):
            for row in block.rows:
                for cell in row.cells:
                    if cell.formula is not None:
                        yield cell.formula
                        if cell.cached_value is not None:
                            yield _scalar_text(cell.cached_value)
                    else:
                        yield cell.display_text


def _scalar_text(value: object) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return str(value)


def _is_valid_text_character(character: str) -> bool:
    if character == "\ufffd":
        return False
    return unicodedata.category(character) not in {"Cc", "Cf", "Cs", "Co", "Cn"}


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
