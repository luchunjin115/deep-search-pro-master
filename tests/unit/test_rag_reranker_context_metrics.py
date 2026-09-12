from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.evals.reranker_context_metrics import (
    ContextMetricSegment,
    EvidenceGateParameters,
    EvidenceRankedCandidate,
    aggregate_context_quality,
    aggregate_reranker_comparisons,
    apply_three_signal_evidence_gate,
    build_bounded_reranker_context_plan,
    evaluate_context_quality,
    evaluate_reranker_comparison,
    evaluate_reranker_context_safety,
    freeze_reranker_context_cohort,
)
from app.schemas.evaluation import (
    ContextCaseQualityResult,
    RerankerCaseComparison,
    RerankerContextEvaluationPlan,
)

ROOT = Path(__file__).resolve().parents[2]
SMOKE_DATASET_PATH = ROOT / "data" / "evals" / "m2_cross_border_rag_smoke_v1.jsonl"


def _candidate(
    candidate_id: str,
    *evidence_ids: str,
    logical_document_id: str | None = None,
    version_id: str | None = None,
) -> EvidenceRankedCandidate:
    return EvidenceRankedCandidate(
        candidate_id=candidate_id,
        evidence_ids=frozenset(evidence_ids),
        logical_document_id=logical_document_id,
        version_id=version_id,
    )


def _comparison(
    case_id: str,
    *,
    rrf_rank: int | None,
    reranker_rank: int | None,
    top_k: int = 5,
) -> RerankerCaseComparison:
    candidates = [
        _candidate(
            f"chunk-{index:02d}",
            *(("evidence-a",) if index == rrf_rank else ()),
        )
        for index in range(1, 11)
    ]
    if rrf_rank is None:
        reranked = list(reversed(candidates))
    else:
        golden = candidates[rrf_rank - 1]
        others = [item for item in candidates if item is not golden]
        assert reranker_rank is not None
        reranked = [*others[: reranker_rank - 1], golden, *others[reranker_rank - 1 :]]
    return evaluate_reranker_comparison(
        case_id=case_id,
        source_group="synthetic_engineering_regression",
        top_k=top_k,
        expected_evidence_ids=frozenset({"evidence-a"}),
        rrf_candidates=candidates,
        reranked_candidates=reranked,
    )


def test_frozen_plan_screens_top_k_before_context_without_repeating_reranking() -> None:
    frozen = RerankerContextEvaluationPlan()

    assert frozen.chunk_config_id == "chunk-compact-overlap-100"
    assert (
        frozen.chunk_target_tokens,
        frozen.chunk_max_tokens,
        frozen.chunk_overlap_tokens,
        frozen.candidate_depth,
        frozen.hybrid_candidate_limit,
        frozen.rrf_k,
    ) == (400, 500, 100, 10, 20, 60)
    assert frozen.reranker_top_k_sequence == (5, 8)
    assert frozen.context_neighbor_window_sequence == (0, 1)
    assert frozen.context_max_tokens_sequence == (2000, 3000, 4000)
    assert frozen.answerable_case_count == 34
    assert frozen.safety_case_count == 6
    assert frozen.reranker_model == "BAAI/bge-reranker-v2-m3"
    assert frozen.reranker_revision == "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"

    plan = build_bounded_reranker_context_plan(selected_top_k=5)
    assert [item.stage for item in plan[:2]] == [
        "reranker_top_k",
        "reranker_top_k",
    ]
    assert [item.reranker_top_k for item in plan[:2]] == [5, 8]
    assert [
        (item.reranker_top_k, item.context_neighbor_window, item.context_max_tokens)
        for item in plan[2:]
    ] == [
        (5, 0, 2000),
        (5, 0, 3000),
        (5, 0, 4000),
        (5, 1, 2000),
        (5, 1, 3000),
        (5, 1, 4000),
    ]
    assert len(plan) == 8


def test_frozen_plan_rejects_scope_or_model_identity_drift() -> None:
    baseline = RerankerContextEvaluationPlan().model_dump(mode="json")

    for change in (
        {"candidate_depth": 20},
        {"rrf_k": 20},
        {"reranker_top_k_sequence": [8, 5]},
        {"context_neighbor_window_sequence": [0]},
        {"context_max_tokens_sequence": [2000, 4000]},
        {"answerable_case_count": 31},
        {"safety_case_count": 5},
        {"reranker_revision": "main"},
    ):
        with pytest.raises(ValidationError):
            RerankerContextEvaluationPlan.model_validate(baseline | change)


def test_formal_cohort_keeps_all_answerable_and_safety_cases() -> None:
    lines = [
        line
        for line in SMOKE_DATASET_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    cohort = freeze_reranker_context_cohort(lines)

    assert len(cohort.answerable_case_ids) == 34
    assert len(cohort.safety_cases) == 6
    assert not set(cohort.answerable_case_ids) & {
        item.case_id for item in cohort.safety_cases
    }
    assert Counter(item.expected_non_answer_reason for item in cohort.safety_cases) == {
        "acl_denied": 2,
        "version_unavailable": 2,
        "no_evidence": 1,
        "unknown": 1,
    }


def test_top5_and_top8_compare_the_same_pool_and_classify_rank_change() -> None:
    promoted_at_five = _comparison(
        "case-promoted", rrf_rank=8, reranker_rank=5, top_k=5
    )
    promoted_at_eight = _comparison(
        "case-promoted", rrf_rank=8, reranker_rank=5, top_k=8
    )
    demoted = _comparison("case-demoted", rrf_rank=2, reranker_rank=6)
    unchanged = _comparison("case-unchanged", rrf_rank=3, reranker_rank=3)

    assert promoted_at_five.rank_change == "promoted"
    assert promoted_at_five.rrf_hit_at_k is False
    assert promoted_at_five.reranker_hit_at_k is True
    assert promoted_at_eight.rrf_hit_at_k is True
    assert promoted_at_eight.reranker_hit_at_k is True
    assert demoted.rank_change == "demoted"
    assert unchanged.rank_change == "unchanged"


def test_upstream_candidate_missing_is_completed_and_stays_in_denominator() -> None:
    missing = _comparison("case-missing", rrf_rank=None, reranker_rank=None, top_k=8)
    promoted = _comparison("case-promoted", rrf_rank=8, reranker_rank=2, top_k=8)
    unchanged = _comparison("case-unchanged", rrf_rank=1, reranker_rank=1, top_k=8)

    assert missing.status == "completed"
    assert missing.rank_change == "candidate_missing"
    assert missing.rrf_first_golden_rank is None
    assert missing.reranker_first_golden_rank is None
    assert missing.rrf_hit_at_k is False
    assert missing.reranker_hit_at_k is False

    aggregate = aggregate_reranker_comparisons(
        [missing, promoted, unchanged],
        expected_case_ids=("case-missing", "case-promoted", "case-unchanged"),
        group_id="all-answerable",
        top_k=8,
    )
    assert aggregate.status == "completed"
    assert aggregate.expected_case_count == 3
    assert aggregate.candidate_missing_count == 1
    assert aggregate.rrf_hit_rate_at_k == pytest.approx(2 / 3)
    assert aggregate.reranker_hit_rate_at_k == pytest.approx(2 / 3)


def test_reranker_comparison_rejects_duplicate_or_changed_candidate_pool() -> None:
    rrf = [_candidate("chunk-a"), _candidate("chunk-b", "evidence-a")]

    with pytest.raises(ValueError, match="unique"):
        evaluate_reranker_comparison(
            case_id="case-duplicate",
            source_group="cross_border_core",
            top_k=5,
            expected_evidence_ids=frozenset({"evidence-a"}),
            rrf_candidates=[rrf[0], rrf[0]],
            reranked_candidates=rrf,
        )
    with pytest.raises(ValueError, match="same candidate pool"):
        evaluate_reranker_comparison(
            case_id="case-changed-pool",
            source_group="cross_border_core",
            top_k=5,
            expected_evidence_ids=frozenset({"evidence-a"}),
            rrf_candidates=rrf,
            reranked_candidates=[rrf[0], _candidate("chunk-c", "evidence-a")],
        )


@pytest.mark.parametrize(
    ("scores", "expected_outcome", "expected_ranks"),
    [
        ((), "no_evidence", ()),
        ((0.42, 0.39, 0.35), "unsupported", ()),
        ((0.90, 0.84, 0.71, 0.30), "supported", (1, 2)),
        ((0.91, 0.40), "supported", (1,)),
        ((0.63, 0.62, 0.38), "uncertain", (1, 2)),
    ],
)
def test_three_signal_gate_rejects_low_scores_and_keeps_only_dynamic_anchors(
    scores: tuple[float, ...],
    expected_outcome: str,
    expected_ranks: tuple[int, ...],
) -> None:
    result = apply_three_signal_evidence_gate(
        scores,
        parameters=EvidenceGateParameters(
            absolute_floor=0.55,
            relative_top_ratio=0.8,
            high_confidence=0.7,
            ambiguous_gap=0.03,
            max_anchors=8,
        ),
    )

    assert result.outcome == expected_outcome
    assert result.retained_ranks == expected_ranks


def test_three_signal_gate_never_refills_or_exceeds_the_anchor_cap() -> None:
    result = apply_three_signal_evidence_gate(
        (0.99, 0.98, 0.97, 0.96, 0.95, 0.94, 0.93, 0.92, 0.91),
        parameters=EvidenceGateParameters(
            absolute_floor=0.5,
            relative_top_ratio=0.8,
            high_confidence=0.9,
            ambiguous_gap=0.01,
            max_anchors=8,
        ),
    )

    assert result.outcome == "supported"
    assert result.retained_ranks == tuple(range(1, 9))


def test_two_depth_ten_routes_may_form_a_twenty_candidate_rrf_pool() -> None:
    rrf = [
        _candidate(
            f"chunk-{index:02d}",
            *(("evidence-a",) if index == 20 else ()),
        )
        for index in range(1, 21)
    ]
    reranked = [rrf[-1], *rrf[:-1]]

    result = evaluate_reranker_comparison(
        case_id="case-union-depth",
        source_group="cross_border_core",
        top_k=8,
        expected_evidence_ids=frozenset({"evidence-a"}),
        rrf_candidates=rrf,
        reranked_candidates=reranked,
    )

    assert result.rrf_candidate_count == 20
    assert result.rrf_first_golden_rank == 20
    assert result.reranker_first_golden_rank == 1


def test_context_metrics_separate_anchor_coverage_from_neighbor_rescue() -> None:
    segments = [
        ContextMetricSegment(
            segment_id="chunk-anchor-a",
            role="anchor",
            anchor_candidate_id=None,
            evidence_ids=frozenset(),
            token_count=400,
        ),
        ContextMetricSegment(
            segment_id="chunk-neighbor-a",
            role="next_neighbor",
            anchor_candidate_id="chunk-anchor-a",
            evidence_ids=frozenset({"evidence-a"}),
            token_count=200,
        ),
        ContextMetricSegment(
            segment_id="chunk-anchor-b",
            role="anchor",
            anchor_candidate_id=None,
            evidence_ids=frozenset({"evidence-b"}),
            token_count=600,
        ),
    ]

    result = evaluate_context_quality(
        case_id="case-context",
        source_group="cross_border_core",
        reranker_top_k=5,
        context_neighbor_window=1,
        context_max_tokens=2000,
        expected_evidence_ids=frozenset({"evidence-a", "evidence-b"}),
        selected_anchor_candidate_ids=("chunk-anchor-a", "chunk-anchor-b"),
        segments=segments,
    )

    assert result.status == "completed"
    assert result.supported is True
    assert result.golden_evidence_coverage_rate == 1.0
    assert result.anchor_golden_evidence_coverage_rate == 0.5
    assert result.redundant_segment_count == 1
    assert result.context_redundancy_rate == pytest.approx(1 / 3)
    assert result.token_utilization_rate == 0.6


def test_context_metrics_reject_duplicate_fake_neighbor_or_token_overflow() -> None:
    duplicate = ContextMetricSegment(
        segment_id="chunk-anchor",
        role="anchor",
        anchor_candidate_id=None,
        evidence_ids=frozenset({"evidence-a"}),
        token_count=1100,
    )
    common = {
        "case_id": "case-context-invalid",
        "source_group": "cross_border_core",
        "reranker_top_k": 5,
        "context_neighbor_window": 1,
        "context_max_tokens": 2000,
        "expected_evidence_ids": frozenset({"evidence-a"}),
        "selected_anchor_candidate_ids": ("chunk-anchor",),
    }

    with pytest.raises(ValueError, match="unique"):
        evaluate_context_quality(**common, segments=[duplicate, duplicate])
    with pytest.raises(ValueError, match="selected anchor"):
        evaluate_context_quality(
            **common,
            segments=[
                ContextMetricSegment(
                    segment_id="chunk-neighbor",
                    role="anchor",
                    anchor_candidate_id=None,
                    evidence_ids=frozenset({"evidence-a"}),
                    token_count=100,
                )
            ],
        )
    with pytest.raises(ValueError, match="token budget"):
        evaluate_context_quality(
            **common,
            segments=[
                duplicate,
                ContextMetricSegment(
                    segment_id="chunk-neighbor",
                    role="next_neighbor",
                    anchor_candidate_id="chunk-anchor",
                    evidence_ids=frozenset(),
                    token_count=1000,
                ),
            ],
        )


def test_empty_context_is_a_real_zero_not_a_calculation_failure() -> None:
    result = evaluate_context_quality(
        case_id="case-empty",
        source_group="synthetic_engineering_regression",
        reranker_top_k=8,
        context_neighbor_window=0,
        context_max_tokens=3000,
        expected_evidence_ids=frozenset({"evidence-a"}),
        selected_anchor_candidate_ids=(),
        segments=[],
    )

    assert result.status == "completed"
    assert result.supported is False
    assert result.segment_count == 0
    assert result.golden_evidence_coverage_rate == 0.0
    assert result.context_redundancy_rate == 0.0
    assert result.token_utilization_rate == 0.0


def test_metric_failure_statuses_cannot_carry_numeric_zeroes() -> None:
    failure = ContextCaseQualityResult(
        case_id="case-failed",
        source_group="cross_border_core",
        reranker_top_k=5,
        context_neighbor_window=0,
        context_max_tokens=2000,
        expected_evidence_count=1,
        status="calculation_failed",
        failure_category="calculation_error",
        failure_summary="Deterministic Context metric calculation failed.",
    )
    assert failure.golden_evidence_coverage_rate is None

    with pytest.raises(ValidationError, match="non-numeric"):
        ContextCaseQualityResult.model_validate(
            failure.model_dump(mode="json") | {"golden_evidence_coverage_rate": 0.0}
        )


def test_context_aggregate_becomes_non_numeric_if_any_case_failed() -> None:
    completed = evaluate_context_quality(
        case_id="case-complete",
        source_group="cross_border_core",
        reranker_top_k=5,
        context_neighbor_window=0,
        context_max_tokens=2000,
        expected_evidence_ids=frozenset({"evidence-a"}),
        selected_anchor_candidate_ids=(),
        segments=[],
    )
    failed = ContextCaseQualityResult(
        case_id="case-failed",
        source_group="cross_border_core",
        reranker_top_k=5,
        context_neighbor_window=0,
        context_max_tokens=2000,
        expected_evidence_count=1,
        status="calculation_failed",
        failure_category="calculation_error",
        failure_summary="Deterministic Context metric calculation failed.",
    )

    aggregate = aggregate_context_quality(
        [completed, failed],
        expected_case_ids=("case-complete", "case-failed"),
        group_id="cross-border-core",
        reranker_top_k=5,
        context_neighbor_window=0,
        context_max_tokens=2000,
    )

    assert aggregate.status == "calculation_failed"
    assert aggregate.golden_evidence_coverage_rate is None
    assert aggregate.context_redundancy_rate is None
    assert aggregate.token_utilization_rate is None


def test_safety_cases_keep_security_checks_separate_from_unknown_semantics() -> None:
    secret = _candidate(
        "chunk-secret",
        logical_document_id="document-secret",
        version_id="version-secret",
    )
    public = _candidate("chunk-public", logical_document_id="document-public")

    denied = evaluate_reranker_context_safety(
        case_id="case-acl",
        expected_non_answer_reason="acl_denied",
        top_k=8,
        rrf_candidates=[public, secret],
        reranked_candidates=[secret, public],
        context_segments=[],
        protected_document_ids=frozenset({"document-secret"}),
    )
    unknown = evaluate_reranker_context_safety(
        case_id="case-unknown",
        expected_non_answer_reason="unknown",
        top_k=8,
        rrf_candidates=[public],
        reranked_candidates=[public],
        context_segments=[],
    )

    assert denied.security_violation is True
    assert denied.rrf_first_forbidden_rank == 2
    assert denied.reranker_first_forbidden_rank == 1
    assert unknown.security_violation is None
    assert unknown.rrf_returned_candidate_count == 1
    assert unknown.context_segment_count == 0
