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
    role: Literal["heading", "paragraph", "list_item"]


@dataclass(slots=True)
class _TextGroup:
    heading_path: tuple[str, ...]
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

    @property
    def text(self) -> str:
        return self.normalized.text[self.start : self.end]


@dataclass(frozen=True, slots=True)
class _ExcludedLineKey:
    block_id: str
    start: int
    end: int


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
        pdf_headings: dict[int, str] = {}

        def append_unit(unit: _TextUnit) -> None:
            nonlocal current
            if current is None or current.heading_path != unit.heading_path:
                if current is not None:
                    groups.append(current)
                current = _TextGroup(heading_path=unit.heading_path)
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

            hints = {
                normalize_source_text(hint.text).text: hint.level
                for hint in sorted(
                    block.heading_hints,
                    key=lambda item: (item.level, item.text),
                )
            }
            for line_index, line in enumerate(_line_slices(block, normalized)):
                exclusion_reason = repeated_lines.get(_line_key(line))
                if exclusion_reason is not None:
                    excluded.append(
                        ExcludedChunkSpan(
                            block_id=block.block_id,
                            reason=exclusion_reason,
                            text=line.text,
                            locator=block.locator,
                            bounding_box=(
                                block.bounding_box
                                if line.start == 0 and line.end == len(normalized.text)
                                else None
                            ),
                        )
                    )
                    continue
                heading_level = (
                    block.heading_level if line_index == 0 else None
                ) or hints.get(line.text)
                if block.heading_path:
                    heading_path = tuple(block.heading_path)
                    if heading_level is not None:
                        pdf_headings = {
                            level: value
                            for level, value in pdf_headings.items()
                            if level < heading_level
                        }
                        pdf_headings[heading_level] = line.text
                elif heading_level is not None:
                    pdf_headings = {
                        level: value
                        for level, value in pdf_headings.items()
                        if level < heading_level
                    }
                    pdf_headings[heading_level] = line.text
                    heading_path = tuple(
                        pdf_headings[level] for level in sorted(pdf_headings)
                    )
                else:
                    heading_path = tuple(
                        pdf_headings[level] for level in sorted(pdf_headings)
                    )
                append_unit(
                    _unit_from_slice(
                        block,
                        normalized,
                        line.start,
                        line.end,
                        heading_path=heading_path,
                        role=(
                            "heading"
                            if heading_level is not None
                            else _text_role(line.text)
                        ),
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
    role: Literal["heading", "paragraph", "list_item"],
) -> _TextUnit:
    return _TextUnit(
        text=normalized.text[start:end],
        characters=tuple(
            _MappedCharacter(
                block_id=block.block_id,
                source_start=character.source_start,
                source_end=character.source_end,
                locator=block.locator,
                bounding_box=block.bounding_box,
            )
            for character in normalized.characters[start:end]
        ),
        heading_path=heading_path,
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
