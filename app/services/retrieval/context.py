"""Deterministic Context Builder over freshly authorized Chunk windows."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal, Protocol, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import (
    CONTEXT_NEIGHBOR_WINDOW_HARD_MAX,
    CONTEXT_SEGMENT_HARD_MAX,
    CONTEXT_TOKEN_HARD_MAX,
)
from app.repositories.retrieval import (
    ContextChunkRecord,
    ContextChunkRehydrationError,
    ContextChunkWindowRecord,
)
from app.schemas.auth import CurrentUser
from app.schemas.common import MarketCode
from app.schemas.context import (
    CONTEXT_BUNDLE_CONTRACT_VERSION,
    CONTEXT_TOKEN_COUNTER_VERSION,
    ContextBundle,
    ContextSegment,
    ContextSegmentRole,
    ContextSourceType,
)
from app.schemas.retrieval import (
    RerankedRetrievalResponse,
    RetrievalCandidateIdentity,
    RetrievalDocumentMetadata,
    RetrievalRequest,
)
from app.services.documents.chunking.contracts import (
    ChunkOverlap,
    ChunkTableData,
)
from app.services.documents.chunking.token_counting import (
    TokenCounter,
    UnicodeMixedTokenCounter,
)
from app.services.retrieval.errors import (
    ContextBuildError,
    ContextDataContractError,
    ContextInputError,
)
from app.services.retrieval.result_mapping import source_locator_from_candidate

CONTEXT_BUILDER_VERSION: Literal["m2-context-builder-v1"] = "m2-context-builder-v1"
CONTEXT_RETRIEVAL_SNAPSHOT_VERSION: Literal["m2-context-retrieval-snapshot-v1"] = (
    "m2-context-retrieval-snapshot-v1"
)
_CONTEXT_NAMESPACE = uuid5(NAMESPACE_URL, "deep-search-pro/m2/context/v1")
_EVIDENCE_NAMESPACE = uuid5(NAMESPACE_URL, "deep-search-pro/m2/evidence/v1")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ContextWindowReader(Protocol):
    """The only freshly authorized database read allowed to the Builder."""

    def rehydrate_context_windows(
        self,
        current_user: CurrentUser,
        response: RerankedRetrievalResponse,
        *,
        neighbor_window: int,
    ) -> list[ContextChunkWindowRecord]: ...


@dataclass(frozen=True, slots=True)
class BuiltContext:
    """Public Bundle plus aligned private facts for the next persistence step."""

    bundle: ContextBundle
    sources: tuple[ContextChunkRecord, ...]
    retrieval_snapshot: dict[str, object]
    retrieval_snapshot_sha256: str
    config: dict[str, object]
    config_sha256: str
    identity_sha256: str


@dataclass(frozen=True, slots=True)
class _Candidate:
    source: ContextChunkRecord
    role: ContextSegmentRole
    reranker_rank: int
    neighbor_of_chunk_id: UUID | None


@dataclass(frozen=True, slots=True)
class _RenderedCandidate:
    candidate: _Candidate
    text: str
    text_sha256: str
    token_count: int
    overlap_trimmed: bool


class ContextBuilderService:
    """Deduplicate, trim, order, and budget authorized Reranker windows."""

    def __init__(
        self,
        repository: ContextWindowReader,
        *,
        max_tokens: int = 4000,
        max_segments: int = CONTEXT_SEGMENT_HARD_MAX,
        neighbor_window: int = 1,
        token_counter: TokenCounter | None = None,
    ) -> None:
        if (
            not isinstance(max_tokens, int)
            or isinstance(max_tokens, bool)
            or not 700 <= max_tokens <= CONTEXT_TOKEN_HARD_MAX
        ):
            raise ValueError("max_tokens must be between 700 and 16000")
        if (
            not isinstance(max_segments, int)
            or isinstance(max_segments, bool)
            or not 5 <= max_segments <= CONTEXT_SEGMENT_HARD_MAX
        ):
            raise ValueError("max_segments must be between 5 and 12")
        if (
            not isinstance(neighbor_window, int)
            or isinstance(neighbor_window, bool)
            or not 0 <= neighbor_window <= CONTEXT_NEIGHBOR_WINDOW_HARD_MAX
        ):
            raise ValueError("neighbor_window must be between 0 and 1")
        counter = token_counter or UnicodeMixedTokenCounter()
        if counter.version != CONTEXT_TOKEN_COUNTER_VERSION:
            raise ValueError("Context token counter version is incompatible")
        self._repository = repository
        self._max_tokens = max_tokens
        self._max_segments = max_segments
        self._neighbor_window = neighbor_window
        self._counter = counter

    def build(
        self,
        current_user: CurrentUser,
        request: RetrievalRequest,
        response: RerankedRetrievalResponse,
    ) -> BuiltContext:
        """Return one stable in-memory Bundle without persisting Evidence yet."""

        if (
            not isinstance(current_user, CurrentUser)
            or not isinstance(request, RetrievalRequest)
            or not isinstance(response, RerankedRetrievalResponse)
        ):
            raise ContextInputError
        try:
            windows = self._repository.rehydrate_context_windows(
                current_user,
                response,
                neighbor_window=self._neighbor_window,
            )
        except ContextChunkRehydrationError:
            raise ContextInputError from None
        except (RuntimeError, SQLAlchemyError):
            raise ContextBuildError from None

        try:
            return self._build_from_windows(current_user, request, response, windows)
        except (KeyError, TypeError, ValueError, ValidationError):
            raise ContextDataContractError from None

    def _build_from_windows(
        self,
        current_user: CurrentUser,
        request: RetrievalRequest,
        response: RerankedRetrievalResponse,
        windows: list[ContextChunkWindowRecord],
    ) -> BuiltContext:
        _validate_windows(
            response,
            windows,
            self._counter,
            neighbor_window=self._neighbor_window,
        )
        candidates = _priority_candidates(response, windows)
        selected: list[_Candidate] = []
        raw_text_hashes: set[str] = set()
        for candidate in candidates:
            raw_hash = _text_sha256(candidate.source.body_text)
            if raw_hash in raw_text_hashes:
                continue
            trial = [*selected, candidate]
            rendered = _render_candidates(trial, self._counter)
            if (
                rendered is None
                or len(rendered) > self._max_segments
                or sum(item.token_count for item in rendered) > self._max_tokens
            ):
                continue
            selected = trial
            raw_text_hashes.add(raw_hash)

        if response.results and not selected:
            raise ValueError("non-empty Reranker input produced no safe Context anchor")
        rendered = _render_candidates(selected, self._counter)
        if rendered is None:
            raise ValueError("selected Context contains an empty or duplicate segment")
        rendered_by_id = {item.candidate.source.chunk_id: item for item in rendered}
        ordered_candidates = _natural_order(selected, windows)
        ordered = [
            rendered_by_id[candidate.source.chunk_id]
            for candidate in ordered_candidates
        ]
        return _built_context(
            current_user=current_user,
            request=request,
            response=response,
            rendered=ordered,
            max_tokens=self._max_tokens,
            max_segments=self._max_segments,
            neighbor_window=self._neighbor_window,
        )


def _validate_windows(
    response: RerankedRetrievalResponse,
    windows: list[ContextChunkWindowRecord],
    counter: TokenCounter,
    *,
    neighbor_window: int,
) -> None:
    if len(windows) != len(response.results):
        raise ValueError("authorized window count does not match Reranker anchors")
    observed: dict[UUID, ContextChunkRecord] = {}
    for result, window in zip(response.results, windows, strict=True):
        if neighbor_window == 0 and (
            window.previous is not None or window.next is not None
        ):
            raise ValueError("repository exceeded the configured neighbor window")
        anchor = window.anchor
        if (
            anchor.chunk_id != result.identity.chunk_id
            or anchor.document_id != result.identity.document_id
            or anchor.version_id != result.identity.version_id
            or anchor.index_set_id != result.identity.index_set_id
            or anchor.body_text != result.body_text
            or anchor.title != result.document.title
            or anchor.document_type != result.document.document_type
            or anchor.language != result.document.language
            or anchor.market != result.document.market
        ):
            raise ValueError("trusted anchor does not match its Reranker result")
        _validate_record(anchor, counter)
        _remember_record(observed, anchor)
        if window.previous is not None:
            _validate_neighbor(anchor, window.previous, expected_offset=-1)
            _validate_record(window.previous, counter)
            _remember_record(observed, window.previous)
        if window.next is not None:
            _validate_neighbor(anchor, window.next, expected_offset=1)
            _validate_record(window.next, counter)
            _remember_record(observed, window.next)


def _validate_record(record: ContextChunkRecord, counter: TokenCounter) -> None:
    if (
        record.canonical_chunk_id != f"c{record.chunk_index:06d}"
        or record.kind not in {"text", "table"}
        or record.access_level not in {"private", "tenant", "restricted"}
        or record.file_extension.lower() not in {".pdf", ".docx", ".xlsx", ".csv"}
        or not _SHA256_PATTERN.fullmatch(record.content_sha256)
        or not record.body_text.strip()
        or counter.count(record.body_text) > record.token_count
        or (record.kind == "table") != (record.table_json is not None)
    ):
        raise ValueError("trusted Chunk record violates its Context boundary")
    source_locator_from_candidate(record)
    if record.kind == "table":
        ChunkTableData.model_validate(record.table_json)
    if record.overlap_json is not None:
        overlap = ChunkOverlap.model_validate(record.overlap_json)
        if (
            record.chunk_index <= 1
            or overlap.previous_chunk_id != f"c{record.chunk_index - 1:06d}"
        ):
            raise ValueError(
                "Chunk overlap does not identify its immediate predecessor"
            )


def _validate_neighbor(
    anchor: ContextChunkRecord,
    neighbor: ContextChunkRecord,
    *,
    expected_offset: int,
) -> None:
    if (
        neighbor.document_id != anchor.document_id
        or neighbor.version_id != anchor.version_id
        or neighbor.chunk_set_id != anchor.chunk_set_id
        or neighbor.index_set_id != anchor.index_set_id
        or neighbor.chunk_index != anchor.chunk_index + expected_offset
    ):
        raise ValueError("Context neighbor crosses its trusted active generation")


def _remember_record(
    observed: dict[UUID, ContextChunkRecord],
    record: ContextChunkRecord,
) -> None:
    existing = observed.setdefault(record.chunk_id, record)
    if existing != record:
        raise ValueError("one Chunk UUID has conflicting trusted facts")


def _priority_candidates(
    response: RerankedRetrievalResponse,
    windows: list[ContextChunkWindowRecord],
) -> list[_Candidate]:
    anchor_ids = {window.anchor.chunk_id for window in windows}
    candidates = [
        _Candidate(
            source=window.anchor,
            role="anchor",
            reranker_rank=result.final_rank,
            neighbor_of_chunk_id=None,
        )
        for result, window in zip(response.results, windows, strict=True)
    ]
    seen = set(anchor_ids)
    for result, window in zip(response.results, windows, strict=True):
        for role, source in (
            ("previous_neighbor", window.previous),
            ("next_neighbor", window.next),
        ):
            if source is None or source.chunk_id in seen:
                continue
            seen.add(source.chunk_id)
            candidates.append(
                _Candidate(
                    source=source,
                    role=cast(ContextSegmentRole, role),
                    reranker_rank=result.final_rank,
                    neighbor_of_chunk_id=window.anchor.chunk_id,
                )
            )
    return candidates


def _render_candidates(
    candidates: list[_Candidate],
    counter: TokenCounter,
) -> list[_RenderedCandidate] | None:
    selected_by_position = {
        _position_key(candidate.source): candidate.source for candidate in candidates
    }
    rendered: list[_RenderedCandidate] = []
    final_hashes: set[str] = set()
    for candidate in candidates:
        source = candidate.source
        text = _normalized_text(source.body_text)
        trimmed = False
        if source.overlap_json is not None:
            overlap = ChunkOverlap.model_validate(source.overlap_json)
            previous = selected_by_position.get(
                (
                    source.document_id,
                    source.version_id,
                    source.chunk_set_id,
                    source.index_set_id,
                    source.chunk_index - 1,
                )
            )
            if previous is not None:
                text = _trim_overlap(source, previous, overlap, counter)
                trimmed = True
        text = text.strip()
        if not text:
            return None
        text_hash = _text_sha256(text)
        if text_hash in final_hashes:
            return None
        token_count = counter.count(text)
        if token_count < 1 or token_count > CONTEXT_TOKEN_HARD_MAX:
            return None
        final_hashes.add(text_hash)
        rendered.append(
            _RenderedCandidate(
                candidate=candidate,
                text=text,
                text_sha256=text_hash,
                token_count=token_count,
                overlap_trimmed=trimmed,
            )
        )
    return rendered


def _trim_overlap(
    current: ContextChunkRecord,
    previous: ContextChunkRecord,
    overlap: ChunkOverlap,
    counter: TokenCounter,
) -> str:
    if current.kind == "table":
        table = ChunkTableData.model_validate(current.table_json)
        lines = _normalized_text(current.body_text).splitlines()
        if len(lines) != len(table.rows):
            raise ValueError("table text rows do not match structured table rows")
        repeated_lines = [
            line
            for line, row in zip(lines, table.rows, strict=True)
            if row.repeated_as_context
        ]
        kept_lines = [
            line
            for line, row in zip(lines, table.rows, strict=True)
            if not row.repeated_as_context
        ]
        if (
            not repeated_lines
            or counter.count("\n".join(repeated_lines)) != overlap.token_count
        ):
            raise ValueError("table overlap facts do not match repeated rows")
        return "\n".join(kept_lines).strip()

    current_text = _normalized_text(current.body_text)
    previous_text = _normalized_text(previous.body_text)
    spans = counter.spans(current_text)
    if overlap.token_count > len(spans):
        raise ValueError("text overlap exceeds the current Chunk")
    overlap_end = spans[overlap.token_count - 1].end
    repeated_text = current_text[:overlap_end].strip()
    if not repeated_text or not previous_text.rstrip().endswith(repeated_text):
        raise ValueError("text overlap does not match the previous Chunk suffix")
    return current_text[overlap_end:].lstrip()


def _natural_order(
    selected: list[_Candidate],
    windows: list[ContextChunkWindowRecord],
) -> list[_Candidate]:
    selected_by_id = {candidate.source.chunk_id: candidate for candidate in selected}
    ordered: list[_Candidate] = []
    emitted: set[UUID] = set()
    for window in windows:
        for source in (window.previous, window.anchor, window.next):
            if (
                source is None
                or source.chunk_id in emitted
                or source.chunk_id not in selected_by_id
            ):
                continue
            emitted.add(source.chunk_id)
            ordered.append(selected_by_id[source.chunk_id])
    if len(ordered) != len(selected):
        raise ValueError("selected Context order omitted a Chunk")
    return ordered


def _built_context(
    *,
    current_user: CurrentUser,
    request: RetrievalRequest,
    response: RerankedRetrievalResponse,
    rendered: list[_RenderedCandidate],
    max_tokens: int,
    max_segments: int,
    neighbor_window: int,
) -> BuiltContext:
    query_sha256 = _text_sha256(request.query)
    retrieval_snapshot: dict[str, object] = {
        "schema_version": CONTEXT_RETRIEVAL_SNAPSHOT_VERSION,
        "response": response.model_dump(mode="json"),
    }
    retrieval_snapshot_sha256 = _canonical_sha256(retrieval_snapshot)
    config: dict[str, object] = {
        "builder_version": CONTEXT_BUILDER_VERSION,
        "token_counter_version": CONTEXT_TOKEN_COUNTER_VERSION,
        "max_tokens": max_tokens,
        "max_segments": max_segments,
        "neighbor_window": neighbor_window,
        "selection_order": "anchors_then_ranked_previous_next",
        "render_order": "reranker_windows_previous_anchor_next",
        "deduplication": "chunk_uuid_then_normalized_text_sha256",
        "overlap_trimming": "audited_previous_chunk_v1",
    }
    config_sha256 = _canonical_sha256(config)
    segment_payloads = [_segment_payload(item) for item in rendered]
    context_payload: dict[str, object] = {
        "contract_version": CONTEXT_BUNDLE_CONTRACT_VERSION,
        "token_counter_version": CONTEXT_TOKEN_COUNTER_VERSION,
        "query_sha256": query_sha256,
        "max_tokens": max_tokens,
        "segments": segment_payloads,
    }
    context_sha256 = _canonical_sha256(context_payload)
    identity_sha256 = _canonical_sha256(
        {
            "contract_version": CONTEXT_BUNDLE_CONTRACT_VERSION,
            "query_sha256": query_sha256,
            "retrieval_snapshot_sha256": retrieval_snapshot_sha256,
            "config_sha256": config_sha256,
            "context_sha256": context_sha256,
        }
    )
    context_id = uuid5(
        _CONTEXT_NAMESPACE,
        f"{current_user.tenant_id}:{current_user.user_id}:{identity_sha256}",
    )
    segments = [
        _public_segment(
            item,
            ordinal=ordinal,
            context_id=context_id,
        )
        for ordinal, item in enumerate(rendered, start=1)
    ]
    total_tokens = sum(segment.token_count for segment in segments)
    bundle = ContextBundle(
        context_id=context_id,
        query_sha256=query_sha256,
        context_sha256=context_sha256,
        max_tokens=max_tokens,
        total_tokens=total_tokens,
        supported=bool(segments),
        segments=segments,
    )
    return BuiltContext(
        bundle=bundle,
        sources=tuple(item.candidate.source for item in rendered),
        retrieval_snapshot=retrieval_snapshot,
        retrieval_snapshot_sha256=retrieval_snapshot_sha256,
        config=config,
        config_sha256=config_sha256,
        identity_sha256=identity_sha256,
    )


def validate_built_context(
    current_user: CurrentUser,
    built: BuiltContext,
) -> None:
    """Reject forged or internally inconsistent Builder output before persistence."""

    if not isinstance(current_user, CurrentUser) or not isinstance(built, BuiltContext):
        raise TypeError("Context persistence requires trusted typed input")
    bundle = built.bundle
    if len(bundle.segments) != len(built.sources):
        raise ValueError("Context segments and private sources are not aligned")
    if _canonical_sha256(built.retrieval_snapshot) != built.retrieval_snapshot_sha256:
        raise ValueError("Context retrieval snapshot hash does not match")
    if _canonical_sha256(built.config) != built.config_sha256:
        raise ValueError("Context configuration hash does not match")

    segment_payloads: list[dict[str, object]] = []
    for ordinal, (segment, source) in enumerate(
        zip(bundle.segments, built.sources, strict=True),
        start=1,
    ):
        if (
            segment.citation_label != f"[E{ordinal}]"
            or segment.identity != _identity(source)
            or segment.document != _document(source)
            or segment.source_locator != source_locator_from_candidate(source)
            or segment.source_type != _source_type(source)
            or segment.text_sha256 != _text_sha256(segment.text)
            or segment.token_count != UnicodeMixedTokenCounter().count(segment.text)
        ):
            raise ValueError("Context segment does not match its trusted source")
        expected_evidence_id = uuid5(
            _EVIDENCE_NAMESPACE,
            f"{bundle.context_id}:{ordinal}:{source.chunk_id}:{segment.text_sha256}",
        )
        if segment.evidence_id != expected_evidence_id:
            raise ValueError("Context Evidence identity does not match")
        segment_payloads.append(
            {
                "source_type": segment.source_type,
                "role": segment.role,
                "neighbor_of_chunk_id": (
                    str(segment.neighbor_of_chunk_id)
                    if segment.neighbor_of_chunk_id is not None
                    else None
                ),
                "reranker_rank": segment.reranker_rank,
                "identity": segment.identity.model_dump(mode="json"),
                "document": segment.document.model_dump(mode="json"),
                "source_locator": segment.source_locator.model_dump(mode="json"),
                "text": segment.text,
                "text_sha256": segment.text_sha256,
                "token_count": segment.token_count,
                "overlap_trimmed": segment.overlap_trimmed,
            }
        )

    expected_context_sha256 = _canonical_sha256(
        {
            "contract_version": bundle.contract_version,
            "token_counter_version": bundle.token_counter_version,
            "query_sha256": bundle.query_sha256,
            "max_tokens": bundle.max_tokens,
            "segments": segment_payloads,
        }
    )
    if bundle.context_sha256 != expected_context_sha256:
        raise ValueError("Context content hash does not match")
    expected_identity_sha256 = _canonical_sha256(
        {
            "contract_version": bundle.contract_version,
            "query_sha256": bundle.query_sha256,
            "retrieval_snapshot_sha256": built.retrieval_snapshot_sha256,
            "config_sha256": built.config_sha256,
            "context_sha256": bundle.context_sha256,
        }
    )
    expected_context_id = uuid5(
        _CONTEXT_NAMESPACE,
        f"{current_user.tenant_id}:{current_user.user_id}:{expected_identity_sha256}",
    )
    if (
        built.identity_sha256 != expected_identity_sha256
        or bundle.context_id != expected_context_id
    ):
        raise ValueError("Context identity does not match its trusted user")


def _segment_payload(item: _RenderedCandidate) -> dict[str, object]:
    candidate = item.candidate
    source = candidate.source
    return {
        "source_type": _source_type(source),
        "role": candidate.role,
        "neighbor_of_chunk_id": (
            str(candidate.neighbor_of_chunk_id)
            if candidate.neighbor_of_chunk_id is not None
            else None
        ),
        "reranker_rank": candidate.reranker_rank,
        "identity": _identity(source).model_dump(mode="json"),
        "document": _document(source).model_dump(mode="json"),
        "source_locator": source_locator_from_candidate(source).model_dump(mode="json"),
        "text": item.text,
        "text_sha256": item.text_sha256,
        "token_count": item.token_count,
        "overlap_trimmed": item.overlap_trimmed,
    }


def _public_segment(
    item: _RenderedCandidate,
    *,
    ordinal: int,
    context_id: UUID,
) -> ContextSegment:
    candidate = item.candidate
    source = candidate.source
    evidence_id = uuid5(
        _EVIDENCE_NAMESPACE,
        f"{context_id}:{ordinal}:{source.chunk_id}:{item.text_sha256}",
    )
    return ContextSegment(
        citation_label=f"[E{ordinal}]",
        evidence_id=evidence_id,
        source_type=_source_type(source),
        role=candidate.role,
        neighbor_of_chunk_id=candidate.neighbor_of_chunk_id,
        reranker_rank=candidate.reranker_rank,
        identity=_identity(source),
        document=_document(source),
        source_locator=source_locator_from_candidate(source),
        text=item.text,
        text_sha256=item.text_sha256,
        token_count=item.token_count,
        overlap_trimmed=item.overlap_trimmed,
    )


def _identity(source: ContextChunkRecord) -> RetrievalCandidateIdentity:
    return RetrievalCandidateIdentity(
        document_id=source.document_id,
        version_id=source.version_id,
        index_set_id=source.index_set_id,
        chunk_id=source.chunk_id,
    )


def _document(source: ContextChunkRecord) -> RetrievalDocumentMetadata:
    return RetrievalDocumentMetadata(
        title=source.title,
        document_type=source.document_type,
        language=source.language,
        market=cast(MarketCode | None, source.market),
    )


def _source_type(source: ContextChunkRecord) -> ContextSourceType:
    return cast(
        ContextSourceType,
        "user_file" if source.access_level == "private" else "knowledge",
    )


def _position_key(
    source: ContextChunkRecord,
) -> tuple[UUID, UUID, UUID, UUID, int]:
    return (
        source.document_id,
        source.version_id,
        source.chunk_set_id,
        source.index_set_id,
        source.chunk_index,
    )


def _normalized_text(value: str) -> str:
    return unicodedata.normalize("NFC", value).strip()


def _text_sha256(value: str) -> str:
    return hashlib.sha256(_normalized_text(value).encode("utf-8")).hexdigest()


def _canonical_sha256(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
