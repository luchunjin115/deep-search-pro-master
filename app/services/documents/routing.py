"""Safe parser router: Native first, optional Docling second, Canonical out."""

from __future__ import annotations

import hashlib
import io
import logging
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import filetype  # type: ignore[import-untyped]
from pydantic import Field, model_validator

from app.schemas.common import M1Schema
from app.services.documents.artifacts import (
    ArtifactSourceType,
    CanonicalParsedArtifact,
)
from app.services.documents.parsers import (
    CsvParser,
    DocumentEnhancementError,
    DocumentParseError,
    DocumentQualityRejected,
    DocxParser,
    PdfParser,
    XlsxParser,
)
from app.services.documents.parsers.docling import (
    DoclingProvider,
    LocalDoclingProvider,
    adapt_docling_snapshot,
)
from app.services.documents.parsers.native import adapt_native_parse_result
from app.services.documents.quality import (
    ParseQualityDecision,
    ParseRoute,
    PostParseQualityDecision,
    decide_parse_route,
    evaluate_post_parse_quality,
    infer_complexity_tags,
)

if TYPE_CHECKING:
    from app.core.config import Settings

_SOURCE_TYPES: dict[str, ArtifactSourceType] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".csv": "csv",
}
_ZIP_TYPE_MEMBERS = {
    "docx": frozenset({"[Content_Types].xml", "word/document.xml"}),
    "xlsx": frozenset({"[Content_Types].xml", "xl/workbook.xml"}),
}
_LOGGER = logging.getLogger(__name__)


class ArtifactComparison(M1Schema):
    """Small audit record; it compares structure without merging Office facts."""

    native_block_count: int = Field(ge=0)
    docling_block_count: int = Field(ge=0)
    native_character_count: int = Field(ge=0)
    docling_character_count: int = Field(ge=0)
    native_table_count: int = Field(ge=0)
    docling_table_count: int = Field(ge=0)
    native_formula_count: int = Field(ge=0)
    docling_formula_count: int = Field(ge=0)


class RoutedParseResult(M1Schema):
    """Canonical result plus enough evidence to explain every route."""

    schema_version: Literal["m2-routed-parsed-document-v1"] = (
        "m2-routed-parsed-document-v1"
    )
    route: ParseRoute
    reasons: list[str] = Field(min_length=1, max_length=30)
    quality: ParseQualityDecision
    selected_artifact: CanonicalParsedArtifact
    native_artifact: CanonicalParsedArtifact
    docling_artifact: CanonicalParsedArtifact | None = None
    comparison: ArtifactComparison | None = None
    post_parse_quality: PostParseQualityDecision | None = None

    @model_validator(mode="after")
    def validate_route_contract(self) -> RoutedParseResult:
        if self.route != self.quality.route or self.reasons != self.quality.reasons:
            raise ValueError("route and quality decision do not match")
        artifacts = [self.native_artifact, self.selected_artifact]
        if self.docling_artifact is not None:
            artifacts.append(self.docling_artifact)
        if len({artifact.source_sha256 for artifact in artifacts}) != 1:
            raise ValueError("routed artifacts must describe the same source")
        if self.route == "native":
            if (
                self.docling_artifact is not None
                or self.comparison is not None
                or self.selected_artifact != self.native_artifact
            ):
                raise ValueError("Native route cannot contain a Docling result")
        elif self.docling_artifact is None or self.comparison is None:
            raise ValueError("enhanced routes require a Docling comparison")
        elif (
            self.route == "docling" and self.selected_artifact != self.docling_artifact
        ):
            raise ValueError("Docling route must select the Docling artifact")
        elif self.route == "hybrid" and self.selected_artifact != self.native_artifact:
            raise ValueError("hybrid Office route must preserve Native facts")
        if self.post_parse_quality is not None:
            if self.post_parse_quality.status != "accepted":
                raise ValueError("rejected post-parse results cannot be published")
            if (
                self.post_parse_quality.native_character_count
                != self.native_artifact.statistics.character_count
                or self.post_parse_quality.final_character_count
                != self.selected_artifact.statistics.character_count
            ):
                raise ValueError("post-parse counts do not match routed artifacts")
            health = self.quality.native_text_health
            if health is None:
                raise ValueError("post-parse quality requires Native text health")
            expected_ratio = (
                round(
                    self.selected_artifact.statistics.character_count
                    / self.native_artifact.statistics.character_count,
                    6,
                )
                if health.status == "healthy"
                and self.native_artifact.statistics.character_count > 0
                else None
            )
            if self.post_parse_quality.character_retention_ratio != expected_ratio:
                raise ValueError("post-parse retention ratio is inconsistent")
            if self.selected_artifact.source_type != "pdf" and (
                self.post_parse_quality.page_assessments
                or self.post_parse_quality.native_page_count is not None
                or self.post_parse_quality.final_page_count is not None
            ):
                raise ValueError("only PDF results may contain page quality")
            if (
                self.selected_artifact.source_type != "docx"
                and self.post_parse_quality.docx_image_assessments
            ):
                raise ValueError("only DOCX results may contain image OCR quality")
        return self


class DocumentParserRouter:
    """Orchestrate existing bounded parsers without persistence side effects."""

    def __init__(
        self,
        settings: Settings,
        *,
        docling_provider: DoclingProvider | None = None,
    ) -> None:
        self._settings = settings
        self._docling_provider = docling_provider

    def parse(
        self,
        *,
        source_name: str,
        content: bytes,
        complexity_tags: tuple[str, ...] = (),
    ) -> RoutedParseResult:
        """Run Native safety/limits first, then the quality-selected path."""

        source_type = _source_type(source_name)
        _validate_source_signature(source_type, content)
        native_result = self._parse_native(source_type, content)
        source_sha256 = hashlib.sha256(content).hexdigest()
        native_artifact = adapt_native_parse_result(
            native_result,
            source_sha256=source_sha256,
        )
        inferred_tags = infer_complexity_tags(source_type, content)
        quality = decide_parse_route(
            native_artifact,
            complexity_tags=tuple(sorted(set(complexity_tags) | set(inferred_tags))),
            minimum_character_count=self._settings.native_text_min_characters,
            minimum_page_character_count=(
                self._settings.pdf_low_text_character_threshold
            ),
            minimum_valid_character_ratio=(
                self._settings.native_text_min_valid_character_ratio
            ),
            minimum_healthy_page_ratio=(
                self._settings.native_text_min_healthy_page_ratio
            ),
        )
        if quality.route == "native":
            return self._release_result(
                route="native",
                reasons=quality.reasons,
                quality=quality,
                selected_artifact=native_artifact,
                native_artifact=native_artifact,
            )

        if source_type == "csv":
            raise DocumentEnhancementError
        provider = self._docling_provider
        if provider is None:
            provider = LocalDoclingProvider(self._settings)
        try:
            snapshot = provider.parse(
                source_name=Path(source_name).name,
                source_type=source_type,
                content=content,
            )
            if snapshot.source_type != source_type:
                raise DocumentEnhancementError
            docling_artifact = adapt_docling_snapshot(
                snapshot,
                source_sha256=source_sha256,
            )
            if (
                docling_artifact.statistics.block_count == 0
                or docling_artifact.statistics.character_count == 0
            ):
                raise DocumentEnhancementError
        except DocumentEnhancementError:
            raise
        except (Exception, MemoryError):  # noqa: BLE001 - provider details stay private.
            raise DocumentEnhancementError from None

        comparison = _compare(native_artifact, docling_artifact)
        selected = docling_artifact if quality.route == "docling" else native_artifact
        return self._release_result(
            route=quality.route,
            reasons=quality.reasons,
            quality=quality,
            selected_artifact=selected,
            native_artifact=native_artifact,
            docling_artifact=docling_artifact,
            comparison=comparison,
        )

    def _release_result(
        self,
        *,
        route: ParseRoute,
        reasons: list[str],
        quality: ParseQualityDecision,
        selected_artifact: CanonicalParsedArtifact,
        native_artifact: CanonicalParsedArtifact,
        docling_artifact: CanonicalParsedArtifact | None = None,
        comparison: ArtifactComparison | None = None,
    ) -> RoutedParseResult:
        health = quality.native_text_health
        if health is None:
            raise DocumentParseError
        post_quality = evaluate_post_parse_quality(
            native_artifact=native_artifact,
            selected_artifact=selected_artifact,
            native_text_health=health,
            minimum_final_native_ratio=(
                self._settings.post_parse_min_final_native_ratio
            ),
            minimum_page_character_count=(
                self._settings.post_parse_min_page_characters
            ),
            native_page_baseline_character_count=(
                self._settings.post_parse_native_page_baseline_characters
            ),
            docx_empty_ocr_min_image_bytes=(
                self._settings.docx_empty_ocr_min_image_bytes
            ),
            minimum_docx_body_character_count=(
                self._settings.native_text_min_characters
            ),
        )
        if post_quality.status == "rejected":
            _LOGGER.warning(
                "post_parse_quality status=rejected policy=%s rejection_codes=%s "
                + "native_characters=%s final_characters=%s",
                post_quality.policy_version,
                ",".join(post_quality.rejection_codes),
                post_quality.native_character_count,
                post_quality.final_character_count,
            )
            raise DocumentQualityRejected(post_quality)
        return RoutedParseResult(
            route=route,
            reasons=reasons,
            quality=quality,
            selected_artifact=selected_artifact,
            native_artifact=native_artifact,
            docling_artifact=docling_artifact,
            comparison=comparison,
            post_parse_quality=post_quality,
        )

    def _parse_native(self, source_type: ArtifactSourceType, content: bytes):  # type: ignore[no-untyped-def]
        stream = io.BytesIO(content)
        if source_type == "pdf":
            return PdfParser.from_settings(self._settings).parse(stream)
        if source_type == "docx":
            return DocxParser.from_settings(self._settings).parse(stream)
        if source_type == "xlsx":
            return XlsxParser.from_settings(self._settings).parse(stream)
        return CsvParser.from_settings(self._settings).parse(stream)


def _source_type(source_name: str) -> ArtifactSourceType:
    suffix = Path(source_name).suffix.lower()
    try:
        return _SOURCE_TYPES[suffix]
    except KeyError:
        raise DocumentParseError from None


def _validate_source_signature(
    source_type: ArtifactSourceType,
    content: bytes,
) -> None:
    """Reject extension/content mismatches before either parser provider runs."""

    try:
        detected = filetype.guess(content[:8192])
        if source_type == "pdf":
            if detected is None or detected.mime != "application/pdf":
                raise DocumentParseError
            return
        if source_type in {"docx", "xlsx"}:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = {member.filename for member in archive.infolist()}
            if not _ZIP_TYPE_MEMBERS[source_type].issubset(names):
                raise DocumentParseError
            return
        if detected is not None or b"\x00" in content[:8192]:
            raise DocumentParseError
    except DocumentParseError:
        raise
    except Exception:  # noqa: BLE001 - malformed signatures stay private.
        raise DocumentParseError from None


def _compare(
    native: CanonicalParsedArtifact,
    docling: CanonicalParsedArtifact,
) -> ArtifactComparison:
    return ArtifactComparison(
        native_block_count=native.statistics.block_count,
        docling_block_count=docling.statistics.block_count,
        native_character_count=native.statistics.character_count,
        docling_character_count=docling.statistics.character_count,
        native_table_count=native.statistics.table_count,
        docling_table_count=docling.statistics.table_count,
        native_formula_count=native.statistics.formula_count,
        docling_formula_count=docling.statistics.formula_count,
    )
