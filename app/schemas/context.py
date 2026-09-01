"""Strict, public-safe contracts at the Reranker to Context Builder boundary."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from app.core.config import CONTEXT_SEGMENT_HARD_MAX, CONTEXT_TOKEN_HARD_MAX
from app.schemas.common import M1Schema
from app.schemas.files import Sha256
from app.schemas.retrieval import (
    RetrievalCandidateIdentity,
    RetrievalDocumentMetadata,
    RetrievalSourceLocator,
)

CONTEXT_BUNDLE_CONTRACT_VERSION: Literal["m2-context-bundle-v1"] = (
    "m2-context-bundle-v1"
)
CONTEXT_TOKEN_COUNTER_VERSION: Literal["m2-unicode-token-counter-v1"] = (
    "m2-unicode-token-counter-v1"
)

CitationLabel = Annotated[
    str,
    StringConstraints(
        strict=True,
        pattern=r"^\[E(?:[1-9]|1[0-2])\]$",
        max_length=5,
    ),
]
ContextSourceType = Literal["knowledge", "user_file"]
ContextSegmentRole = Literal["anchor", "previous_neighbor", "next_neighbor"]


class ContextSegment(M1Schema):
    """One ordered, authorized passage exposed with a local citation label."""

    citation_label: CitationLabel
    evidence_id: UUID
    source_type: ContextSourceType
    role: ContextSegmentRole
    neighbor_of_chunk_id: UUID | None = None
    reranker_rank: int = Field(ge=1, le=8)
    identity: RetrievalCandidateIdentity
    document: RetrievalDocumentMetadata
    source_locator: RetrievalSourceLocator
    text: str = Field(strict=True, min_length=1, max_length=100_000)
    text_sha256: Sha256
    token_count: int = Field(ge=1, le=CONTEXT_TOKEN_HARD_MAX)
    overlap_trimmed: bool

    @model_validator(mode="after")
    def validate_role_link(self) -> ContextSegment:
        if self.role == "anchor" and self.neighbor_of_chunk_id is not None:
            raise ValueError("anchor segment cannot identify a neighbor anchor")
        if self.role != "anchor" and self.neighbor_of_chunk_id is None:
            raise ValueError("neighbor segment requires its anchor Chunk identity")
        return self


class ContextBundle(M1Schema):
    """One bounded Evidence allow-list; unsupported is an ordinary empty result."""

    contract_version: Literal["m2-context-bundle-v1"] = CONTEXT_BUNDLE_CONTRACT_VERSION
    context_id: UUID
    query_sha256: Sha256
    context_sha256: Sha256
    token_counter_version: Literal["m2-unicode-token-counter-v1"] = (
        CONTEXT_TOKEN_COUNTER_VERSION
    )
    max_tokens: int = Field(ge=700, le=CONTEXT_TOKEN_HARD_MAX)
    total_tokens: int = Field(ge=0, le=CONTEXT_TOKEN_HARD_MAX)
    supported: bool
    segments: list[ContextSegment] = Field(
        default_factory=list,
        max_length=CONTEXT_SEGMENT_HARD_MAX,
    )

    @model_validator(mode="after")
    def validate_bundle_consistency(self) -> ContextBundle:
        if not self.supported:
            if self.segments or self.total_tokens != 0:
                raise ValueError("unsupported context must be empty")
            return self
        if not self.segments or self.total_tokens == 0:
            raise ValueError("supported context requires at least one segment")
        if self.total_tokens > self.max_tokens:
            raise ValueError("context token total cannot exceed its budget")
        if sum(segment.token_count for segment in self.segments) > self.total_tokens:
            raise ValueError("context token total cannot omit segment tokens")

        expected_labels = [f"[E{index}]" for index in range(1, len(self.segments) + 1)]
        if [segment.citation_label for segment in self.segments] != expected_labels:
            raise ValueError("context citation labels must be contiguous and ordered")

        evidence_ids = [segment.evidence_id for segment in self.segments]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("context Evidence IDs must be unique")
        chunk_ids = [segment.identity.chunk_id for segment in self.segments]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("context Chunk IDs must be unique")
        return self


class ContextCitation(M1Schema):
    """One validated local label to persistent Evidence mapping."""

    citation_label: CitationLabel
    evidence_id: UUID


class CitationValidationResult(M1Schema):
    """Successful citation validation without echoing the model answer."""

    valid: Literal[True] = True
    context_id: UUID
    citations: list[ContextCitation] = Field(
        default_factory=list,
        max_length=CONTEXT_SEGMENT_HARD_MAX,
    )

    @model_validator(mode="after")
    def validate_unique_mapping(self) -> CitationValidationResult:
        labels = [citation.citation_label for citation in self.citations]
        if len(labels) != len(set(labels)):
            raise ValueError("validated citation labels must be unique")
        evidence_ids = [citation.evidence_id for citation in self.citations]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("validated citation Evidence IDs must be unique")
        return self
