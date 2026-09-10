"""Strict public-safe report contracts for M2-22.6 retrieval candidates."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, FiniteFloat, model_validator

from app.evals.ragas_retrieval import RagasRetrievalEvaluation
from app.evals.retrieval_metrics import (
    AnswerableRankingMetrics,
    NoAnswerRankingMetrics,
)
from app.schemas.common import M1Schema
from app.schemas.evaluation import FailureCategory, SafeIdentifier, Sha256
from app.schemas.retrieval import RetrievalSourceLocator


class RetrievalCandidateTrace(M1Schema):
    """One full ordered candidate without vectors, tenant facts, or source body."""

    chunk_id: UUID
    document_id: UUID
    version_id: UUID
    index_set_id: UUID
    logical_document_id: SafeIdentifier
    rank: int = Field(ge=1, le=100)
    body_text_sha256: Sha256
    source_locator: RetrievalSourceLocator
    dense_rank: int | None = Field(default=None, ge=1, le=100)
    dense_similarity: FiniteFloat | None = Field(default=None, ge=-1, le=1)
    lexical_rank: int | None = Field(default=None, ge=1, le=100)
    lexical_score: FiniteFloat | None = None
    rrf_score: FiniteFloat | None = Field(default=None, gt=0)
    matched_evidence_ids: list[SafeIdentifier] = Field(
        default_factory=list, max_length=20
    )

    @model_validator(mode="after")
    def validate_scores(self) -> RetrievalCandidateTrace:
        if (self.dense_rank is None) != (self.dense_similarity is None):
            raise ValueError("Dense rank and score must be present together")
        if (self.lexical_rank is None) != (self.lexical_score is None):
            raise ValueError("Lexical rank and score must be present together")
        if self.dense_rank is None and self.lexical_rank is None:
            raise ValueError("candidate requires at least one route score")
        if len(self.matched_evidence_ids) != len(set(self.matched_evidence_ids)):
            raise ValueError("matched Evidence identities must be unique")
        return self


class RetrievalCandidateFailureTrace(M1Schema):
    """Safe evidence that one original route position failed Locator mapping."""

    source_mode: Literal["dense", "lexical"]
    rank: int = Field(ge=1, le=100)
    chunk_id: UUID
    stage: Literal["source_locator_mapping"]
    reason: Literal["invalid_source_locator"]


class RetrievalRouteTrace(M1Schema):
    """One complete Dense, Lexical, or RRF list and its measured latency."""

    mode: Literal["dense", "lexical", "hybrid"]
    requested_candidate_depth: int = Field(ge=5, le=100)
    returned_candidate_count: int = Field(ge=0, le=100)
    latency_ms: int = Field(ge=0, le=86_400_000)
    candidates: list[RetrievalCandidateTrace] = Field(
        default_factory=list, max_length=100
    )
    candidate_failures: list[RetrievalCandidateFailureTrace] = Field(
        default_factory=list,
        max_length=200,
    )

    @model_validator(mode="after")
    def validate_complete_route(self) -> RetrievalRouteTrace:
        candidate_ranks = [candidate.rank for candidate in self.candidates]
        if candidate_ranks != sorted(candidate_ranks):
            raise ValueError("candidate ranks must be ordered")
        if self.returned_candidate_count != len(self.candidates):
            raise ValueError("returned candidate count must match the full list")
        if self.mode in {"dense", "lexical"}:
            failure_ranks = [failure.rank for failure in self.candidate_failures]
            if any(
                failure.source_mode != self.mode for failure in self.candidate_failures
            ):
                raise ValueError("candidate failure mode must match route mode")
            all_ranks = [*candidate_ranks, *failure_ranks]
            if sorted(all_ranks) != list(range(1, len(all_ranks) + 1)):
                raise ValueError(
                    "candidates and failures must form one contiguous route ranking"
                )
            if len(all_ranks) > self.requested_candidate_depth:
                raise ValueError("single-route candidates exceed requested depth")
        else:
            expected_ranks = list(range(1, len(self.candidates) + 1))
            if candidate_ranks != expected_ranks:
                raise ValueError(
                    "Hybrid candidate ranks must be contiguous and ordered"
                )
            failure_keys = [
                (failure.source_mode, failure.rank)
                for failure in self.candidate_failures
            ]
            if failure_keys != sorted(failure_keys) or len(failure_keys) != len(
                set(failure_keys)
            ):
                raise ValueError("Hybrid candidate failures must be unique and ordered")
        if self.mode == "hybrid" and len(self.candidates) > min(
            100, self.requested_candidate_depth * 2
        ):
            raise ValueError("RRF union exceeds the two complete input lists")
        for candidate in self.candidates:
            if self.mode == "dense" and (
                candidate.dense_rank != candidate.rank
                or candidate.lexical_rank is not None
                or candidate.rrf_score is not None
            ):
                raise ValueError("Dense trace contains non-Dense ranking facts")
            if self.mode == "lexical" and (
                candidate.lexical_rank != candidate.rank
                or candidate.dense_rank is not None
                or candidate.rrf_score is not None
            ):
                raise ValueError("Lexical trace contains non-Lexical ranking facts")
            if self.mode == "hybrid" and candidate.rrf_score is None:
                raise ValueError("Hybrid trace requires RRF scores")
        return self


class RetrievalCaseResult(M1Schema):
    """Per-case metrics kept beside, but separate from, its full trace line."""

    case_id: SafeIdentifier
    cohort: Literal[
        "real_cross_border",
        "synthetic_cross_border",
        "general_diagnostics",
        "safety_acl_version",
    ]
    mode: Literal["dense", "lexical", "hybrid"]
    deterministic: AnswerableRankingMetrics | NoAnswerRankingMetrics
    similar_product_confusion: bool | None = None
    candidate_mapping_failures: int = Field(default=0, ge=0, le=200)
    first_candidate_mapping_failure_rank: int | None = Field(
        default=None,
        ge=1,
        le=100,
    )
    ragas: RagasRetrievalEvaluation | None = None

    @model_validator(mode="after")
    def validate_mapping_failure_summary(self) -> RetrievalCaseResult:
        if (self.candidate_mapping_failures > 0) != (
            self.first_candidate_mapping_failure_rank is not None
        ):
            raise ValueError("mapping failure count and first rank must agree")
        return self


class RetrievalLatencySummary(M1Schema):
    """Observed per-layer latency distribution for one report slice."""

    samples: int = Field(ge=0)
    candidate_count_min: int | None = Field(default=None, ge=0, le=100)
    candidate_count_p50: int | None = Field(default=None, ge=0, le=100)
    candidate_count_p95: int | None = Field(default=None, ge=0, le=100)
    candidate_count_max: int | None = Field(default=None, ge=0, le=100)
    latency_p50_ms: int | None = Field(default=None, ge=0)
    latency_p95_ms: int | None = Field(default=None, ge=0)
    latency_max_ms: int | None = Field(default=None, ge=0)


class RetrievalAggregate(M1Schema):
    """Mean deterministic retrieval metrics for one cohort and route."""

    cohort: Literal[
        "all_answerable",
        "real_cross_border",
        "synthetic_cross_border",
        "general_diagnostics",
        "safety_acl_version",
    ]
    mode: Literal["dense", "lexical", "hybrid"]
    answerable_cases: int = Field(ge=0, le=1000)
    precision_at: dict[int, FiniteFloat]
    recall_at: dict[int, FiniteFloat]
    hit_rate_at: dict[int, FiniteFloat]
    mrr_at_10: FiniteFloat = Field(ge=0, le=1)
    ndcg_at: dict[int, FiniteFloat]
    first_correct_evidence_rank_mean: FiniteFloat | None = Field(default=None, ge=1)
    missed_evidence_cases: int = Field(ge=0, le=1000)
    similar_product_cases: int = Field(ge=0, le=1000)
    similar_product_confusions: int = Field(ge=0, le=1000)
    similar_product_confusion_rate: FiniteFloat | None = Field(default=None, ge=0, le=1)
    no_answer_cases: int = Field(default=0, ge=0, le=1000)
    judged_no_answer_cases: int = Field(default=0, ge=0, le=1000)
    no_answer_false_recalls: int = Field(default=0, ge=0, le=1000)
    latency: RetrievalLatencySummary


class RetrievalTraceArtifact(M1Schema):
    """One JSONL containing complete route candidates for every case."""

    relative_path: str = Field(pattern=r"^traces/[a-z0-9._-]+\.jsonl$")
    sha256: Sha256
    cases: int = Field(ge=1, le=1000)
    route_lists: int = Field(ge=3, le=3000)
    candidates: int = Field(ge=0)
    candidate_mapping_failures: int = Field(default=0, ge=0)


class RetrievalExperimentResult(M1Schema):
    """One bounded matrix point for a frozen Chunk candidate."""

    config_id: SafeIdentifier
    production_baseline: bool
    stage: Literal["candidate_depth", "rrf"]
    candidate_depth: Literal[10, 20, 30]
    rrf_k: Literal[20, 60, 100]
    index_sets: int = Field(ge=1, le=64)
    chunks: int = Field(ge=1)
    index_latency_ms: int = Field(ge=0)
    candidate_mapping_quality_gate_passed: bool
    cases: list[RetrievalCaseResult] = Field(min_length=1, max_length=3000)
    aggregates: list[RetrievalAggregate] = Field(min_length=3, max_length=15)
    trace: RetrievalTraceArtifact


class RetrievalConfigSelection(M1Schema):
    """Sequential depth then RRF selection; never a Cartesian search."""

    config_id: SafeIdentifier
    selected_candidate_depth: Literal[10, 20, 30]
    selected_rrf_k: Literal[20, 60, 100]
    criterion: Literal["real-core-hit8-recall8-mrr10-then-lower-cost"] = (
        "real-core-hit8-recall8-mrr10-then-lower-cost"
    )


class RetrievalFilterAudit(M1Schema):
    """Proof that forbidden rows were absent from each pre-ranking route."""

    probe_config_id: SafeIdentifier
    acl_denied_cases: int = Field(ge=0)
    acl_leaks: int = Field(ge=0)
    deleted_probe_routes: int = Field(ge=0)
    deleted_leaks: int = Field(ge=0)
    inactive_probe_routes: int = Field(ge=0)
    inactive_index_leaks: int = Field(ge=0)
    tenant_probe_routes: int = Field(ge=0)
    tenant_leaks: int = Field(ge=0)
    ranking_stability_routes: int = Field(ge=0)
    unstable_routes: int = Field(ge=0)


class RetrievalCleanupResult(M1Schema):
    """Precise isolation cleanup plus formal Seed/M1 restoration facts."""

    cleanup_attempted: bool
    evaluation_database_rows_remaining: int = Field(ge=0)
    evaluation_storage_objects_remaining: int = Field(ge=0)
    formal_files: int = Field(ge=0)
    formal_documents: int = Field(ge=0)
    formal_versions: int = Field(ge=0)
    formal_acl: int = Field(ge=0)
    formal_chunk_sets: int = Field(ge=0)
    formal_index_sets: int = Field(ge=0)
    formal_chunks: int = Field(ge=0)
    formal_upload_objects: int = Field(ge=0)
    m1_guard_available: int | None = Field(default=None, ge=0)
    formal_seed_reapplied: bool
    baseline_restored: bool


class RetrievalEvaluationReport(M1Schema):
    """M2-22.6 summary; full ordered candidates live in hashed JSONL files."""

    schema_version: Literal["m2-retrieval-evaluation-report-v1"] = (
        "m2-retrieval-evaluation-report-v1"
    )
    run_id: SafeIdentifier
    run_status: Literal["completed", "failed"]
    started_at: AwareDatetime
    completed_at: AwareDatetime
    source_manifest_version: str = Field(min_length=1, max_length=128)
    source_manifest_sha256: Sha256
    dataset_version: str = Field(min_length=1, max_length=128)
    dataset_sha256: Sha256
    embedding_provider: str = Field(min_length=1, max_length=64)
    embedding_model: str = Field(min_length=1, max_length=200)
    embedding_revision: str = Field(min_length=1, max_length=100)
    embedding_batch_size: int = Field(ge=1, le=32)
    production_database_statement_timeout_ms: int = Field(ge=50, le=30_000)
    evaluation_database_statement_timeout_ms: int = Field(ge=50, le=30_000)
    production_index_timeout_observed: bool
    query_embedding_latency: RetrievalLatencySummary
    ragas_version: Literal["0.4.3"]
    ragas_scope: Literal["retrieval-only-selected-candidate"]
    experiments: list[RetrievalExperimentResult] = Field(min_length=1, max_length=100)
    selections: list[RetrievalConfigSelection] = Field(min_length=1, max_length=16)
    recommended_candidate_config_id: SafeIdentifier
    recommended_candidate_depth: Literal[10, 20, 30]
    recommended_rrf_k: Literal[20, 60, 100]
    production_defaults_changed: Literal[False] = False
    integrity_quality_gate_passed: bool
    filter_audit: RetrievalFilterAudit
    bad_cases: list[dict[str, object]] = Field(default_factory=list, max_length=1000)
    failure_category: FailureCategory | None = None
    failure_summary: str | None = Field(default=None, max_length=300)
    cleanup: RetrievalCleanupResult

    @model_validator(mode="after")
    def validate_run(self) -> RetrievalEvaluationReport:
        expected_integrity_gate = (
            all(
                experiment.candidate_mapping_quality_gate_passed
                for experiment in self.experiments
            )
            and self.filter_audit.acl_leaks == 0
            and self.filter_audit.deleted_leaks == 0
            and self.filter_audit.inactive_index_leaks == 0
            and self.filter_audit.tenant_leaks == 0
            and self.filter_audit.unstable_routes == 0
            and self.cleanup.baseline_restored
        )
        if self.integrity_quality_gate_passed != expected_integrity_gate:
            raise ValueError("integrity quality gate does not match report evidence")
        if self.run_status == "completed":
            if (
                self.failure_category is not None
                or self.failure_summary is not None
                or not self.cleanup.baseline_restored
            ):
                raise ValueError("completed retrieval evaluation must be clean")
        elif self.failure_category is None or self.failure_summary is None:
            raise ValueError("failed retrieval evaluation requires a safe reason")
        return self
