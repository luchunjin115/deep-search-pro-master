"""Public-safe deterministic report contracts for M2-22.7 Reranker/Context runs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field, FiniteFloat, model_validator

from app.schemas.common import M1Schema
from app.schemas.evaluation import (
    ContextCaseQualityResult,
    ContextGroupAggregateResult,
    ModelIdentifier,
    RerankerCaseComparison,
    RerankerContextEvaluationCohort,
    RerankerContextEvaluationPlan,
    RerankerContextExperimentPoint,
    RerankerContextSafetyCaseResult,
    RerankerGroupAggregateResult,
    RerankerTopK,
    SafeIdentifier,
    Sha256,
    VersionLabel,
)
from app.schemas.retrieval import (
    RetrievalEmbeddingIdentity,
    RetrievalFtsIdentity,
    RetrievalSourceLocator,
)


class FakeRerankerIdentity(M1Schema):
    """An explicitly fake scorer identity that can never claim a real BGE run."""

    provider: Literal["deterministic_fake"] = "deterministic_fake"
    model_id: ModelIdentifier = "fake/m2-deterministic-reranker"
    revision: VersionLabel = "m2-fake-v1"
    max_length: Literal[8192] = 8192
    precision: Literal["float32"] = "float32"
    scorer_version: Literal["sha256-unit-interval-v1"] = "sha256-unit-interval-v1"


class FakeContextReaderIdentity(M1Schema):
    """An explicitly in-memory Context reader identity for this fake-only step."""

    provider: Literal["in_memory_fake"] = "in_memory_fake"
    version: Literal["m2-in-memory-context-reader-v1"] = (
        "m2-in-memory-context-reader-v1"
    )


class RerankerContextCacheStats(M1Schema):
    """Run-local score cache facts; cache entries never cross report runs."""

    scope: Literal["current_run_only"] = "current_run_only"
    score_requests: int = Field(strict=True, ge=0)
    cache_hits: int = Field(strict=True, ge=0)
    cache_misses: int = Field(strict=True, ge=0)
    provider_score_calls: int = Field(strict=True, ge=0)
    cache_entries: int = Field(strict=True, ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> RerankerContextCacheStats:
        if self.score_requests != self.cache_hits + self.cache_misses:
            raise ValueError("score requests must equal cache hits plus misses")
        if self.provider_score_calls != self.cache_misses:
            raise ValueError("each completed cache miss must call the provider")
        if self.cache_entries > self.provider_score_calls:
            raise ValueError("cache entries cannot exceed provider calls")
        return self


class BgeRerankerProbeIdentity(M1Schema):
    """Exact public identity required by the pinned local BGE probe."""

    contract_version: Literal["m2-reranker-provider-v1"] = "m2-reranker-provider-v1"
    provider: Literal["bge-reranker-local"] = "bge-reranker-local"
    model_id: Literal["BAAI/bge-reranker-v2-m3"] = "BAAI/bge-reranker-v2-m3"
    revision: Literal["953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"] = (
        "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
    )
    max_length: Literal[8192] = 8192
    precision: Literal["float32"] = "float32"
    score_transform: Literal["sigmoid"] = "sigmoid"
    scorer_version: Literal["m2-bge-resource-probe-v1"] = "m2-bge-resource-probe-v1"


class BgeRerankerFormalIdentity(M1Schema):
    """Exact scorer identity for the complete 18-document/40-case matrix."""

    contract_version: Literal["m2-reranker-provider-v1"] = "m2-reranker-provider-v1"
    provider: Literal["bge-reranker-local"] = "bge-reranker-local"
    model_id: Literal["BAAI/bge-reranker-v2-m3"] = "BAAI/bge-reranker-v2-m3"
    revision: Literal["953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"] = (
        "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
    )
    max_length: Literal[8192] = 8192
    precision: Literal["float32"] = "float32"
    score_transform: Literal["sigmoid"] = "sigmoid"
    scorer_version: Literal["m2-bge-formal-matrix-v1"] = "m2-bge-formal-matrix-v1"


class PostgresContextReaderIdentity(M1Schema):
    """Identity of the production Context path exercised by the formal matrix."""

    provider: Literal["postgresql_context_repository"] = "postgresql_context_repository"
    builder_version: Literal["m2-context-builder-v1"] = "m2-context-builder-v1"
    token_counter_version: Literal["m2-unicode-token-counter-v1"] = (
        "m2-unicode-token-counter-v1"
    )


class FrozenRagCorpusPublicIdentity(M1Schema):
    """Public hashes and counts proving the retained chunks were reused."""

    contract_version: Literal["m2-reranker-context-corpus-v1"] = (
        "m2-reranker-context-corpus-v1"
    )
    corpus_sha256: Sha256
    index_sha256: Sha256
    snapshot_sha256: Sha256
    source_count: Literal[18] = 18
    document_count: Literal[18] = 18
    chunk_set_count: Literal[18] = 18
    index_set_count: int = Field(strict=True, ge=18)
    chunk_count: Literal[779] = 779
    chunks_reused_without_rechunking: Literal[True] = True


class FormalEvaluationMeasurements(M1Schema):
    """Bounded local CPU and latency facts for the complete matrix."""

    total_elapsed_seconds: FiniteFloat = Field(ge=0)
    reranker_load_seconds: FiniteFloat = Field(ge=0)
    scoring_latency_p50_ms: FiniteFloat = Field(ge=0)
    scoring_latency_p95_ms: FiniteFloat = Field(ge=0)
    scoring_latency_max_ms: FiniteFloat = Field(ge=0)
    effective_batch_size_min: int = Field(strict=True, ge=1, le=20)
    effective_batch_size_max: int = Field(strict=True, ge=1, le=20)
    rss_start_mib: FiniteFloat = Field(ge=0)
    rss_peak_mib: FiniteFloat = Field(ge=0)
    rss_peak_delta_mib: FiniteFloat = Field(ge=0)

    @model_validator(mode="after")
    def validate_measurements(self) -> FormalEvaluationMeasurements:
        if not (
            self.scoring_latency_p50_ms
            <= self.scoring_latency_p95_ms
            <= self.scoring_latency_max_ms
        ):
            raise ValueError("formal scoring latency percentiles must be ordered")
        if self.effective_batch_size_min > self.effective_batch_size_max:
            raise ValueError("formal effective batch bounds are reversed")
        if self.rss_peak_mib < self.rss_start_mib:
            raise ValueError("formal peak RSS cannot precede its start RSS")
        return self


class RerankerContextBadCase(M1Schema):
    """Safe failure attribution without question or source body text."""

    case_id: SafeIdentifier
    stage: Literal[
        "upstream_candidate_missing",
        "reranker_topk_miss",
        "context_evidence_miss",
        "metric_calculation_failed",
        "safety_violation",
    ]
    selected_top_k: RerankerTopK
    summary: str = Field(strict=True, min_length=1, max_length=300)


class RerankerResourceProbeCaseResult(M1Schema):
    """Safe result for one 20-candidate probe pool; source text is excluded."""

    case_id: SafeIdentifier
    category: Literal[
        "chinese",
        "english",
        "german",
        "table",
        "candidate_missing",
        "no_answer",
    ]
    status: Literal["completed", "candidate_missing", "no_answer"]
    candidate_count: Literal[20] = 20
    score_count: Literal[20] = 20
    finite_scores: Literal[True] = True
    expected_candidate_id: SafeIdentifier | None = None
    expected_candidate_rank: int | None = Field(default=None, strict=True, ge=1, le=20)
    scores_sha256: Sha256

    @model_validator(mode="after")
    def validate_status(self) -> RerankerResourceProbeCaseResult:
        if self.category in {"candidate_missing", "no_answer"}:
            if self.status != self.category:
                raise ValueError("probe safety status must match its category")
            if (
                self.expected_candidate_id is not None
                or self.expected_candidate_rank is not None
            ):
                raise ValueError("missing/no-answer probes cannot invent a rank")
            return self
        if (
            self.status != "completed"
            or self.expected_candidate_id is None
            or self.expected_candidate_rank is None
        ):
            raise ValueError("answerable probe cases require one retained rank")
        return self


class RerankerResourceProbeMeasurements(M1Schema):
    """Bounded CPU load, scoring, memory, batch, and process measurements."""

    load_seconds: FiniteFloat = Field(ge=0)
    scoring_latency_p50_ms: FiniteFloat = Field(ge=0)
    scoring_latency_p95_ms: FiniteFloat = Field(ge=0)
    scoring_latency_max_ms: FiniteFloat = Field(ge=0)
    rss_start_mib: FiniteFloat = Field(ge=0)
    rss_peak_mib: FiniteFloat = Field(ge=0)
    rss_peak_delta_mib: FiniteFloat = Field(ge=0)
    configured_batch_size: int = Field(strict=True, ge=1, le=16)
    effective_batch_size_min: int = Field(strict=True, ge=1, le=20)
    effective_batch_size_max: int = Field(strict=True, ge=1, le=20)
    new_live_child_process_count: int = Field(strict=True, ge=0)

    @model_validator(mode="after")
    def validate_measurements(self) -> RerankerResourceProbeMeasurements:
        if not (
            self.scoring_latency_p50_ms
            <= self.scoring_latency_p95_ms
            <= self.scoring_latency_max_ms
        ):
            raise ValueError("probe latency percentiles must be ordered")
        if self.rss_peak_mib < self.rss_start_mib:
            raise ValueError("probe peak RSS cannot precede its start RSS")
        if self.effective_batch_size_min > self.effective_batch_size_max:
            raise ValueError("effective batch bounds are reversed")
        return self


class RerankerResourceProbeReport(M1Schema):
    """Public-safe report for a few real local-BGE resource probes."""

    schema_version: Literal["m2-reranker-resource-probe-v1"] = (
        "m2-reranker-resource-probe-v1"
    )
    execution_mode: Literal["pinned_local_bge_probe"] = "pinned_local_bge_probe"
    run_id: SafeIdentifier
    run_status: Literal["completed"] = "completed"
    quality_gate_passed: None = None
    offline_inference: Literal[True] = True
    snapshot_verified: Literal[True] = True
    actual_device: Literal["cpu"] = "cpu"
    max_candidate_pool: Literal[20] = 20
    max_length_contract_verified: Literal[True] = True
    long_input_exercised: Literal[False] = False
    input_sha256: Sha256
    scorer: BgeRerankerProbeIdentity
    cases: list[RerankerResourceProbeCaseResult] = Field(
        min_length=6,
        max_length=6,
    )
    cache: RerankerContextCacheStats
    measurements: RerankerResourceProbeMeasurements

    @model_validator(mode="after")
    def validate_report(self) -> RerankerResourceProbeReport:
        if self.run_id != f"m2-2274-{self.input_sha256[:16]}":
            raise ValueError("probe run ID must derive from the complete safe input")
        expected_categories = [
            "chinese",
            "english",
            "german",
            "table",
            "candidate_missing",
            "no_answer",
        ]
        if [item.category for item in self.cases] != expected_categories:
            raise ValueError("probe must retain the six fixed categories in order")
        if (
            self.cache.score_requests != 12
            or self.cache.cache_misses != 6
            or self.cache.cache_hits != 6
            or self.cache.provider_score_calls != 6
            or self.cache.cache_entries != 6
        ):
            raise ValueError(
                "probe cache must score six pools once and reuse each once"
            )
        return self

    def artifact_sha256(self) -> str:
        """Hash the exact public bytes written by the probe report writer."""

        return hashlib.sha256(serialize_reranker_resource_probe(self)).hexdigest()


class PublicRerankerCandidateTrace(M1Schema):
    """One safe candidate trace without question text, body text, or private paths."""

    candidate_id: SafeIdentifier
    logical_document_id: SafeIdentifier
    version_id: SafeIdentifier | None = None
    index_set_id: SafeIdentifier | None = None
    rrf_rank: int = Field(strict=True, ge=1, le=20)
    reranker_rank: int = Field(strict=True, ge=1, le=20)
    rrf_score: FiniteFloat = Field(gt=0)
    reranker_score: FiniteFloat
    body_text_sha256: Sha256
    source_locator: RetrievalSourceLocator | None = None
    matched_evidence_ids: list[SafeIdentifier] = Field(
        default_factory=list, max_length=20
    )

    @model_validator(mode="after")
    def validate_evidence(self) -> PublicRerankerCandidateTrace:
        if len(self.matched_evidence_ids) != len(set(self.matched_evidence_ids)):
            raise ValueError("candidate trace Evidence IDs must be unique")
        return self


class RerankerContextAnswerableTrace(M1Schema):
    """One answerable trace whose hash covers ranks and all deterministic results."""

    case_id: SafeIdentifier
    query_sha256: Sha256
    selected_top_k: RerankerTopK
    candidates: list[PublicRerankerCandidateTrace] = Field(max_length=20)
    comparisons: list[RerankerCaseComparison] = Field(min_length=2, max_length=2)
    context_results: list[ContextCaseQualityResult] = Field(
        min_length=6,
        max_length=6,
    )

    @model_validator(mode="after")
    def validate_trace(self) -> RerankerContextAnswerableTrace:
        candidate_ids = [item.candidate_id for item in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("answerable trace candidate IDs must be unique")
        expected_ranks = list(range(1, len(self.candidates) + 1))
        if sorted(item.rrf_rank for item in self.candidates) != expected_ranks:
            raise ValueError("RRF trace ranks must be contiguous")
        if sorted(item.reranker_rank for item in self.candidates) != expected_ranks:
            raise ValueError("Reranker trace ranks must be contiguous")
        if [item.top_k for item in self.comparisons] != [5, 8]:
            raise ValueError("answerable trace must contain Top5 then Top8")
        if any(item.case_id != self.case_id for item in self.comparisons):
            raise ValueError("comparison case IDs must match their trace")
        expected_contexts = [
            (self.selected_top_k, neighbor, tokens)
            for neighbor in (0, 1)
            for tokens in (2000, 3000, 4000)
        ]
        actual_contexts = [
            (
                item.reranker_top_k,
                item.context_neighbor_window,
                item.context_max_tokens,
            )
            for item in self.context_results
        ]
        if actual_contexts != expected_contexts:
            raise ValueError(
                "answerable trace must contain the six ordered Context points"
            )
        if any(item.case_id != self.case_id for item in self.context_results):
            raise ValueError("Context case IDs must match their trace")
        return self


class RerankerContextAnswerableRunResult(M1Schema):
    """One answerable trace plus its tamper-evident SHA-256."""

    trace: RerankerContextAnswerableTrace
    trace_sha256: Sha256

    @model_validator(mode="after")
    def validate_trace_hash(self) -> RerankerContextAnswerableRunResult:
        if self.trace_sha256 != public_trace_sha256(self.trace):
            raise ValueError("answerable trace hash does not match its payload")
        return self


class RerankerContextSafetyTrace(M1Schema):
    """One retained safety row with the same safe rank trace format."""

    case_id: SafeIdentifier
    query_sha256: Sha256
    selected_top_k: RerankerTopK
    candidates: list[PublicRerankerCandidateTrace] = Field(max_length=20)
    result: RerankerContextSafetyCaseResult

    @model_validator(mode="after")
    def validate_trace(self) -> RerankerContextSafetyTrace:
        if (
            self.result.case_id != self.case_id
            or self.result.top_k != self.selected_top_k
        ):
            raise ValueError("safety result identity must match its trace")
        return self


class RerankerContextSafetyRunResult(M1Schema):
    """One safety trace plus its tamper-evident SHA-256."""

    trace: RerankerContextSafetyTrace
    trace_sha256: Sha256

    @model_validator(mode="after")
    def validate_trace_hash(self) -> RerankerContextSafetyRunResult:
        if self.trace_sha256 != public_trace_sha256(self.trace):
            raise ValueError("safety trace hash does not match its payload")
        return self


class RerankerContextEvaluationReport(M1Schema):
    """Fake-only report that cannot be mistaken for a completed quality gate."""

    schema_version: Literal["m2-reranker-context-fake-report-v1"] = (
        "m2-reranker-context-fake-report-v1"
    )
    execution_mode: Literal["deterministic_fake"] = "deterministic_fake"
    run_id: SafeIdentifier
    run_status: Literal["completed"] = "completed"
    quality_gate_passed: None = None
    selected_top_k: RerankerTopK
    plan: RerankerContextEvaluationPlan
    experiment_points: list[RerankerContextExperimentPoint] = Field(
        min_length=8,
        max_length=8,
    )
    dataset_version: VersionLabel
    dataset_sha256: Sha256
    input_sha256: Sha256
    scorer: FakeRerankerIdentity
    context_reader: FakeContextReaderIdentity
    cohort: RerankerContextEvaluationCohort
    answerable_results: list[RerankerContextAnswerableRunResult] = Field(
        min_length=34,
        max_length=34,
    )
    reranker_aggregates: list[RerankerGroupAggregateResult] = Field(
        min_length=2,
        max_length=2,
    )
    context_aggregates: list[ContextGroupAggregateResult] = Field(
        min_length=6,
        max_length=6,
    )
    safety_results: list[RerankerContextSafetyRunResult] = Field(
        min_length=6,
        max_length=6,
    )
    safety_gate_passed: bool
    cache: RerankerContextCacheStats
    trace_set_sha256: Sha256

    @model_validator(mode="after")
    def validate_report(self) -> RerankerContextEvaluationReport:
        if self.run_id != f"m2-2272-{self.input_sha256[:16]}":
            raise ValueError("run ID must be derived from the complete fake input")
        if self.cohort.dataset_version != self.dataset_version:
            raise ValueError("report and cohort dataset versions must match")
        expected_plan = [
            ("reranker_top_k", 5, None, None),
            ("reranker_top_k", 8, None, None),
            *[
                ("context", self.selected_top_k, neighbor, tokens)
                for neighbor in (0, 1)
                for tokens in (2000, 3000, 4000)
            ],
        ]
        actual_plan = [
            (
                item.stage,
                item.reranker_top_k,
                item.context_neighbor_window,
                item.context_max_tokens,
            )
            for item in self.experiment_points
        ]
        if actual_plan != expected_plan:
            raise ValueError(
                "report experiment plan is not the bounded eight-point order"
            )

        answerable_ids = [item.trace.case_id for item in self.answerable_results]
        if answerable_ids != self.cohort.answerable_case_ids:
            raise ValueError(
                "answerable report rows must preserve the frozen denominator"
            )
        if any(
            item.trace.selected_top_k != self.selected_top_k
            for item in self.answerable_results
        ):
            raise ValueError("answerable traces must use the report-selected TopK")
        safety_ids = [item.trace.case_id for item in self.safety_results]
        expected_safety_ids = [item.case_id for item in self.cohort.safety_cases]
        if safety_ids != expected_safety_ids:
            raise ValueError("safety report rows must preserve the frozen denominator")
        reason_by_case = {
            item.case_id: item.expected_non_answer_reason
            for item in self.cohort.safety_cases
        }
        if any(
            item.trace.result.expected_non_answer_reason
            != reason_by_case[item.trace.case_id]
            for item in self.safety_results
        ):
            raise ValueError("safety reasons must match the frozen cohort")

        if [item.top_k for item in self.reranker_aggregates] != [5, 8]:
            raise ValueError(
                "report must contain all-answerable Top5 then Top8 aggregates"
            )
        if any(
            item.group_id != "all-answerable"
            or item.expected_case_count != self.plan.answerable_case_count
            for item in self.reranker_aggregates
        ):
            raise ValueError("Reranker aggregates must preserve all 34 answerable rows")
        expected_contexts = [
            (self.selected_top_k, neighbor, tokens)
            for neighbor in (0, 1)
            for tokens in (2000, 3000, 4000)
        ]
        actual_contexts = [
            (
                item.reranker_top_k,
                item.context_neighbor_window,
                item.context_max_tokens,
            )
            for item in self.context_aggregates
        ]
        if actual_contexts != expected_contexts or any(
            item.group_id != "all-answerable"
            or item.expected_case_count != self.plan.answerable_case_count
            for item in self.context_aggregates
        ):
            raise ValueError("Context aggregates must preserve all six 34-case points")

        expected_requests = (
            self.plan.answerable_case_count * len(self.experiment_points)
            + self.plan.safety_case_count
        )
        if self.cache.score_requests != expected_requests:
            raise ValueError(
                "cache requests must cover every bounded logical score use"
            )
        if self.cache.provider_score_calls > (
            self.plan.answerable_case_count + self.plan.safety_case_count
        ):
            raise ValueError("provider scored more than once per case")
        if self.cache.cache_entries != self.cache.provider_score_calls:
            raise ValueError("a completed fake run cannot contain uncached failures")

        deterministic_security = [
            item.trace.result.security_violation
            for item in self.safety_results
            if item.trace.result.security_violation is not None
        ]
        if self.safety_gate_passed != all(
            violation is False for violation in deterministic_security
        ):
            raise ValueError("safety gate contradicts the retained safety rows")
        expected_trace_set_hash = hashlib.sha256(
            _canonical_bytes(
                [
                    *[item.trace_sha256 for item in self.answerable_results],
                    *[item.trace_sha256 for item in self.safety_results],
                ]
            )
        ).hexdigest()
        if self.trace_set_sha256 != expected_trace_set_hash:
            raise ValueError("trace set hash does not match the ordered case hashes")
        return self

    def artifact_sha256(self) -> str:
        """Hash the exact public bytes written by the report writer."""

        return hashlib.sha256(serialize_public_report(self)).hexdigest()


class FormalRerankerContextEvaluationReport(M1Schema):
    """Complete real-BGE report; completion is separate from its quality gate."""

    schema_version: Literal["m2-reranker-context-formal-report-v1"] = (
        "m2-reranker-context-formal-report-v1"
    )
    execution_mode: Literal["pinned_local_bge_formal"] = "pinned_local_bge_formal"
    run_id: SafeIdentifier
    run_status: Literal["completed"] = "completed"
    evaluation_completed: Literal[True] = True
    quality_gate_passed: bool
    quality_gate_min_real_cross_border_hit_at_selected_k: FiniteFloat = Field(
        default=0.9,
        ge=0.9,
        le=0.9,
    )
    selected_top_k: RerankerTopK
    plan: RerankerContextEvaluationPlan
    experiment_points: list[RerankerContextExperimentPoint] = Field(
        min_length=8,
        max_length=8,
    )
    dataset_version: VersionLabel
    dataset_sha256: Sha256
    input_sha256: Sha256
    corpus: FrozenRagCorpusPublicIdentity
    retrieval_embedding: RetrievalEmbeddingIdentity
    retrieval_fts: RetrievalFtsIdentity
    scorer: BgeRerankerFormalIdentity
    context_reader: PostgresContextReaderIdentity
    cohort: RerankerContextEvaluationCohort
    answerable_results: list[RerankerContextAnswerableRunResult] = Field(
        min_length=34,
        max_length=34,
    )
    reranker_aggregates: list[RerankerGroupAggregateResult] = Field(
        min_length=8,
        max_length=8,
    )
    context_aggregates: list[ContextGroupAggregateResult] = Field(
        min_length=24,
        max_length=24,
    )
    safety_results: list[RerankerContextSafetyRunResult] = Field(
        min_length=6,
        max_length=6,
    )
    safety_gate_passed: bool
    candidate_mapping_failure_count: int = Field(default=0, strict=True, ge=0)
    safety_leak_count: int = Field(default=0, strict=True, ge=0)
    cache: RerankerContextCacheStats
    measurements: FormalEvaluationMeasurements
    bad_cases: list[RerankerContextBadCase] = Field(
        default_factory=list, max_length=136
    )
    trace_set_sha256: Sha256

    @model_validator(mode="after")
    def validate_report(self) -> FormalRerankerContextEvaluationReport:
        if self.run_id != f"m2-2275-{self.input_sha256[:16]}":
            raise ValueError("formal run ID must derive from the complete safe input")
        if self.cohort.dataset_version != self.dataset_version:
            raise ValueError("formal report and cohort dataset versions must match")
        expected_plan = [
            ("reranker_top_k", 5, None, None),
            ("reranker_top_k", 8, None, None),
            *[
                ("context", self.selected_top_k, neighbor, tokens)
                for neighbor in (0, 1)
                for tokens in (2000, 3000, 4000)
            ],
        ]
        actual_plan = [
            (
                item.stage,
                item.reranker_top_k,
                item.context_neighbor_window,
                item.context_max_tokens,
            )
            for item in self.experiment_points
        ]
        if actual_plan != expected_plan:
            raise ValueError("formal report does not preserve the bounded eight points")

        answerable_ids = [item.trace.case_id for item in self.answerable_results]
        if answerable_ids != self.cohort.answerable_case_ids:
            raise ValueError(
                "formal report shrank or reordered the 34-case denominator"
            )
        if any(
            item.trace.selected_top_k != self.selected_top_k
            for item in self.answerable_results
        ):
            raise ValueError("formal answerable traces disagree on selected TopK")
        safety_ids = [item.trace.case_id for item in self.safety_results]
        expected_safety_ids = [item.case_id for item in self.cohort.safety_cases]
        if safety_ids != expected_safety_ids:
            raise ValueError("formal report shrank or reordered the safety denominator")

        group_counts = {
            "all-answerable": 34,
            "real-cross-border": 14,
            "synthetic-cross-border": 10,
            "general-diagnostics": 10,
        }
        expected_reranker = [
            (group_id, top_k, case_count)
            for top_k in (5, 8)
            for group_id, case_count in group_counts.items()
        ]
        actual_reranker = [
            (item.group_id, item.top_k, item.expected_case_count)
            for item in self.reranker_aggregates
        ]
        if actual_reranker != expected_reranker:
            raise ValueError("formal Reranker groups or denominators are incomplete")

        expected_context = [
            (group_id, self.selected_top_k, neighbor, tokens, case_count)
            for neighbor in (0, 1)
            for tokens in (2000, 3000, 4000)
            for group_id, case_count in group_counts.items()
        ]
        actual_context = [
            (
                item.group_id,
                item.reranker_top_k,
                item.context_neighbor_window,
                item.context_max_tokens,
                item.expected_case_count,
            )
            for item in self.context_aggregates
        ]
        if actual_context != expected_context:
            raise ValueError("formal Context groups or denominators are incomplete")

        all_by_top_k = {
            item.top_k: item
            for item in self.reranker_aggregates
            if item.group_id == "all-answerable"
        }
        if set(all_by_top_k) != {5, 8} or any(
            item.status != "completed" for item in all_by_top_k.values()
        ):
            raise ValueError("formal TopK selection requires two completed aggregates")
        top5_hits = all_by_top_k[5].reranker_hit_count
        top8_hits = all_by_top_k[8].reranker_hit_count
        assert top5_hits is not None and top8_hits is not None
        expected_top_k = 8 if top8_hits > top5_hits else 5
        if self.selected_top_k != expected_top_k:
            raise ValueError("formal selected TopK contradicts the frozen rule")

        nonempty_answerable = sum(
            bool(item.trace.candidates) for item in self.answerable_results
        )
        nonempty_safety = sum(
            bool(item.trace.candidates) for item in self.safety_results
        )
        if (
            self.cache.score_requests != nonempty_answerable * 2 + nonempty_safety
            or self.cache.cache_hits != nonempty_answerable
            or self.cache.cache_misses != nonempty_answerable + nonempty_safety
            or self.cache.provider_score_calls != self.cache.cache_misses
            or self.cache.cache_entries != self.cache.cache_misses
        ):
            raise ValueError(
                "formal cache did not score each non-empty pool exactly once"
            )

        deterministic_security = [
            item.trace.result.security_violation
            for item in self.safety_results
            if item.trace.result.security_violation is not None
        ]
        expected_safety_gate = all(
            item.trace.result.status == "completed"
            and item.trace.result.security_violation is not True
            for item in self.safety_results
        )
        if (
            self.safety_gate_passed != expected_safety_gate
            or self.safety_leak_count
            != sum(value is True for value in deterministic_security)
        ):
            raise ValueError("formal safety gate contradicts retained safety rows")

        real_aggregate = next(
            item
            for item in self.reranker_aggregates
            if item.group_id == "real-cross-border"
            and item.top_k == self.selected_top_k
        )
        expected_quality_gate = bool(
            self.safety_gate_passed
            and real_aggregate.status == "completed"
            and real_aggregate.reranker_hit_rate_at_k is not None
            and real_aggregate.reranker_hit_rate_at_k
            >= self.quality_gate_min_real_cross_border_hit_at_selected_k
            and all(item.status == "completed" for item in self.context_aggregates)
        )
        if self.quality_gate_passed != expected_quality_gate:
            raise ValueError("formal quality gate contradicts the retained metrics")

        bad_case_keys = [(item.case_id, item.stage) for item in self.bad_cases]
        if len(bad_case_keys) != len(set(bad_case_keys)):
            raise ValueError("formal Bad Cases must be unique by case and stage")
        expected_trace_set_hash = hashlib.sha256(
            _canonical_bytes(
                [
                    *[item.trace_sha256 for item in self.answerable_results],
                    *[item.trace_sha256 for item in self.safety_results],
                ]
            )
        ).hexdigest()
        if self.trace_set_sha256 != expected_trace_set_hash:
            raise ValueError("formal trace set hash does not match its case hashes")
        return self

    def artifact_sha256(self) -> str:
        return hashlib.sha256(serialize_public_report(self)).hexdigest()


def public_trace_sha256(
    trace: RerankerContextAnswerableTrace | RerankerContextSafetyTrace,
) -> str:
    """Hash one canonical, public-only per-case trace."""

    return hashlib.sha256(_canonical_bytes(trace.model_dump(mode="json"))).hexdigest()


def build_trace_set_sha256(trace_hashes: list[str]) -> str:
    """Hash the ordered 34+6 per-case hashes without exposing source text."""

    return hashlib.sha256(_canonical_bytes(trace_hashes)).hexdigest()


def serialize_public_report(
    report: RerankerContextEvaluationReport | FormalRerankerContextEvaluationReport,
) -> bytes:
    """Serialize only the strict report schema in stable UTF-8 JSON."""

    payload = report.model_dump(mode="json")
    _reject_private_report_keys(payload)
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def write_public_report(
    path: Path,
    report: RerankerContextEvaluationReport | FormalRerankerContextEvaluationReport,
) -> str:
    """Write one deterministic report and return its exact artifact hash."""

    content = serialize_public_report(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def serialize_reranker_resource_probe(
    report: RerankerResourceProbeReport,
) -> bytes:
    """Serialize the strict probe report without private inputs or machine paths."""

    payload = report.model_dump(mode="json")
    _reject_private_report_keys(payload)
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def write_reranker_resource_probe_report(
    path: Path,
    report: RerankerResourceProbeReport,
) -> Path:
    """Write one public-safe probe artifact and return its resolved target."""

    content = serialize_reranker_resource_probe(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _reject_private_report_keys(value: object) -> None:
    forbidden = {
        "body_text",
        "question",
        "storage_key",
        "tenant_id",
        "owner_user_id",
        "local_path",
        "sql",
    }
    if isinstance(value, dict):
        if forbidden & set(value):
            raise ValueError("public report contains a private field")
        for item in value.values():
            _reject_private_report_keys(item)
    elif isinstance(value, list):
        for item in value:
            _reject_private_report_keys(item)
