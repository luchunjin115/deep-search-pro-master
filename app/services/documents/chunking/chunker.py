"""Parser-independent, structure-aware text chunking for PDF and DOCX."""

from __future__ import annotations

import re
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.common import M1Schema
from app.services.documents.artifacts import (
    ArtifactBoundingBox,
    ArtifactTableBlock,
    ArtifactTextBlock,
    CanonicalParsedArtifact,
)
from app.services.documents.chunking.contracts import (
    ChunkHeadingSource,
    ChunkingConfig,
    ChunkOverlap,
    ChunkSourceSpan,
    DocumentChunk,
    ExcludedChunkSpan,
    build_document_chunk,
)
from app.services.documents.chunking.normalization import (
    NormalizedSourceText,
    normalize_source_text,
)
from app.services.documents.chunking.token_counting import (
    TokenCounter,
    TokenSpan,
    UnicodeMixedTokenCounter,
)
from app.services.documents.parsers.base import SourceLocator

_LIST_MARKER = re.compile(
    r"^(?:[-*–—]\s+|[•▪◦]\s*|(?:\d{1,4}|[A-Za-z])[.)、]\s*)",
)
_BULLET_HEADING_MARKER = re.compile(r"^(?:[-*–—]\s+|[•▪◦\x07]\s*)")
_OUTLINE_PREFIX = re.compile(
    r"^(?:"
    r"(?:\d{1,4}(?:\.\d{1,4})*)[.)、:]?"
    r"|[A-Za-z][.)、]"
    r"|[（(]?[一二三四五六七八九十]+[)）.、]"
    r")\s*$",
)
_HEADING_LABEL_PREFIX = re.compile(
    r"^(?:"
    r"(?:\d{1,4}(?:\.\d{1,4})*)[.)、:]"
    r"|[A-Za-z][.)、]"
    r"|[（(]?[一二三四五六七八九十]+[)）.、]"
    r")\s+",
)
_ROOT_SECTION_PREFIX = re.compile(
    r"^(?:part|annex|chapter|section)\s+[A-Za-z0-9]",
    flags=re.IGNORECASE,
)
_CURRENCY_VALUE = re.compile(
    r"^(?:approximately\s+)?(?:EUR|USD|GBP|CNY|JPY|€|\$|£|¥)\s*"
    r"\d[\d.,]*(?:\s+(?:billion|million|thousand))?(?:\s+per\s+\w+)?$",
    flags=re.IGNORECASE,
)
_REFERENCE_CODE_VALUE = re.compile(r"^[A-Z]?\d+(?:[/_-]\d+){1,}[A-Z]?$", re.IGNORECASE)
_FIELD_LABEL = re.compile(
    r"(?:number|identifier|reference|code|date|country|category|brand|model|type)$",
    flags=re.IGNORECASE,
)
_BOUNDARY_PATTERNS = (
    re.compile(r"\n\s*\n"),
    re.compile(r"[。！？.!?](?:[”’」』】）》])?"),
    re.compile(r"[；;，,、:]"),
    re.compile(r"\s+"),
)


class DocumentChunkingError(RuntimeError):
    """Safe failure for unsupported or internally inconsistent chunk input."""


class TextChunkingResult(M1Schema):
    """M2-12.2 text-only output; table blocks are explicit deferred work."""

    chunks: list[DocumentChunk] = Field(max_length=1_100_000)
    excluded_spans: list[ExcludedChunkSpan] = Field(max_length=1_100_000)
    deferred_table_block_ids: list[str] = Field(max_length=100_000)

    @model_validator(mode="after")
    def validate_text_only_result(self) -> TextChunkingResult:
        if any(chunk.kind != "text" for chunk in self.chunks):
            raise ValueError("text chunking result cannot contain table chunks")
        if self.deferred_table_block_ids != list(
            dict.fromkeys(self.deferred_table_block_ids)
        ):
            raise ValueError("deferred table block IDs must be unique and ordered")
        heading_exclusions = {
            (
                span.block_id,
                span.character_start,
                span.character_end,
                span.text,
            )
            for span in self.excluded_spans
            if span.reason == "heading_metadata"
        }
        if any(
            (
                source.source_span.block_id,
                source.source_span.character_start,
                source.source_span.character_end,
                source.source_text,
            )
            not in heading_exclusions
            for chunk in self.chunks
            for source in chunk.heading_sources
        ):
            raise ValueError("heading source is missing its exact exclusion audit")
        return self


@dataclass(frozen=True, slots=True)
class _MappedCharacter:
    block_id: str
    source_start: int
    source_end: int
    locator: SourceLocator
    bounding_box: ArtifactBoundingBox | None


@dataclass(frozen=True, slots=True)
class _TextUnit:
    text: str
    characters: tuple[_MappedCharacter, ...]
    heading_path: tuple[str, ...]
    heading_sources: tuple[ChunkHeadingSource, ...]
    role: Literal["heading", "paragraph", "list_item"]


@dataclass(slots=True)
class _TextGroup:
    heading_path: tuple[str, ...]
    heading_sources: tuple[ChunkHeadingSource, ...]
    text_parts: list[str] = field(default_factory=list)
    characters: list[_MappedCharacter | None] = field(default_factory=list)
    last_role: Literal["heading", "paragraph", "list_item"] | None = None

    @property
    def text(self) -> str:
        return "".join(self.text_parts)

    def append(self, unit: _TextUnit) -> None:
        if self.text_parts:
            separator = "\n" if self.last_role == unit.role == "list_item" else "\n\n"
            self.text_parts.append(separator)
            self.characters.extend([None] * len(separator))
        self.text_parts.append(unit.text)
        self.characters.extend(unit.characters)
        self.last_role = unit.role


@dataclass(frozen=True, slots=True)
class _LineSlice:
    block: ArtifactTextBlock
    normalized: NormalizedSourceText
    start: int
    end: int
    layout_line_number: int | None = None
    bounding_box: ArtifactBoundingBox | None = None

    @property
    def text(self) -> str:
        return self.normalized.text[self.start : self.end]


@dataclass(frozen=True, slots=True)
class _ExcludedLineKey:
    block_id: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class _HeadingMatch:
    text: str
    level: int
    start: int
    end: int
    lane: int | None = None
    force_root: bool = False


@dataclass(frozen=True, slots=True)
class _HeadingSourceReference:
    heading_text: str
    source_text: str
    source_span: ChunkSourceSpan


class StructureAwareTextChunker:
    """Create deterministic text Chunks from Canonical PDF/DOCX blocks only."""

    def __init__(
        self,
        *,
        config: ChunkingConfig | None = None,
        token_counter: TokenCounter | None = None,
    ) -> None:
        self._config = config or ChunkingConfig()
        self._counter = token_counter or UnicodeMixedTokenCounter()

    @property
    def config(self) -> ChunkingConfig:
        return self._config

    @property
    def token_counter(self) -> TokenCounter:
        return self._counter

    def chunk(self, artifact: CanonicalParsedArtifact) -> TextChunkingResult:
        if artifact.source_type not in {"pdf", "docx"}:
            raise DocumentChunkingError("M2-12.2只支持Canonical PDF/DOCX文本切块")

        normalized_blocks = {
            block.block_id: normalize_source_text(block.text)
            for block in artifact.blocks
            if isinstance(block, ArtifactTextBlock)
        }
        repeated_lines = (
            self._find_repeated_pdf_edges(artifact, normalized_blocks)
            if artifact.source_type == "pdf"
            else {}
        )
        groups, excluded, deferred = self._build_groups(
            artifact,
            normalized_blocks,
            repeated_lines,
        )
        chunks: list[DocumentChunk] = []
        for group in groups:
            chunks.extend(self._chunk_group(group, first_chunk_index=len(chunks) + 1))
        return TextChunkingResult(
            chunks=chunks,
            excluded_spans=excluded,
            deferred_table_block_ids=deferred,
        )

    def _find_repeated_pdf_edges(
        self,
        artifact: CanonicalParsedArtifact,
        normalized_blocks: dict[str, NormalizedSourceText],
    ) -> dict[_ExcludedLineKey, Literal["repeated_header", "repeated_footer"]]:
        lines_by_page: dict[int, list[_LineSlice]] = {}
        for block in artifact.blocks:
            if not isinstance(block, ArtifactTextBlock):
                continue
            page_number = block.locator.page_number
            if page_number is None:
                continue
            normalized = normalized_blocks[block.block_id]
            lines_by_page.setdefault(page_number, []).extend(
                _line_slices(block, normalized)
            )

        header_candidates: list[_LineSlice] = []
        footer_candidates: list[_LineSlice] = []
        for page_number in sorted(lines_by_page):
            lines = lines_by_page[page_number]
            if len(lines) < 2:
                continue
            if _eligible_repeated_edge(lines[0].text):
                header_candidates.append(lines[0])
            if lines[-1].text != lines[0].text and _eligible_repeated_edge(
                lines[-1].text
            ):
                footer_candidates.append(lines[-1])

        header_counts = Counter(line.text for line in header_candidates)
        footer_counts = Counter(line.text for line in footer_candidates)
        repeated: dict[
            _ExcludedLineKey,
            Literal["repeated_header", "repeated_footer"],
        ] = {}
        for line in header_candidates:
            if header_counts[line.text] >= self._config.repeated_edge_min_pages:
                repeated[_line_key(line)] = "repeated_header"
        for line in footer_candidates:
            if footer_counts[line.text] >= self._config.repeated_edge_min_pages:
                repeated[_line_key(line)] = "repeated_footer"
        return repeated

    def _build_groups(
        self,
        artifact: CanonicalParsedArtifact,
        normalized_blocks: dict[str, NormalizedSourceText],
        repeated_lines: dict[
            _ExcludedLineKey,
            Literal["repeated_header", "repeated_footer"],
        ],
    ) -> tuple[list[_TextGroup], list[ExcludedChunkSpan], list[str]]:
        groups: list[_TextGroup] = []
        excluded: list[ExcludedChunkSpan] = []
        deferred: list[str] = []
        current: _TextGroup | None = None
        pdf_headings: dict[int, _HeadingSourceReference] = {}

        def append_unit(unit: _TextUnit) -> None:
            nonlocal current
            if (
                current is None
                or current.heading_path != unit.heading_path
                or current.heading_sources != unit.heading_sources
            ):
                if current is not None:
                    groups.append(current)
                current = _TextGroup(
                    heading_path=unit.heading_path,
                    heading_sources=unit.heading_sources,
                )
            current.append(unit)

        def flush() -> None:
            nonlocal current
            if current is not None:
                groups.append(current)
                current = None

        for block in artifact.blocks:
            if isinstance(block, ArtifactTableBlock):
                flush()
                deferred.append(block.block_id)
                continue

            normalized = normalized_blocks[block.block_id]
            if not normalized.text:
                excluded.append(
                    ExcludedChunkSpan(
                        block_id=block.block_id,
                        reason="blank",
                        text="",
                        locator=block.locator,
                        bounding_box=block.bounding_box,
                    )
                )
                continue

            if artifact.source_type == "docx":
                append_unit(_docx_unit(block, normalized))
                continue

            lines = _pdf_slices(block, normalized)
            heading_lanes = _parallel_heading_lanes(block)
            heading_matches, consumed_heading_lines = _prepared_heading_matches(
                block,
                lines,
                heading_lanes,
            )
            lane_headings: dict[int, dict[int, _HeadingSourceReference]] = {}
            for line_index, line in enumerate(lines):
                if line_index in consumed_heading_lines:
                    if not any(
                        heading.start <= line.start and line.end <= heading.end
                        for retained_index, heading in heading_matches.items()
                        if retained_index not in consumed_heading_lines
                    ):
                        excluded.append(
                            _excluded_span_from_range(
                                block,
                                normalized,
                                line.start,
                                line.end,
                                reason="noise",
                                bounding_box=line.bounding_box,
                            )
                        )
                    continue
                exclusion_reason = _slice_exclusion_reason(line, repeated_lines)
                if exclusion_reason is not None:
                    excluded.append(
                        _excluded_span_from_range(
                            block,
                            normalized,
                            line.start,
                            line.end,
                            reason=exclusion_reason,
                            bounding_box=(
                                line.bounding_box or block.bounding_box
                                if line.start == 0 and line.end == len(normalized.text)
                                else line.bounding_box
                            ),
                        )
                    )
                    continue

                heading = heading_matches.get(line_index)
                if heading is not None:
                    heading_level = (
                        1
                        if heading.force_root
                        or _ROOT_SECTION_PREFIX.match(heading.text)
                        else heading.level
                    )
                    heading_source = _heading_source_reference(
                        block,
                        normalized,
                        heading,
                        fallback_bounding_box=line.bounding_box,
                    )
                    excluded.append(
                        _excluded_span_from_range(
                            block,
                            normalized,
                            heading.start,
                            heading.end,
                            reason="heading_metadata",
                            bounding_box=line.bounding_box,
                        )
                    )
                    if heading.lane is None:
                        pdf_headings = _updated_heading_stack(
                            pdf_headings,
                            level=heading_level,
                            source=heading_source,
                        )
                        lane_headings.clear()
                    else:
                        lane_headings[heading.lane] = _updated_heading_stack(
                            {
                                level: source
                                for level, source in pdf_headings.items()
                                if level < heading_level
                            },
                            level=heading_level,
                            source=heading_source,
                        )
                    body_start, body_end = _trim_range(
                        normalized.text,
                        heading.end,
                        line.end,
                    )
                    if body_start >= body_end:
                        continue
                    heading_path, heading_sources = _pdf_heading_context(
                        block,
                        pdf_headings,
                        lane_headings,
                        line,
                        preferred_lane=heading.lane,
                    )
                    append_unit(
                        _unit_from_slice(
                            block,
                            normalized,
                            body_start,
                            body_end,
                            heading_path=heading_path,
                            heading_sources=heading_sources,
                            role=_text_role(normalized.text[body_start:body_end]),
                            bounding_box=line.bounding_box,
                        )
                    )
                    continue

                heading_path, heading_sources = _pdf_heading_context(
                    block,
                    pdf_headings,
                    lane_headings,
                    line,
                )
                append_unit(
                    _unit_from_slice(
                        block,
                        normalized,
                        line.start,
                        line.end,
                        heading_path=heading_path,
                        heading_sources=heading_sources,
                        role=_text_role(line.text),
                        bounding_box=line.bounding_box,
                    )
                )
        flush()
        return groups, excluded, deferred

    def _chunk_group(
        self,
        group: _TextGroup,
        *,
        first_chunk_index: int,
    ) -> list[DocumentChunk]:
        text = group.text
        tokens = self._counter.spans(text)
        if not tokens:
            return []
        heading_context = self._heading_context(group.heading_path)
        heading_tokens = self._counter.count(heading_context)
        target_body_tokens = self._config.target_tokens - heading_tokens
        hard_body_tokens = self._config.max_tokens - heading_tokens
        if target_body_tokens <= self._config.overlap_tokens or hard_body_tokens <= 0:
            raise DocumentChunkingError("标题上下文占用了过多切块预算")

        token_ends = [token.end for token in tokens]
        chunks: list[DocumentChunk] = []
        start = tokens[0].start
        previous_end: int | None = None
        while start < len(text):
            start_token_index = bisect_right(token_ends, start)
            if start_token_index >= len(tokens):
                break
            end = _window_end(
                text=text,
                tokens=tokens,
                start_token_index=start_token_index,
                target_body_tokens=target_body_tokens,
                hard_body_tokens=hard_body_tokens,
            )
            body_start, body_end = _trim_range(text, start, end)
            if body_start >= body_end:
                raise DocumentChunkingError("切块窗口没有可索引文字")
            body_text = text[body_start:body_end]
            retrieval_text = (
                f"{heading_context}\n\n{body_text}" if heading_context else body_text
            )
            token_count = self._counter.count(retrieval_text)
            if token_count > self._config.max_tokens:
                raise DocumentChunkingError("文本切块超过已冻结的Token硬上限")

            chunk_index = first_chunk_index + len(chunks)
            source_spans = _source_spans(group.characters, body_start, body_end)
            if not source_spans:
                raise DocumentChunkingError("文本切块缺少Canonical来源定位")
            overlap = None
            if previous_end is not None:
                overlap_start, overlap_end = _trim_range(
                    text,
                    body_start,
                    min(previous_end, body_end),
                )
                overlap_spans = _source_spans(
                    group.characters,
                    overlap_start,
                    overlap_end,
                )
                overlap_count = self._counter.count(text[overlap_start:overlap_end])
                if overlap_count and overlap_spans:
                    overlap = ChunkOverlap(
                        previous_chunk_id=f"c{chunk_index - 1:06d}",
                        token_count=overlap_count,
                        source_spans=overlap_spans,
                    )

            chunks.append(
                build_document_chunk(
                    chunk_id=f"c{chunk_index:06d}",
                    chunk_index=chunk_index,
                    kind="text",
                    body_text=body_text,
                    retrieval_text=retrieval_text,
                    token_count=token_count,
                    heading_path=list(group.heading_path),
                    heading_sources=list(group.heading_sources),
                    source_block_ids=list(
                        dict.fromkeys(span.block_id for span in source_spans)
                    ),
                    source_spans=source_spans,
                    page_numbers=_page_numbers(source_spans),
                    bounding_boxes=_bounding_boxes(source_spans),
                    overlap=overlap,
                )
            )
            if body_end >= tokens[-1].end:
                break
            end_token_index = bisect_right(token_ends, body_end)
            next_token_index = max(
                start_token_index + 1,
                end_token_index - self._config.overlap_tokens,
            )
            if next_token_index >= len(tokens):
                break
            next_start = tokens[next_token_index].start
            if next_start <= start:
                raise DocumentChunkingError("重叠窗口没有向前推进")
            previous_end = body_end
            start = next_start
        return chunks

    def _heading_context(self, heading_path: tuple[str, ...]) -> str:
        context = " > ".join(heading_path)
        spans = self._counter.spans(context)
        if len(spans) <= self._config.heading_context_max_tokens:
            return context
        return context[spans[-self._config.heading_context_max_tokens].start :]


def _docx_unit(
    block: ArtifactTextBlock,
    normalized: NormalizedSourceText,
) -> _TextUnit:
    role: Literal["heading", "paragraph", "list_item"] = (
        "heading" if block.heading_level is not None else _text_role(normalized.text)
    )
    return _unit_from_slice(
        block,
        normalized,
        0,
        len(normalized.text),
        heading_path=tuple(block.heading_path),
        heading_sources=(),
        role=role,
    )


def _text_role(text: str) -> Literal["paragraph", "list_item"]:
    return "list_item" if _LIST_MARKER.match(text) else "paragraph"


def _unit_from_slice(
    block: ArtifactTextBlock,
    normalized: NormalizedSourceText,
    start: int,
    end: int,
    *,
    heading_path: tuple[str, ...],
    heading_sources: tuple[ChunkHeadingSource, ...],
    role: Literal["heading", "paragraph", "list_item"],
    bounding_box: ArtifactBoundingBox | None = None,
) -> _TextUnit:
    return _TextUnit(
        text=normalized.text[start:end],
        characters=tuple(
            _MappedCharacter(
                block_id=block.block_id,
                source_start=character.source_start,
                source_end=character.source_end,
                locator=block.locator,
                bounding_box=bounding_box or block.bounding_box,
            )
            for character in normalized.characters[start:end]
        ),
        heading_path=heading_path,
        heading_sources=heading_sources,
        role=role,
    )


def _line_slices(
    block: ArtifactTextBlock,
    normalized: NormalizedSourceText,
) -> list[_LineSlice]:
    lines: list[_LineSlice] = []
    start = 0
    for match in re.finditer(r"\n|$", normalized.text):
        end = match.start()
        trimmed_start, trimmed_end = _trim_range(normalized.text, start, end)
        if trimmed_start < trimmed_end:
            lines.append(_LineSlice(block, normalized, trimmed_start, trimmed_end))
        start = match.end()
        if match.start() == len(normalized.text):
            break
    return lines


def _pdf_slices(
    block: ArtifactTextBlock,
    normalized: NormalizedSourceText,
) -> list[_LineSlice]:
    fallback = _line_slices(block, normalized)
    if not block.pdf_layout_lines:
        return fallback

    located: list[_LineSlice] = []
    for layout_line in block.pdf_layout_lines:
        if layout_line.character_start is None or layout_line.character_end is None:
            continue
        normalized_range = _normalized_range_for_source(
            normalized,
            layout_line.character_start,
            layout_line.character_end,
        )
        if normalized_range is None:
            continue
        start, end = normalized_range
        if _comparable_text(normalized.text[start:end]) != _comparable_text(
            layout_line.text
        ):
            continue
        located.append(
            _LineSlice(
                block=block,
                normalized=normalized,
                start=start,
                end=end,
                layout_line_number=layout_line.line_number,
                bounding_box=layout_line.bounding_box,
            )
        )

    if not located:
        return fallback

    located.sort(key=lambda item: (item.start, item.end, item.layout_line_number or 0))
    result = list(located)
    for line in fallback:
        cursor = line.start
        for item in located:
            if item.end <= line.start or item.start >= line.end:
                continue
            residual_start, residual_end = _trim_range(
                normalized.text,
                cursor,
                max(cursor, item.start),
            )
            if residual_start < residual_end:
                result.append(
                    _LineSlice(block, normalized, residual_start, residual_end)
                )
            cursor = max(cursor, item.end)
        residual_start, residual_end = _trim_range(
            normalized.text,
            cursor,
            line.end,
        )
        if residual_start < residual_end:
            result.append(_LineSlice(block, normalized, residual_start, residual_end))
    return sorted(
        result,
        key=lambda item: (item.start, item.end, item.layout_line_number or 0),
    )


def _normalized_range_for_source(
    normalized: NormalizedSourceText,
    source_start: int,
    source_end: int,
) -> tuple[int, int] | None:
    indexes = [
        index
        for index, character in enumerate(normalized.characters)
        if character.source_end > source_start and character.source_start < source_end
    ]
    if not indexes:
        return None
    return _trim_range(normalized.text, indexes[0], indexes[-1] + 1)


def _comparable_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _heading_match(
    block: ArtifactTextBlock,
    line: _LineSlice,
    *,
    line_index: int,
    heading_lanes: dict[int, int],
) -> _HeadingMatch | None:
    if block.heading_level is not None and line_index == 0:
        text = block.heading_path[-1] if block.heading_path else line.text
        return _HeadingMatch(
            text=_heading_label(text),
            level=block.heading_level,
            start=line.start,
            end=line.end,
        )

    if line.layout_line_number is not None:
        located_candidates = [
            hint
            for hint in block.heading_hints
            if hint.layout_line_number == line.layout_line_number
            and hint.locator.page_number == block.locator.page_number
            and _is_structural_heading_text(hint.text)
            and hint.layout_line_number not in _rejected_field_label_line_numbers(block)
        ]
        if len(located_candidates) != 1:
            return None
        hint = located_candidates[0]
        return _HeadingMatch(
            text=_heading_label(hint.text),
            level=hint.level,
            start=line.start,
            end=line.end,
            lane=heading_lanes.get(line.layout_line_number),
        )

    legacy_candidates: list[_HeadingMatch] = []
    for hint in block.heading_hints:
        if (
            hint.layout_line_number is not None
            or hint.locator.page_number != block.locator.page_number
            or not _is_structural_heading_text(hint.text)
        ):
            continue
        matched = _legacy_heading_range(line.text, hint.text)
        if matched is None:
            continue
        relative_start, relative_end = matched
        legacy_candidates.append(
            _HeadingMatch(
                text=_heading_label(hint.text),
                level=hint.level,
                start=line.start + relative_start,
                end=line.start + relative_end,
            )
        )
    unique = {
        (item.text, item.level, item.start, item.end): item
        for item in legacy_candidates
    }
    return next(iter(unique.values())) if len(unique) == 1 else None


def _prepared_heading_matches(
    block: ArtifactTextBlock,
    lines: list[_LineSlice],
    heading_lanes: dict[int, int],
) -> tuple[dict[int, _HeadingMatch], set[int]]:
    matches = {
        line_index: heading
        for line_index, line in enumerate(lines)
        if (
            heading := _heading_match(
                block,
                line,
                line_index=line_index,
                heading_lanes=heading_lanes,
            )
        )
        is not None
    }
    consumed: set[int] = set()
    composite_starts: set[int] = set()
    for line_index in sorted(matches):
        if line_index in consumed:
            continue
        run = [line_index]
        while True:
            next_index = run[-1] + 1
            if next_index not in matches or next_index in consumed:
                break
            if not _can_join_heading_lines(
                lines[run[-1]],
                matches[run[-1]],
                lines[next_index],
                matches[next_index],
            ):
                break
            run.append(next_index)
        if len(run) == 1:
            continue
        first = matches[run[0]]
        last = matches[run[-1]]
        matches[run[0]] = _HeadingMatch(
            text=" ".join(matches[index].text for index in run),
            level=first.level,
            start=first.start,
            end=last.end,
            lane=first.lane,
        )
        consumed.update(run[1:])
        composite_starts.add(run[0])

    for composite_index in sorted(composite_starts):
        previous_index = composite_index - 1
        if previous_index not in matches or previous_index in consumed:
            continue
        if not _is_masthead_before_main_title(
            lines[previous_index],
            matches[previous_index],
            lines[composite_index],
            matches[composite_index],
        ):
            continue
        consumed.add(previous_index)
        composite = matches[composite_index]
        matches[composite_index] = _HeadingMatch(
            text=composite.text,
            level=composite.level,
            start=composite.start,
            end=composite.end,
            lane=composite.lane,
            force_root=True,
        )
    return matches, consumed


def _can_join_heading_lines(
    first_line: _LineSlice,
    first: _HeadingMatch,
    second_line: _LineSlice,
    second: _HeadingMatch,
) -> bool:
    first_box = first_line.bounding_box
    second_box = second_line.bounding_box
    if (
        first.level != second.level
        or first.lane is not None
        or second.lane is not None
        or first_box is None
        or second_box is None
        or first_box.page_number != second_box.page_number
    ):
        return False
    height = max(first_box.bottom - first_box.top, second_box.bottom - second_box.top)
    return (
        abs(first_box.left - second_box.left) <= 2.0
        and 0 < second_box.top - first_box.top <= height * 1.8
        and not first_line.normalized.text[first.end : second.start].strip()
    )


def _is_masthead_before_main_title(
    masthead_line: _LineSlice,
    masthead: _HeadingMatch,
    title_line: _LineSlice,
    title: _HeadingMatch,
) -> bool:
    masthead_box = masthead_line.bounding_box
    title_box = title_line.bounding_box
    return bool(
        masthead_box is not None
        and title_box is not None
        and masthead.text.isupper()
        and title.text.isupper()
        and len(title.text) > len(masthead.text)
        and abs(masthead_box.left - title_box.left) <= 2.0
        and not masthead_line.normalized.text[masthead.end : title.start].strip()
    )


def _is_structural_heading_text(value: str) -> bool:
    normalized = normalize_source_text(value).text
    return bool(
        normalized
        and not _BULLET_HEADING_MARKER.match(normalized)
        and not _CURRENCY_VALUE.fullmatch(normalized)
        and not _REFERENCE_CODE_VALUE.fullmatch(normalized)
    )


def _rejected_field_label_line_numbers(block: ArtifactTextBlock) -> set[int]:
    located = [
        hint
        for hint in block.heading_hints
        if hint.layout_line_number is not None and hint.bounding_box is not None
    ]
    rejected: set[int] = set()
    for label in located:
        if not _FIELD_LABEL.search(normalize_source_text(label.text).text):
            continue
        label_box = label.bounding_box
        if label_box is None or label.layout_line_number is None:
            continue
        for value in located:
            value_box = value.bounding_box
            if (
                value_box is None
                or value.layout_line_number is None
                or value.layout_line_number == label.layout_line_number
                or not _looks_like_data_value(value.text)
                or label_box.page_number != value_box.page_number
            ):
                continue
            vertical_overlap = min(label_box.bottom, value_box.bottom) - max(
                label_box.top,
                value_box.top,
            )
            if vertical_overlap > 0:
                rejected.add(label.layout_line_number)
                break
    return rejected


def _looks_like_data_value(value: str) -> bool:
    normalized = normalize_source_text(value).text
    return bool(
        _CURRENCY_VALUE.fullmatch(normalized)
        or _REFERENCE_CODE_VALUE.fullmatch(normalized)
    )


def _legacy_heading_range(line_text: str, hint_text: str) -> tuple[int, int] | None:
    normalized_hint = normalize_source_text(hint_text).text
    if not normalized_hint:
        return None
    if line_text == normalized_hint:
        return 0, len(line_text)
    position = line_text.find(normalized_hint)
    if position < 0:
        return None
    prefix = line_text[:position]
    suffix = line_text[position + len(normalized_hint) :]
    if not _OUTLINE_PREFIX.fullmatch(prefix.strip()):
        return None
    if suffix and not suffix[0].isspace():
        return None
    return 0, position + len(normalized_hint)


def _heading_label(value: str) -> str:
    normalized = normalize_source_text(value).text
    return _HEADING_LABEL_PREFIX.sub("", normalized, count=1).strip()


def _heading_source_reference(
    block: ArtifactTextBlock,
    normalized: NormalizedSourceText,
    heading: _HeadingMatch,
    *,
    fallback_bounding_box: ArtifactBoundingBox | None,
) -> _HeadingSourceReference:
    source_start, source_end = normalized.source_range(heading.start, heading.end)
    boxes: list[ArtifactBoundingBox] = []
    for layout_line in block.pdf_layout_lines:
        if (
            layout_line.character_start is None
            or layout_line.character_end is None
            or layout_line.character_end <= source_start
            or layout_line.character_start >= source_end
        ):
            continue
        if layout_line.bounding_box not in boxes:
            boxes.append(layout_line.bounding_box)
    if not boxes and fallback_bounding_box is not None:
        boxes.append(fallback_bounding_box)
    if not boxes and block.bounding_box is not None:
        boxes.append(block.bounding_box)
    return _HeadingSourceReference(
        heading_text=heading.text,
        source_text=block.text[source_start:source_end],
        source_span=ChunkSourceSpan(
            block_id=block.block_id,
            start_locator=block.locator,
            end_locator=block.locator,
            character_start=source_start,
            character_end=source_end,
            bounding_boxes=boxes,
        ),
    )


def _excluded_span_from_range(
    block: ArtifactTextBlock,
    normalized: NormalizedSourceText,
    start: int,
    end: int,
    *,
    reason: Literal[
        "repeated_header",
        "repeated_footer",
        "heading_metadata",
        "noise",
    ],
    bounding_box: ArtifactBoundingBox | None,
) -> ExcludedChunkSpan:
    source_start, source_end = normalized.source_range(start, end)
    return ExcludedChunkSpan(
        block_id=block.block_id,
        reason=reason,
        text=block.text[source_start:source_end],
        locator=block.locator,
        bounding_box=bounding_box,
        character_start=source_start,
        character_end=source_end,
    )


def _updated_heading_stack(
    headings: dict[int, _HeadingSourceReference],
    *,
    level: int,
    source: _HeadingSourceReference,
) -> dict[int, _HeadingSourceReference]:
    updated = {
        existing_level: value
        for existing_level, value in headings.items()
        if existing_level < level
    }
    updated[level] = source
    return updated


def _parallel_heading_lanes(block: ArtifactTextBlock) -> dict[int, int]:
    located = [
        hint
        for hint in block.heading_hints
        if hint.layout_line_number is not None
        and hint.bounding_box is not None
        and not _BULLET_HEADING_MARKER.match(hint.text)
    ]
    lanes: dict[int, int] = {}
    for index, first in enumerate(located):
        first_box = first.bounding_box
        if first_box is None or first.layout_line_number is None:
            continue
        for second in located[index + 1 :]:
            second_box = second.bounding_box
            if (
                second_box is None
                or second.layout_line_number is None
                or first.level != second.level
                or first_box.page_number != second_box.page_number
            ):
                continue
            tolerance = max(
                first_box.bottom - first_box.top,
                second_box.bottom - second_box.top,
            )
            if abs(first_box.top - second_box.top) > tolerance:
                continue
            page_middle = first_box.page_width / 2
            first_center = (first_box.left + first_box.right) / 2
            second_center = (second_box.left + second_box.right) / 2
            if (first_center < page_middle) == (second_center < page_middle):
                continue
            lanes[first.layout_line_number] = int(first_center >= page_middle)
            lanes[second.layout_line_number] = int(second_center >= page_middle)
    return lanes


def _pdf_heading_context(
    block: ArtifactTextBlock,
    headings: dict[int, _HeadingSourceReference],
    lane_headings: dict[int, dict[int, _HeadingSourceReference]],
    line: _LineSlice,
    *,
    preferred_lane: int | None = None,
) -> tuple[tuple[str, ...], tuple[ChunkHeadingSource, ...]]:
    lane = preferred_lane
    if lane is None and line.bounding_box is not None and lane_headings:
        middle = line.bounding_box.page_width / 2
        center = (line.bounding_box.left + line.bounding_box.right) / 2
        lane = int(center >= middle)
    selected = lane_headings.get(lane) if lane is not None else None
    active = selected or headings
    ordered_sources = [active[level] for level in sorted(active)]
    path = (
        tuple(block.heading_path)
        if block.heading_path
        else tuple(source.heading_text for source in ordered_sources)
    )
    materialized: list[ChunkHeadingSource] = []
    search_start = 0
    for path_index, part in enumerate(path):
        matched_index = next(
            (
                index
                for index in range(search_start, len(ordered_sources))
                if _comparable_text(ordered_sources[index].heading_text)
                == _comparable_text(part)
            ),
            None,
        )
        if matched_index is None:
            continue
        source = ordered_sources[matched_index]
        materialized.append(
            ChunkHeadingSource(
                heading_path_index=path_index,
                heading_text=part,
                source_text=source.source_text,
                source_span=source.source_span,
            )
        )
        search_start = matched_index + 1
    return path, tuple(materialized)


def _slice_exclusion_reason(
    line: _LineSlice,
    repeated_lines: dict[
        _ExcludedLineKey,
        Literal["repeated_header", "repeated_footer"],
    ],
) -> Literal["repeated_header", "repeated_footer"] | None:
    direct = repeated_lines.get(_line_key(line))
    if direct is not None:
        return direct
    for key, reason in repeated_lines.items():
        if (
            key.block_id == line.block.block_id
            and key.start <= line.start
            and line.end <= key.end
        ):
            return reason
    return None


def _line_key(line: _LineSlice) -> _ExcludedLineKey:
    return _ExcludedLineKey(line.block.block_id, line.start, line.end)


def _eligible_repeated_edge(text: str) -> bool:
    return 1 <= len(text) <= 200 and any(character.isalnum() for character in text)


def _window_end(
    *,
    text: str,
    tokens: tuple[TokenSpan, ...],
    start_token_index: int,
    target_body_tokens: int,
    hard_body_tokens: int,
) -> int:
    remaining = len(tokens) - start_token_index
    if remaining <= hard_body_tokens:
        return len(text)
    target_index = start_token_index + target_body_tokens - 1
    hard_index = start_token_index + hard_body_tokens - 1
    target_end = tokens[target_index].end
    hard_end = tokens[hard_index].end
    minimum_index = start_token_index + max(1, target_body_tokens // 2) - 1
    minimum_end = tokens[minimum_index].end
    for pattern in _BOUNDARY_PATTERNS:
        positions = [
            match.end() for match in pattern.finditer(text, minimum_end, hard_end)
        ]
        before_target = [position for position in positions if position <= target_end]
        if before_target:
            return before_target[-1]
        if positions:
            return positions[0]
    return target_end


def _trim_range(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _source_spans(
    characters: list[_MappedCharacter | None],
    start: int,
    end: int,
) -> list[ChunkSourceSpan]:
    spans: list[ChunkSourceSpan] = []
    current_start: int | None = None
    current_end: int | None = None
    current: _MappedCharacter | None = None

    def flush() -> None:
        nonlocal current, current_start, current_end
        if current is None or current_start is None or current_end is None:
            return
        spans.append(
            ChunkSourceSpan(
                block_id=current.block_id,
                start_locator=current.locator,
                end_locator=current.locator,
                character_start=current_start,
                character_end=current_end,
                bounding_boxes=(
                    [current.bounding_box] if current.bounding_box is not None else []
                ),
            )
        )
        current = None
        current_start = None
        current_end = None

    for character in characters[start:end]:
        if character is None:
            flush()
            continue
        if (
            current is not None
            and current_end is not None
            and character.block_id == current.block_id
            and character.source_start <= current_end
            and character.locator == current.locator
            and character.bounding_box == current.bounding_box
        ):
            current_end = max(current_end, character.source_end)
            continue
        flush()
        current = character
        current_start = character.source_start
        current_end = character.source_end
    flush()
    return spans


def _page_numbers(spans: list[ChunkSourceSpan]) -> list[int]:
    pages = {
        page
        for span in spans
        for page in (
            [span.start_locator.page_number]
            if span.start_locator.page_number is not None
            else []
        )
    }
    return sorted(pages)


def _bounding_boxes(spans: list[ChunkSourceSpan]) -> list[ArtifactBoundingBox]:
    boxes: list[ArtifactBoundingBox] = []
    seen: set[tuple[object, ...]] = set()
    for span in spans:
        for box in span.bounding_boxes:
            identity = (
                box.page_number,
                box.left,
                box.top,
                box.right,
                box.bottom,
                box.page_width,
                box.page_height,
                box.coordinate_system,
            )
            if identity not in seen:
                seen.add(identity)
                boxes.append(box)
    return boxes
