"""Formal, bounded M2-22.7.5 Reranker and Context evaluation orchestration."""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, cast
from uuid import UUID

import psutil  # type: ignore[import-untyped]
from sqlalchemy import select

from app.core.config import BGE_RERANKER_MODEL_ID, BGE_RERANKER_REVISION, Settings
from app.db.session import DatabaseRuntime
from app.evals.rag_runner import (
    DEFAULT_DATASET_PATH,
    PROJECT_ROOT,
    _load_cases,
    _PeakRssSampler,
)
from app.evals.reranker_context_corpus import FrozenRagCorpusSnapshot
from app.evals.reranker_context_metrics import (
    aggregate_context_quality,
    aggregate_reranker_comparisons,
    build_bounded_reranker_context_plan,
    evaluate_context_quality,
    evaluate_reranker_comparison,
    evaluate_reranker_context_safety,
    freeze_reranker_context_cohort,
)
from app.evals.reranker_context_report import (
    BgeRerankerFormalIdentity,
    FormalEvaluationMeasurements,
    FormalRerankerContextEvaluationReport,
    FrozenRagCorpusPublicIdentity,
    PostgresContextReaderIdentity,
    RerankerContextAnswerableRunResult,
    RerankerContextAnswerableTrace,
    RerankerContextBadCase,
    RerankerContextCacheStats,
    RerankerContextSafetyRunResult,
    RerankerContextSafetyTrace,
    build_trace_set_sha256,
    public_trace_sha256,
)
from app.evals.reranker_context_runner import (
    RerankerContextCandidateInput,
    _candidate_trace,
    _FrozenHybridRoute,
    build_m2_database_probe_context,
)
from app.evals.retrieval_runner import (
    _case_database_state,
    _evaluation_users,
    _fuse_routes,
    _measure_routes,
    case_reporting_cohort,
)
from app.models.knowledge import DocumentIndexSet
from app.repositories.retrieval import RetrievalRepository
from app.schemas.auth import CurrentUser
from app.schemas.evaluation import (
    ContextCaseQualityResult,
    ContextEvaluationNeighborWindow,
    ContextEvaluationTokenBudget,
    ContextGroupAggregateResult,
    EvaluationCase,
    RerankerCaseComparison,
    RerankerContextEvaluationPlan,
    RerankerContextSafetyCaseResult,
    RerankerGroupAggregateResult,
    RerankerTopK,
)
from app.schemas.retrieval import (
    RerankedRetrievalResponse,
    RetrievalEmbeddingIdentity,
    RetrievalFtsIdentity,
    RetrievalRequest,
    RetrievalResponse,
)
from app.services.retrieval import EmbeddingProvider
from app.services.retrieval.context import CONTEXT_BUILDER_VERSION
from app.services.retrieval.reranker import RerankerRetrievalService
from app.services.retrieval.reranker_provider import (
    RERANKER_CONTRACT_VERSION,
    RerankerBatch,
    RerankerProvider,
    validate_reranker_batch,
)

_TOP_K_SEQUENCE: tuple[RerankerTopK, ...] = (5, 8)
_GROUP_ORDER = (
    "all-answerable",
    "real-cross-border",
    "synthetic-cross-border",
    "general-diagnostics",
)


@dataclass(frozen=True, slots=True)
class _ScoredCase:
    case: EvaluationCase
    user: CurrentUser
    request: RetrievalRequest
    hybrid: RetrievalResponse
    candidates: tuple[RerankerContextCandidateInput, ...]
    reranked: tuple[RerankerContextCandidateInput, ...]
    normalized_scores: tuple[float, ...]
    responses: Mapping[RerankerTopK, RerankedRetrievalResponse]
    comparisons: tuple[RerankerCaseComparison, ...]


class RunCachingRerankerProvider:
    """Cache one complete candidate-pool score batch for the current run only."""

    def __init__(self, delegate: RerankerProvider) -> None:
        _validate_pinned_bge_identity(delegate)
        self._delegate = delegate
        self._batches: dict[str, RerankerBatch] = {}
        self._score_requests = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._provider_score_calls = 0
        self._score_latencies_ms: list[float] = []
        self._effective_batch_sizes: list[int] = []

    @property
    def identity(self):  # type: ignore[no-untyped-def]
        return self._delegate.identity

    @property
    def score_latencies_ms(self) -> tuple[float, ...]:
        return tuple(self._score_latencies_ms)

    @property
    def effective_batch_sizes(self) -> tuple[int, ...]:
        return tuple(self._effective_batch_sizes)

    def score(self, query: str, passages: Sequence[str]) -> RerankerBatch:
        self._score_requests += 1
        key = _batch_cache_key(self._delegate, query=query, passages=passages)
        cached = self._batches.get(key)
        if cached is not None:
            self._cache_hits += 1
            return cached

        self._cache_misses += 1
        self._provider_score_calls += 1
        started = time.perf_counter()
        batch = self._delegate.score(query, passages)
        elapsed_ms = max(0.0, (time.perf_counter() - started) * 1000)
        validated = validate_reranker_batch(
            batch,
            query=query,
            passages=passages,
            expected_identity=self.identity,
        )
        self._score_latencies_ms.append(elapsed_ms)
        self._effective_batch_sizes.append(validated.effective_batch_size)
        self._batches[key] = validated
        return validated

    def cached_batch(self, query: str, passages: Sequence[str]) -> RerankerBatch:
        """Read a batch only after the production Reranker Service scored it."""

        key = _batch_cache_key(self._delegate, query=query, passages=passages)
        try:
            return self._batches[key]
        except KeyError:
            raise ValueError("candidate pool has not been scored in this run") from None

    def stats(self) -> RerankerContextCacheStats:
        return RerankerContextCacheStats(
            score_requests=self._score_requests,
            cache_hits=self._cache_hits,
            cache_misses=self._cache_misses,
            provider_score_calls=self._provider_score_calls,
            cache_entries=len(self._batches),
        )


def select_reranker_top_k(
    comparisons: Sequence[RerankerCaseComparison],
    *,
    answerable_case_ids: Sequence[str],
) -> RerankerTopK:
    """Choose more answerable hits; if coverage ties, keep the smaller TopK."""

    expected_ids = tuple(answerable_case_ids)
    if not expected_ids or len(expected_ids) != len(set(expected_ids)):
        raise ValueError("answerable denominator must contain unique case IDs")
    hit_counts: dict[RerankerTopK, int] = {}
    for top_k in _TOP_K_SEQUENCE:
        selected = [item for item in comparisons if item.top_k == top_k]
        observed_ids = tuple(item.case_id for item in selected)
        if len(selected) != len(expected_ids) or set(observed_ids) != set(expected_ids):
            raise ValueError("TopK comparison shrank the answerable denominator")
        if any(item.status != "completed" for item in selected):
            raise ValueError("TopK selection cannot use failed metrics")
        hit_counts[top_k] = sum(item.reranker_hit_at_k is True for item in selected)
    return max(_TOP_K_SEQUENCE, key=lambda value: (hit_counts[value], -value))


def run_m2_reranker_context_formal_evaluation(
    *,
    settings: Settings,
    runtime: DatabaseRuntime,
    snapshot: FrozenRagCorpusSnapshot,
    embedding_provider: EmbeddingProvider,
    reranker_provider: RerankerProvider,
    evidence_ids_by_chunk: Mapping[UUID, frozenset[str]],
    reranker_load_seconds: float,
    project_root: Path = PROJECT_ROOT,
) -> FormalRerankerContextEvaluationReport:
    """Run the fixed 34+6 matrix over the retained active Chunk generation."""

    started = time.perf_counter()
    process = psutil.Process()
    rss_start = process.memory_info().rss
    rss_peak = rss_start
    rss_sampler = _PeakRssSampler()
    rss_sampler.start()
    dataset_path = project_root / DEFAULT_DATASET_PATH.relative_to(PROJECT_ROOT)
    dataset_content = dataset_path.read_bytes()
    cases = _load_cases(dataset_path)
    cohort = freeze_reranker_context_cohort(
        line for line in dataset_content.decode("utf-8").splitlines() if line.strip()
    )
    users = _evaluation_users(
        runtime,
        tenant_id=snapshot.tenant_id,
        run_id=f"m2-2273-{snapshot.corpus_sha256[:16]}",
    )
    document_ids = {
        logical_id: document_id
        for document_id, logical_id in snapshot.logical_document_ids.items()
    }
    protected_inactive_indexes = _inactive_index_ids_by_logical_document(
        runtime=runtime,
        snapshot=snapshot,
    )
    cached_provider = RunCachingRerankerProvider(reranker_provider)
    answerable_work: list[_ScoredCase] = []

    for case in cases:
        if not case.should_answer:
            continue
        with _case_database_state(
            runtime,
            case=case,
            document_ids=document_ids,
        ):
            work = _retrieve_and_score_case(
                runtime=runtime,
                settings=settings,
                embedding_provider=embedding_provider,
                reranker_provider=cached_provider,
                case=case,
                user=users[case.trusted_user_fixture_id],
                logical_document_ids=snapshot.logical_document_ids,
                evidence_ids_by_chunk=evidence_ids_by_chunk,
                top_k_sequence=_TOP_K_SEQUENCE,
            )
        answerable_work.append(work)
        rss_peak = max(rss_peak, process.memory_info().rss)

    comparisons = [
        comparison for work in answerable_work for comparison in work.comparisons
    ]
    selected_top_k = select_reranker_top_k(
        comparisons,
        answerable_case_ids=cohort.answerable_case_ids,
    )
    experiment_points = build_bounded_reranker_context_plan(
        selected_top_k=selected_top_k
    )
    answerable_results = [
        _answerable_result(
            runtime=runtime,
            settings=settings,
            snapshot=snapshot,
            work=work,
            selected_top_k=selected_top_k,
            evidence_ids_by_chunk=evidence_ids_by_chunk,
        )
        for work in answerable_work
    ]
    rss_peak = max(rss_peak, process.memory_info().rss)

    safety_results: list[RerankerContextSafetyRunResult] = []
    safety_work: list[_ScoredCase] = []
    for case in cases:
        if case.should_answer:
            continue
        with _case_database_state(
            runtime,
            case=case,
            document_ids=document_ids,
        ):
            work = _retrieve_and_score_case(
                runtime=runtime,
                settings=settings,
                embedding_provider=embedding_provider,
                reranker_provider=cached_provider,
                case=case,
                user=users[case.trusted_user_fixture_id],
                logical_document_ids=snapshot.logical_document_ids,
                evidence_ids_by_chunk=evidence_ids_by_chunk,
                top_k_sequence=(selected_top_k,),
            )
            safety_work.append(work)
            safety_results.append(
                _safety_result(
                    runtime=runtime,
                    settings=settings,
                    snapshot=snapshot,
                    work=work,
                    selected_top_k=selected_top_k,
                    evidence_ids_by_chunk=evidence_ids_by_chunk,
                    protected_inactive_indexes=protected_inactive_indexes,
                )
            )
        rss_peak = max(rss_peak, process.memory_info().rss)

    reranker_aggregates = _reranker_aggregates(answerable_results, cases)
    context_aggregates = _context_aggregates(
        answerable_results,
        cases,
        selected_top_k=selected_top_k,
    )
    safety_gate_passed = all(
        item.trace.result.status == "completed"
        and item.trace.result.security_violation is not True
        for item in safety_results
    )
    embedding_identity = _shared_embedding_identity(
        [item.hybrid for item in answerable_work]
    )
    fts_identity = _shared_fts_identity([item.hybrid for item in answerable_work])
    input_sha256 = _formal_input_sha256(
        dataset_sha256=hashlib.sha256(dataset_content).hexdigest(),
        snapshot=snapshot,
        embedding_identity=embedding_identity,
        fts_identity=fts_identity,
        scored_cases=[*answerable_work, *safety_work],
        selected_top_k=selected_top_k,
    )
    latencies = cached_provider.score_latencies_ms
    batch_sizes = cached_provider.effective_batch_sizes
    if not latencies or not batch_sizes:
        raise RuntimeError("formal matrix did not score any candidate pool")
    rss_peak = max(rss_peak, rss_sampler.stop())
    measurements = FormalEvaluationMeasurements(
        total_elapsed_seconds=max(0.0, time.perf_counter() - started),
        reranker_load_seconds=reranker_load_seconds,
        scoring_latency_p50_ms=_percentile(latencies, 0.50),
        scoring_latency_p95_ms=_percentile(latencies, 0.95),
        scoring_latency_max_ms=max(latencies),
        effective_batch_size_min=min(batch_sizes),
        effective_batch_size_max=max(batch_sizes),
        rss_start_mib=rss_start / (1024 * 1024),
        rss_peak_mib=rss_peak / (1024 * 1024),
        rss_peak_delta_mib=(rss_peak - rss_start) / (1024 * 1024),
    )
    trace_hashes = [
        *[item.trace_sha256 for item in answerable_results],
        *[item.trace_sha256 for item in safety_results],
    ]
    real_selected = next(
        item
        for item in reranker_aggregates
        if item.group_id == "real-cross-border" and item.top_k == selected_top_k
    )
    quality_gate_passed = bool(
        safety_gate_passed
        and real_selected.status == "completed"
        and real_selected.reranker_hit_rate_at_k is not None
        and real_selected.reranker_hit_rate_at_k >= 0.9
        and all(item.status == "completed" for item in context_aggregates)
    )
    return FormalRerankerContextEvaluationReport(
        run_id=f"m2-2275-{input_sha256[:16]}",
        quality_gate_passed=quality_gate_passed,
        selected_top_k=selected_top_k,
        plan=RerankerContextEvaluationPlan(),
        experiment_points=experiment_points,
        dataset_version=cases[0].dataset_version,
        dataset_sha256=hashlib.sha256(dataset_content).hexdigest(),
        input_sha256=input_sha256,
        corpus=FrozenRagCorpusPublicIdentity(
            corpus_sha256=snapshot.corpus_sha256,
            index_sha256=snapshot.index_sha256,
            snapshot_sha256=snapshot.snapshot_sha256,
            source_count=cast(Literal[18], snapshot.source_count),
            document_count=cast(Literal[18], snapshot.document_count),
            chunk_set_count=cast(Literal[18], snapshot.chunk_set_count),
            index_set_count=snapshot.index_set_count,
            chunk_count=cast(Literal[779], snapshot.chunk_count),
        ),
        retrieval_embedding=embedding_identity,
        retrieval_fts=fts_identity,
        scorer=BgeRerankerFormalIdentity(),
        context_reader=PostgresContextReaderIdentity(
            builder_version=CONTEXT_BUILDER_VERSION
        ),
        cohort=cohort,
        answerable_results=answerable_results,
        reranker_aggregates=reranker_aggregates,
        context_aggregates=context_aggregates,
        safety_results=safety_results,
        safety_gate_passed=safety_gate_passed,
        safety_leak_count=sum(
            item.trace.result.security_violation is True for item in safety_results
        ),
        cache=cached_provider.stats(),
        measurements=measurements,
        bad_cases=_bad_cases(
            answerable_results=answerable_results,
            safety_results=safety_results,
            selected_top_k=selected_top_k,
        ),
        trace_set_sha256=build_trace_set_sha256(trace_hashes),
    )


def _retrieve_and_score_case(
    *,
    runtime: DatabaseRuntime,
    settings: Settings,
    embedding_provider: EmbeddingProvider,
    reranker_provider: RunCachingRerankerProvider,
    case: EvaluationCase,
    user: CurrentUser,
    logical_document_ids: Mapping[UUID, str],
    evidence_ids_by_chunk: Mapping[UUID, frozenset[str]],
    top_k_sequence: Sequence[RerankerTopK],
) -> _ScoredCase:
    measured = _measure_routes(
        runtime=runtime,
        settings=settings,
        provider=embedding_provider,
        user=user,
        case_id=case.case_id,
        question=case.question,
        depth=10,
    )
    hybrid, _latency = _fuse_routes(
        measured,
        user=user,
        question=case.question,
        depth=10,
        rrf_k=60,
        production_baseline=False,
    )
    if (
        measured.dense.candidate_failures
        or measured.lexical.candidate_failures
        or hybrid.candidate_failures
    ):
        raise RuntimeError("formal retrieval contains a candidate mapping failure")
    request = RetrievalRequest(query=case.question)
    responses = {
        top_k: RerankerRetrievalService(
            _FrozenHybridRoute(hybrid),
            reranker_provider,
            top_k=top_k,
        ).retrieve(user, request)
        for top_k in top_k_sequence
    }
    case_prefix = f"{case.case_id}-evidence-"
    case_evidence = {
        chunk_id: frozenset(
            evidence_id
            for evidence_id in evidence_ids
            if evidence_id.startswith(case_prefix)
        )
        for chunk_id, evidence_ids in evidence_ids_by_chunk.items()
    }
    if any(result.rrf_score is None for result in hybrid.results):
        raise RuntimeError("formal Hybrid candidate is missing its RRF score")
    candidates = tuple(
        RerankerContextCandidateInput(
            candidate_id=str(result.identity.chunk_id),
            logical_document_id=logical_document_ids[result.identity.document_id],
            body_text=result.body_text,
            body_text_sha256=hashlib.sha256(
                result.body_text.encode("utf-8")
            ).hexdigest(),
            rrf_score=float(cast(float, result.rrf_score)),
            evidence_ids=case_evidence.get(result.identity.chunk_id, frozenset()),
            version_id=str(result.identity.version_id),
            index_set_id=str(result.identity.index_set_id),
            source_locator=result.source_locator,
        )
        for result in hybrid.results
    )
    if hybrid.results:
        passages = tuple(item.body_text for item in hybrid.results)
        batch = reranker_provider.cached_batch(case.question, passages)
        ranked_indexes = sorted(
            range(len(hybrid.results)),
            key=lambda index: (
                -batch.scores[index].normalized_score,
                hybrid.results[index].final_rank,
                hybrid.results[index].identity.chunk_id,
            ),
        )
        reranked = tuple(candidates[index] for index in ranked_indexes)
        normalized_scores = tuple(item.normalized_score for item in batch.scores)
        expected_ids = [item.candidate_id for item in reranked]
        for top_k, response in responses.items():
            if [
                str(item.identity.chunk_id) for item in response.results
            ] != expected_ids[:top_k]:
                raise RuntimeError("formal Service order differs from the full pool")
    else:
        reranked = ()
        normalized_scores = ()
    expected_evidence = frozenset(
        f"{case.case_id}-evidence-{position:03d}"
        for position in range(1, len(case.expected_evidence_spans) + 1)
    )
    comparisons = tuple(
        evaluate_reranker_comparison(
            case_id=case.case_id,
            source_group=case.source_group,
            top_k=top_k,
            expected_evidence_ids=expected_evidence,
            rrf_candidates=[item.metric_candidate() for item in candidates],
            reranked_candidates=[item.metric_candidate() for item in reranked],
        )
        for top_k in top_k_sequence
        if case.should_answer
    )
    return _ScoredCase(
        case=case,
        user=user,
        request=request,
        hybrid=hybrid,
        candidates=candidates,
        reranked=reranked,
        normalized_scores=normalized_scores,
        responses=responses,
        comparisons=comparisons,
    )


def _answerable_result(
    *,
    runtime: DatabaseRuntime,
    settings: Settings,
    snapshot: FrozenRagCorpusSnapshot,
    work: _ScoredCase,
    selected_top_k: RerankerTopK,
    evidence_ids_by_chunk: Mapping[UUID, frozenset[str]],
) -> RerankerContextAnswerableRunResult:
    expected_evidence = frozenset(
        f"{work.case.case_id}-evidence-{position:03d}"
        for position in range(1, len(work.case.expected_evidence_spans) + 1)
    )
    selected_response = work.responses[selected_top_k]
    case_evidence = _case_evidence_map(
        work.case.case_id,
        evidence_ids_by_chunk,
    )
    context_results: list[ContextCaseQualityResult] = []
    for neighbor_window in (0, 1):
        for max_tokens in (2000, 3000, 4000):
            try:
                with runtime.session_factory() as session:
                    repository = RetrievalRepository(
                        session,
                        statement_timeout_ms=settings.database_statement_timeout_ms,
                    )
                    _built, segments = build_m2_database_probe_context(
                        current_user=work.user,
                        request=work.request,
                        reranked_response=selected_response,
                        context_reader=repository,
                        neighbor_window=cast(
                            ContextEvaluationNeighborWindow,
                            neighbor_window,
                        ),
                        max_tokens=cast(ContextEvaluationTokenBudget, max_tokens),
                        logical_document_ids=snapshot.logical_document_ids,
                        evidence_ids_by_chunk=case_evidence,
                    )
                context_results.append(
                    evaluate_context_quality(
                        case_id=work.case.case_id,
                        source_group=work.case.source_group,
                        reranker_top_k=selected_top_k,
                        context_neighbor_window=cast(
                            ContextEvaluationNeighborWindow,
                            neighbor_window,
                        ),
                        context_max_tokens=cast(
                            ContextEvaluationTokenBudget,
                            max_tokens,
                        ),
                        expected_evidence_ids=expected_evidence,
                        selected_anchor_candidate_ids=tuple(
                            str(item.identity.chunk_id)
                            for item in selected_response.results
                        ),
                        segments=segments,
                    )
                )
            except Exception:  # noqa: BLE001 - retain a safe non-numeric metric row.
                context_results.append(
                    ContextCaseQualityResult(
                        case_id=work.case.case_id,
                        source_group=work.case.source_group,
                        reranker_top_k=selected_top_k,
                        context_neighbor_window=cast(
                            ContextEvaluationNeighborWindow,
                            neighbor_window,
                        ),
                        context_max_tokens=cast(
                            ContextEvaluationTokenBudget,
                            max_tokens,
                        ),
                        expected_evidence_count=len(expected_evidence),
                        status="calculation_failed",
                        failure_category="calculation_error",
                        failure_summary="Deterministic Context calculation failed.",
                    )
                )
    trace = RerankerContextAnswerableTrace(
        case_id=work.case.case_id,
        query_sha256=hashlib.sha256(work.case.question.encode("utf-8")).hexdigest(),
        selected_top_k=selected_top_k,
        candidates=_candidate_trace(
            rrf_candidates=work.candidates,
            reranked_candidates=work.reranked,
            scores=work.normalized_scores,
        ),
        comparisons=list(work.comparisons),
        context_results=context_results,
    )
    return RerankerContextAnswerableRunResult(
        trace=trace,
        trace_sha256=public_trace_sha256(trace),
    )


def _safety_result(
    *,
    runtime: DatabaseRuntime,
    settings: Settings,
    snapshot: FrozenRagCorpusSnapshot,
    work: _ScoredCase,
    selected_top_k: RerankerTopK,
    evidence_ids_by_chunk: Mapping[UUID, frozenset[str]],
    protected_inactive_indexes: Mapping[str, frozenset[str]],
) -> RerankerContextSafetyRunResult:
    response = work.responses[selected_top_k]
    try:
        with runtime.session_factory() as session:
            repository = RetrievalRepository(
                session,
                statement_timeout_ms=settings.database_statement_timeout_ms,
            )
            _built, segments = build_m2_database_probe_context(
                current_user=work.user,
                request=work.request,
                reranked_response=response,
                context_reader=repository,
                neighbor_window=1,
                max_tokens=4000,
                logical_document_ids=snapshot.logical_document_ids,
                evidence_ids_by_chunk=_case_evidence_map(
                    work.case.case_id,
                    evidence_ids_by_chunk,
                ),
            )
        reason = work.case.expected_non_answer_reason
        if reason is None:
            raise RuntimeError("safety case is missing its frozen reason")
        protected_documents = frozenset(work.case.expected_document_ids)
        protected_index_sets: frozenset[str] = frozenset()
        if work.case.version_fixture_id == "version-fixture-old-inactive":
            protected_documents = frozenset()
            protected_index_sets = frozenset(
                index_set_id
                for logical_id in work.case.expected_document_ids
                for index_set_id in protected_inactive_indexes.get(
                    logical_id,
                    frozenset(),
                )
            )
        result = evaluate_reranker_context_safety(
            case_id=work.case.case_id,
            expected_non_answer_reason=reason,
            top_k=selected_top_k,
            rrf_candidates=[item.metric_candidate() for item in work.candidates],
            reranked_candidates=[item.metric_candidate() for item in work.reranked],
            context_segments=segments,
            protected_document_ids=protected_documents,
            protected_index_set_ids=protected_index_sets,
        )
    except Exception:  # noqa: BLE001 - retain a safe non-numeric safety row.
        reason = work.case.expected_non_answer_reason
        if reason is None:
            raise RuntimeError("safety case is missing its frozen reason") from None
        result = RerankerContextSafetyCaseResult(
            case_id=work.case.case_id,
            expected_non_answer_reason=reason,
            top_k=selected_top_k,
            status="calculation_failed",
            failure_category="calculation_error",
            failure_summary="Deterministic safety calculation failed.",
        )
    trace = RerankerContextSafetyTrace(
        case_id=work.case.case_id,
        query_sha256=hashlib.sha256(work.case.question.encode("utf-8")).hexdigest(),
        selected_top_k=selected_top_k,
        candidates=_candidate_trace(
            rrf_candidates=work.candidates,
            reranked_candidates=work.reranked,
            scores=work.normalized_scores,
        ),
        result=result,
    )
    return RerankerContextSafetyRunResult(
        trace=trace,
        trace_sha256=public_trace_sha256(trace),
    )


def _case_evidence_map(
    case_id: str,
    evidence_ids_by_chunk: Mapping[UUID, frozenset[str]],
) -> dict[UUID, frozenset[str]]:
    prefix = f"{case_id}-evidence-"
    return {
        chunk_id: frozenset(
            evidence_id
            for evidence_id in evidence_ids
            if evidence_id.startswith(prefix)
        )
        for chunk_id, evidence_ids in evidence_ids_by_chunk.items()
    }


def _group_case_ids(
    cases: Sequence[EvaluationCase],
) -> dict[str, tuple[str, ...]]:
    answerable = [case for case in cases if case.should_answer]
    return {
        "all-answerable": tuple(case.case_id for case in answerable),
        "real-cross-border": tuple(
            case.case_id
            for case in answerable
            if case_reporting_cohort(case) == "real_cross_border"
        ),
        "synthetic-cross-border": tuple(
            case.case_id
            for case in answerable
            if case_reporting_cohort(case) == "synthetic_cross_border"
        ),
        "general-diagnostics": tuple(
            case.case_id
            for case in answerable
            if case_reporting_cohort(case) == "general_diagnostics"
        ),
    }


def _reranker_aggregates(
    results: Sequence[RerankerContextAnswerableRunResult],
    cases: Sequence[EvaluationCase],
) -> list[RerankerGroupAggregateResult]:
    groups = _group_case_ids(cases)
    comparisons = [
        comparison for result in results for comparison in result.trace.comparisons
    ]
    return [
        aggregate_reranker_comparisons(
            [
                item
                for item in comparisons
                if item.top_k == top_k and item.case_id in groups[group_id]
            ],
            expected_case_ids=groups[group_id],
            group_id=group_id,
            top_k=top_k,
        )
        for top_k in _TOP_K_SEQUENCE
        for group_id in _GROUP_ORDER
    ]


def _context_aggregates(
    results: Sequence[RerankerContextAnswerableRunResult],
    cases: Sequence[EvaluationCase],
    *,
    selected_top_k: RerankerTopK,
) -> list[ContextGroupAggregateResult]:
    groups = _group_case_ids(cases)
    context_results = [
        context for result in results for context in result.trace.context_results
    ]
    return [
        aggregate_context_quality(
            [
                item
                for item in context_results
                if item.case_id in groups[group_id]
                and item.context_neighbor_window == neighbor_window
                and item.context_max_tokens == max_tokens
            ],
            expected_case_ids=groups[group_id],
            group_id=group_id,
            reranker_top_k=selected_top_k,
            context_neighbor_window=cast(
                ContextEvaluationNeighborWindow,
                neighbor_window,
            ),
            context_max_tokens=cast(ContextEvaluationTokenBudget, max_tokens),
        )
        for neighbor_window in (0, 1)
        for max_tokens in (2000, 3000, 4000)
        for group_id in _GROUP_ORDER
    ]


def _shared_embedding_identity(
    responses: Sequence[RetrievalResponse],
) -> RetrievalEmbeddingIdentity:
    identities = {
        (
            None
            if item.embedding_identity is None
            else item.embedding_identity.model_dump_json()
        ): item.embedding_identity
        for item in responses
    }
    if len(identities) != 1 or None in identities:
        raise RuntimeError(
            "formal Hybrid responses do not share one Embedding identity"
        )
    identity = next(iter(identities.values()))
    assert identity is not None
    return identity


def _shared_fts_identity(
    responses: Sequence[RetrievalResponse],
) -> RetrievalFtsIdentity:
    identities = {
        (
            None if item.fts_identity is None else item.fts_identity.model_dump_json()
        ): item.fts_identity
        for item in responses
    }
    if len(identities) != 1 or None in identities:
        raise RuntimeError("formal Hybrid responses do not share one FTS identity")
    identity = next(iter(identities.values()))
    assert identity is not None
    return identity


def _formal_input_sha256(
    *,
    dataset_sha256: str,
    snapshot: FrozenRagCorpusSnapshot,
    embedding_identity: RetrievalEmbeddingIdentity,
    fts_identity: RetrievalFtsIdentity,
    scored_cases: Sequence[_ScoredCase],
    selected_top_k: RerankerTopK,
) -> str:
    payload = {
        "dataset_sha256": dataset_sha256,
        "corpus_sha256": snapshot.corpus_sha256,
        "index_sha256": snapshot.index_sha256,
        "snapshot_sha256": snapshot.snapshot_sha256,
        "embedding": embedding_identity.model_dump(mode="json"),
        "fts": fts_identity.model_dump(mode="json"),
        "reranker": BgeRerankerFormalIdentity().model_dump(mode="json"),
        "context": PostgresContextReaderIdentity().model_dump(mode="json"),
        "selected_top_k": selected_top_k,
        "candidate_snapshots": [
            {
                "case_id": work.case.case_id,
                "query_sha256": hashlib.sha256(
                    work.case.question.encode("utf-8")
                ).hexdigest(),
                "candidates": [
                    {
                        "candidate_id": item.candidate_id,
                        "body_text_sha256": item.body_text_sha256,
                        "rrf_score": item.rrf_score,
                    }
                    for item in work.candidates
                ],
            }
            for work in scored_cases
        ],
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _inactive_index_ids_by_logical_document(
    *,
    runtime: DatabaseRuntime,
    snapshot: FrozenRagCorpusSnapshot,
) -> dict[str, frozenset[str]]:
    active_ids = set(snapshot.index_set_ids)
    with runtime.session_factory() as session:
        rows = session.execute(
            select(DocumentIndexSet.document_id, DocumentIndexSet.id).where(
                DocumentIndexSet.tenant_id == snapshot.tenant_id,
                DocumentIndexSet.document_id.in_(snapshot.document_ids),
            )
        ).all()
    output: dict[str, set[str]] = {}
    for document_id, index_set_id in rows:
        if index_set_id not in active_ids:
            logical_id = snapshot.logical_document_ids[document_id]
            output.setdefault(logical_id, set()).add(str(index_set_id))
    return {key: frozenset(value) for key, value in output.items()}


def _bad_cases(
    *,
    answerable_results: Sequence[RerankerContextAnswerableRunResult],
    safety_results: Sequence[RerankerContextSafetyRunResult],
    selected_top_k: RerankerTopK,
) -> list[RerankerContextBadCase]:
    output: list[RerankerContextBadCase] = []
    for item in answerable_results:
        comparison = next(
            value for value in item.trace.comparisons if value.top_k == selected_top_k
        )
        if comparison.rank_change == "candidate_missing":
            output.append(
                RerankerContextBadCase(
                    case_id=item.trace.case_id,
                    stage="upstream_candidate_missing",
                    selected_top_k=selected_top_k,
                    summary="Golden Evidence was absent before Reranker scoring.",
                )
            )
        elif comparison.reranker_hit_at_k is False:
            output.append(
                RerankerContextBadCase(
                    case_id=item.trace.case_id,
                    stage="reranker_topk_miss",
                    selected_top_k=selected_top_k,
                    summary="Golden Evidence remained outside the selected Reranker TopK.",
                )
            )
        max_context = next(
            value
            for value in item.trace.context_results
            if value.context_neighbor_window == 1 and value.context_max_tokens == 4000
        )
        if max_context.status != "completed":
            output.append(
                RerankerContextBadCase(
                    case_id=item.trace.case_id,
                    stage="metric_calculation_failed",
                    selected_top_k=selected_top_k,
                    summary="At least one deterministic Context metric failed.",
                )
            )
        elif max_context.golden_evidence_coverage_rate == 0:
            output.append(
                RerankerContextBadCase(
                    case_id=item.trace.case_id,
                    stage="context_evidence_miss",
                    selected_top_k=selected_top_k,
                    summary="The largest Context point contained no Golden Evidence.",
                )
            )
    for safety_item in safety_results:
        if safety_item.trace.result.status != "completed":
            output.append(
                RerankerContextBadCase(
                    case_id=safety_item.trace.case_id,
                    stage="metric_calculation_failed",
                    selected_top_k=selected_top_k,
                    summary="The deterministic safety metric failed.",
                )
            )
        elif safety_item.trace.result.security_violation is True:
            output.append(
                RerankerContextBadCase(
                    case_id=safety_item.trace.case_id,
                    stage="safety_violation",
                    selected_top_k=selected_top_k,
                    summary="A protected source appeared in the evaluated path.",
                )
            )
    return output


def _percentile(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * quantile) - 1)]


def _validate_pinned_bge_identity(provider: RerankerProvider) -> None:
    identity = provider.identity
    if (
        identity.contract_version != RERANKER_CONTRACT_VERSION
        or identity.provider != "bge-reranker-local"
        or identity.model_id != BGE_RERANKER_MODEL_ID
        or identity.revision != BGE_RERANKER_REVISION
        or identity.max_length != 8192
        or identity.precision != "float32"
        or identity.score_transform != "sigmoid"
    ):
        raise TypeError(
            "formal evaluation requires the exact pinned local BGE identity"
        )


def _batch_cache_key(
    provider: RerankerProvider,
    *,
    query: str,
    passages: Sequence[str],
) -> str:
    payload = {
        "identity": asdict(provider.identity),
        "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
        "ordered_passage_sha256": [
            hashlib.sha256(item.encode("utf-8")).hexdigest() for item in passages
        ],
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
