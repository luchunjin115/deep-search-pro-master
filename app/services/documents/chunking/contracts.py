"""Strict, deterministic contracts for M2 structure-aware Chunk Artifacts."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, model_validator

from app.schemas.common import M1Schema
from app.services.documents.artifacts import (
    ARTIFACT_SCHEMA_VERSION,
    ArtifactBoundingBox,
    ArtifactTableCell,
)
from app.services.documents.parsers.base import SourceLocator

if TYPE_CHECKING:
    from app.core.config import Settings

CHUNK_ARTIFACT_SCHEMA_VERSION: Literal["m2-canonical-chunk-artifact-v1"] = (
    "m2-canonical-chunk-artifact-v1"
)
CHUNK_CONTENT_HASH_VERSION: Literal["m2-chunk-content-v1"] = "m2-chunk-content-v1"
CHUNKER_NAME: Literal["structure_aware"] = "structure_aware"
CHUNKER_VERSION: Literal["m2-structure-aware-chunker-v1"] = (
    "m2-structure-aware-chunker-v1"
)
NORMALIZATION_VERSION: Literal["m2-chunk-normalization-v1"] = (
    "m2-chunk-normalization-v1"
)
ROUTED_ARTIFACT_SCHEMA_VERSION: Literal["m2-routed-parsed-document-v1"] = (
    "m2-routed-parsed-document-v1"
)
_CHUNK_SET_NAMESPACE = uuid5(NAMESPACE_URL, "deep-search-pro/m2/chunk-set/v1")


class ChunkInputProvenance(M1Schema):
    """Immutable input facts that tie one Chunk Set to one parsed version."""

    document_id: UUID
    document_version_id: UUID
    routed_schema_version: Literal["m2-routed-parsed-document-v1"] = (
        ROUTED_ARTIFACT_SCHEMA_VERSION
    )
    canonical_schema_version: Literal["m2-canonical-parsed-artifact-v1"] = (
        ARTIFACT_SCHEMA_VERSION
    )
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parsed_publication_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_artifact_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ChunkerIdentity(M1Schema):
    """Algorithm provenance; every behavior change requires a new version."""

    name: Literal["structure_aware"] = CHUNKER_NAME
    version: Literal["m2-structure-aware-chunker-v1"] = CHUNKER_VERSION
    token_counter_name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    token_counter_version: str = Field(
        pattern=r"^m2-[a-z0-9-]+-v[0-9]+$",
        max_length=100,
    )


class ChunkingConfig(M1Schema):
    """Canonical configuration included in identity and output hashing."""

    normalization_version: Literal["m2-chunk-normalization-v1"] = NORMALIZATION_VERSION
    target_tokens: int = Field(default=600, ge=400, le=700)
    max_tokens: int = Field(default=700, ge=400, le=1000)
    overlap_tokens: int = Field(default=100, ge=80, le=120)
    heading_context_max_tokens: int = Field(default=120, ge=20, le=200)
    table_row_overlap: int = Field(default=1, ge=0, le=20)
    repeated_edge_min_pages: int = Field(default=2, ge=2, le=20)
    include_hidden_sheets: bool = True
    repeat_table_headers: bool = True

    @model_validator(mode="after")
    def validate_budget_relationships(self) -> ChunkingConfig:
        if self.target_tokens > self.max_tokens:
            raise ValueError("chunk target cannot exceed the hard maximum")
        if self.overlap_tokens >= self.target_tokens:
            raise ValueError("chunk overlap must be smaller than the target")
        if self.heading_context_max_tokens >= self.target_tokens:
            raise ValueError("heading context must be smaller than the target")
        return self

    @classmethod
    def from_settings(cls, settings: Settings) -> ChunkingConfig:
        return cls(
            target_tokens=settings.chunk_target_tokens,
            max_tokens=settings.chunk_max_tokens,
            overlap_tokens=settings.chunk_overlap_tokens,
            heading_context_max_tokens=settings.chunk_heading_context_max_tokens,
            table_row_overlap=settings.chunk_table_row_overlap,
            repeated_edge_min_pages=settings.chunk_repeated_edge_min_pages,
        )


class ChunkSourceSpan(M1Schema):
    """Exact portion of one Canonical Block used by a Chunk."""

    block_id: str = Field(pattern=r"^b[0-9]{6}$")
    start_locator: SourceLocator
    end_locator: SourceLocator
    character_start: int | None = Field(default=None, ge=0)
    character_end: int | None = Field(default=None, ge=1)
    bounding_boxes: list[ArtifactBoundingBox] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_character_range(self) -> ChunkSourceSpan:
        if (self.character_start is None) != (self.character_end is None):
            raise ValueError("character offsets must be provided together")
        if (
            self.character_start is not None
            and self.character_end is not None
            and self.character_start >= self.character_end
        ):
            raise ValueError("character offsets must have positive length")
        return self


class ChunkTableRow(M1Schema):
    """One source row retained with its cells and retrieval-context role."""

    source_row_number: int = Field(ge=1, le=1_048_576)
    role: Literal["header", "data"]
    repeated_as_context: bool = False
    cells: list[ArtifactTableCell] = Field(min_length=1, max_length=16_384)

    @model_validator(mode="after")
    def validate_columns(self) -> ChunkTableRow:
        columns = [cell.column_number for cell in self.cells]
        if columns != sorted(set(columns)):
            raise ValueError("chunk table cells must have unique ordered columns")
        if self.repeated_as_context and self.role != "header":
            raise ValueError("only table headers may be repeated as context")
        return self


class ChunkTableData(M1Schema):
    """Structured table facts retained alongside a retrieval text view."""

    source_kind: Literal["docx_table", "worksheet", "csv", "document_table"]
    title: str | None = Field(default=None, max_length=200)
    sheet_name: str | None = Field(default=None, min_length=1, max_length=31)
    sheet_state: Literal["visible", "hidden", "veryHidden"] | None = None
    encoding: Literal["utf-8-sig", "utf-8", "gb18030"] | None = None
    delimiter: Literal[",", ";", "\t", "|"] | None = None
    cell_range: str | None = Field(default=None, min_length=1, max_length=50)
    row_start: int | None = Field(default=None, ge=1)
    row_end: int | None = Field(default=None, ge=1)
    rows: list[ChunkTableRow] = Field(min_length=1, max_length=1_048_576)

    @model_validator(mode="after")
    def validate_source_and_rows(self) -> ChunkTableData:
        if (self.row_start is None) != (self.row_end is None):
            raise ValueError("table row range bounds must be provided together")
        if (
            self.row_start is not None
            and self.row_end is not None
            and self.row_start > self.row_end
        ):
            raise ValueError("table row range start cannot exceed end")
        if self.source_kind == "worksheet":
            if self.sheet_name is None or self.sheet_state is None:
                raise ValueError("worksheet chunks require sheet metadata")
        elif self.source_kind == "csv":
            if self.encoding is None or self.delimiter is None:
                raise ValueError("CSV chunks require encoding and delimiter")
        elif self.sheet_name is not None or self.sheet_state is not None:
            raise ValueError("document tables cannot declare worksheet metadata")
        return self


class ChunkOverlap(M1Schema):
    """Auditable duplication from the immediately previous semantic Chunk."""

    previous_chunk_id: str = Field(pattern=r"^c[0-9]{6}$")
    token_count: int = Field(ge=1, le=1000)
    source_spans: list[ChunkSourceSpan] = Field(min_length=1, max_length=1000)


class DocumentChunk(M1Schema):
    """One structure-preserving unit prepared for later persistence and retrieval."""

    chunk_id: str = Field(pattern=r"^c[0-9]{6}$")
    chunk_index: int = Field(ge=1)
    kind: Literal["text", "table"]
    body_text: str = Field(min_length=1, max_length=2_000_000)
    retrieval_text: str = Field(min_length=1, max_length=2_000_000)
    token_count: int = Field(ge=1, le=1_000_000)
    heading_path: list[str] = Field(default_factory=list, max_length=9)
    source_block_ids: list[str] = Field(min_length=1, max_length=1000)
    source_spans: list[ChunkSourceSpan] = Field(min_length=1, max_length=1000)
    page_numbers: list[int] = Field(default_factory=list, max_length=2000)
    bounding_boxes: list[ArtifactBoundingBox] = Field(default_factory=list)
    table: ChunkTableData | None = None
    overlap: ChunkOverlap | None = None
    warnings: list[str] = Field(default_factory=list, max_length=100)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_structure_and_hash(self) -> DocumentChunk:
        if (self.kind == "table") != (self.table is not None):
            raise ValueError("table chunks require structured table data")
        if self.source_block_ids != list(dict.fromkeys(self.source_block_ids)):
            raise ValueError("source block IDs must be unique and ordered")
        if self.page_numbers != sorted(set(self.page_numbers)):
            raise ValueError("chunk page numbers must be unique and ordered")
        expected = canonical_sha256(
            self.model_dump(mode="json", exclude={"content_sha256"})
        )
        if self.content_sha256 != expected:
            raise ValueError("chunk content hash does not match its content")
        return self


class ExcludedChunkSpan(M1Schema):
    """Source text deliberately not indexed, retained for loss auditing."""

    block_id: str = Field(pattern=r"^b[0-9]{6}$")
    reason: Literal["blank", "repeated_header", "repeated_footer", "noise"]
    text: str = Field(max_length=20_000)
    locator: SourceLocator
    bounding_box: ArtifactBoundingBox | None = None


class ChunkArtifactStatistics(M1Schema):
    """Self-validated aggregate counts for one Chunk Artifact."""

    chunk_count: int = Field(ge=1, le=1_100_000)
    text_chunk_count: int = Field(ge=0, le=1_100_000)
    table_chunk_count: int = Field(ge=0, le=1_100_000)
    total_token_count: int = Field(ge=1)
    excluded_span_count: int = Field(ge=0, le=1_100_000)


class CanonicalChunkArtifact(M1Schema):
    """Immutable Chunk Set output whose bytes are reproducible and self-checking."""

    schema_version: Literal["m2-canonical-chunk-artifact-v1"] = (
        CHUNK_ARTIFACT_SCHEMA_VERSION
    )
    content_hash_version: Literal["m2-chunk-content-v1"] = CHUNK_CONTENT_HASH_VERSION
    chunk_set_id: UUID
    input: ChunkInputProvenance
    chunker: ChunkerIdentity
    config: ChunkingConfig
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    chunks: list[DocumentChunk] = Field(min_length=1, max_length=1_100_000)
    excluded_spans: list[ExcludedChunkSpan] = Field(
        default_factory=list,
        max_length=1_100_000,
    )
    statistics: ChunkArtifactStatistics
    output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_identity_counts_and_hash(self) -> CanonicalChunkArtifact:
        expected_config_hash = canonical_sha256(self.config.model_dump(mode="json"))
        if self.config_sha256 != expected_config_hash:
            raise ValueError("chunk config hash does not match its config")
        if self.chunk_set_id != derive_chunk_set_id(
            input_provenance=self.input,
            chunker=self.chunker,
            config_sha256=self.config_sha256,
        ):
            raise ValueError("chunk set ID does not match its deterministic identity")
        expected_ids = [f"c{index:06d}" for index in range(1, len(self.chunks) + 1)]
        if [chunk.chunk_id for chunk in self.chunks] != expected_ids or [
            chunk.chunk_index for chunk in self.chunks
        ] != list(range(1, len(self.chunks) + 1)):
            raise ValueError("chunk IDs and indexes must be stable and sequential")
        for index, chunk in enumerate(self.chunks):
            if chunk.token_count > self.config.max_tokens:
                raise ValueError("chunk exceeds its configured hard token maximum")
            if chunk.overlap is not None:
                if (
                    index == 0
                    or chunk.overlap.previous_chunk_id != expected_ids[index - 1]
                ):
                    raise ValueError("chunk overlap must reference the previous chunk")
                if chunk.overlap.token_count > self.config.overlap_tokens:
                    raise ValueError("chunk overlap exceeds its configured budget")
        text_count = sum(chunk.kind == "text" for chunk in self.chunks)
        table_count = sum(chunk.kind == "table" for chunk in self.chunks)
        expected_statistics = ChunkArtifactStatistics(
            chunk_count=len(self.chunks),
            text_chunk_count=text_count,
            table_chunk_count=table_count,
            total_token_count=sum(chunk.token_count for chunk in self.chunks),
            excluded_span_count=len(self.excluded_spans),
        )
        if self.statistics != expected_statistics:
            raise ValueError("chunk artifact statistics do not match its chunks")
        expected_output_hash = canonical_sha256(
            self.model_dump(mode="json", exclude={"output_sha256"})
        )
        if self.output_sha256 != expected_output_hash:
            raise ValueError("chunk artifact output hash does not match its content")
        return self


def canonical_sha256(payload: dict[str, Any]) -> str:
    """Hash UTF-8 canonical JSON with stable keys and no insignificant spaces."""

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def derive_chunk_set_id(
    *,
    input_provenance: ChunkInputProvenance,
    chunker: ChunkerIdentity,
    config_sha256: str,
) -> UUID:
    """Derive one stable ID without timestamps, randomness, paths, or secrets."""

    identity = {
        "document_version_id": str(input_provenance.document_version_id),
        "selected_artifact_content_sha256": (
            input_provenance.selected_artifact_content_sha256
        ),
        "chunker": chunker.model_dump(mode="json"),
        "config_sha256": config_sha256,
    }
    return uuid5(_CHUNK_SET_NAMESPACE, canonical_sha256(identity))


def build_document_chunk(**facts: Any) -> DocumentChunk:
    """Build one self-hashing Chunk from already validated algorithm facts."""

    payload = DocumentChunk.model_construct(
        **facts,
        content_sha256="0" * 64,
    ).model_dump(mode="json", exclude={"content_sha256"})
    return DocumentChunk.model_validate(
        {**payload, "content_sha256": canonical_sha256(payload)}
    )


def build_chunk_artifact(
    *,
    input_provenance: ChunkInputProvenance,
    chunker: ChunkerIdentity,
    config: ChunkingConfig,
    chunks: list[DocumentChunk],
    excluded_spans: list[ExcludedChunkSpan] | None = None,
) -> CanonicalChunkArtifact:
    """Build and self-validate deterministic output without a runtime timestamp."""

    exclusions = excluded_spans or []
    config_hash = canonical_sha256(config.model_dump(mode="json"))
    chunk_set_id = derive_chunk_set_id(
        input_provenance=input_provenance,
        chunker=chunker,
        config_sha256=config_hash,
    )
    statistics = ChunkArtifactStatistics(
        chunk_count=len(chunks),
        text_chunk_count=sum(chunk.kind == "text" for chunk in chunks),
        table_chunk_count=sum(chunk.kind == "table" for chunk in chunks),
        total_token_count=sum(chunk.token_count for chunk in chunks),
        excluded_span_count=len(exclusions),
    )
    payload: dict[str, Any] = {
        "schema_version": CHUNK_ARTIFACT_SCHEMA_VERSION,
        "content_hash_version": CHUNK_CONTENT_HASH_VERSION,
        "chunk_set_id": str(chunk_set_id),
        "input": input_provenance.model_dump(mode="json"),
        "chunker": chunker.model_dump(mode="json"),
        "config": config.model_dump(mode="json"),
        "config_sha256": config_hash,
        "chunks": [chunk.model_dump(mode="json") for chunk in chunks],
        "excluded_spans": [span.model_dump(mode="json") for span in exclusions],
        "statistics": statistics.model_dump(mode="json"),
    }
    return CanonicalChunkArtifact.model_validate(
        {**payload, "output_sha256": canonical_sha256(payload)}
    )
