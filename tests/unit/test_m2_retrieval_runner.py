from __future__ import annotations

from uuid import UUID

import pytest

from app.evals.retrieval_runner import (
    FrozenChunkCandidate,
    RetrievalEvaluationDenseMappingError,
    _candidate_mapping_quality_gate,
    _hybrid_first_failure_layer,
    _ranked_candidates,
    _validate_dense_candidates,
    build_frozen_chunk_candidates,
    case_reporting_cohort,
    trace_retrieval_response,
)
from app.repositories.retrieval import DenseCandidateRecord
from app.schemas.evaluation import EvaluationCase
from app.schemas.retrieval import RetrievalCandidateFailure, RetrievalResponse
from scripts.run_m2_retrieval_evaluation import _parse_args, _resolve_run_scope


def test_only_m2_22_5_frozen_chunk_candidates_enter_retrieval_matrix() -> None:
    candidates = build_frozen_chunk_candidates()

    assert len(candidates) == 10
    assert sum(item.production_baseline for item in candidates) == 1
    assert {item.config.config_id for item in candidates} == {
        "chunk-current",
        "chunk-compact-overlap-080",
        "chunk-compact-overlap-100",
        "chunk-compact-overlap-120",
        "chunk-medium-overlap-080",
        "chunk-medium-overlap-100",
        "chunk-medium-overlap-120",
        "chunk-large-overlap-080",
        "chunk-large-overlap-100",
        "chunk-large-overlap-120",
    }
    assert all(isinstance(item, FrozenChunkCandidate) for item in candidates)


def test_ragas_selected_only_cli_freezes_the_authorized_resume_scope() -> None:
    args = _parse_args(["--ragas-selected-only"])

    candidates, depths, rrf_constants = _resolve_run_scope(args)

    assert candidates is not None
    assert [item.config.config_id for item in candidates] == [
        "chunk-compact-overlap-100"
    ]
    assert depths == (10,)
    assert rrf_constants == (60,)


@pytest.mark.parametrize(
    "conflict",
    (
        ["--config-id", "chunk-current"],
        ["--case-id", "smoke-syn-001-voltage"],
        ["--no-ragas"],
        ["--baseline-only"],
    ),
)
def test_ragas_selected_only_cli_rejects_scope_expansion_or_semantic_skip(
    conflict: list[str],
) -> None:
    with pytest.raises(SystemExit):
        _parse_args(["--ragas-selected-only", *conflict])


def test_reporting_cohort_separates_real_synthetic_diagnostic_and_safety() -> None:
    def case(**updates: object) -> EvaluationCase:
        payload: dict[str, object] = {
            "case_id": "case-001",
            "dataset_version": "dataset-v1",
            "split": "debug",
            "question": "Question?",
            "language": "en",
            "category": "ordinary_fact",
            "difficulty": "direct",
            "source_group": "synthetic_engineering_regression",
            "expected_document_ids": ["document-one"],
            "expected_evidence_spans": [
                {
                    "source_id": "m2-v1-document-one",
                    "document_id": "document-one",
                    "source_type": "pdf",
                    "page_start": 1,
                    "page_end": 1,
                    "exact_text": "Exact evidence",
                }
            ],
            "answer_key_points": ["Exact evidence"],
            "should_answer": True,
            "trusted_user_fixture_id": "user-fixture-eval-reader",
            "acl_fixture_id": "acl-fixture-tenant",
            "version_fixture_id": "version-fixture-active",
        }
        payload.update(updates)
        return EvaluationCase.model_validate(payload)

    assert case_reporting_cohort(case()) == "synthetic_cross_border"
    assert (
        case_reporting_cohort(
            case(
                case_id="case-002",
                expected_evidence_spans=[
                    {
                        "source_id": "m2-complex-v1-two-column-market-brief",
                        "document_id": "document-one",
                        "source_type": "pdf",
                        "page_start": 1,
                        "page_end": 1,
                        "exact_text": "Exact evidence",
                    }
                ],
            )
        )
        == "general_diagnostics"
    )
    assert (
        case_reporting_cohort(
            case(case_id="case-003", source_group="cross_border_core")
        )
        == "real_cross_border"
    )
    assert (
        case_reporting_cohort(
            case(case_id="case-004", source_group="security_acl_version")
        )
        == "safety_acl_version"
    )


def test_trace_keeps_the_complete_ordered_route_not_only_metric_topk() -> None:
    response = RetrievalResponse.model_validate(
        {
            "mode": "dense",
            "embedding_identity": {
                "contract_version": "m2-embedding-provider-v1",
                "provider": "fake",
                "model_id": "fake/m2-deterministic",
                "revision": "m2-fake-v1",
                "pooling": "sha256-shake-v1",
                "max_length": 8192,
                "normalize": True,
                "precision": "float32",
                "dimensions": 1024,
            },
            "results": [
                {
                    "identity": {
                        "document_id": f"00000000-0000-0000-0000-{i:012d}",
                        "version_id": "10000000-0000-0000-0000-000000000001",
                        "index_set_id": "20000000-0000-0000-0000-000000000001",
                        "chunk_id": f"30000000-0000-0000-0000-{i:012d}",
                    },
                    "document": {
                        "title": "Document",
                        "document_type": "manual",
                        "language": "en",
                        "market": None,
                    },
                    "body_text": f"body {i}",
                    "source_locator": {"source_type": "pdf", "page_number": 1},
                    "scores": {
                        "dense": {"rank": i, "distance": 0.1, "similarity": 0.9}
                    },
                    "final_rank": i,
                }
                for i in range(1, 11)
            ],
        }
    )
    logical_ids = {
        UUID(f"00000000-0000-0000-0000-{i:012d}"): f"document-{i:03d}"
        for i in range(1, 11)
    }

    trace = trace_retrieval_response(
        response,
        requested_candidate_depth=10,
        latency_ms=7,
        logical_document_ids=logical_ids,
        evidence_ids_by_chunk={},
    )

    assert trace.returned_candidate_count == 10
    assert trace.candidate_failures == []
    assert [candidate.rank for candidate in trace.candidates] == list(range(1, 11))
    assert trace.candidates[-1].logical_document_id == "document-010"


def test_trace_records_mapping_failure_and_metrics_keep_the_original_rank() -> None:
    document_id = UUID("00000000-0000-0000-0000-000000000002")
    chunk_id = UUID("30000000-0000-0000-0000-000000000002")
    response = RetrievalResponse.model_validate(
        {
            "mode": "dense",
            "embedding_identity": {
                "contract_version": "m2-embedding-provider-v1",
                "provider": "fake",
                "model_id": "fake/m2-deterministic",
                "revision": "m2-fake-v1",
                "pooling": "sha256-shake-v1",
                "max_length": 8192,
                "normalize": True,
                "precision": "float32",
                "dimensions": 1024,
            },
            "results": [
                {
                    "identity": {
                        "document_id": str(document_id),
                        "version_id": "10000000-0000-0000-0000-000000000002",
                        "index_set_id": "20000000-0000-0000-0000-000000000002",
                        "chunk_id": str(chunk_id),
                    },
                    "document": {
                        "title": "Document",
                        "document_type": "manual",
                        "language": "en",
                        "market": None,
                    },
                    "body_text": "evidence body",
                    "source_locator": {"source_type": "pdf", "page_number": 1},
                    "scores": {
                        "dense": {"rank": 2, "distance": 0.1, "similarity": 0.9}
                    },
                    "final_rank": 2,
                }
            ],
            "candidate_failures": [
                RetrievalCandidateFailure(
                    source_mode="dense",
                    rank=1,
                    chunk_id=UUID("30000000-0000-0000-0000-000000000001"),
                )
            ],
        }
    )

    trace = trace_retrieval_response(
        response,
        requested_candidate_depth=10,
        latency_ms=7,
        logical_document_ids={document_id: "document-002"},
        evidence_ids_by_chunk={chunk_id: frozenset({"case-evidence-001"})},
    )
    ranked = _ranked_candidates(trace)

    assert trace.returned_candidate_count == 1
    assert trace.candidate_failures[0].rank == 1
    assert trace.candidates[0].rank == 2
    assert len(ranked) == 2
    assert ranked[0].evidence_ids == frozenset()
    assert ranked[1].evidence_ids == frozenset({"case-evidence-001"})
    assert _candidate_mapping_quality_gate([trace]) is False


def test_dense_mapping_diagnostic_preserves_the_first_invalid_chunk() -> None:
    candidate = DenseCandidateRecord(
        chunk_id=UUID("30000000-0000-0000-0000-000000000001"),
        document_id=UUID("00000000-0000-0000-0000-000000000001"),
        version_id=UUID("10000000-0000-0000-0000-000000000001"),
        index_set_id=UUID("20000000-0000-0000-0000-000000000001"),
        title="Document",
        document_type="manual",
        language="en",
        market=None,
        body_text="body",
        file_extension=".pdf",
        heading_path=[],
        page_numbers=[],
        source_block_ids=["b000001"],
        source_spans=[],
        table_json=None,
        distance=0.1,
    )

    try:
        _validate_dense_candidates([candidate])
    except RetrievalEvaluationDenseMappingError as error:
        assert str(candidate.chunk_id) in str(error)
        assert "source span is missing" in str(error)
    else:
        raise AssertionError("invalid Dense candidate must retain its exact cause")


def test_hybrid_bad_case_is_not_blamed_on_rrf_when_both_inputs_missed() -> None:
    assert (
        _hybrid_first_failure_layer(
            dense_hit_at_8=False,
            lexical_hit_at_8=False,
        )
        is None
    )
    assert (
        _hybrid_first_failure_layer(
            dense_hit_at_8=True,
            lexical_hit_at_8=False,
        )
        == "RRF fusion"
    )
