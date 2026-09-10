"""Read-only M2 parser diagnostics across Native, Docling, and selected artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypeAlias
from uuid import uuid4

from pydantic import AwareDatetime, Field, model_validator

from app.core.config import Settings
from app.evals import rag_runner
from app.schemas.common import M1Schema
from app.schemas.evaluation import EvaluationCase, SafeIdentifier, Sha256
from app.services.documents.artifacts import (
    ArtifactTableBlock,
    ArtifactTextBlock,
    CanonicalParsedArtifact,
)
from app.services.documents.parsers.docling import (
    DoclingProvider,
    LocalDoclingProvider,
    adapt_docling_snapshot,
)
from app.services.documents.parsers.native import adapt_native_parse_result
from app.services.documents.quality import decide_parse_route, infer_complexity_tags
from app.services.documents.routing import DocumentParserRouter, ParseRoute

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE_REPORT_PATH = rag_runner.DEFAULT_REPORT_PATH
DEFAULT_DIAGNOSTIC_REPORT_PATH = (
    PROJECT_ROOT
    / "data"
    / "evals"
    / "runtime"
    / "reports"
    / "m2_parser_diagnostic_report_v1.json"
)

DiagnosticCategory: TypeAlias = Literal[
    "recovered_on_rerun",
    "evaluation_normalization_gap",
    "route_selection_loss",
    "provider_partial_result",
    "enhanced_provider_execution_failure",
    "reading_order_or_format_loss",
    "ocr_extraction_loss",
    "partial_extraction_loss",
    "complete_extraction_loss",
]


class ArtifactEvidenceSignal(M1Schema):
    """Safe comparison signal without reproducing licensed source text."""

    provider: Literal["native", "docling"]
    exact_match: bool
    relaxed_match: bool
    located_exact_match: bool | None = None
    located_relaxed_match: bool | None = None
    token_recall: float = Field(ge=0, le=1)
    located_token_recall: float | None = Field(default=None, ge=0, le=1)
    character_count: int = Field(ge=0)
    warning_codes: list[str] = Field(max_length=6000)


class ParserEvidenceDiagnosis(M1Schema):
    """Attribution for one previously missing Golden case."""

    case_id: SafeIdentifier
    category: DiagnosticCategory
    route: ParseRoute
    selected_provider: Literal["native", "docling"]
    selected: ArtifactEvidenceSignal | None = None
    native: ArtifactEvidenceSignal
    docling: ArtifactEvidenceSignal | None = None


class ParserArtifactDiagnosticSummary(M1Schema):
    provider: Literal["native", "docling"]
    character_count: int = Field(ge=0)
    block_count: int = Field(ge=0)
    page_count: int | None = Field(default=None, ge=1)
    docx_header_block_count: int = Field(default=0, ge=0)
    docx_footer_block_count: int = Field(default=0, ge=0)
    docx_image_ocr_block_count: int = Field(default=0, ge=0)
    warning_codes: list[str] = Field(max_length=6000)


class ParserDiagnosticDocument(M1Schema):
    source_id: SafeIdentifier
    logical_document_id: SafeIdentifier
    source_type: Literal["pdf", "docx", "xlsx", "csv"]
    requires_ocr: bool
    run_status: Literal["completed", "failed"]
    route: ParseRoute | None = None
    route_reasons: list[str] = Field(default_factory=list, max_length=30)
    selected_provider: Literal["native", "docling"] | None = None
    enhanced_probe_status: Literal["not_required", "completed", "failed"] | None = None
    base_missing_case_ids: list[SafeIdentifier] = Field(min_length=1, max_length=100)
    native: ParserArtifactDiagnosticSummary | None = None
    docling: ParserArtifactDiagnosticSummary | None = None
    cases: list[ParserEvidenceDiagnosis] = Field(max_length=100)
    failure_summary: str | None = Field(default=None, min_length=1, max_length=300)

    @model_validator(mode="after")
    def validate_completion(self) -> ParserDiagnosticDocument:
        if self.run_status == "completed":
            if (
                self.route is None
                or self.selected_provider is None
                or self.enhanced_probe_status is None
                or self.native is None
                or len(self.cases) != len(self.base_missing_case_ids)
                or {case.case_id for case in self.cases}
                != set(self.base_missing_case_ids)
                or self.failure_summary is not None
            ):
                raise ValueError("completed diagnostic document is incomplete")
        elif self.cases or self.failure_summary is None:
            raise ValueError("failed diagnostic document requires a safe failure")
        return self


class ParserDiagnosticCategoryCounts(M1Schema):
    recovered_on_rerun: int = Field(ge=0)
    evaluation_normalization_gap: int = Field(ge=0)
    route_selection_loss: int = Field(ge=0)
    provider_partial_result: int = Field(ge=0)
    enhanced_provider_execution_failure: int = Field(ge=0)
    reading_order_or_format_loss: int = Field(ge=0)
    ocr_extraction_loss: int = Field(ge=0)
    partial_extraction_loss: int = Field(ge=0)
    complete_extraction_loss: int = Field(ge=0)


class ParserDiagnosticAggregate(M1Schema):
    documents_total: int = Field(ge=0)
    documents_completed: int = Field(ge=0)
    documents_failed: int = Field(ge=0)
    cases_diagnosed: int = Field(ge=0)
    category_counts: ParserDiagnosticCategoryCounts


class ParserDiagnosticReport(M1Schema):
    """Public-safe diagnosis tied to one immutable parser evaluation report."""

    schema_version: Literal["m2-parser-diagnostic-report-v1"] = (
        "m2-parser-diagnostic-report-v1"
    )
    run_id: SafeIdentifier
    run_status: Literal["planned", "completed", "failed"]
    started_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None
    base_report_run_id: SafeIdentifier | None = None
    base_report_sha256: Sha256 | None = None
    documents: list[ParserDiagnosticDocument] = Field(max_length=64)
    aggregate: ParserDiagnosticAggregate

    @model_validator(mode="after")
    def validate_run(self) -> ParserDiagnosticReport:
        if self.run_status == "planned":
            if (
                self.started_at is not None
                or self.completed_at is not None
                or self.base_report_run_id is not None
                or self.base_report_sha256 is not None
                or self.documents
                or self.aggregate.documents_total != 0
                or self.aggregate.cases_diagnosed != 0
            ):
                raise ValueError("planned diagnostic report cannot claim observations")
            return self
        if (
            self.started_at is None
            or self.completed_at is None
            or self.completed_at < self.started_at
            or self.base_report_run_id is None
            or self.base_report_sha256 is None
            or not self.documents
        ):
            raise ValueError("executed diagnostic report is incomplete")
        completed = sum(item.run_status == "completed" for item in self.documents)
        failed = sum(item.run_status == "failed" for item in self.documents)
        cases = sum(len(item.cases) for item in self.documents)
        category_total = sum(self.aggregate.category_counts.model_dump().values())
        if (
            self.aggregate.documents_total != len(self.documents)
            or self.aggregate.documents_completed != completed
            or self.aggregate.documents_failed != failed
            or self.aggregate.cases_diagnosed != cases
            or category_total != cases
        ):
            raise ValueError("diagnostic aggregate does not match documents")
        if self.run_status == "completed" and failed:
            raise ValueError("completed diagnostic report cannot contain failures")
        return self


def diagnose_evidence_artifacts(
    *,
    case_id: str,
    expected_texts: list[str],
    page_ranges: list[tuple[int | None, int | None]],
    route: ParseRoute,
    selected_artifact: CanonicalParsedArtifact,
    native_artifact: CanonicalParsedArtifact,
    docling_artifact: CanonicalParsedArtifact | None,
    requires_ocr: bool,
) -> ParserEvidenceDiagnosis:
    """Explain one miss using observable text from every existing parser path."""

    if not expected_texts or len(expected_texts) != len(page_ranges):
        raise ValueError("diagnosis requires aligned evidence texts and page ranges")
    selected = _artifact_signal(selected_artifact, expected_texts, page_ranges)
    native = _artifact_signal(native_artifact, expected_texts, page_ranges)
    docling = (
        _artifact_signal(docling_artifact, expected_texts, page_ranges)
        if docling_artifact is not None
        else None
    )
    other_signals = [native, *(signal for signal in [docling] if signal is not None)]
    if selected.exact_match:
        category: DiagnosticCategory = "recovered_on_rerun"
    elif selected.relaxed_match:
        category = "evaluation_normalization_gap"
    elif any(signal.exact_match or signal.relaxed_match for signal in other_signals):
        category = "route_selection_loss"
    elif any(
        "docling_partial_result" in signal.warning_codes for signal in other_signals
    ):
        category = "provider_partial_result"
    elif max(signal.token_recall for signal in other_signals) >= 0.85:
        category = "reading_order_or_format_loss"
    elif requires_ocr:
        category = "ocr_extraction_loss"
    elif max(signal.token_recall for signal in other_signals) > 0:
        category = "partial_extraction_loss"
    else:
        category = "complete_extraction_loss"
    return ParserEvidenceDiagnosis(
        case_id=case_id,
        category=category,
        route=route,
        selected_provider=selected_artifact.parser.provider,
        selected=selected,
        native=native,
        docling=docling,
    )


def run_m2_parser_diagnostics(
    settings: Settings,
    *,
    project_root: Path = PROJECT_ROOT,
    base_report_path: Path = DEFAULT_BASE_REPORT_PATH,
    docling_provider: DoclingProvider | None = None,
) -> ParserDiagnosticReport:
    """Reparse only baseline misses; never upload, persist, chunk, or index them."""

    started_at = datetime.now(UTC)
    run_id = f"m2-22.4-diagnostic-{started_at:%Y%m%dt%H%M%S}-{uuid4().hex[:8]}"
    base_bytes = base_report_path.read_bytes()
    base_report = rag_runner.ParserEvaluationReport.model_validate_json(base_bytes)
    if base_report.run_status != "completed":
        raise ValueError("parser diagnostics require a completed base report")
    missing_documents = {
        item.source_id: item
        for item in base_report.documents
        if item.recovery.missing_case_ids
    }
    if not missing_documents:
        raise ValueError("base report has no missing parser evidence to diagnose")

    cases = rag_runner._load_cases(
        project_root / rag_runner.DEFAULT_DATASET_PATH.relative_to(PROJECT_ROOT)
    )
    manifest = rag_runner._load_source_manifest(
        project_root / rag_runner.DEFAULT_SOURCE_MANIFEST_PATH.relative_to(PROJECT_ROOT)
    )
    sources = rag_runner._load_evaluation_sources(
        project_root=project_root,
        manifest=manifest,
        source_ids=set(missing_documents),
    )
    provider = docling_provider
    if provider is None and settings.docling_backend == "docling":
        provider = LocalDoclingProvider(settings)
    router = DocumentParserRouter(settings, docling_provider=provider)
    documents: list[ParserDiagnosticDocument] = []
    for source in sources:
        base_document = missing_documents[source.source_id]
        try:
            native_result = router._parse_native(
                source.source_type,
                source.content,
            )
            source_sha256 = hashlib.sha256(source.content).hexdigest()
            native_artifact = adapt_native_parse_result(
                native_result,
                source_sha256=source_sha256,
            )
            quality = decide_parse_route(
                native_artifact,
                complexity_tags=infer_complexity_tags(
                    source.source_type,
                    source.content,
                ),
                minimum_character_count=settings.native_text_min_characters,
                minimum_page_character_count=(
                    settings.pdf_low_text_character_threshold
                ),
                minimum_valid_character_ratio=(
                    settings.native_text_min_valid_character_ratio
                ),
                minimum_healthy_page_ratio=(
                    settings.native_text_min_healthy_page_ratio
                ),
            )
            missing_cases = [
                case
                for case in cases
                if case.case_id in base_document.recovery.missing_case_ids
            ]
            native_signals = {
                case.case_id: _case_artifact_signal(
                    case=case,
                    logical_document_id=source.logical_document_id,
                    artifact=native_artifact,
                )
                for case in missing_cases
            }
            base_selected_provider = base_document.parser_provider
            if base_selected_provider is None or base_document.route is None:
                raise ValueError("base parser result is incomplete")
            native_proves_selection_loss = all(
                base_selected_provider != "native"
                and (signal.exact_match or signal.relaxed_match)
                for signal in native_signals.values()
            )
            docling_artifact: CanonicalParsedArtifact | None = None
            enhanced_probe_status: Literal["not_required", "completed", "failed"]
            if native_proves_selection_loss:
                enhanced_probe_status = "not_required"
                diagnoses = [
                    ParserEvidenceDiagnosis(
                        case_id=case.case_id,
                        category="route_selection_loss",
                        route=base_document.route,
                        selected_provider=base_selected_provider,
                        selected=None,
                        native=native_signals[case.case_id],
                        docling=None,
                    )
                    for case in missing_cases
                ]
            else:
                try:
                    if provider is None:
                        raise RuntimeError("enhanced provider is unavailable")
                    snapshot = provider.parse(
                        source_name=source.original_name,
                        source_type=source.source_type,  # type: ignore[arg-type]
                        content=source.content,
                    )
                    docling_artifact = adapt_docling_snapshot(
                        snapshot,
                        source_sha256=source_sha256,
                    )
                    enhanced_probe_status = "completed"
                    selected_artifact = (
                        docling_artifact
                        if base_selected_provider == "docling"
                        else native_artifact
                    )
                    diagnoses = [
                        _diagnose_case(
                            case=case,
                            logical_document_id=source.logical_document_id,
                            route=base_document.route,
                            selected_artifact=selected_artifact,
                            native_artifact=native_artifact,
                            docling_artifact=docling_artifact,
                            requires_ocr=source.requires_ocr,
                        )
                        for case in missing_cases
                    ]
                except Exception:  # noqa: BLE001 - the failure is the observation.
                    enhanced_probe_status = "failed"
                    diagnoses = [
                        ParserEvidenceDiagnosis(
                            case_id=case.case_id,
                            category=(
                                "route_selection_loss"
                                if base_selected_provider != "native"
                                and (
                                    native_signals[case.case_id].exact_match
                                    or native_signals[case.case_id].relaxed_match
                                )
                                else "enhanced_provider_execution_failure"
                            ),
                            route=base_document.route,
                            selected_provider=base_selected_provider,
                            selected=(
                                native_signals[case.case_id]
                                if base_selected_provider == "native"
                                else None
                            ),
                            native=native_signals[case.case_id],
                            docling=None,
                        )
                        for case in missing_cases
                    ]
            documents.append(
                ParserDiagnosticDocument(
                    source_id=source.source_id,
                    logical_document_id=source.logical_document_id,
                    source_type=source.source_type,
                    requires_ocr=source.requires_ocr,
                    run_status="completed",
                    route=base_document.route,
                    route_reasons=quality.reasons,
                    selected_provider=base_selected_provider,
                    enhanced_probe_status=enhanced_probe_status,
                    base_missing_case_ids=base_document.recovery.missing_case_ids,
                    native=_artifact_summary(native_artifact),
                    docling=(
                        _artifact_summary(docling_artifact)
                        if docling_artifact is not None
                        else None
                    ),
                    cases=diagnoses,
                )
            )
        except Exception:  # noqa: BLE001 - report retains no provider internals.
            documents.append(
                ParserDiagnosticDocument(
                    source_id=source.source_id,
                    logical_document_id=source.logical_document_id,
                    source_type=source.source_type,
                    requires_ocr=source.requires_ocr,
                    run_status="failed",
                    base_missing_case_ids=base_document.recovery.missing_case_ids,
                    cases=[],
                    failure_summary="Parser diagnostic execution failed",
                )
            )

    aggregate = _aggregate(documents)
    return ParserDiagnosticReport(
        run_id=run_id,
        run_status=("completed" if aggregate.documents_failed == 0 else "failed"),
        started_at=started_at,
        completed_at=datetime.now(UTC),
        base_report_run_id=base_report.run_id,
        base_report_sha256=hashlib.sha256(base_bytes).hexdigest(),
        documents=documents,
        aggregate=aggregate,
    )


def _diagnose_case(
    *,
    case: EvaluationCase,
    logical_document_id: str,
    route: ParseRoute,
    selected_artifact: CanonicalParsedArtifact,
    native_artifact: CanonicalParsedArtifact,
    docling_artifact: CanonicalParsedArtifact | None,
    requires_ocr: bool,
) -> ParserEvidenceDiagnosis:
    spans = [
        span
        for span in case.expected_evidence_spans
        if span.document_id == logical_document_id
    ]
    return diagnose_evidence_artifacts(
        case_id=case.case_id,
        expected_texts=[span.exact_text for span in spans],
        page_ranges=[(span.page_start, span.page_end) for span in spans],
        route=route,
        selected_artifact=selected_artifact,
        native_artifact=native_artifact,
        docling_artifact=docling_artifact,
        requires_ocr=requires_ocr,
    )


def _case_artifact_signal(
    *,
    case: EvaluationCase,
    logical_document_id: str,
    artifact: CanonicalParsedArtifact,
) -> ArtifactEvidenceSignal:
    spans = [
        span
        for span in case.expected_evidence_spans
        if span.document_id == logical_document_id
    ]
    if not spans:
        raise ValueError("diagnostic case has no evidence for its document")
    return _artifact_signal(
        artifact,
        [span.exact_text for span in spans],
        [(span.page_start, span.page_end) for span in spans],
    )


def _artifact_signal(
    artifact: CanonicalParsedArtifact,
    expected_texts: list[str],
    page_ranges: list[tuple[int | None, int | None]],
) -> ArtifactEvidenceSignal:
    global_text = _artifact_text(artifact)
    global_normalized = _normalize_exact(global_text)
    global_relaxed = _normalize_relaxed(global_text)
    exact = all(_normalize_exact(text) in global_normalized for text in expected_texts)
    relaxed = all(_normalize_relaxed(text) in global_relaxed for text in expected_texts)

    located_available = all(start is not None for start, _end in page_ranges)
    located_exact: bool | None = None
    located_relaxed: bool | None = None
    located_recall: float | None = None
    if located_available:
        scoped_texts = [
            _artifact_text(artifact, page_start=start, page_end=end or start)
            for start, end in page_ranges
        ]
        located_exact = all(
            _normalize_exact(expected) in _normalize_exact(candidate)
            for expected, candidate in zip(expected_texts, scoped_texts, strict=True)
        )
        located_relaxed = all(
            _normalize_relaxed(expected) in _normalize_relaxed(candidate)
            for expected, candidate in zip(expected_texts, scoped_texts, strict=True)
        )
        located_recall = min(
            _token_recall(expected, candidate)
            for expected, candidate in zip(expected_texts, scoped_texts, strict=True)
        )
    return ArtifactEvidenceSignal(
        provider=artifact.parser.provider,
        exact_match=exact,
        relaxed_match=relaxed,
        located_exact_match=located_exact,
        located_relaxed_match=located_relaxed,
        token_recall=min(_token_recall(text, global_text) for text in expected_texts),
        located_token_recall=located_recall,
        character_count=artifact.statistics.character_count,
        warning_codes=sorted({warning.code for warning in artifact.warnings}),
    )


def _artifact_text(
    artifact: CanonicalParsedArtifact,
    *,
    page_start: int | None = None,
    page_end: int | None = None,
) -> str:
    parts: list[str] = []
    for block in artifact.blocks:
        page = block.locator.page_number
        if page_start is not None:
            effective_page_end = page_end if page_end is not None else page_start
            if page is None or not page_start <= page <= effective_page_end:
                continue
        if isinstance(block, ArtifactTextBlock):
            parts.append(block.text)
        elif isinstance(block, ArtifactTableBlock):
            for row in block.rows:
                for cell in row.cells:
                    parts.append(cell.display_text)
                    if cell.formula is not None:
                        parts.append(cell.formula)
    return "\n".join(parts)


def _normalize_exact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _normalize_relaxed(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(
        character
        for character in normalized
        if not unicodedata.category(character).startswith(("P", "Z"))
        and not character.isspace()
    )


def _token_recall(expected: str, candidate: str) -> float:
    expected_tokens = Counter(
        re.findall(r"\w+", unicodedata.normalize("NFKC", expected).casefold())
    )
    if not expected_tokens:
        return 1.0
    candidate_tokens = Counter(
        re.findall(r"\w+", unicodedata.normalize("NFKC", candidate).casefold())
    )
    recovered = sum(
        min(count, candidate_tokens[token]) for token, count in expected_tokens.items()
    )
    return recovered / sum(expected_tokens.values())


def _artifact_summary(
    artifact: CanonicalParsedArtifact,
) -> ParserArtifactDiagnosticSummary:
    text_source_counts = Counter(
        block.source_kind
        for block in artifact.blocks
        if isinstance(block, ArtifactTextBlock)
    )
    return ParserArtifactDiagnosticSummary(
        provider=artifact.parser.provider,
        character_count=artifact.statistics.character_count,
        block_count=artifact.statistics.block_count,
        page_count=artifact.statistics.page_count,
        docx_header_block_count=text_source_counts["docx_header"],
        docx_footer_block_count=text_source_counts["docx_footer"],
        docx_image_ocr_block_count=text_source_counts["docx_image_ocr"],
        warning_codes=sorted({warning.code for warning in artifact.warnings}),
    )


def _aggregate(
    documents: list[ParserDiagnosticDocument],
) -> ParserDiagnosticAggregate:
    diagnoses = [case for document in documents for case in document.cases]
    counts = Counter(case.category for case in diagnoses)
    return ParserDiagnosticAggregate(
        documents_total=len(documents),
        documents_completed=sum(item.run_status == "completed" for item in documents),
        documents_failed=sum(item.run_status == "failed" for item in documents),
        cases_diagnosed=len(diagnoses),
        category_counts=ParserDiagnosticCategoryCounts(
            recovered_on_rerun=counts["recovered_on_rerun"],
            evaluation_normalization_gap=counts["evaluation_normalization_gap"],
            route_selection_loss=counts["route_selection_loss"],
            provider_partial_result=counts["provider_partial_result"],
            enhanced_provider_execution_failure=counts[
                "enhanced_provider_execution_failure"
            ],
            reading_order_or_format_loss=counts["reading_order_or_format_loss"],
            ocr_extraction_loss=counts["ocr_extraction_loss"],
            partial_extraction_loss=counts["partial_extraction_loss"],
            complete_extraction_loss=counts["complete_extraction_loss"],
        ),
    )


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Diagnose the bounded M2-22.4 Native/Docling parser misses"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_DIAGNOSTIC_REPORT_PATH)
    parser.add_argument("--base-report", type=Path, default=DEFAULT_BASE_REPORT_PATH)
    parser.add_argument(
        "--enable-docling",
        action="store_true",
        help="explicitly enable the local offline Docling/OCR path",
    )
    args = parser.parse_args()
    if not args.enable_docling:
        parser.error("--enable-docling is required for parser diagnostics")
    settings = Settings(docling_backend="docling")  # type: ignore[call-arg]
    report = run_m2_parser_diagnostics(
        settings,
        base_report_path=args.base_report,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"run_status={report.run_status} "
        f"documents={report.aggregate.documents_total} "
        f"cases={report.aggregate.cases_diagnosed}"
    )
    return 0 if report.run_status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(_main())
