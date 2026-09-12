"""Bounded orchestration for the M2-22.7 Reranker/Context evaluation."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast
from uuid import UUID

from app.evals.reranker_context_metrics import (
    ContextMetricSegment,
    EvidenceRankedCandidate,
    aggregate_context_quality,
    aggregate_reranker_comparisons,
    build_bounded_reranker_context_plan,
    evaluate_context_quality,
    evaluate_reranker_comparison,
    evaluate_reranker_context_safety,
)
from app.evals.reranker_context_report import (
    BgeRerankerProbeIdentity,
    FakeContextReaderIdentity,
    FakeRerankerIdentity,
    PublicRerankerCandidateTrace,
    RerankerContextAnswerableRunResult,
    RerankerContextAnswerableTrace,
    RerankerContextCacheStats,
    RerankerContextEvaluationReport,
    RerankerContextSafetyRunResult,
    RerankerContextSafetyTrace,
    build_trace_set_sha256,
    public_trace_sha256,
)
from app.schemas.auth import CurrentUser
from app.schemas.evaluation import (
    ContextEvaluationNeighborWindow,
    ContextEvaluationTokenBudget,
    EvaluationCase,
    EvaluationSourceGroup,
    ExpectedEvidenceSpan,
    ExpectedNonAnswerReason,
    RerankerContextEvaluationCohort,
    RerankerContextEvaluationPlan,
    RerankerContextExperimentPoint,
    RerankerContextSafetyCase,
    RerankerTopK,
)
from app.schemas.retrieval import (
    CsvRetrievalSourceLocator,
    DocxRetrievalSourceLocator,
    PdfRetrievalSourceLocator,
    RerankedRetrievalResponse,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalSourceLocator,
    XlsxRetrievalSourceLocator,
)
from app.services.documents.chunking.token_counting import UnicodeMixedTokenCounter
from app.services.retrieval.context import (
    BuiltContext,
    ContextBuilderService,
    ContextWindowReader,
)
from app.services.retrieval.reranker import (
    HybridRetrievalRoute,
    RerankerRetrievalService,
)
from app.services.retrieval.reranker_provider import (
    FakeRerankerProvider,
    RerankerProvider,
)

_TOP_K_SEQUENCE: tuple[RerankerTopK, ...] = (5, 8)


@dataclass(frozen=True, slots=True)
class RerankerContextCandidateInput:
    """Private runner input; body text is replaced by its hash in the report."""

    candidate_id: str
    logical_document_id: str
    body_text: str
    body_text_sha256: str
    rrf_score: float
    evidence_ids: frozenset[str] = frozenset()
    version_id: str | None = None
    index_set_id: str | None = None
    source_locator: RetrievalSourceLocator | None = None

    def metric_candidate(self) -> EvidenceRankedCandidate:
        return EvidenceRankedCandidate(
            candidate_id=self.candidate_id,
            evidence_ids=self.evidence_ids,
            logical_document_id=self.logical_document_id,
            version_id=self.version_id,
            index_set_id=self.index_set_id,
        )


@dataclass(frozen=True, slots=True)
class RerankerContextCaseInput:
    """One private question and its frozen full RRF candidate snapshot."""

    case_id: str
    source_group: EvaluationSourceGroup
    question: str
    should_answer: bool
    expected_evidence_ids: frozenset[str]
    expected_non_answer_reason: ExpectedNonAnswerReason | None
    candidates: tuple[RerankerContextCandidateInput, ...]
    protected_document_ids: frozenset[str] = frozenset()
    protected_version_ids: frozenset[str] = frozenset()
    protected_index_set_ids: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class DatabaseRerankerContextProbeResult:
    """Private real-database probe result; it is never serialized as a report."""

    hybrid_response: RetrievalResponse
    reranked_response: RerankedRetrievalResponse
    built_context: BuiltContext
    hybrid_candidate_ids: tuple[UUID, ...]
    reranked_candidate_ids: tuple[UUID, ...]
    context_metric_segments: tuple[ContextMetricSegment, ...]


class RerankerScorer(Protocol):
    """Minimal scoring seam shared by fake runs and the bounded real probe."""

    @property
    def identity(self) -> FakeRerankerIdentity | BgeRerankerProbeIdentity: ...

    def score(self, query: str, documents: Sequence[str]) -> Sequence[float]: ...


class ContextReader(Protocol):
    """The minimal in-memory Context seam used before repository integration."""

    @property
    def identity(self) -> FakeContextReaderIdentity: ...

    def build_context(
        self,
        *,
        case: RerankerContextCaseInput,
        anchors: Sequence[RerankerContextCandidateInput],
        neighbor_window: ContextEvaluationNeighborWindow,
        max_tokens: ContextEvaluationTokenBudget,
    ) -> Sequence[ContextMetricSegment]: ...


class DeterministicFakeReranker:
    """Stable hash scorer used only to verify orchestration and cache behavior."""

    def __init__(self, *, identity: FakeRerankerIdentity | None = None) -> None:
        self._identity = identity or FakeRerankerIdentity()
        self.call_count = 0

    @property
    def identity(self) -> FakeRerankerIdentity:
        return self._identity

    def score(self, query: str, documents: Sequence[str]) -> tuple[float, ...]:
        self.call_count += 1
        return tuple(
            int.from_bytes(
                hashlib.sha256(f"{query}\0{document}".encode()).digest()[:8],
                "big",
            )
            / float(2**64 - 1)
            for document in documents
        )


class InMemoryFakeContextReader:
    """Build deterministic anchor-only Context without a Repository or Storage."""

    def __init__(self) -> None:
        self._identity = FakeContextReaderIdentity()
        self._token_counter = UnicodeMixedTokenCounter()
        self.call_count = 0

    @property
    def identity(self) -> FakeContextReaderIdentity:
        return self._identity

    def build_context(
        self,
        *,
        case: RerankerContextCaseInput,
        anchors: Sequence[RerankerContextCandidateInput],
        neighbor_window: ContextEvaluationNeighborWindow,
        max_tokens: ContextEvaluationTokenBudget,
    ) -> tuple[ContextMetricSegment, ...]:
        del case, neighbor_window
        self.call_count += 1
        segments: list[ContextMetricSegment] = []
        used_tokens = 0
        for anchor in anchors:
            token_count = self._token_counter.count(anchor.body_text)
            if token_count <= 0 or used_tokens + token_count > max_tokens:
                continue
            segments.append(
                ContextMetricSegment(
                    segment_id=anchor.candidate_id,
                    role="anchor",
                    anchor_candidate_id=None,
                    evidence_ids=anchor.evidence_ids,
                    token_count=token_count,
                    logical_document_id=anchor.logical_document_id,
                    version_id=anchor.version_id,
                    index_set_id=anchor.index_set_id,
                )
            )
            used_tokens += token_count
        return tuple(segments)


class _FrozenHybridRoute:
    """Replay one already-authorized Hybrid snapshot exactly once to the Service."""

    def __init__(self, response: RetrievalResponse) -> None:
        self._response = response

    def retrieve(
        self,
        current_user: CurrentUser,
        request: RetrievalRequest,
    ) -> RetrievalResponse:
        del current_user, request
        return self._response


def rerank_m2_database_probe_candidates(
    *,
    current_user: CurrentUser,
    request: RetrievalRequest,
    hybrid_response: RetrievalResponse,
    reranker_provider: RerankerProvider,
    top_k: RerankerTopK,
) -> RerankedRetrievalResponse:
    """Apply the production Reranker Service to one frozen depth-10 Hybrid pool."""

    _validate_m2_database_probe_inputs(
        current_user=current_user,
        request=request,
        hybrid_response=hybrid_response,
        reranker_provider=reranker_provider,
        top_k=top_k,
    )
    reranked = RerankerRetrievalService(
        _FrozenHybridRoute(hybrid_response),
        reranker_provider,
        top_k=top_k,
    ).retrieve(current_user, request)
    hybrid_ids = tuple(item.identity.chunk_id for item in hybrid_response.results)
    reranked_ids = tuple(item.identity.chunk_id for item in reranked.results)
    if (
        reranked.input_candidate_count != len(hybrid_ids)
        or len(reranked_ids) != len(set(reranked_ids))
        or not set(reranked_ids) <= set(hybrid_ids)
    ):
        raise ValueError("Reranker expanded or corrupted the frozen Hybrid pool")
    return reranked


def build_m2_database_probe_context(
    *,
    current_user: CurrentUser,
    request: RetrievalRequest,
    reranked_response: RerankedRetrievalResponse,
    context_reader: ContextWindowReader,
    neighbor_window: ContextEvaluationNeighborWindow,
    max_tokens: ContextEvaluationTokenBudget,
    logical_document_ids: Mapping[UUID, str],
    evidence_ids_by_chunk: Mapping[UUID, frozenset[str]],
) -> tuple[BuiltContext, tuple[ContextMetricSegment, ...]]:
    """Build Context from a fresh authorized database snapshot and map metrics."""

    if not isinstance(current_user, CurrentUser):
        raise TypeError("database Context probe requires a trusted CurrentUser")
    if not isinstance(request, RetrievalRequest):
        raise TypeError("database Context probe requires a RetrievalRequest")
    if not isinstance(reranked_response, RerankedRetrievalResponse):
        raise TypeError("database Context probe requires a Reranked response")
    if reranked_response.top_k not in _TOP_K_SEQUENCE:
        raise ValueError("database Context probe requires Reranker Top5 or Top8")
    if neighbor_window not in (0, 1):
        raise ValueError("database Context probe neighbor window must be 0 or 1")
    if max_tokens not in (2000, 3000, 4000):
        raise ValueError("database Context probe token budget is outside the plan")

    built = ContextBuilderService(
        context_reader,
        max_tokens=max_tokens,
        max_segments=12,
        neighbor_window=neighbor_window,
    ).build(current_user, request, reranked_response)
    reranked_ids = {str(item.identity.chunk_id) for item in reranked_response.results}
    metric_segments = tuple(
        ContextMetricSegment(
            segment_id=str(segment.identity.chunk_id),
            role=segment.role,
            anchor_candidate_id=(
                str(segment.neighbor_of_chunk_id)
                if segment.neighbor_of_chunk_id is not None
                else None
            ),
            evidence_ids=evidence_ids_by_chunk.get(
                segment.identity.chunk_id,
                frozenset(),
            ),
            token_count=segment.token_count,
            logical_document_id=logical_document_ids.get(
                segment.identity.document_id,
                str(segment.identity.document_id),
            ),
            version_id=str(segment.identity.version_id),
            index_set_id=str(segment.identity.index_set_id),
        )
        for segment in built.bundle.segments
    )
    for segment in metric_segments:
        if segment.role == "anchor" and segment.segment_id not in reranked_ids:
            raise ValueError("database Context introduced an unranked anchor")
        if segment.role != "anchor" and segment.anchor_candidate_id not in reranked_ids:
            raise ValueError("database Context neighbor lost its Reranker anchor")
    return built, metric_segments


def run_m2_reranker_context_database_probe(
    *,
    current_user: CurrentUser,
    request: RetrievalRequest,
    hybrid_route: HybridRetrievalRoute,
    context_reader: ContextWindowReader,
    reranker_provider: RerankerProvider,
    top_k: RerankerTopK,
    neighbor_window: ContextEvaluationNeighborWindow,
    max_tokens: ContextEvaluationTokenBudget,
    logical_document_ids: Mapping[UUID, str],
    evidence_ids_by_chunk: Mapping[UUID, frozenset[str]],
) -> DatabaseRerankerContextProbeResult:
    """Run one read-only real retrieval-to-Context probe over persisted Chunks."""

    hybrid_response = hybrid_route.retrieve(current_user, request)
    reranked_response = rerank_m2_database_probe_candidates(
        current_user=current_user,
        request=request,
        hybrid_response=hybrid_response,
        reranker_provider=reranker_provider,
        top_k=top_k,
    )
    built_context, metric_segments = build_m2_database_probe_context(
        current_user=current_user,
        request=request,
        reranked_response=reranked_response,
        context_reader=context_reader,
        neighbor_window=neighbor_window,
        max_tokens=max_tokens,
        logical_document_ids=logical_document_ids,
        evidence_ids_by_chunk=evidence_ids_by_chunk,
    )
    return DatabaseRerankerContextProbeResult(
        hybrid_response=hybrid_response,
        reranked_response=reranked_response,
        built_context=built_context,
        hybrid_candidate_ids=tuple(
            item.identity.chunk_id for item in hybrid_response.results
        ),
        reranked_candidate_ids=tuple(
            item.identity.chunk_id for item in reranked_response.results
        ),
        context_metric_segments=metric_segments,
    )


def _validate_m2_database_probe_inputs(
    *,
    current_user: CurrentUser,
    request: RetrievalRequest,
    hybrid_response: RetrievalResponse,
    reranker_provider: RerankerProvider,
    top_k: RerankerTopK,
) -> None:
    if not isinstance(current_user, CurrentUser):
        raise TypeError("database Reranker probe requires a trusted CurrentUser")
    if not isinstance(request, RetrievalRequest):
        raise TypeError("database Reranker probe requires a RetrievalRequest")
    if not isinstance(hybrid_response, RetrievalResponse):
        raise TypeError("database Reranker probe requires a Hybrid response")
    if reranker_provider.identity != FakeRerankerProvider().identity:
        raise TypeError("M2-22.7.3 accepts only the deterministic Fake Reranker")
    plan = RerankerContextEvaluationPlan()
    if top_k not in plan.reranker_top_k_sequence:
        raise ValueError("database Reranker probe requires Top5 or Top8")
    if (
        hybrid_response.mode != "hybrid"
        or hybrid_response.rrf_k != plan.rrf_k
        or hybrid_response.embedding_identity is None
        or hybrid_response.fts_identity is None
        or len(hybrid_response.results) > plan.hybrid_candidate_limit
    ):
        raise ValueError("Hybrid response is outside the frozen M2-22.7 plan")
    for result in hybrid_response.results:
        route_scores = (result.scores.dense, result.scores.lexical)
        if all(score is None for score in route_scores) or any(
            score is not None and score.rank > plan.candidate_depth
            for score in route_scores
        ):
            raise ValueError("Hybrid candidate exceeds the two depth-10 routes")


class RunScoringCache:
    """One-run cache bound to query, ordered bodies, and complete scorer identity."""

    def __init__(self) -> None:
        self._values: dict[str, tuple[float, ...]] = {}
        self._score_requests = 0
        self._cache_hits = 0
        self._cache_misses = 0
        self._provider_score_calls = 0

    def get_or_score(
        self,
        *,
        query: str,
        candidates: Sequence[RerankerContextCandidateInput],
        scorer: RerankerScorer,
    ) -> tuple[float, ...]:
        _validate_candidate_snapshot(candidates)
        if not isinstance(query, str) or not query.strip():
            raise ValueError("Reranker query must be a non-empty string")
        self._score_requests += 1
        key = _score_cache_key(query=query, candidates=candidates, scorer=scorer)
        cached = self._values.get(key)
        if cached is not None:
            self._cache_hits += 1
            return cached

        self._cache_misses += 1
        self._provider_score_calls += 1
        raw_scores = scorer.score(query, [item.body_text for item in candidates])
        scores = tuple(float(item) for item in raw_scores)
        if len(scores) != len(candidates):
            raise ValueError("Reranker score count must match the candidate snapshot")
        if any(not math.isfinite(item) for item in scores):
            raise ValueError("Reranker scores must be finite")
        self._values[key] = scores
        return scores

    def stats(self) -> RerankerContextCacheStats:
        return RerankerContextCacheStats(
            score_requests=self._score_requests,
            cache_hits=self._cache_hits,
            cache_misses=self._cache_misses,
            provider_score_calls=self._provider_score_calls,
            cache_entries=len(self._values),
        )


def build_fake_case_inputs_from_dataset(
    path: Path,
) -> tuple[tuple[RerankerContextCaseInput, ...], str, str]:
    """Build deterministic fake candidates from the frozen 40-row JSONL dataset."""

    content = path.read_bytes()
    cases = [
        EvaluationCase.model_validate_json(line)
        for line in content.decode("utf-8").splitlines()
        if line.strip()
    ]
    if not cases:
        raise ValueError("fake Reranker/Context dataset cannot be empty")
    dataset_versions = {item.dataset_version for item in cases}
    if len(dataset_versions) != 1:
        raise ValueError("fake Reranker/Context cases must share one dataset version")
    inputs = tuple(_fake_case_input(item) for item in cases)
    _build_cohort(inputs, dataset_version=next(iter(dataset_versions)))
    return inputs, next(iter(dataset_versions)), hashlib.sha256(content).hexdigest()


def run_m2_reranker_context_fake_evaluation(
    *,
    cases: Sequence[RerankerContextCaseInput],
    dataset_version: str,
    dataset_sha256: str,
    selected_top_k: RerankerTopK,
    scorer: RerankerScorer,
    context_reader: ContextReader,
) -> RerankerContextEvaluationReport:
    """Run the exact eight-point fake plan without database or model access."""

    if not isinstance(scorer.identity, FakeRerankerIdentity):
        raise TypeError("M2-22.7.2 accepts only the explicit fake scorer identity")
    if not isinstance(context_reader.identity, FakeContextReaderIdentity):
        raise TypeError("M2-22.7.2 accepts only the in-memory Context reader identity")
    plan = RerankerContextEvaluationPlan()
    experiment_points = build_bounded_reranker_context_plan(
        selected_top_k=selected_top_k
    )
    cohort = _build_cohort(cases, dataset_version=dataset_version)
    _validate_case_inputs(cases)
    input_sha256 = _fake_input_sha256(
        cases=cases,
        dataset_version=dataset_version,
        dataset_sha256=dataset_sha256,
        selected_top_k=selected_top_k,
        scorer_identity=scorer.identity,
        context_identity=context_reader.identity,
    )
    cache = RunScoringCache()
    answerable_results: list[RerankerContextAnswerableRunResult] = []
    safety_results: list[RerankerContextSafetyRunResult] = []

    for case in cases:
        if case.should_answer:
            answerable_results.append(
                _run_answerable_case(
                    case=case,
                    selected_top_k=selected_top_k,
                    experiment_points=experiment_points,
                    scorer=scorer,
                    context_reader=context_reader,
                    cache=cache,
                )
            )
        else:
            safety_results.append(
                _run_safety_case(
                    case=case,
                    selected_top_k=selected_top_k,
                    scorer=scorer,
                    context_reader=context_reader,
                    cache=cache,
                )
            )

    expected_answerable_ids = cohort.answerable_case_ids
    reranker_aggregates = [
        aggregate_reranker_comparisons(
            [item.trace.comparisons[index] for item in answerable_results],
            expected_case_ids=expected_answerable_ids,
            group_id="all-answerable",
            top_k=top_k,
        )
        for index, top_k in enumerate(_TOP_K_SEQUENCE)
    ]
    context_aggregates = [
        aggregate_context_quality(
            [item.trace.context_results[index] for item in answerable_results],
            expected_case_ids=expected_answerable_ids,
            group_id="all-answerable",
            reranker_top_k=selected_top_k,
            context_neighbor_window=cast(
                ContextEvaluationNeighborWindow,
                point.context_neighbor_window,
            ),
            context_max_tokens=cast(
                ContextEvaluationTokenBudget,
                point.context_max_tokens,
            ),
        )
        for index, point in enumerate(experiment_points[2:])
    ]
    trace_hashes = [
        *[item.trace_sha256 for item in answerable_results],
        *[item.trace_sha256 for item in safety_results],
    ]
    return RerankerContextEvaluationReport(
        run_id=f"m2-2272-{input_sha256[:16]}",
        selected_top_k=selected_top_k,
        plan=plan,
        experiment_points=experiment_points,
        dataset_version=dataset_version,
        dataset_sha256=dataset_sha256,
        input_sha256=input_sha256,
        scorer=scorer.identity,
        context_reader=context_reader.identity,
        cohort=cohort,
        answerable_results=answerable_results,
        reranker_aggregates=reranker_aggregates,
        context_aggregates=context_aggregates,
        safety_results=safety_results,
        safety_gate_passed=all(
            item.trace.result.security_violation is not True for item in safety_results
        ),
        cache=cache.stats(),
        trace_set_sha256=build_trace_set_sha256(trace_hashes),
    )


def _run_answerable_case(
    *,
    case: RerankerContextCaseInput,
    selected_top_k: RerankerTopK,
    experiment_points: Sequence[RerankerContextExperimentPoint],
    scorer: RerankerScorer,
    context_reader: ContextReader,
    cache: RunScoringCache,
) -> RerankerContextAnswerableRunResult:
    comparisons = []
    context_results = []
    final_scores: tuple[float, ...] | None = None
    final_order: tuple[RerankerContextCandidateInput, ...] | None = None
    for position, point in enumerate(experiment_points):
        reranker_top_k = point.reranker_top_k
        scores = cache.get_or_score(
            query=case.question,
            candidates=case.candidates,
            scorer=scorer,
        )
        reranked = _reranked_candidates(case.candidates, scores)
        final_scores = scores
        final_order = reranked
        if position < 2:
            comparisons.append(
                evaluate_reranker_comparison(
                    case_id=case.case_id,
                    source_group=case.source_group,
                    top_k=reranker_top_k,
                    expected_evidence_ids=case.expected_evidence_ids,
                    rrf_candidates=[
                        item.metric_candidate() for item in case.candidates
                    ],
                    reranked_candidates=[item.metric_candidate() for item in reranked],
                )
            )
            continue
        neighbor_window = cast(
            ContextEvaluationNeighborWindow,
            point.context_neighbor_window,
        )
        max_tokens = cast(
            ContextEvaluationTokenBudget,
            point.context_max_tokens,
        )
        anchors = reranked[:selected_top_k]
        segments = context_reader.build_context(
            case=case,
            anchors=anchors,
            neighbor_window=neighbor_window,
            max_tokens=max_tokens,
        )
        context_results.append(
            evaluate_context_quality(
                case_id=case.case_id,
                source_group=case.source_group,
                reranker_top_k=selected_top_k,
                context_neighbor_window=neighbor_window,
                context_max_tokens=max_tokens,
                expected_evidence_ids=case.expected_evidence_ids,
                selected_anchor_candidate_ids=tuple(
                    item.candidate_id for item in anchors
                ),
                segments=segments,
            )
        )

    assert final_scores is not None
    assert final_order is not None
    trace = RerankerContextAnswerableTrace(
        case_id=case.case_id,
        query_sha256=_sha256_text(case.question),
        selected_top_k=selected_top_k,
        candidates=_candidate_trace(
            rrf_candidates=case.candidates,
            reranked_candidates=final_order,
            scores=final_scores,
        ),
        comparisons=comparisons,
        context_results=context_results,
    )
    return RerankerContextAnswerableRunResult(
        trace=trace,
        trace_sha256=public_trace_sha256(trace),
    )


def _run_safety_case(
    *,
    case: RerankerContextCaseInput,
    selected_top_k: RerankerTopK,
    scorer: RerankerScorer,
    context_reader: ContextReader,
    cache: RunScoringCache,
) -> RerankerContextSafetyRunResult:
    scores = cache.get_or_score(
        query=case.question,
        candidates=case.candidates,
        scorer=scorer,
    )
    reranked = _reranked_candidates(case.candidates, scores)
    anchors = reranked[:selected_top_k]
    segments = context_reader.build_context(
        case=case,
        anchors=anchors,
        neighbor_window=1,
        max_tokens=4000,
    )
    assert case.expected_non_answer_reason is not None
    result = evaluate_reranker_context_safety(
        case_id=case.case_id,
        expected_non_answer_reason=case.expected_non_answer_reason,
        top_k=selected_top_k,
        rrf_candidates=[item.metric_candidate() for item in case.candidates],
        reranked_candidates=[item.metric_candidate() for item in reranked],
        context_segments=segments,
        protected_document_ids=case.protected_document_ids,
        protected_version_ids=case.protected_version_ids,
        protected_index_set_ids=case.protected_index_set_ids,
    )
    trace = RerankerContextSafetyTrace(
        case_id=case.case_id,
        query_sha256=_sha256_text(case.question),
        selected_top_k=selected_top_k,
        candidates=_candidate_trace(
            rrf_candidates=case.candidates,
            reranked_candidates=reranked,
            scores=scores,
        ),
        result=result,
    )
    return RerankerContextSafetyRunResult(
        trace=trace,
        trace_sha256=public_trace_sha256(trace),
    )


def _candidate_trace(
    *,
    rrf_candidates: Sequence[RerankerContextCandidateInput],
    reranked_candidates: Sequence[RerankerContextCandidateInput],
    scores: Sequence[float],
) -> list[PublicRerankerCandidateTrace]:
    score_by_id = {
        candidate.candidate_id: score
        for candidate, score in zip(rrf_candidates, scores, strict=True)
    }
    reranker_rank_by_id = {
        candidate.candidate_id: rank
        for rank, candidate in enumerate(reranked_candidates, start=1)
    }
    return [
        PublicRerankerCandidateTrace(
            candidate_id=candidate.candidate_id,
            logical_document_id=candidate.logical_document_id,
            version_id=candidate.version_id,
            index_set_id=candidate.index_set_id,
            rrf_rank=rank,
            reranker_rank=reranker_rank_by_id[candidate.candidate_id],
            rrf_score=candidate.rrf_score,
            reranker_score=score_by_id[candidate.candidate_id],
            body_text_sha256=candidate.body_text_sha256,
            source_locator=candidate.source_locator,
            matched_evidence_ids=sorted(candidate.evidence_ids),
        )
        for rank, candidate in enumerate(rrf_candidates, start=1)
    ]


def _reranked_candidates(
    candidates: Sequence[RerankerContextCandidateInput],
    scores: Sequence[float],
) -> tuple[RerankerContextCandidateInput, ...]:
    ranked_indexes = sorted(
        range(len(candidates)),
        key=lambda index: (-scores[index], index),
    )
    return tuple(candidates[index] for index in ranked_indexes)


def _build_cohort(
    cases: Sequence[RerankerContextCaseInput],
    *,
    dataset_version: str,
) -> RerankerContextEvaluationCohort:
    return RerankerContextEvaluationCohort(
        dataset_version=dataset_version,
        answerable_case_ids=[item.case_id for item in cases if item.should_answer],
        safety_cases=[
            RerankerContextSafetyCase(
                case_id=item.case_id,
                expected_non_answer_reason=cast(
                    ExpectedNonAnswerReason,
                    item.expected_non_answer_reason,
                ),
            )
            for item in cases
            if not item.should_answer
        ],
    )


def _validate_case_inputs(cases: Sequence[RerankerContextCaseInput]) -> None:
    case_ids = [item.case_id for item in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("fake runner case IDs must be unique")
    for case in cases:
        if not case.question.strip():
            raise ValueError("fake runner question must be non-empty")
        if case.should_answer:
            if (
                not case.expected_evidence_ids
                or case.expected_non_answer_reason is not None
            ):
                raise ValueError("answerable fake case requires Golden Evidence only")
            if any(
                not candidate.evidence_ids <= case.expected_evidence_ids
                for candidate in case.candidates
            ):
                raise ValueError(
                    "candidate Evidence must belong to the case Golden set"
                )
        elif case.expected_evidence_ids or case.expected_non_answer_reason is None:
            raise ValueError("safety fake case requires one non-answer reason")
        _validate_candidate_snapshot(case.candidates)


def _validate_candidate_snapshot(
    candidates: Sequence[RerankerContextCandidateInput],
) -> None:
    if len(candidates) > 20:
        raise ValueError("candidate snapshot exceeds the Hybrid depth-10 union")
    candidate_ids = [item.candidate_id for item in candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("candidate snapshot IDs must be unique")
    for candidate in candidates:
        if not candidate.body_text:
            raise ValueError("candidate body text must be non-empty")
        if candidate.body_text_sha256 != _sha256_text(candidate.body_text):
            raise ValueError("candidate body hash does not match its private text")
        if not math.isfinite(candidate.rrf_score) or candidate.rrf_score <= 0:
            raise ValueError("candidate RRF score must be positive and finite")


def _score_cache_key(
    *,
    query: str,
    candidates: Sequence[RerankerContextCandidateInput],
    scorer: RerankerScorer,
) -> str:
    payload = {
        "query_sha256": _sha256_text(query),
        "ordered_candidates": [
            {
                "candidate_id": item.candidate_id,
                "body_text_sha256": item.body_text_sha256,
            }
            for item in candidates
        ],
        "scorer": scorer.identity.model_dump(mode="json"),
    }
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _fake_input_sha256(
    *,
    cases: Sequence[RerankerContextCaseInput],
    dataset_version: str,
    dataset_sha256: str,
    selected_top_k: RerankerTopK,
    scorer_identity: FakeRerankerIdentity,
    context_identity: FakeContextReaderIdentity,
) -> str:
    payload = {
        "dataset_version": dataset_version,
        "dataset_sha256": dataset_sha256,
        "selected_top_k": selected_top_k,
        "scorer": scorer_identity.model_dump(mode="json"),
        "context_reader": context_identity.model_dump(mode="json"),
        "cases": [
            {
                "case_id": case.case_id,
                "source_group": case.source_group,
                "query_sha256": _sha256_text(case.question),
                "should_answer": case.should_answer,
                "expected_evidence_ids": sorted(case.expected_evidence_ids),
                "expected_non_answer_reason": case.expected_non_answer_reason,
                "protected_document_ids": sorted(case.protected_document_ids),
                "protected_version_ids": sorted(case.protected_version_ids),
                "protected_index_set_ids": sorted(case.protected_index_set_ids),
                "candidates": [
                    {
                        "candidate_id": item.candidate_id,
                        "logical_document_id": item.logical_document_id,
                        "version_id": item.version_id,
                        "index_set_id": item.index_set_id,
                        "body_text_sha256": item.body_text_sha256,
                        "rrf_score": item.rrf_score,
                        "evidence_ids": sorted(item.evidence_ids),
                        "source_locator": (
                            None
                            if item.source_locator is None
                            else item.source_locator.model_dump(mode="json")
                        ),
                    }
                    for item in case.candidates
                ],
            }
            for case in cases
        ],
    }
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _fake_case_input(case: EvaluationCase) -> RerankerContextCaseInput:
    if not case.should_answer:
        return RerankerContextCaseInput(
            case_id=case.case_id,
            source_group=case.source_group,
            question=case.question,
            should_answer=False,
            expected_evidence_ids=frozenset(),
            expected_non_answer_reason=case.expected_non_answer_reason,
            candidates=(),
        )

    expected_evidence_ids = tuple(
        _safe_hashed_id("evidence", case.case_id, index)
        for index, _span in enumerate(case.expected_evidence_spans, start=1)
    )
    candidates: list[RerankerContextCandidateInput] = []
    for index, (span, evidence_id) in enumerate(
        zip(case.expected_evidence_spans, expected_evidence_ids, strict=True),
        start=1,
    ):
        candidates.append(
            _candidate_from_text(
                case_id=case.case_id,
                index=index,
                logical_document_id=span.document_id,
                body_text=span.exact_text,
                rrf_rank=index,
                evidence_ids=frozenset({evidence_id}),
                source_locator=_locator_from_span(span),
            )
        )
    target_count = max(10, len(candidates))
    while len(candidates) < target_count:
        index = len(candidates) + 1
        candidates.append(
            _candidate_from_text(
                case_id=case.case_id,
                index=index,
                logical_document_id="fake-public-document",
                body_text=f"deterministic fake distractor {index} for {case.category}",
                rrf_rank=index,
                evidence_ids=frozenset(),
                source_locator=None,
            )
        )
    return RerankerContextCaseInput(
        case_id=case.case_id,
        source_group=case.source_group,
        question=case.question,
        should_answer=True,
        expected_evidence_ids=frozenset(expected_evidence_ids),
        expected_non_answer_reason=None,
        candidates=tuple(candidates),
    )


def _candidate_from_text(
    *,
    case_id: str,
    index: int,
    logical_document_id: str,
    body_text: str,
    rrf_rank: int,
    evidence_ids: frozenset[str],
    source_locator: RetrievalSourceLocator | None,
) -> RerankerContextCandidateInput:
    return RerankerContextCandidateInput(
        candidate_id=_safe_hashed_id("candidate", case_id, index),
        logical_document_id=logical_document_id,
        body_text=body_text,
        body_text_sha256=_sha256_text(body_text),
        rrf_score=1.0 / (60 + rrf_rank),
        evidence_ids=evidence_ids,
        source_locator=source_locator,
    )


def _locator_from_span(span: ExpectedEvidenceSpan) -> RetrievalSourceLocator | None:
    if span.source_type == "pdf" and span.page_start is not None:
        pages = list(range(span.page_start, cast(int, span.page_end) + 1))
        return PdfRetrievalSourceLocator(
            page_number=pages[0] if len(pages) == 1 else None,
            page_numbers=[] if len(pages) == 1 else pages,
        )
    if span.source_type == "docx" and span.page_start is not None:
        pages = list(range(span.page_start, cast(int, span.page_end) + 1))
        return DocxRetrievalSourceLocator(
            page_number=pages[0] if len(pages) == 1 else None,
            page_numbers=[] if len(pages) == 1 else pages,
        )
    if span.source_type == "xlsx" and span.sheet_name is not None:
        return XlsxRetrievalSourceLocator(
            sheet_name=span.sheet_name,
            cell_range=span.cell_range,
            row_start=span.row_start,
            row_end=span.row_end,
        )
    if (
        span.source_type == "csv"
        and span.row_start is not None
        and span.row_end is not None
    ):
        return CsvRetrievalSourceLocator(
            row_start=span.row_start,
            row_end=span.row_end,
        )
    return None


def _safe_hashed_id(kind: str, case_id: str, index: int) -> str:
    digest = _sha256_text(f"{case_id}:{index}")[:24]
    return f"fake-{kind}-{digest}"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
