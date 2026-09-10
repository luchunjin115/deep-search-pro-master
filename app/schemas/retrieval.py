"""Strict public contracts shared by future Dense, Lexical, and Hybrid retrieval."""

from __future__ import annotations

import math
from typing import Annotated, Literal, TypeAlias
from uuid import UUID

from pydantic import Field, FiniteFloat, StringConstraints, model_validator

from app.core.config import RETRIEVAL_QUERY_HARD_MAX_CHARACTERS
from app.schemas.common import M1Schema, MarketCode

RetrievalMode = Literal["dense", "lexical", "hybrid"]
RetrievalPrecision = Literal["float32", "float16", "bfloat16"]
HeadingSegment = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=300),
]


class RetrievalRequest(M1Schema):
    """The only caller-controlled retrieval input; scope comes from trusted context."""

    query: str = Field(
        strict=True,
        min_length=1,
        max_length=RETRIEVAL_QUERY_HARD_MAX_CHARACTERS,
    )


class RetrievalCandidateIdentity(M1Schema):
    """Public row identities without tenant, ACL, or Storage implementation details."""

    document_id: UUID
    version_id: UUID
    index_set_id: UUID
    chunk_id: UUID


class RetrievalCandidateFailure(M1Schema):
    """One safe record for a ranked row that could not become a public result."""

    source_mode: Literal["dense", "lexical"]
    rank: int = Field(ge=1, le=100)
    chunk_id: UUID
    stage: Literal["source_locator_mapping"] = "source_locator_mapping"
    reason: Literal["invalid_source_locator"] = "invalid_source_locator"


class RetrievalDocumentMetadata(M1Schema):
    """Authorized document facts safe to show beside one retrieved Chunk."""

    title: str = Field(min_length=1, max_length=300)
    document_type: str = Field(
        min_length=1,
        max_length=32,
        pattern=r"^[a-z][a-z0-9_-]{0,31}$",
    )
    language: str | None = Field(
        default=None,
        max_length=8,
        pattern=r"^[a-z]{2}(-[A-Z]{2})?$",
    )
    market: MarketCode | None = None


class PdfRetrievalSourceLocator(M1Schema):
    """Public PDF coordinates for a page or multi-page Chunk."""

    source_type: Literal["pdf"] = "pdf"
    page_number: int | None = Field(default=None, ge=1)
    page_numbers: list[int] = Field(default_factory=list, max_length=500)
    block_number: int | None = Field(default=None, ge=1)
    paragraph_number: int | None = Field(default=None, ge=1)
    table_number: int | None = Field(default=None, ge=1)
    heading_path: list[HeadingSegment] = Field(default_factory=list, max_length=9)

    @model_validator(mode="after")
    def validate_page_coordinates(self) -> PdfRetrievalSourceLocator:
        if any(page < 1 for page in self.page_numbers):
            raise ValueError("page_numbers must contain positive integers")
        if len(self.page_numbers) != len(set(self.page_numbers)):
            raise ValueError("page_numbers cannot contain duplicates")
        if self.page_number is None and not self.page_numbers:
            raise ValueError("PDF source requires page_number or page_numbers")
        return self


class DocxRetrievalSourceLocator(M1Schema):
    """Public DOCX coordinates from native or layout-aware parsing."""

    source_type: Literal["docx"] = "docx"
    page_number: int | None = Field(default=None, ge=1)
    page_numbers: list[int] = Field(default_factory=list, max_length=500)
    block_number: int | None = Field(default=None, ge=1)
    paragraph_number: int | None = Field(default=None, ge=1)
    table_number: int | None = Field(default=None, ge=1)
    heading_path: list[HeadingSegment] = Field(default_factory=list, max_length=9)

    @model_validator(mode="after")
    def validate_docx_coordinates(self) -> DocxRetrievalSourceLocator:
        if any(page < 1 for page in self.page_numbers):
            raise ValueError("page_numbers must contain positive integers")
        if len(self.page_numbers) != len(set(self.page_numbers)):
            raise ValueError("page_numbers cannot contain duplicates")
        if not any(
            (
                self.page_number,
                self.page_numbers,
                self.block_number,
                self.paragraph_number,
                self.table_number,
                self.heading_path,
            )
        ):
            raise ValueError("DOCX source requires at least one public coordinate")
        return self


class XlsxRetrievalSourceLocator(M1Schema):
    """Public XLSX coordinates without workbook paths or Storage keys."""

    source_type: Literal["xlsx"] = "xlsx"
    sheet_name: str = Field(min_length=1, max_length=31)
    cell_range: str | None = Field(
        default=None,
        max_length=64,
        pattern=r"^[A-Z]{1,3}[1-9][0-9]*(?::[A-Z]{1,3}[1-9][0-9]*)?$",
    )
    row_start: int | None = Field(default=None, ge=1)
    row_end: int | None = Field(default=None, ge=1)
    heading_path: list[HeadingSegment] = Field(default_factory=list, max_length=9)

    @model_validator(mode="after")
    def validate_row_range(self) -> XlsxRetrievalSourceLocator:
        _validate_optional_row_range(self.row_start, self.row_end)
        if self.cell_range is None and self.row_start is None:
            raise ValueError("XLSX source requires cell_range or row range")
        return self


class CsvRetrievalSourceLocator(M1Schema):
    """Public CSV row coordinates without revealing a local file path."""

    source_type: Literal["csv"] = "csv"
    row_start: int = Field(ge=1)
    row_end: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_row_range(self) -> CsvRetrievalSourceLocator:
        _validate_optional_row_range(self.row_start, self.row_end)
        return self


RetrievalSourceLocator: TypeAlias = Annotated[
    PdfRetrievalSourceLocator
    | DocxRetrievalSourceLocator
    | XlsxRetrievalSourceLocator
    | CsvRetrievalSourceLocator,
    Field(discriminator="source_type"),
]


class DenseRetrievalScore(M1Schema):
    """One Dense-list position and its finite cosine measurements."""

    rank: int = Field(ge=1)
    distance: FiniteFloat | None = Field(default=None, ge=0, le=2)
    similarity: FiniteFloat | None = Field(default=None, ge=-1, le=1)

    @model_validator(mode="after")
    def require_dense_measurement(self) -> DenseRetrievalScore:
        if self.distance is None and self.similarity is None:
            raise ValueError("dense score requires distance or similarity")
        if (
            self.distance is not None
            and self.similarity is not None
            and not math.isclose(
                self.similarity,
                1 - self.distance,
                rel_tol=0,
                abs_tol=1e-6,
            )
        ):
            raise ValueError("cosine similarity must equal one minus cosine distance")
        return self


class LexicalRetrievalScore(M1Schema):
    """One Lexical-list position and an unbounded-but-finite FTS score."""

    rank: int = Field(ge=1)
    score: FiniteFloat


class RetrievalScoreBreakdown(M1Schema):
    """Optional per-list hits; absence is represented by None, never a fake number."""

    dense: DenseRetrievalScore | None = None
    lexical: LexicalRetrievalScore | None = None

    @model_validator(mode="after")
    def require_at_least_one_hit(self) -> RetrievalScoreBreakdown:
        if self.dense is None and self.lexical is None:
            raise ValueError("score breakdown requires dense or lexical hit")
        return self


class RetrievalEmbeddingIdentity(M1Schema):
    """Public, reproducible Embedding identity without a local snapshot path."""

    contract_version: str = Field(min_length=1, max_length=128)
    provider: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",
    )
    model_id: str = Field(
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$",
    )
    revision: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$",
    )
    pooling: str = Field(min_length=1, max_length=64)
    max_length: int = Field(ge=1, le=100_000)
    normalize: Literal[True] = True
    precision: RetrievalPrecision
    dimensions: Literal[1024] = 1024


class RetrievalFtsIdentity(M1Schema):
    """Version of the deterministic builder that produced searchable FTS text."""

    builder_version: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9][a-z0-9._-]{0,127}$",
    )


class RetrievalRerankerIdentity(M1Schema):
    """Public logical identity for reproducible Reranker scores."""

    contract_version: str = Field(min_length=1, max_length=128)
    provider: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",
    )
    model_id: str = Field(
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$",
    )
    revision: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$",
    )
    max_length: int = Field(ge=1, le=8192)
    precision: RetrievalPrecision
    score_transform: Literal["sigmoid"] = "sigmoid"


class RetrievalRerankerScore(M1Schema):
    """One finite cross-encoder score; normalized_score is not probability."""

    rank: int = Field(ge=1)
    raw_score: FiniteFloat
    normalized_score: FiniteFloat = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_sigmoid_transform(self) -> RetrievalRerankerScore:
        expected = _sigmoid(float(self.raw_score))
        if not math.isclose(
            float(self.normalized_score),
            expected,
            rel_tol=0,
            abs_tol=1e-6,
        ):
            raise ValueError("normalized score must equal sigmoid of raw score")
        return self


class RetrievalResult(M1Schema):
    """One safe public Chunk candidate with optional per-list score decomposition."""

    identity: RetrievalCandidateIdentity
    document: RetrievalDocumentMetadata
    body_text: str = Field(min_length=1, max_length=100_000)
    source_locator: RetrievalSourceLocator
    scores: RetrievalScoreBreakdown
    rrf_score: FiniteFloat | None = Field(default=None, gt=0)
    final_rank: int = Field(ge=1)


class RerankedRetrievalResult(RetrievalResult):
    """One unchanged Hybrid candidate with its new Reranker position."""

    hybrid_rank: int = Field(ge=1)
    reranker: RetrievalRerankerScore


class RetrievalResponse(M1Schema):
    """One shared result shape with mode-specific identities and ranking evidence."""

    mode: RetrievalMode
    embedding_identity: RetrievalEmbeddingIdentity | None = None
    fts_identity: RetrievalFtsIdentity | None = None
    rrf_k: int | None = Field(default=None, ge=1, le=200)
    results: list[RetrievalResult] = Field(default_factory=list, max_length=100)
    candidate_failures: list[RetrievalCandidateFailure] = Field(
        default_factory=list,
        max_length=200,
    )

    @model_validator(mode="after")
    def validate_mode_and_ranking(self) -> RetrievalResponse:
        result_ranks = [result.final_rank for result in self.results]
        if result_ranks != sorted(result_ranks):
            raise ValueError("final ranks must be ordered")

        if self.mode == "dense":
            if self.embedding_identity is None:
                raise ValueError("dense retrieval requires embedding identity")
            if self.rrf_k is not None or any(
                result.scores.dense is None
                or result.scores.lexical is not None
                or result.rrf_score is not None
                for result in self.results
            ):
                raise ValueError("dense retrieval requires only Dense scores")
            self._validate_single_route_ranks("dense")
            return self

        if self.mode == "lexical":
            if self.fts_identity is None:
                raise ValueError("lexical retrieval requires FTS identity")
            if self.rrf_k is not None or any(
                result.scores.lexical is None
                or result.scores.dense is not None
                or result.rrf_score is not None
                for result in self.results
            ):
                raise ValueError("lexical retrieval requires only Lexical scores")
            self._validate_single_route_ranks("lexical")
            return self

        expected_ranks = list(range(1, len(self.results) + 1))
        if result_ranks != expected_ranks:
            raise ValueError("final ranks must be contiguous and ordered")
        failure_keys = [
            (failure.source_mode, failure.rank) for failure in self.candidate_failures
        ]
        if failure_keys != sorted(failure_keys) or len(failure_keys) != len(
            set(failure_keys)
        ):
            raise ValueError("Hybrid candidate failures must be unique and ordered")
        if (
            self.embedding_identity is None
            or self.fts_identity is None
            or self.rrf_k is None
            or any(result.rrf_score is None for result in self.results)
        ):
            raise ValueError("hybrid retrieval requires both identities and RRF scores")
        return self

    def _validate_single_route_ranks(
        self,
        mode: Literal["dense", "lexical"],
    ) -> None:
        if any(failure.source_mode != mode for failure in self.candidate_failures):
            raise ValueError("candidate failure mode must match retrieval mode")
        failure_ranks = [failure.rank for failure in self.candidate_failures]
        if failure_ranks != sorted(failure_ranks):
            raise ValueError("candidate failure ranks must be ordered")
        all_ranks = [result.final_rank for result in self.results] + failure_ranks
        if sorted(all_ranks) != list(range(1, len(all_ranks) + 1)):
            raise ValueError("results and failures must account for every route rank")


class RerankedRetrievalResponse(M1Schema):
    """A bounded, auditable reranking of server-built Hybrid candidates."""

    mode: Literal["reranked"] = "reranked"
    embedding_identity: RetrievalEmbeddingIdentity
    fts_identity: RetrievalFtsIdentity
    rrf_k: int = Field(ge=1, le=200)
    reranker_identity: RetrievalRerankerIdentity
    input_candidate_count: int = Field(ge=0, le=100)
    top_k: int = Field(ge=5, le=8)
    results: list[RerankedRetrievalResult] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def validate_reranked_results(self) -> RerankedRetrievalResponse:
        expected_ranks = list(range(1, len(self.results) + 1))
        if [result.final_rank for result in self.results] != expected_ranks:
            raise ValueError("final ranks must be contiguous and ordered")
        if [result.reranker.rank for result in self.results] != expected_ranks:
            raise ValueError("Reranker score rank must equal final rank")

        hybrid_ranks = [result.hybrid_rank for result in self.results]
        if len(hybrid_ranks) != len(set(hybrid_ranks)):
            raise ValueError("Reranked Hybrid ranks must be unique")
        if any(rank > self.input_candidate_count for rank in hybrid_ranks):
            raise ValueError("Hybrid rank cannot exceed input candidate count")
        if len(self.results) > min(self.top_k, self.input_candidate_count):
            raise ValueError("Reranked result count cannot exceed server top k")
        if any(result.rrf_score is None for result in self.results):
            raise ValueError("Reranked candidates must preserve Hybrid RRF scores")

        order = sorted(
            self.results,
            key=lambda result: (
                -float(result.reranker.normalized_score),
                result.hybrid_rank,
                result.identity.chunk_id,
            ),
        )
        if self.results != order:
            raise ValueError("Reranked results violate stable score order")
        return self


def _validate_optional_row_range(row_start: int | None, row_end: int | None) -> None:
    if (row_start is None) != (row_end is None):
        raise ValueError("row_start and row_end must be provided together")
    if row_start is not None and row_end is not None and row_end < row_start:
        raise ValueError("row_end must be greater than or equal to row_start")


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1 / (1 + math.exp(-value))
    exponential = math.exp(value)
    return exponential / (1 + exponential)
