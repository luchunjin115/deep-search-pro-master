from __future__ import annotations

import math

import pytest

from app.evals.retrieval_metrics import (
    RankedEvidenceCandidate,
    build_bounded_retrieval_plan,
    evaluate_answerable_ranking,
    evaluate_no_answer_ranking,
)
from app.evals.retrieval_report import (
    RetrievalCandidateTrace,
    RetrievalRouteTrace,
)


def test_answerable_ranking_metrics_keep_duplicate_hits_out_of_recall_and_ndcg() -> (
    None
):
    candidates = [
        RankedEvidenceCandidate(candidate_id="chunk-001", evidence_ids=frozenset()),
        RankedEvidenceCandidate(
            candidate_id="chunk-002", evidence_ids=frozenset({"evidence-a"})
        ),
        RankedEvidenceCandidate(
            candidate_id="chunk-003", evidence_ids=frozenset({"evidence-a"})
        ),
        RankedEvidenceCandidate(
            candidate_id="chunk-004", evidence_ids=frozenset({"evidence-b"})
        ),
    ]

    metrics = evaluate_answerable_ranking(
        candidates,
        expected_evidence_ids=frozenset({"evidence-a", "evidence-b"}),
    )

    assert metrics.first_correct_evidence_rank == 2
    assert metrics.mrr_at_10 == 0.5
    assert metrics.precision_at[1] == 0.0
    assert metrics.precision_at[3] == pytest.approx(2 / 3)
    assert metrics.precision_at[5] == pytest.approx(3 / 5)
    assert metrics.recall_at[3] == 0.5
    assert metrics.recall_at[5] == 1.0
    assert metrics.hit_rate_at[1] == 0.0
    assert metrics.hit_rate_at[3] == 1.0
    # Repeating evidence-a at rank 3 must not earn another nDCG gain.
    observed_dcg = 1 / math.log2(3) + 1 / math.log2(5)
    ideal_dcg = 1 + 1 / math.log2(3)
    assert metrics.ndcg_at[5] == pytest.approx(observed_dcg / ideal_dcg)


def test_no_answer_ranking_separates_security_leak_from_unjudged_noise() -> None:
    candidates = [
        RankedEvidenceCandidate(
            candidate_id="chunk-public",
            logical_document_id="document-public",
            evidence_ids=frozenset(),
        ),
        RankedEvidenceCandidate(
            candidate_id="chunk-secret",
            logical_document_id="document-secret",
            evidence_ids=frozenset({"secret-evidence"}),
        ),
    ]

    denied = evaluate_no_answer_ranking(
        candidates,
        expected_non_answer_reason="acl_denied",
        protected_document_ids=frozenset({"document-secret"}),
        cutoff=8,
    )
    unknown = evaluate_no_answer_ranking(
        candidates,
        expected_non_answer_reason="unknown",
        protected_document_ids=frozenset(),
        cutoff=8,
    )

    assert denied.false_recall is True
    assert denied.first_forbidden_rank == 2
    assert unknown.false_recall is None
    assert unknown.first_forbidden_rank is None
    assert unknown.returned_candidate_count == 2


def test_inactive_index_probe_does_not_confuse_active_document_with_old_generation() -> (
    None
):
    candidates = [
        RankedEvidenceCandidate(
            candidate_id="active-chunk",
            logical_document_id="operations-document",
            version_id="active-version",
            index_set_id="active-index",
            evidence_ids=frozenset(),
        )
    ]

    result = evaluate_no_answer_ranking(
        candidates,
        expected_non_answer_reason="version_unavailable",
        protected_document_ids=frozenset(),
        protected_version_ids=frozenset({"old-version"}),
        protected_index_set_ids=frozenset({"old-index"}),
        cutoff=8,
    )

    assert result.false_recall is False
    assert result.first_forbidden_rank is None


def test_retrieval_plan_screens_depth_before_rrf_without_cartesian_product() -> None:
    plan = build_bounded_retrieval_plan(selected_depth=20)

    assert [(item.candidate_depth, item.rrf_k) for item in plan] == [
        (10, 60),
        (20, 60),
        (30, 60),
        (20, 20),
        (20, 100),
    ]
    assert sum(item.production_baseline for item in plan) == 0

    baseline = build_bounded_retrieval_plan(
        selected_depth=30,
        production_chunk_baseline=True,
    )
    assert sum(item.production_baseline for item in baseline) == 1
    assert next(item for item in baseline if item.production_baseline) == baseline[2]


def test_route_report_requires_complete_contiguous_ranked_candidates() -> None:
    first = RetrievalCandidateTrace.model_validate(
        {
            "chunk_id": "00000000-0000-0000-0000-000000000001",
            "document_id": "00000000-0000-0000-0000-000000000002",
            "version_id": "00000000-0000-0000-0000-000000000003",
            "index_set_id": "00000000-0000-0000-0000-000000000004",
            "logical_document_id": "document-one",
            "rank": 1,
            "body_text_sha256": "0123456789abcdef" * 4,
            "source_locator": {"source_type": "pdf", "page_number": 1},
            "dense_rank": 1,
            "dense_similarity": 0.9,
            "lexical_rank": None,
            "lexical_score": None,
            "rrf_score": None,
            "matched_evidence_ids": ["case-001-evidence-001"],
        }
    )
    second = first.model_copy(
        update={
            "chunk_id": "00000000-0000-0000-0000-000000000005",
            "rank": 2,
            "dense_rank": 2,
            "matched_evidence_ids": [],
        }
    )

    trace = RetrievalRouteTrace(
        mode="dense",
        requested_candidate_depth=5,
        returned_candidate_count=2,
        latency_ms=4,
        candidates=[first, second],
    )
    assert [item.rank for item in trace.candidates] == [1, 2]

    with pytest.raises(ValueError, match="contiguous"):
        RetrievalRouteTrace(
            mode="dense",
            requested_candidate_depth=5,
            returned_candidate_count=2,
            latency_ms=4,
            candidates=[first, second.model_copy(update={"rank": 3})],
        )
