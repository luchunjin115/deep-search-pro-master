"""Deterministic M2-22.5 Chunk quality metrics over real Chunk Artifacts."""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.common import M1Schema
from app.schemas.evaluation import (
    EvaluationCase,
    ExpectedEvidenceSpan,
    SafeIdentifier,
    TrustedHeadingContextCase,
)
from app.services.documents.artifacts import (
    ArtifactTableBlock,
    ArtifactTableCell,
    ArtifactTableRow,
    ArtifactTextBlock,
    CanonicalParsedArtifact,
)
from app.services.documents.chunking import (
    CanonicalChunkArtifact,
    ChunkHeadingSource,
    DocumentChunk,
    NormalizedSourceText,
    UnicodeMixedTokenCounter,
    normalize_source_text,
)
from app.services.documents.chunking.contracts import ExcludedChunkSpan

ChunkFailureLayer = Literal["parser_artifact", "chunk_rule", "locator"]
_HEADING_LABEL_PREFIX = re.compile(
    r"^(?:"
    r"(?:\d{1,4}(?:\.\d{1,4})*)[.)、:]"
    r"|[A-Za-z][.)、]"
    r"|[（(]?[一二三四五六七八九十]+[)）.、]"
    r")\s+"
)


class GoldenChunkCaseResult(M1Schema):
    """One reviewed Golden result without copying source or answer text."""

    case_id: SafeIdentifier
    evidence_span_count: int = Field(ge=1, le=20)
    artifact_recovered: bool
    answer_contained: bool
    locator_passed: bool
    evidence_span_coverage: float = Field(ge=0, le=1)
    content_match_chunk_ids: list[str] = Field(max_length=1000)
    locator_match_chunk_ids: list[str] = Field(max_length=1000)
    locator_basis: Literal[
        "page_and_canonical_source_span",
        "table_coordinates",
        "canonical_source_span",
        "canonical_table_locator",
    ]
    failure_layer: ChunkFailureLayer | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> GoldenChunkCaseResult:
        expected_failure: ChunkFailureLayer | None
        if not self.artifact_recovered:
            expected_failure = "parser_artifact"
        elif not self.answer_contained:
            expected_failure = "chunk_rule"
        elif not self.locator_passed:
            expected_failure = "locator"
        else:
            expected_failure = None
        if self.failure_layer != expected_failure:
            raise ValueError("Golden Chunk failure attribution is inconsistent")
        if self.locator_passed and not self.answer_contained:
            raise ValueError("locator cannot pass without answer containment")
        return self


class ChunkStructureAudit(M1Schema):
    """Auditable preservation counts for structures exposed by the Parser Artifact."""

    paragraph_units: int = Field(ge=0)
    paragraph_units_preserved: int = Field(ge=0)
    heading_units: int = Field(ge=0)
    heading_units_preserved: int = Field(ge=0)
    table_rows: int = Field(ge=0)
    table_rows_preserved: int = Field(ge=0)
    docx_header_units: int = Field(ge=0)
    docx_header_units_preserved: int = Field(ge=0)
    docx_footer_units: int = Field(ge=0)
    docx_footer_units_preserved: int = Field(ge=0)
    image_ocr_units: int = Field(ge=0)
    image_ocr_units_preserved: int = Field(ge=0)
    context_links: int = Field(ge=0)
    context_links_preserved: int = Field(ge=0)
    repeated_header_exclusions: int = Field(ge=0)
    repeated_footer_exclusions: int = Field(ge=0)
    boundary_units: int = Field(ge=0)
    boundary_breaks: int = Field(ge=0)
    boundary_break_rate: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_counts(self) -> ChunkStructureAudit:
        for total_name, passed_name in (
            ("paragraph_units", "paragraph_units_preserved"),
            ("heading_units", "heading_units_preserved"),
            ("table_rows", "table_rows_preserved"),
            ("docx_header_units", "docx_header_units_preserved"),
            ("docx_footer_units", "docx_footer_units_preserved"),
            ("image_ocr_units", "image_ocr_units_preserved"),
            ("context_links", "context_links_preserved"),
        ):
            if getattr(self, passed_name) > getattr(self, total_name):
                raise ValueError("preserved structure count cannot exceed its total")
        expected_rate = (
            self.boundary_breaks / self.boundary_units if self.boundary_units else None
        )
        if self.boundary_breaks > self.boundary_units:
            raise ValueError("boundary breaks cannot exceed audited units")
        if self.boundary_break_rate != expected_rate:
            raise ValueError("boundary break rate does not match its counts")
        return self


class ChunkDocumentQuality(M1Schema):
    """One document/config result computed without models or retrieval."""

    source_id: SafeIdentifier
    logical_document_id: SafeIdentifier
    chunk_output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    chunk_count: int = Field(ge=1)
    text_chunk_count: int = Field(ge=0)
    table_chunk_count: int = Field(ge=0)
    token_counts: list[int] = Field(min_length=1, max_length=1_100_000)
    total_token_count: int = Field(ge=1)
    token_min: int = Field(ge=1)
    token_p50: int = Field(ge=1)
    token_p95: int = Field(ge=1)
    token_max: int = Field(ge=1)
    explicit_overlap_tokens: int = Field(ge=0)
    overlap_redundancy_rate: float = Field(ge=0, le=1)
    empty_chunk_count: int = Field(ge=0)
    near_duplicate_chunk_count: int = Field(ge=0)
    source_order_preserved: bool
    locator_integrity_passed: bool
    deterministic_rebuild_passed: bool = False
    structure: ChunkStructureAudit
    golden_cases: list[GoldenChunkCaseResult] = Field(max_length=100)

    @model_validator(mode="after")
    def validate_chunk_statistics(self) -> ChunkDocumentQuality:
        ordered = sorted(self.token_counts)
        if (
            len(self.token_counts) != self.chunk_count
            or sum(self.token_counts) != self.total_token_count
            or self.text_chunk_count + self.table_chunk_count != self.chunk_count
            or self.token_min != ordered[0]
            or self.token_p50 != _percentile(ordered, 0.50)
            or self.token_p95 != _percentile(ordered, 0.95)
            or self.token_max != ordered[-1]
        ):
            raise ValueError("document Chunk statistics do not match token counts")
        expected_overlap = self.explicit_overlap_tokens / self.total_token_count
        if self.overlap_redundancy_rate != expected_overlap:
            raise ValueError("document overlap rate does not match token counts")
        return self


class ChunkConfigurationAggregate(M1Schema):
    """Comparable aggregate for one complete structure-aware configuration."""

    config_id: SafeIdentifier
    documents_total: int = Field(ge=0)
    golden_cases_total: int = Field(ge=0)
    golden_cases_contained: int = Field(ge=0)
    golden_cases_located: int = Field(ge=0)
    answer_containment_rate: float | None = Field(default=None, ge=0, le=1)
    locator_pass_rate: float | None = Field(default=None, ge=0, le=1)
    evidence_span_coverage_rate: float | None = Field(default=None, ge=0, le=1)
    boundary_units: int = Field(ge=0)
    boundary_breaks: int = Field(ge=0)
    boundary_break_rate: float | None = Field(default=None, ge=0, le=1)
    heading_units: int = Field(ge=0)
    heading_units_preserved: int = Field(ge=0)
    heading_retention_rate: float | None = Field(default=None, ge=0, le=1)
    table_rows: int = Field(ge=0)
    table_rows_preserved: int = Field(ge=0)
    table_row_integrity_rate: float | None = Field(default=None, ge=0, le=1)
    deterministic_documents: int = Field(ge=0)
    ordered_documents: int = Field(ge=0)
    locator_integrity_documents: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    token_min: int | None = Field(default=None, ge=1)
    token_p50: int | None = Field(default=None, ge=1)
    token_p95: int | None = Field(default=None, ge=1)
    token_max: int | None = Field(default=None, ge=1)
    overlap_redundancy_rate: float | None = Field(default=None, ge=0, le=1)
    empty_chunk_count: int = Field(ge=0)
    near_duplicate_chunk_count: int = Field(ge=0)
    parser_artifact_failures: int = Field(ge=0)
    chunk_rule_failures: int = Field(ge=0)
    locator_failures: int = Field(ge=0)

    @classmethod
    def for_test(
        cls,
        *,
        config_id: str,
        answer_containment_rate: float,
        locator_pass_rate: float,
        boundary_break_rate: float,
    ) -> ChunkConfigurationAggregate:
        """Build a minimal internally consistent candidate-selection fixture."""

        return cls(
            config_id=config_id,
            documents_total=1,
            golden_cases_total=10,
            golden_cases_contained=round(answer_containment_rate * 10),
            golden_cases_located=round(locator_pass_rate * 10),
            answer_containment_rate=answer_containment_rate,
            locator_pass_rate=locator_pass_rate,
            evidence_span_coverage_rate=answer_containment_rate,
            boundary_units=10,
            boundary_breaks=round(boundary_break_rate * 10),
            boundary_break_rate=boundary_break_rate,
            heading_units=0,
            heading_units_preserved=0,
            table_rows=0,
            table_rows_preserved=0,
            deterministic_documents=1,
            ordered_documents=1,
            locator_integrity_documents=1,
            chunk_count=1,
            token_min=1,
            token_p50=1,
            token_p95=1,
            token_max=1,
            overlap_redundancy_rate=0,
            empty_chunk_count=0,
            near_duplicate_chunk_count=0,
            parser_artifact_failures=0,
            chunk_rule_failures=0,
            locator_failures=0,
        )


@dataclass(frozen=True, slots=True)
class _OccurrenceRange:
    block_id: str
    source_start: int
    source_end: int


@dataclass(frozen=True, slots=True)
class _TextOccurrence:
    ranges: tuple[_OccurrenceRange, ...]


@dataclass(frozen=True, slots=True)
class _StructureTextUnit:
    text: str
    character_start: int
    character_end: int


def evaluate_chunk_document(
    *,
    source_id: str,
    logical_document_id: str,
    artifact: CanonicalParsedArtifact,
    chunk_artifact: CanonicalChunkArtifact,
    cases: Sequence[EvaluationCase],
    heading_cases: Sequence[TrustedHeadingContextCase] = (),
    deterministic_rebuild_passed: bool = False,
) -> ChunkDocumentQuality:
    """Evaluate one real Chunk Artifact against its Canonical input and Golden."""

    relevant_cases = [
        case
        for case in cases
        if case.should_answer and logical_document_id in case.expected_document_ids
    ]
    golden = [
        _evaluate_golden_case(
            case=case,
            logical_document_id=logical_document_id,
            artifact=artifact,
            chunks=chunk_artifact.chunks,
        )
        for case in relevant_cases
    ]
    tokens = sorted(chunk.token_count for chunk in chunk_artifact.chunks)
    overlap_tokens = sum(
        chunk.overlap.token_count
        for chunk in chunk_artifact.chunks
        if chunk.overlap is not None
    )
    total_tokens = sum(tokens)
    return ChunkDocumentQuality(
        source_id=source_id,
        logical_document_id=logical_document_id,
        chunk_output_sha256=chunk_artifact.output_sha256,
        chunk_count=len(chunk_artifact.chunks),
        text_chunk_count=sum(chunk.kind == "text" for chunk in chunk_artifact.chunks),
        table_chunk_count=sum(chunk.kind == "table" for chunk in chunk_artifact.chunks),
        token_counts=[chunk.token_count for chunk in chunk_artifact.chunks],
        total_token_count=total_tokens,
        token_min=tokens[0],
        token_p50=_percentile(tokens, 0.50),
        token_p95=_percentile(tokens, 0.95),
        token_max=tokens[-1],
        explicit_overlap_tokens=overlap_tokens,
        overlap_redundancy_rate=overlap_tokens / total_tokens,
        empty_chunk_count=sum(
            not chunk.body_text.strip() for chunk in chunk_artifact.chunks
        ),
        near_duplicate_chunk_count=_near_duplicate_chunk_count(chunk_artifact.chunks),
        source_order_preserved=_source_order_is_preserved(chunk_artifact.chunks),
        locator_integrity_passed=_locator_integrity_is_preserved(
            artifact,
            chunk_artifact.chunks,
        ),
        deterministic_rebuild_passed=deterministic_rebuild_passed,
        structure=_audit_structure(
            artifact,
            chunk_artifact,
            source_id=source_id,
            logical_document_id=logical_document_id,
            heading_cases=heading_cases,
        ),
        golden_cases=golden,
    )


def aggregate_chunk_documents(
    config_id: str,
    documents: Sequence[ChunkDocumentQuality],
) -> ChunkConfigurationAggregate:
    """Aggregate only like-for-like results from one complete configuration."""

    cases = [case for document in documents for case in document.golden_cases]
    structures = [document.structure for document in documents]
    tokens = sorted(token for document in documents for token in document.token_counts)
    cases_total = len(cases)
    contained = sum(case.answer_contained for case in cases)
    located = sum(case.locator_passed for case in cases)
    boundary_total = sum(item.boundary_units for item in structures)
    boundary_breaks = sum(item.boundary_breaks for item in structures)
    heading_total = sum(item.heading_units for item in structures)
    heading_preserved = sum(item.heading_units_preserved for item in structures)
    table_total = sum(item.table_rows for item in structures)
    table_preserved = sum(item.table_rows_preserved for item in structures)
    weighted_overlap_numerator = sum(
        document.explicit_overlap_tokens for document in documents
    )
    total_chunk_tokens = sum(document.total_token_count for document in documents)
    overlap_rate = (
        weighted_overlap_numerator / total_chunk_tokens if total_chunk_tokens else 0.0
    )
    return ChunkConfigurationAggregate(
        config_id=config_id,
        documents_total=len(documents),
        golden_cases_total=cases_total,
        golden_cases_contained=contained,
        golden_cases_located=located,
        answer_containment_rate=contained / cases_total if cases_total else None,
        locator_pass_rate=located / cases_total if cases_total else None,
        evidence_span_coverage_rate=(
            sum(case.evidence_span_coverage for case in cases) / cases_total
            if cases_total
            else None
        ),
        boundary_units=boundary_total,
        boundary_breaks=boundary_breaks,
        boundary_break_rate=(
            boundary_breaks / boundary_total if boundary_total else None
        ),
        heading_units=heading_total,
        heading_units_preserved=heading_preserved,
        heading_retention_rate=(
            heading_preserved / heading_total if heading_total else None
        ),
        table_rows=table_total,
        table_rows_preserved=table_preserved,
        table_row_integrity_rate=(
            table_preserved / table_total if table_total else None
        ),
        deterministic_documents=sum(
            document.deterministic_rebuild_passed for document in documents
        ),
        ordered_documents=sum(
            document.source_order_preserved for document in documents
        ),
        locator_integrity_documents=sum(
            document.locator_integrity_passed for document in documents
        ),
        chunk_count=sum(document.chunk_count for document in documents),
        token_min=min(tokens) if tokens else None,
        token_p50=_percentile(tokens, 0.50) if tokens else None,
        token_p95=_percentile(tokens, 0.95) if tokens else None,
        token_max=max(tokens) if tokens else None,
        overlap_redundancy_rate=overlap_rate,
        empty_chunk_count=sum(document.empty_chunk_count for document in documents),
        near_duplicate_chunk_count=sum(
            document.near_duplicate_chunk_count for document in documents
        ),
        parser_artifact_failures=sum(
            case.failure_layer == "parser_artifact" for case in cases
        ),
        chunk_rule_failures=sum(case.failure_layer == "chunk_rule" for case in cases),
        locator_failures=sum(case.failure_layer == "locator" for case in cases),
    )


def select_first_round_candidates(
    aggregates: Sequence[ChunkConfigurationAggregate],
) -> list[str]:
    """Keep all configs tied on the best structural-quality tuple.

    Chunk count and overlap are reported but deliberately excluded: retrieval has
    not run yet, so M2-22.5 must not call a larger or smaller Chunk "optimal" from
    storage cost alone.
    """

    if not aggregates:
        return []
    scored = [(item, _quality_tuple(item)) for item in aggregates]
    best = max(score for _item, score in scored)
    return sorted(item.config_id for item, score in scored if score == best)


def _quality_tuple(item: ChunkConfigurationAggregate) -> tuple[float, ...]:
    documents = item.documents_total or 1
    return (
        item.answer_containment_rate or 0.0,
        item.locator_pass_rate or 0.0,
        item.evidence_span_coverage_rate or 0.0,
        1.0 - (item.boundary_break_rate or 0.0),
        item.heading_retention_rate if item.heading_retention_rate is not None else 1.0,
        (
            item.table_row_integrity_rate
            if item.table_row_integrity_rate is not None
            else 1.0
        ),
        item.deterministic_documents / documents,
        item.ordered_documents / documents,
        item.locator_integrity_documents / documents,
    )


def _evaluate_golden_case(
    *,
    case: EvaluationCase,
    logical_document_id: str,
    artifact: CanonicalParsedArtifact,
    chunks: Sequence[DocumentChunk],
) -> GoldenChunkCaseResult:
    spans = [
        span
        for span in case.expected_evidence_spans
        if span.document_id == logical_document_id
    ]
    span_content_ids: list[set[str]] = []
    span_locator_ids: list[set[str]] = []
    coverages: list[float] = []
    artifact_recovered = True
    for span in spans:
        artifact_views = _artifact_views(artifact, span)
        if not _contains_exact(artifact_views, span.exact_text):
            artifact_recovered = False
        matching = {
            chunk.chunk_id
            for chunk in chunks
            if _contains_exact(_chunk_views(chunk), span.exact_text)
        }
        located = {
            chunk.chunk_id
            for chunk in chunks
            if chunk.chunk_id in matching
            and _chunk_covers_expected_span(chunk, span, artifact)
        }
        span_content_ids.append(matching)
        span_locator_ids.append(located)
        coverages.append(
            1.0
            if matching
            else max(
                (
                    _contiguous_token_coverage(span.exact_text, view)
                    for chunk in chunks
                    for view in _chunk_views(chunk)
                ),
                default=0.0,
            )
        )
    common_content = set.intersection(*span_content_ids) if span_content_ids else set()
    common_located = set.intersection(*span_locator_ids) if span_locator_ids else set()
    answer_contained = artifact_recovered and bool(common_content)
    locator_passed = answer_contained and bool(common_located)
    failure: ChunkFailureLayer | None = None
    if not artifact_recovered:
        failure = "parser_artifact"
    elif not answer_contained:
        failure = "chunk_rule"
    elif not locator_passed:
        failure = "locator"
    source_type = spans[0].source_type
    basis: Literal[
        "page_and_canonical_source_span",
        "table_coordinates",
        "canonical_source_span",
        "canonical_table_locator",
    ]
    if source_type in {"xlsx", "csv"}:
        basis = "table_coordinates"
    elif any(
        isinstance(block, ArtifactTableBlock)
        and _contains_exact([_table_block_view(block)], spans[0].exact_text)
        for block in artifact.blocks
    ):
        basis = "canonical_table_locator"
    elif spans[0].page_start is not None:
        basis = "page_and_canonical_source_span"
    else:
        basis = "canonical_source_span"
    return GoldenChunkCaseResult(
        case_id=case.case_id,
        evidence_span_count=len(spans),
        artifact_recovered=artifact_recovered,
        answer_contained=answer_contained,
        locator_passed=locator_passed,
        evidence_span_coverage=(sum(coverages) / len(coverages)),
        content_match_chunk_ids=sorted(common_content),
        locator_match_chunk_ids=sorted(common_located),
        locator_basis=basis,
        failure_layer=failure,
    )


def _artifact_views(
    artifact: CanonicalParsedArtifact,
    span: ExpectedEvidenceSpan,
) -> list[str]:
    views: list[str] = []
    for block in artifact.blocks:
        if isinstance(block, ArtifactTextBlock):
            if span.page_start is not None and block.locator.page_number not in range(
                span.page_start,
                (span.page_end or span.page_start) + 1,
            ):
                continue
            views.append(block.text)
        elif isinstance(block, ArtifactTableBlock):
            views.append(_table_block_view(block))
    views.append("\n".join(views))
    return views


def _chunk_views(chunk: DocumentChunk) -> list[str]:
    views = [chunk.body_text]
    if chunk.table is not None:
        views.append(
            "\n".join(
                " ".join(_cell_evidence_parts(cell) for cell in row.cells)
                for row in chunk.table.rows
            )
        )
    return views


def _table_block_view(block: ArtifactTableBlock) -> str:
    return "\n".join(
        " ".join(_cell_evidence_parts(cell) for cell in row.cells) for row in block.rows
    )


def _cell_evidence_parts(cell: ArtifactTableCell) -> str:
    parts = [cell.display_text]
    if cell.formula is not None and cell.formula not in cell.display_text:
        parts.append(cell.formula)
    return " ".join(part for part in parts if part)


def _contains_exact(views: Sequence[str], expected: str) -> bool:
    needle = _match_normalize(expected)
    return bool(needle) and any(needle in _match_normalize(view) for view in views)


def _chunk_covers_expected_span(
    chunk: DocumentChunk,
    expected: ExpectedEvidenceSpan,
    artifact: CanonicalParsedArtifact,
) -> bool:
    if expected.page_start is not None and not set(
        range(expected.page_start, (expected.page_end or expected.page_start) + 1)
    ).issubset(chunk.page_numbers):
        return False
    if expected.source_type == "xlsx" and (
        chunk.table is None or chunk.table.sheet_name != expected.sheet_name
    ):
        return False
    if expected.cell_range is not None and not _chunk_covers_cell_range(
        chunk,
        expected.cell_range,
    ):
        return False
    if expected.row_start is not None and expected.row_end is not None:
        if chunk.table is None:
            return False
        rows = {row.source_row_number for row in chunk.table.rows}
        if not set(range(expected.row_start, expected.row_end + 1)).issubset(rows):
            return False
    if expected.source_type in {"xlsx", "csv"}:
        return True
    table_matches = [
        block
        for block in artifact.blocks
        if isinstance(block, ArtifactTableBlock)
        and _contains_exact([_table_block_view(block)], expected.exact_text)
    ]
    if table_matches:
        return any(
            block.block_id in chunk.source_block_ids
            and chunk.table is not None
            and _contains_exact(_chunk_views(chunk), expected.exact_text)
            for block in table_matches
        )
    occurrences = _text_occurrences(artifact, expected)
    return any(
        _chunk_covers_occurrence(chunk, occurrence) for occurrence in occurrences
    )


def _text_occurrences(
    artifact: CanonicalParsedArtifact,
    expected: ExpectedEvidenceSpan,
) -> list[_TextOccurrence]:
    needle = _match_normalize(expected.exact_text)
    flattened: list[str] = []
    references: list[_OccurrenceRange | None] = []
    last_was_space = False
    for block in artifact.blocks:
        if not isinstance(block, ArtifactTextBlock):
            continue
        page = block.locator.page_number
        if expected.page_start is not None and page not in range(
            expected.page_start,
            (expected.page_end or expected.page_start) + 1,
        ):
            continue
        normalized = normalize_source_text(block.text)
        for index, character in enumerate(normalized.text):
            expanded = unicodedata.normalize("NFKC", character).casefold()
            source = normalized.characters[index]
            for item in expanded:
                if item.isspace():
                    if flattened and not last_was_space:
                        flattened.append(" ")
                        references.append(None)
                        last_was_space = True
                    continue
                flattened.append(item)
                references.append(
                    _OccurrenceRange(
                        block_id=block.block_id,
                        source_start=source.source_start,
                        source_end=source.source_end,
                    )
                )
                last_was_space = False
        if flattened and not last_was_space:
            flattened.append(" ")
            references.append(None)
            last_was_space = True
    while flattened and flattened[-1] == " ":
        flattened.pop()
        references.pop()

    haystack = "".join(flattened)
    occurrences: list[_TextOccurrence] = []
    start = haystack.find(needle)
    while start >= 0:
        raw_ranges = [
            reference
            for reference in references[start : start + len(needle)]
            if reference is not None
        ]
        occurrences.append(_TextOccurrence(ranges=_coalesce_ranges(raw_ranges)))
        start = haystack.find(needle, start + 1)
    return occurrences


def _chunk_covers_occurrence(
    chunk: DocumentChunk,
    occurrence: _TextOccurrence,
) -> bool:
    by_block: dict[str, list[tuple[int, int]]] = {}
    for span in chunk.source_spans:
        if span.character_start is not None and span.character_end is not None:
            by_block.setdefault(span.block_id, []).append(
                (span.character_start, span.character_end)
            )
    return all(
        any(
            start <= required.source_start and end >= required.source_end
            for start, end in by_block.get(required.block_id, [])
        )
        for required in occurrence.ranges
    )


def _coalesce_ranges(
    ranges: Sequence[_OccurrenceRange],
) -> tuple[_OccurrenceRange, ...]:
    output: list[_OccurrenceRange] = []
    for item in ranges:
        if (
            output
            and output[-1].block_id == item.block_id
            and item.source_start <= output[-1].source_end
        ):
            previous = output[-1]
            output[-1] = _OccurrenceRange(
                block_id=previous.block_id,
                source_start=previous.source_start,
                source_end=max(previous.source_end, item.source_end),
            )
        else:
            output.append(item)
    return tuple(output)


_CELL_RANGE = re.compile(
    r"^(?P<start_col>[A-Z]{1,3})(?P<start_row>[1-9][0-9]*)"
    r"(?::(?P<end_col>[A-Z]{1,3})(?P<end_row>[1-9][0-9]*))?$"
)


def _chunk_covers_cell_range(chunk: DocumentChunk, expected: str) -> bool:
    if chunk.table is None or (match := _CELL_RANGE.fullmatch(expected)) is None:
        return False
    start_column = _column_number(match.group("start_col"))
    end_column = _column_number(match.group("end_col") or match.group("start_col"))
    start_row = int(match.group("start_row"))
    end_row = int(match.group("end_row") or match.group("start_row"))
    actual = {
        (cell.locator.row_number, cell.locator.column_number)
        for row in chunk.table.rows
        for cell in row.cells
    }
    required = {
        (row, column)
        for row in range(start_row, end_row + 1)
        for column in range(start_column, end_column + 1)
    }
    return required.issubset(actual)


def _column_number(label: str) -> int:
    value = 0
    for character in label:
        value = value * 26 + ord(character) - ord("A") + 1
    return value


def _audit_structure(
    artifact: CanonicalParsedArtifact,
    chunk_artifact: CanonicalChunkArtifact,
    *,
    source_id: str,
    logical_document_id: str,
    heading_cases: Sequence[TrustedHeadingContextCase],
) -> ChunkStructureAudit:
    chunks = chunk_artifact.chunks
    chunks_by_block: dict[str, list[DocumentChunk]] = {}
    for chunk in chunks:
        for block_id in chunk.source_block_ids:
            chunks_by_block.setdefault(block_id, []).append(chunk)
    normalized_body = {
        chunk.chunk_id: _match_normalize(chunk.body_text) for chunk in chunks
    }
    normalized_retrieval = {
        chunk.chunk_id: _match_normalize(chunk.retrieval_text) for chunk in chunks
    }
    config = chunk_artifact.config
    counter = UnicodeMixedTokenCounter()
    repeated_block_text = {
        (span.block_id, _match_normalize(span.text))
        for span in chunk_artifact.excluded_spans
        if span.reason in {"repeated_header", "repeated_footer"}
        and span.character_start is None
    }
    audited_heading_ranges = _audited_heading_ranges_by_block(
        artifact,
        chunks,
        chunk_artifact.excluded_spans,
    )
    ignored_ranges = _ignored_structure_ranges(
        artifact,
        chunk_artifact.excluded_spans,
        audited_heading_ranges,
    )
    paragraph_total = paragraph_preserved = 0
    header_total = header_preserved = 0
    footer_total = footer_preserved = 0
    ocr_total = ocr_preserved = 0
    relevant_heading_cases = [
        case
        for case in heading_cases
        if case.source_id == source_id and case.document_id == logical_document_id
    ]
    heading_checks = [
        _trusted_heading_context_is_preserved(
            case=case,
            artifact=artifact,
            chunks=chunks,
            exclusions=chunk_artifact.excluded_spans,
        )
        for case in relevant_heading_cases
    ]
    text_unit_results: list[bool] = []

    for block in artifact.blocks:
        if not isinstance(block, ArtifactTextBlock):
            continue
        units = _structure_text_units(block, source_type=artifact.source_type)
        for unit in units:
            residual = _text_after_ignored_ranges(
                block.text,
                unit,
                ignored_ranges.get(block.block_id, []),
            )
            normalized = _match_normalize(residual)
            if not normalized or (block.block_id, normalized) in repeated_block_text:
                continue
            heading_context = " > ".join(block.heading_path)
            if (
                counter.count(residual) + counter.count(heading_context)
                > config.max_tokens
            ):
                continue
            preserved = any(
                normalized in normalized_body[chunk.chunk_id]
                for chunk in chunks_by_block.get(block.block_id, [])
            )
            text_unit_results.append(preserved)
            if block.source_kind == "docx_header":
                header_total += 1
                header_preserved += preserved
            elif block.source_kind == "docx_footer":
                footer_total += 1
                footer_preserved += preserved
            elif block.source_kind == "docx_image_ocr":
                ocr_total += 1
                ocr_preserved += preserved
            elif block.heading_level is None:
                paragraph_total += 1
                paragraph_preserved += preserved

        if block.heading_path and not relevant_heading_cases:
            heading_checks.append(
                any(
                    chunk.heading_path == block.heading_path
                    and all(
                        _match_normalize(part) in normalized_retrieval[chunk.chunk_id]
                        for part in block.heading_path
                    )
                    and _chunk_has_source_backed_non_heading_body(
                        chunk,
                        artifact,
                        block.heading_path,
                    )
                    and (
                        block.block_id in chunk.source_block_ids
                        or _chunk_has_audited_heading_source(
                            chunk,
                            artifact,
                            chunk_artifact.excluded_spans,
                            block_id=block.block_id,
                        )
                    )
                    for chunk in chunks
                    if chunk.kind == "text"
                )
            )

    table_results = _table_row_integrity(
        artifact,
        chunk_artifact,
        chunks_by_block=chunks_by_block,
    )
    context_results = _image_context_integrity(artifact, chunks)
    boundary_results = [*text_unit_results, *table_results]
    boundary_breaks = sum(not passed for passed in boundary_results)
    return ChunkStructureAudit(
        paragraph_units=paragraph_total,
        paragraph_units_preserved=paragraph_preserved,
        heading_units=len(heading_checks),
        heading_units_preserved=sum(heading_checks),
        table_rows=len(table_results),
        table_rows_preserved=sum(table_results),
        docx_header_units=header_total,
        docx_header_units_preserved=header_preserved,
        docx_footer_units=footer_total,
        docx_footer_units_preserved=footer_preserved,
        image_ocr_units=ocr_total,
        image_ocr_units_preserved=ocr_preserved,
        context_links=len(context_results),
        context_links_preserved=sum(context_results),
        repeated_header_exclusions=sum(
            span.reason == "repeated_header" for span in chunk_artifact.excluded_spans
        ),
        repeated_footer_exclusions=sum(
            span.reason == "repeated_footer" for span in chunk_artifact.excluded_spans
        ),
        boundary_units=len(boundary_results),
        boundary_breaks=boundary_breaks,
        boundary_break_rate=(
            boundary_breaks / len(boundary_results) if boundary_results else None
        ),
    )


def _structure_text_units(
    block: ArtifactTextBlock,
    *,
    source_type: str,
) -> list[_StructureTextUnit]:
    normalized = normalize_source_text(block.text)
    if not normalized.text:
        return []
    if source_type != "pdf":
        start, end = normalized.source_range(0, len(normalized.text))
        return [_StructureTextUnit(block.text[start:end], start, end)]

    fallback_ranges: list[tuple[int, int]] = []
    normalized_start = 0
    for match in re.finditer(r"\n|$", normalized.text):
        normalized_end = match.start()
        while (
            normalized_start < normalized_end
            and normalized.text[normalized_start].isspace()
        ):
            normalized_start += 1
        while (
            normalized_end > normalized_start
            and normalized.text[normalized_end - 1].isspace()
        ):
            normalized_end -= 1
        if normalized_start < normalized_end:
            fallback_ranges.append((normalized_start, normalized_end))
        normalized_start = match.end()
        if match.start() == len(normalized.text):
            break

    located_ranges: list[tuple[int, int, int]] = []
    for line in block.pdf_layout_lines:
        if line.character_start is None or line.character_end is None:
            continue
        indexes = [
            index
            for index, character in enumerate(normalized.characters)
            if character.source_end > line.character_start
            and character.source_start < line.character_end
        ]
        if not indexes:
            continue
        start = indexes[0]
        end = indexes[-1] + 1
        while start < end and normalized.text[start].isspace():
            start += 1
        while end > start and normalized.text[end - 1].isspace():
            end -= 1
        if start < end and _match_normalize(
            normalized.text[start:end]
        ) == _match_normalize(line.text):
            located_ranges.append((start, end, line.line_number))
    if not located_ranges:
        return _source_units_from_normalized_ranges(
            block.text,
            normalized,
            fallback_ranges,
        )

    located_ranges.sort(key=lambda item: (item[0], item[1], item[2]))
    result_ranges = [(start, end) for start, end, _ in located_ranges]
    for line_start, line_end in fallback_ranges:
        cursor = line_start
        for start, end, _ in located_ranges:
            if end <= line_start or start >= line_end:
                continue
            residual_start = cursor
            residual_end = max(cursor, start)
            while (
                residual_start < residual_end
                and normalized.text[residual_start].isspace()
            ):
                residual_start += 1
            while (
                residual_end > residual_start
                and normalized.text[residual_end - 1].isspace()
            ):
                residual_end -= 1
            if residual_start < residual_end:
                result_ranges.append((residual_start, residual_end))
            cursor = max(cursor, end)
        residual_start = cursor
        residual_end = line_end
        while (
            residual_start < residual_end and normalized.text[residual_start].isspace()
        ):
            residual_start += 1
        while (
            residual_end > residual_start
            and normalized.text[residual_end - 1].isspace()
        ):
            residual_end -= 1
        if residual_start < residual_end:
            result_ranges.append((residual_start, residual_end))
    return _source_units_from_normalized_ranges(
        block.text,
        normalized,
        sorted(set(result_ranges)),
    )


def _source_units_from_normalized_ranges(
    source_text: str,
    normalized: NormalizedSourceText,
    ranges: Sequence[tuple[int, int]],
) -> list[_StructureTextUnit]:
    units: list[_StructureTextUnit] = []
    for start, end in ranges:
        source_start, source_end = normalized.source_range(start, end)
        units.append(
            _StructureTextUnit(
                text=source_text[source_start:source_end],
                character_start=source_start,
                character_end=source_end,
            )
        )
    return units


def _text_after_ignored_ranges(
    source_text: str,
    unit: _StructureTextUnit,
    ignored_ranges: Sequence[tuple[int, int]],
) -> str:
    cursor = unit.character_start
    parts: list[str] = []
    for start, end in sorted(ignored_ranges):
        if end <= cursor or start >= unit.character_end:
            continue
        clipped_start = max(start, unit.character_start)
        clipped_end = min(end, unit.character_end)
        if cursor < clipped_start:
            parts.append(source_text[cursor:clipped_start])
        cursor = max(cursor, clipped_end)
    if cursor < unit.character_end:
        parts.append(source_text[cursor : unit.character_end])
    return " ".join(parts)


def _ignored_structure_ranges(
    artifact: CanonicalParsedArtifact,
    exclusions: Sequence[ExcludedChunkSpan],
    audited_heading_ranges: dict[str, list[tuple[int, int]]],
) -> dict[str, list[tuple[int, int]]]:
    blocks = {
        block.block_id: block
        for block in artifact.blocks
        if isinstance(block, ArtifactTextBlock)
    }
    ignored = {
        block_id: list(ranges) for block_id, ranges in audited_heading_ranges.items()
    }
    for exclusion in exclusions:
        if exclusion.reason not in {"repeated_header", "repeated_footer", "noise"}:
            continue
        block = blocks.get(exclusion.block_id)
        start = exclusion.character_start
        end = exclusion.character_end
        if (
            block is None
            or start is None
            or end is None
            or end > len(block.text)
            or _match_normalize(block.text[start:end])
            != _match_normalize(exclusion.text)
        ):
            continue
        ignored.setdefault(exclusion.block_id, []).append((start, end))
    return {block_id: sorted(set(ranges)) for block_id, ranges in ignored.items()}


def _audited_heading_ranges_by_block(
    artifact: CanonicalParsedArtifact,
    chunks: Sequence[DocumentChunk],
    exclusions: Sequence[ExcludedChunkSpan],
) -> dict[str, list[tuple[int, int]]]:
    ranges: dict[str, list[tuple[int, int]]] = {}
    for chunk in chunks:
        for source in chunk.heading_sources:
            if not _heading_source_is_audited(
                source,
                chunk,
                artifact,
                exclusions,
            ):
                continue
            span = source.source_span
            assert span.character_start is not None
            assert span.character_end is not None
            ranges.setdefault(span.block_id, []).append(
                (span.character_start, span.character_end)
            )
    blocks = {
        block.block_id: block
        for block in artifact.blocks
        if isinstance(block, ArtifactTextBlock)
    }
    for exclusion in exclusions:
        block = blocks.get(exclusion.block_id)
        if block is None or not _heading_exclusion_is_audited(exclusion, block):
            continue
        assert exclusion.character_start is not None
        assert exclusion.character_end is not None
        ranges.setdefault(exclusion.block_id, []).append(
            (exclusion.character_start, exclusion.character_end)
        )
    return {block_id: sorted(set(items)) for block_id, items in ranges.items()}


def _heading_exclusion_is_audited(
    exclusion: ExcludedChunkSpan,
    block: ArtifactTextBlock,
) -> bool:
    start = exclusion.character_start
    end = exclusion.character_end
    if (
        exclusion.reason != "heading_metadata"
        or start is None
        or end is None
        or end > len(block.text)
        or exclusion.locator != block.locator
        or _match_normalize(block.text[start:end]) != _match_normalize(exclusion.text)
    ):
        return False
    normalized = normalize_source_text(exclusion.text).text
    without_label = _HEADING_LABEL_PREFIX.sub("", normalized, count=1).strip()
    return _block_declares_heading_source(block, without_label or normalized)


def _chunk_has_audited_heading_source(
    chunk: DocumentChunk,
    artifact: CanonicalParsedArtifact,
    exclusions: Sequence[ExcludedChunkSpan],
    *,
    heading_text: str | None = None,
    page_number: int | None = None,
    block_id: str | None = None,
) -> bool:
    target = _match_normalize(heading_text) if heading_text is not None else None
    for source in chunk.heading_sources:
        span = source.source_span
        if target is not None and _match_normalize(source.heading_text) != target:
            continue
        if page_number is not None and span.start_locator.page_number != page_number:
            continue
        if block_id is not None and span.block_id != block_id:
            continue
        if _heading_source_is_audited(source, chunk, artifact, exclusions):
            return True
    return False


def _heading_source_is_audited(
    source: ChunkHeadingSource,
    chunk: DocumentChunk,
    artifact: CanonicalParsedArtifact,
    exclusions: Sequence[ExcludedChunkSpan],
) -> bool:
    if chunk.kind != "text" or source.heading_path_index >= len(chunk.heading_path):
        return False
    if chunk.heading_path[source.heading_path_index] != source.heading_text:
        return False
    if not _chunk_has_source_backed_non_heading_body(
        chunk,
        artifact,
        chunk.heading_path,
    ):
        return False
    normalized_retrieval = _match_normalize(chunk.retrieval_text)
    if any(
        _match_normalize(part) not in normalized_retrieval
        for part in chunk.heading_path
    ):
        return False

    blocks = {
        block.block_id: block
        for block in artifact.blocks
        if isinstance(block, ArtifactTextBlock)
    }
    block = blocks.get(source.source_span.block_id)
    start = source.source_span.character_start
    end = source.source_span.character_end
    if (
        block is None
        or start is None
        or end is None
        or end > len(block.text)
        or source.source_span.start_locator != block.locator
        or source.source_span.end_locator != block.locator
    ):
        return False
    source_slice = block.text[start:end]
    if (
        _match_normalize(source_slice) != _match_normalize(source.source_text)
        or _match_normalize(source.heading_text) not in _match_normalize(source_slice)
        or not _block_declares_heading_source(block, source.heading_text)
    ):
        return False
    return any(
        exclusion.reason == "heading_metadata"
        and exclusion.block_id == block.block_id
        and exclusion.character_start == start
        and exclusion.character_end == end
        and exclusion.locator == block.locator
        and _match_normalize(exclusion.text) == _match_normalize(source_slice)
        for exclusion in exclusions
    )


def _block_declares_heading_source(
    block: ArtifactTextBlock,
    heading_text: str,
) -> bool:
    target = _match_normalize(heading_text)
    if block.heading_level is not None and any(
        _match_normalize(part) == target for part in block.heading_path
    ):
        return True
    hints = [
        hint.text
        for hint in block.heading_hints
        if hint.locator.page_number == block.locator.page_number
    ]
    for start in range(len(hints)):
        for width in range(1, min(9, len(hints) - start) + 1):
            candidate = " ".join(hints[start : start + width])
            normalized_candidate = normalize_source_text(candidate).text
            without_label = _HEADING_LABEL_PREFIX.sub(
                "",
                normalized_candidate,
                count=1,
            ).strip()
            if _match_normalize(without_label) == target:
                return True
    return False


def _trusted_heading_context_is_preserved(
    *,
    case: TrustedHeadingContextCase,
    artifact: CanonicalParsedArtifact,
    chunks: Sequence[DocumentChunk],
    exclusions: Sequence[ExcludedChunkSpan],
) -> bool:
    if not _artifact_has_heading_source(artifact, case):
        return False
    body_span = ExpectedEvidenceSpan(
        source_id=case.source_id,
        document_id=case.document_id,
        source_type=case.source_type,
        page_start=case.body_page_number,
        page_end=case.body_page_number,
        exact_text=case.body_exact_text,
    )
    expected_path = [_match_normalize(part) for part in case.heading_path]
    return any(
        [_match_normalize(part) for part in chunk.heading_path] == expected_path
        and _contains_exact([chunk.body_text], case.body_exact_text)
        and all(
            part in _match_normalize(chunk.retrieval_text) for part in expected_path
        )
        and _chunk_covers_expected_span(chunk, body_span, artifact)
        and _chunk_has_source_backed_non_heading_body(
            chunk,
            artifact,
            case.heading_path,
        )
        and _chunk_has_audited_heading_source(
            chunk,
            artifact,
            exclusions,
            heading_text=case.heading_exact_text,
            page_number=case.heading_page_number,
        )
        for chunk in chunks
        if chunk.kind == "text"
    )


def _artifact_has_heading_source(
    artifact: CanonicalParsedArtifact,
    case: TrustedHeadingContextCase,
) -> bool:
    target = _match_normalize(case.heading_exact_text)
    page_hints = [
        hint.text
        for block in artifact.blocks
        if isinstance(block, ArtifactTextBlock)
        for hint in block.heading_hints
        if hint.locator.page_number == case.heading_page_number
    ]
    for start in range(len(page_hints)):
        for width in range(1, min(4, len(page_hints) - start) + 1):
            if _match_normalize(" ".join(page_hints[start : start + width])) == target:
                return True
    return any(
        block.locator.page_number == case.heading_page_number
        and any(_match_normalize(part) == target for part in block.heading_path)
        for block in artifact.blocks
        if isinstance(block, ArtifactTextBlock)
    )


def _chunk_has_source_backed_non_heading_body(
    chunk: DocumentChunk,
    artifact: CanonicalParsedArtifact,
    heading_path: Sequence[str],
) -> bool:
    normalized_body = _match_normalize(chunk.body_text)
    normalized_headings = {_match_normalize(part) for part in heading_path}
    if not normalized_body or normalized_body in normalized_headings:
        return False
    blocks = {block.block_id: block for block in artifact.blocks}
    for span in chunk.source_spans:
        block = blocks.get(span.block_id)
        if (
            not isinstance(block, ArtifactTextBlock)
            or span.character_start is None
            or span.character_end is None
            or span.character_end > len(block.text)
        ):
            continue
        source_slice = _match_normalize(
            block.text[span.character_start : span.character_end]
        )
        if (
            source_slice
            and source_slice not in normalized_headings
            and source_slice in normalized_body
        ):
            return True
    return False


def _table_row_integrity(
    artifact: CanonicalParsedArtifact,
    chunk_artifact: CanonicalChunkArtifact,
    *,
    chunks_by_block: dict[str, list[DocumentChunk]],
) -> list[bool]:
    counter = UnicodeMixedTokenCounter()
    results: list[bool] = []
    for block in artifact.blocks:
        if not isinstance(block, ArtifactTableBlock):
            continue
        header_numbers = {
            row.row_number
            for row in block.rows
            if row.row_number == block.header_row_number
            or any(cell.column_header for cell in row.cells)
        }
        headers = [row for row in block.rows if row.row_number in header_numbers]
        for row in block.rows:
            if not any(cell.display_text.strip() or cell.formula for cell in row.cells):
                continue
            required = [row] if row.row_number in header_numbers else [*headers, row]
            rough_text = " ".join(
                _cell_evidence_parts(cell)
                for required_row in required
                for cell in required_row.cells
            )
            if counter.count(rough_text) > chunk_artifact.config.max_tokens:
                continue
            results.append(
                any(
                    chunk.table is not None
                    and all(_chunk_has_artifact_row(chunk, item) for item in required)
                    for chunk in chunks_by_block.get(block.block_id, [])
                )
            )
    return results


def _chunk_has_artifact_row(
    chunk: DocumentChunk,
    expected: ArtifactTableRow,
) -> bool:
    if chunk.table is None:
        return False
    for row in chunk.table.rows:
        if row.source_row_number != expected.row_number:
            continue
        actual = {cell.column_number: cell for cell in row.cells}
        if all(actual.get(cell.column_number) == cell for cell in expected.cells):
            return True
    return False


def _image_context_integrity(
    artifact: CanonicalParsedArtifact,
    chunks: Sequence[DocumentChunk],
) -> list[bool]:
    blocks = list(artifact.blocks)
    block_indices = {
        block_id: {
            index
            for index, chunk in enumerate(chunks, start=1)
            if block_id in chunk.source_block_ids
        }
        for block_id in (block.block_id for block in blocks)
    }
    results: list[bool] = []
    for index, block in enumerate(blocks):
        if (
            not isinstance(block, ArtifactTextBlock)
            or block.source_kind != "docx_image_ocr"
        ):
            continue
        previous = next(
            (
                item
                for item in reversed(blocks[:index])
                if isinstance(item, ArtifactTextBlock)
                and item.source_kind == "document_text"
                and item.text.strip()
            ),
            None,
        )
        following = next(
            (
                item
                for item in blocks[index + 1 :]
                if isinstance(item, ArtifactTextBlock)
                and item.source_kind == "document_text"
                and item.text.strip()
            ),
            None,
        )
        if previous is None or following is None:
            results.append(False)
            continue
        results.append(
            any(
                before <= image <= after and image - before <= 1 and after - image <= 1
                for before in block_indices[previous.block_id]
                for image in block_indices[block.block_id]
                for after in block_indices[following.block_id]
            )
        )
    return results


def _source_order_is_preserved(chunks: Sequence[DocumentChunk]) -> bool:
    anchors = [_chunk_anchor(chunk) for chunk in chunks]
    return anchors == sorted(anchors)


def _chunk_anchor(chunk: DocumentChunk) -> tuple[int, int]:
    block = min(int(block_id[1:]) for block_id in chunk.source_block_ids)
    if chunk.table is not None:
        primary = [
            row.source_row_number
            for row in chunk.table.rows
            if not row.repeated_as_context
        ]
        return block, min(
            primary or [row.source_row_number for row in chunk.table.rows]
        )
    starts = [
        span.character_start
        for span in chunk.source_spans
        if span.block_id == f"b{block:06d}" and span.character_start is not None
    ]
    return block, min(starts or [0])


def _locator_integrity_is_preserved(
    artifact: CanonicalParsedArtifact,
    chunks: Sequence[DocumentChunk],
) -> bool:
    blocks = {block.block_id: block for block in artifact.blocks}
    for chunk in chunks:
        if any(block_id not in blocks for block_id in chunk.source_block_ids):
            return False
        expected_pages: set[int] = set()
        for span in chunk.source_spans:
            block = blocks.get(span.block_id)
            if block is None:
                return False
            if isinstance(block, ArtifactTextBlock):
                if (
                    span.start_locator != block.locator
                    or span.end_locator != block.locator
                    or span.character_start is None
                    or span.character_end is None
                    or span.character_end > len(block.text)
                ):
                    return False
            else:
                locators = [cell.locator for row in block.rows for cell in row.cells]
                if (
                    span.start_locator not in locators
                    or span.end_locator not in locators
                ):
                    return False
            for locator in (block.locator, span.start_locator, span.end_locator):
                if locator.page_number is not None:
                    expected_pages.add(locator.page_number)
        if chunk.table is not None:
            table_blocks = [
                blocks[block_id]
                for block_id in chunk.source_block_ids
                if isinstance(blocks[block_id], ArtifactTableBlock)
            ]
            if len(table_blocks) != 1:
                return False
            table_block = table_blocks[0]
            assert isinstance(table_block, ArtifactTableBlock)
            for row in chunk.table.rows:
                matching = next(
                    (
                        source_row
                        for source_row in table_block.rows
                        if source_row.row_number == row.source_row_number
                    ),
                    None,
                )
                if matching is None or any(
                    cell not in matching.cells for cell in row.cells
                ):
                    return False
                expected_pages.update(
                    cell.locator.page_number
                    for cell in row.cells
                    if cell.locator.page_number is not None
                )
        if chunk.page_numbers != sorted(expected_pages):
            return False
    return True


def _near_duplicate_chunk_count(chunks: Sequence[DocumentChunk]) -> int:
    normalized = [_match_normalize(chunk.body_text) for chunk in chunks]
    token_sets = [
        {span.text.casefold() for span in UnicodeMixedTokenCounter().spans(text)}
        for text in normalized
    ]
    duplicates = 0
    for index in range(1, len(chunks)):
        for previous in range(index):
            if normalized[index] == normalized[previous]:
                duplicates += 1
                break
            left = token_sets[index]
            right = token_sets[previous]
            if min(len(left), len(right)) < 20:
                continue
            union = left | right
            if union and len(left & right) / len(union) >= 0.90:
                duplicates += 1
                break
    return duplicates


def _contiguous_token_coverage(expected: str, actual: str) -> float:
    counter = UnicodeMixedTokenCounter()
    needle = [
        span.text.casefold() for span in counter.spans(_match_normalize(expected))
    ]
    haystack = [
        span.text.casefold() for span in counter.spans(_match_normalize(actual))
    ]
    if not needle:
        return 0.0
    previous = [0] * (len(haystack) + 1)
    longest = 0
    for expected_token in needle:
        current = [0] * (len(haystack) + 1)
        for index, actual_token in enumerate(haystack, start=1):
            if expected_token == actual_token:
                current[index] = previous[index - 1] + 1
                longest = max(longest, current[index])
        previous = current
    return longest / len(needle)


def _match_normalize(value: str) -> str:
    normalized, _positions = _match_normalize_with_positions(value)
    return normalized


def _match_normalize_with_positions(value: str) -> tuple[str, list[int]]:
    output: list[str] = []
    positions: list[int] = []
    for index, character in enumerate(value):
        expanded = unicodedata.normalize("NFKC", character).casefold()
        for item in expanded:
            if item.isspace():
                if output and output[-1] != " ":
                    output.append(" ")
                    positions.append(index)
                continue
            output.append(item)
            positions.append(index)
    while output and output[-1] == " ":
        output.pop()
        positions.pop()
    return "".join(output), positions


def _percentile(values: Sequence[int], quantile: float) -> int:
    return values[max(0, math.ceil(len(values) * quantile) - 1)]


__all__ = [
    "ChunkConfigurationAggregate",
    "ChunkDocumentQuality",
    "ChunkFailureLayer",
    "ChunkStructureAudit",
    "GoldenChunkCaseResult",
    "aggregate_chunk_documents",
    "evaluate_chunk_document",
    "select_first_round_candidates",
]
