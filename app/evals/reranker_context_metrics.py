"""Deterministic M2-22.7 Reranker and Context evaluation metrics."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Literal, cast

from app.schemas.context import ContextSegmentRole
from app.schemas.evaluation import (
    ContextCaseQualityResult,
    ContextEvaluationNeighborWindow,
    ContextEvaluationTokenBudget,
    ContextGroupAggregateResult,
    EvaluationCase,
    EvaluationSourceGroup,
    ExpectedNonAnswerReason,
    RerankerCaseComparison,
    RerankerContextEvaluationCohort,
    RerankerContextExperimentPoint,
    RerankerContextSafetyCase,
    RerankerContextSafetyCaseResult,
    RerankerGroupAggregateResult,
    RerankerRankChange,
    RerankerTopK,
)

_TOP_K_SEQUENCE: tuple[RerankerTopK, ...] = (5, 8)
_NEIGHBOR_SEQUENCE: tuple[ContextEvaluationNeighborWindow, ...] = (0, 1)
_TOKEN_SEQUENCE: tuple[ContextEvaluationTokenBudget, ...] = (2000, 3000, 4000)
_SECURITY_REASONS = {"acl_denied", "version_unavailable", "source_rejected"}
_FAILED_METRIC_SUMMARY = "Deterministic metric calculation failed."


@dataclass(frozen=True, slots=True)
class EvidenceRankedCandidate:
    """One candidate whose exact Golden and protected-source facts are frozen."""

    candidate_id: str
    evidence_ids: frozenset[str]
    logical_document_id: str | None = None
    version_id: str | None = None
    index_set_id: str | None = None


@dataclass(frozen=True, slots=True)
class ContextMetricSegment:
    """One final Context segment in display order, with its real role retained."""

    segment_id: str
    role: ContextSegmentRole
    anchor_candidate_id: str | None
    evidence_ids: frozenset[str]
    token_count: int
    logical_document_id: str | None = None
    version_id: str | None = None
    index_set_id: str | None = None


@dataclass(frozen=True, slots=True)
class EvidenceGateParameters:
    """One bounded three-signal rule used only by offline calibration."""

    absolute_floor: float
    relative_top_ratio: float
    high_confidence: float
    ambiguous_gap: float
    max_anchors: int = 8

    def __post_init__(self) -> None:
        values = (
            self.absolute_floor,
            self.relative_top_ratio,
            self.high_confidence,
            self.ambiguous_gap,
        )
        if (
            any(
                not isinstance(value, (int, float)) or not math.isfinite(value)
                for value in values
            )
            or not 0 <= self.absolute_floor <= self.high_confidence <= 1
            or not 0 < self.relative_top_ratio <= 1
            or not 0 <= self.ambiguous_gap <= 1
            or not isinstance(self.max_anchors, int)
            or isinstance(self.max_anchors, bool)
            or not 1 <= self.max_anchors <= 8
        ):
            raise ValueError("invalid evidence gate calibration parameters")


@dataclass(frozen=True, slots=True)
class EvidenceGateDecision:
    """One deterministic gate decision; retained ranks are never refilled."""

    outcome: Literal["no_evidence", "unsupported", "uncertain", "supported"]
    retained_ranks: tuple[int, ...]


def apply_three_signal_evidence_gate(
    scores: Sequence[float],
    *,
    parameters: EvidenceGateParameters,
) -> EvidenceGateDecision:
    """Apply absolute floor, relative Top-1 retention, then low-confidence gap."""

    normalized = tuple(float(score) for score in scores)
    if any(
        not math.isfinite(score) or not 0 <= score <= 1 for score in normalized
    ) or any(first < second for first, second in pairwise(normalized)):
        raise ValueError("evidence gate scores must be finite and descending")
    if not normalized:
        return EvidenceGateDecision(outcome="no_evidence", retained_ranks=())

    top_score = normalized[0]
    if top_score < parameters.absolute_floor:
        return EvidenceGateDecision(outcome="unsupported", retained_ranks=())

    dynamic_floor = max(
        parameters.absolute_floor,
        top_score * parameters.relative_top_ratio,
    )
    retained = tuple(
        rank for rank, score in enumerate(normalized, start=1) if score >= dynamic_floor
    )[: parameters.max_anchors]
    if not retained:
        return EvidenceGateDecision(outcome="unsupported", retained_ranks=())

    ambiguous = (
        len(retained) >= 2
        and top_score < parameters.high_confidence
        and top_score - normalized[1] <= parameters.ambiguous_gap
    )
    return EvidenceGateDecision(
        outcome="uncertain" if ambiguous else "supported",
        retained_ranks=retained,
    )


def build_bounded_reranker_context_plan(
    *,
    selected_top_k: RerankerTopK,
) -> list[RerankerContextExperimentPoint]:
    """Screen Top5/Top8 first, then vary Context only at the selected TopK."""

    if selected_top_k not in _TOP_K_SEQUENCE:
        raise ValueError("selected Reranker TopK must be 5 or 8")
    points = [
        RerankerContextExperimentPoint(
            stage="reranker_top_k",
            reranker_top_k=top_k,
        )
        for top_k in _TOP_K_SEQUENCE
    ]
    points.extend(
        RerankerContextExperimentPoint(
            stage="context",
            reranker_top_k=selected_top_k,
            context_neighbor_window=neighbor_window,
            context_max_tokens=max_tokens,
        )
        for neighbor_window in _NEIGHBOR_SEQUENCE
        for max_tokens in _TOKEN_SEQUENCE
    )
    return points


def freeze_reranker_context_cohort(
    serialized_cases: Iterable[str | EvaluationCase],
) -> RerankerContextEvaluationCohort:
    """Freeze all 34 answerable rows and all six non-answer safety rows."""

    cases = [
        item
        if isinstance(item, EvaluationCase)
        else EvaluationCase.model_validate_json(item)
        for item in serialized_cases
    ]
    if not cases:
        raise ValueError("Reranker/Context cohort cannot be empty")
    dataset_versions = {item.dataset_version for item in cases}
    if len(dataset_versions) != 1:
        raise ValueError("Reranker/Context cases must share one dataset version")
    answerable_ids = [item.case_id for item in cases if item.should_answer]
    safety_cases = [
        RerankerContextSafetyCase(
            case_id=item.case_id,
            expected_non_answer_reason=cast(
                ExpectedNonAnswerReason,
                item.expected_non_answer_reason,
            ),
        )
        for item in cases
        if not item.should_answer
    ]
    return RerankerContextEvaluationCohort(
        dataset_version=dataset_versions.pop(),
        answerable_case_ids=answerable_ids,
        safety_cases=safety_cases,
    )


def evaluate_reranker_comparison(
    *,
    case_id: str,
    source_group: EvaluationSourceGroup,
    top_k: RerankerTopK,
    expected_evidence_ids: frozenset[str],
    rrf_candidates: Sequence[EvidenceRankedCandidate],
    reranked_candidates: Sequence[EvidenceRankedCandidate],
) -> RerankerCaseComparison:
    """Compare Golden rank while requiring the exact same candidate pool."""

    if top_k not in _TOP_K_SEQUENCE:
        raise ValueError("Reranker TopK must be 5 or 8")
    _validate_expected_evidence(expected_evidence_ids)
    _validate_same_candidate_pool(rrf_candidates, reranked_candidates)
    if any(not item.evidence_ids <= expected_evidence_ids for item in rrf_candidates):
        raise ValueError("candidate Evidence must belong to the expected set")

    rrf_rank = _first_evidence_rank(rrf_candidates)
    reranker_rank = _first_evidence_rank(reranked_candidates)
    rank_change: RerankerRankChange
    if rrf_rank is None:
        rank_change = "candidate_missing"
    elif reranker_rank is None:
        raise ValueError("unchanged candidate pool cannot drop Golden Evidence")
    elif reranker_rank < rrf_rank:
        rank_change = "promoted"
    elif reranker_rank > rrf_rank:
        rank_change = "demoted"
    else:
        rank_change = "unchanged"

    return RerankerCaseComparison(
        case_id=case_id,
        source_group=source_group,
        top_k=top_k,
        expected_evidence_count=len(expected_evidence_ids),
        status="completed",
        rrf_candidate_count=len(rrf_candidates),
        reranker_candidate_count=len(reranked_candidates),
        candidate_set_unchanged=True,
        rrf_first_golden_rank=rrf_rank,
        reranker_first_golden_rank=reranker_rank,
        rank_change=rank_change,
        rrf_hit_at_k=rrf_rank is not None and rrf_rank <= top_k,
        reranker_hit_at_k=(reranker_rank is not None and reranker_rank <= top_k),
    )


def evaluate_context_quality(
    *,
    case_id: str,
    source_group: EvaluationSourceGroup,
    reranker_top_k: RerankerTopK,
    context_neighbor_window: ContextEvaluationNeighborWindow,
    context_max_tokens: ContextEvaluationTokenBudget,
    expected_evidence_ids: frozenset[str],
    selected_anchor_candidate_ids: Sequence[str],
    segments: Sequence[ContextMetricSegment],
) -> ContextCaseQualityResult:
    """Measure Golden coverage, Golden-relative redundancy, and Token use.

    Overall coverage may be rescued by a neighbor. Anchor coverage only uses
    real Reranker anchors, so a neighbor can never be reported as an anchor hit.
    A segment is redundant when it contributes no previously uncovered Golden
    Evidence in final Context order. This is a deterministic Golden-relative
    measure, not a semantic relevance judgment.
    """

    _validate_context_config(
        reranker_top_k=reranker_top_k,
        neighbor_window=context_neighbor_window,
        max_tokens=context_max_tokens,
    )
    _validate_expected_evidence(expected_evidence_ids)
    anchor_ids = _validate_selected_anchors(
        selected_anchor_candidate_ids,
        reranker_top_k=reranker_top_k,
    )
    _validate_context_segments(
        segments,
        selected_anchor_ids=anchor_ids,
        neighbor_window=context_neighbor_window,
        expected_evidence_ids=expected_evidence_ids,
    )
    total_tokens = sum(item.token_count for item in segments)
    if total_tokens > context_max_tokens:
        raise ValueError("Context total exceeds its token budget")

    covered: set[str] = set()
    anchor_covered: set[str] = set()
    redundant_segments = 0
    for segment in segments:
        new_evidence = segment.evidence_ids - covered
        if not new_evidence:
            redundant_segments += 1
        covered.update(segment.evidence_ids)
        if segment.role == "anchor":
            anchor_covered.update(segment.evidence_ids)

    segment_count = len(segments)
    return ContextCaseQualityResult(
        case_id=case_id,
        source_group=source_group,
        reranker_top_k=reranker_top_k,
        context_neighbor_window=context_neighbor_window,
        context_max_tokens=context_max_tokens,
        expected_evidence_count=len(expected_evidence_ids),
        status="completed",
        supported=bool(segments),
        segment_count=segment_count,
        anchor_segment_count=sum(item.role == "anchor" for item in segments),
        covered_golden_evidence_count=len(covered),
        anchor_covered_golden_evidence_count=len(anchor_covered),
        redundant_segment_count=redundant_segments,
        total_tokens=total_tokens,
        golden_evidence_coverage_rate=len(covered) / len(expected_evidence_ids),
        anchor_golden_evidence_coverage_rate=(
            len(anchor_covered) / len(expected_evidence_ids)
        ),
        context_redundancy_rate=(
            redundant_segments / segment_count if segment_count else 0.0
        ),
        token_utilization_rate=total_tokens / context_max_tokens,
    )


def aggregate_reranker_comparisons(
    results: Sequence[RerankerCaseComparison],
    *,
    expected_case_ids: Sequence[str],
    group_id: str,
    top_k: RerankerTopK,
) -> RerankerGroupAggregateResult:
    """Aggregate over the declared denominator, including candidate misses."""

    _validate_complete_case_set(results, expected_case_ids)
    if any(item.top_k != top_k for item in results):
        raise ValueError("Reranker aggregate mixes TopK configurations")
    if any(item.status != "completed" for item in results):
        return RerankerGroupAggregateResult(
            group_id=group_id,
            top_k=top_k,
            expected_case_count=len(expected_case_ids),
            status="calculation_failed",
            failure_category="calculation_error",
            failure_summary=_FAILED_METRIC_SUMMARY,
        )

    movement_counts = {
        movement: sum(item.rank_change == movement for item in results)
        for movement in ("candidate_missing", "promoted", "demoted", "unchanged")
    }
    rrf_hits = sum(item.rrf_hit_at_k is True for item in results)
    reranker_hits = sum(item.reranker_hit_at_k is True for item in results)
    denominator = len(expected_case_ids)
    return RerankerGroupAggregateResult(
        group_id=group_id,
        top_k=top_k,
        expected_case_count=denominator,
        status="completed",
        candidate_missing_count=movement_counts["candidate_missing"],
        promoted_count=movement_counts["promoted"],
        demoted_count=movement_counts["demoted"],
        unchanged_count=movement_counts["unchanged"],
        rrf_hit_count=rrf_hits,
        reranker_hit_count=reranker_hits,
        rrf_hit_rate_at_k=rrf_hits / denominator,
        reranker_hit_rate_at_k=reranker_hits / denominator,
    )


def aggregate_context_quality(
    results: Sequence[ContextCaseQualityResult],
    *,
    expected_case_ids: Sequence[str],
    group_id: str,
    reranker_top_k: RerankerTopK,
    context_neighbor_window: ContextEvaluationNeighborWindow,
    context_max_tokens: ContextEvaluationTokenBudget,
) -> ContextGroupAggregateResult:
    """Aggregate Context counts; one failed case keeps all aggregate rates absent."""

    _validate_complete_case_set(results, expected_case_ids)
    if any(
        item.reranker_top_k != reranker_top_k
        or item.context_neighbor_window != context_neighbor_window
        or item.context_max_tokens != context_max_tokens
        for item in results
    ):
        raise ValueError("Context aggregate mixes experiment configurations")
    if any(item.status != "completed" for item in results):
        return ContextGroupAggregateResult(
            group_id=group_id,
            reranker_top_k=reranker_top_k,
            context_neighbor_window=context_neighbor_window,
            context_max_tokens=context_max_tokens,
            expected_case_count=len(expected_case_ids),
            status="calculation_failed",
            failure_category="calculation_error",
            failure_summary=_FAILED_METRIC_SUMMARY,
        )

    expected = sum(_required_int(item.expected_evidence_count) for item in results)
    covered = sum(_required_int(item.covered_golden_evidence_count) for item in results)
    anchor_covered = sum(
        _required_int(item.anchor_covered_golden_evidence_count) for item in results
    )
    segment_count = sum(_required_int(item.segment_count) for item in results)
    redundant_count = sum(
        _required_int(item.redundant_segment_count) for item in results
    )
    total_tokens = sum(_required_int(item.total_tokens) for item in results)
    total_budget = len(expected_case_ids) * context_max_tokens
    return ContextGroupAggregateResult(
        group_id=group_id,
        reranker_top_k=reranker_top_k,
        context_neighbor_window=context_neighbor_window,
        context_max_tokens=context_max_tokens,
        expected_case_count=len(expected_case_ids),
        status="completed",
        expected_evidence_count=expected,
        covered_golden_evidence_count=covered,
        anchor_covered_golden_evidence_count=anchor_covered,
        segment_count=segment_count,
        redundant_segment_count=redundant_count,
        total_tokens=total_tokens,
        golden_evidence_coverage_rate=covered / expected,
        anchor_golden_evidence_coverage_rate=anchor_covered / expected,
        context_redundancy_rate=(
            redundant_count / segment_count if segment_count else 0.0
        ),
        token_utilization_rate=total_tokens / total_budget,
    )


def evaluate_reranker_context_safety(
    *,
    case_id: str,
    expected_non_answer_reason: ExpectedNonAnswerReason,
    top_k: RerankerTopK,
    rrf_candidates: Sequence[EvidenceRankedCandidate],
    reranked_candidates: Sequence[EvidenceRankedCandidate],
    context_segments: Sequence[ContextMetricSegment],
    protected_document_ids: frozenset[str] = frozenset(),
    protected_version_ids: frozenset[str] = frozenset(),
    protected_index_set_ids: frozenset[str] = frozenset(),
) -> RerankerContextSafetyCaseResult:
    """Keep all non-answer rows while only scoring deterministic security facts."""

    if top_k not in _TOP_K_SEQUENCE:
        raise ValueError("Reranker TopK must be 5 or 8")
    _validate_same_candidate_pool(rrf_candidates, reranked_candidates)
    _validate_basic_context_segments(context_segments)
    security_reason = expected_non_answer_reason in _SECURITY_REASONS
    if not security_reason:
        return RerankerContextSafetyCaseResult(
            case_id=case_id,
            expected_non_answer_reason=expected_non_answer_reason,
            top_k=top_k,
            status="completed",
            rrf_returned_candidate_count=min(len(rrf_candidates), top_k),
            reranker_returned_candidate_count=min(len(reranked_candidates), top_k),
            context_segment_count=len(context_segments),
        )

    protected = (
        protected_document_ids,
        protected_version_ids,
        protected_index_set_ids,
    )
    rrf_rank = _first_forbidden_rank(rrf_candidates[:top_k], protected)
    reranker_rank = _first_forbidden_rank(reranked_candidates[:top_k], protected)
    context_forbidden = sum(
        _is_forbidden_source(
            item.logical_document_id,
            item.version_id,
            item.index_set_id,
            protected,
        )
        for item in context_segments
    )
    return RerankerContextSafetyCaseResult(
        case_id=case_id,
        expected_non_answer_reason=expected_non_answer_reason,
        top_k=top_k,
        status="completed",
        rrf_returned_candidate_count=min(len(rrf_candidates), top_k),
        reranker_returned_candidate_count=min(len(reranked_candidates), top_k),
        context_segment_count=len(context_segments),
        rrf_first_forbidden_rank=rrf_rank,
        reranker_first_forbidden_rank=reranker_rank,
        context_forbidden_segment_count=context_forbidden,
        security_violation=bool(rrf_rank or reranker_rank or context_forbidden),
    )


def _validate_expected_evidence(expected_evidence_ids: frozenset[str]) -> None:
    if not expected_evidence_ids or len(expected_evidence_ids) > 20:
        raise ValueError("answerable metric requires 1-20 expected Evidence IDs")
    if any(
        not isinstance(item, str) or not item.strip() for item in expected_evidence_ids
    ):
        raise ValueError("expected Evidence IDs must be non-empty strings")


def _validate_ranked_candidates(
    candidates: Sequence[EvidenceRankedCandidate],
) -> None:
    if len(candidates) > 20:
        raise ValueError("candidate list exceeds the two-route depth-10 union")
    candidate_ids = [item.candidate_id for item in candidates]
    if any(not isinstance(item, str) or not item.strip() for item in candidate_ids):
        raise ValueError("candidate IDs must be non-empty strings")
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("ranked candidate IDs must be unique")


def _validate_same_candidate_pool(
    rrf_candidates: Sequence[EvidenceRankedCandidate],
    reranked_candidates: Sequence[EvidenceRankedCandidate],
) -> None:
    _validate_ranked_candidates(rrf_candidates)
    _validate_ranked_candidates(reranked_candidates)
    rrf_by_id = {item.candidate_id: item for item in rrf_candidates}
    reranked_by_id = {item.candidate_id: item for item in reranked_candidates}
    if rrf_by_id != reranked_by_id:
        raise ValueError("RRF and Reranker must use the same candidate pool")


def _first_evidence_rank(
    candidates: Sequence[EvidenceRankedCandidate],
) -> int | None:
    return next(
        (
            rank
            for rank, candidate in enumerate(candidates, start=1)
            if candidate.evidence_ids
        ),
        None,
    )


def _validate_context_config(
    *,
    reranker_top_k: int,
    neighbor_window: int,
    max_tokens: int,
) -> None:
    if reranker_top_k not in _TOP_K_SEQUENCE:
        raise ValueError("Reranker TopK must be 5 or 8")
    if neighbor_window not in _NEIGHBOR_SEQUENCE:
        raise ValueError("Context neighbor window must be 0 or 1")
    if max_tokens not in _TOKEN_SEQUENCE:
        raise ValueError("Context Token budget must be 2000, 3000, or 4000")


def _validate_selected_anchors(
    selected_anchor_candidate_ids: Sequence[str],
    *,
    reranker_top_k: int,
) -> frozenset[str]:
    if any(
        not isinstance(item, str) or not item.strip()
        for item in selected_anchor_candidate_ids
    ):
        raise ValueError("selected anchor IDs must be non-empty strings")
    anchors = frozenset(selected_anchor_candidate_ids)
    if len(anchors) != len(selected_anchor_candidate_ids):
        raise ValueError("selected anchor IDs must be unique")
    if len(anchors) > reranker_top_k:
        raise ValueError("selected anchor IDs exceed the Reranker TopK")
    return anchors


def _validate_basic_context_segments(
    segments: Sequence[ContextMetricSegment],
) -> None:
    if len(segments) > 12:
        raise ValueError("Context cannot exceed 12 segments")
    segment_ids = [item.segment_id for item in segments]
    if any(not isinstance(item, str) or not item.strip() for item in segment_ids):
        raise ValueError("Context segment IDs must be non-empty strings")
    if len(segment_ids) != len(set(segment_ids)):
        raise ValueError("Context segment IDs must be unique")
    if any(
        item.role not in {"anchor", "previous_neighbor", "next_neighbor"}
        for item in segments
    ):
        raise ValueError("Context segment role is outside the frozen set")
    if any(
        not isinstance(item.token_count, int)
        or isinstance(item.token_count, bool)
        or item.token_count < 1
        for item in segments
    ):
        raise ValueError("Context segment Token counts must be positive integers")


def _validate_context_segments(
    segments: Sequence[ContextMetricSegment],
    *,
    selected_anchor_ids: frozenset[str],
    neighbor_window: int,
    expected_evidence_ids: frozenset[str],
) -> None:
    _validate_basic_context_segments(segments)
    present_anchor_ids = {item.segment_id for item in segments if item.role == "anchor"}
    if not present_anchor_ids <= selected_anchor_ids:
        raise ValueError("Context anchor is not a selected anchor candidate")
    if any(not item.evidence_ids <= expected_evidence_ids for item in segments):
        raise ValueError("Context Evidence must belong to the expected set")
    for item in segments:
        if item.role == "anchor":
            if item.anchor_candidate_id is not None:
                raise ValueError("anchor segment cannot point to another anchor")
            continue
        if neighbor_window == 0:
            raise ValueError("neighbor segment is forbidden by the zero window")
        if item.anchor_candidate_id not in present_anchor_ids:
            raise ValueError("neighbor must reference a selected Context anchor")


def _validate_complete_case_set(
    results: Sequence[RerankerCaseComparison | ContextCaseQualityResult],
    expected_case_ids: Sequence[str],
) -> None:
    if not expected_case_ids:
        raise ValueError("aggregate denominator cannot be empty")
    if len(expected_case_ids) != len(set(expected_case_ids)):
        raise ValueError("aggregate expected case IDs must be unique")
    result_ids = [item.case_id for item in results]
    if len(result_ids) != len(set(result_ids)):
        raise ValueError("aggregate result case IDs must be unique")
    if set(result_ids) != set(expected_case_ids):
        raise ValueError("aggregate results must preserve the complete denominator")


def _required_int(value: int | None) -> int:
    if value is None:
        raise ValueError("completed Context result is missing a deterministic count")
    return value


def _first_forbidden_rank(
    candidates: Sequence[EvidenceRankedCandidate],
    protected: tuple[frozenset[str], frozenset[str], frozenset[str]],
) -> int | None:
    return next(
        (
            rank
            for rank, item in enumerate(candidates, start=1)
            if _is_forbidden_source(
                item.logical_document_id,
                item.version_id,
                item.index_set_id,
                protected,
            )
        ),
        None,
    )


def _is_forbidden_source(
    logical_document_id: str | None,
    version_id: str | None,
    index_set_id: str | None,
    protected: tuple[frozenset[str], frozenset[str], frozenset[str]],
) -> bool:
    protected_documents, protected_versions, protected_index_sets = protected
    return bool(
        logical_document_id in protected_documents
        or version_id in protected_versions
        or index_set_id in protected_index_sets
    )
