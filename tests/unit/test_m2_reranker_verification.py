from __future__ import annotations

import importlib
from copy import deepcopy
from types import ModuleType
from typing import Any

import pytest

from app.core.config import BGE_RERANKER_MODEL_ID, BGE_RERANKER_REVISION


def _verifier() -> ModuleType:
    try:
        return importlib.import_module("scripts.verify_m2_reranker")
    except ModuleNotFoundError:
        pytest.fail("M2-17.5 Reranker verifier is missing")


def _query_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(1, 19):
        rows.append(
            {
                "case_id": f"document-{index}:1",
                "document_key": f"document-{index}",
                "fact_number": 1,
                "question": f"合成问题{index}",
                "excluded": False,
                "exclusion_reason": None,
                "rrf_first_evidence_rank": index if index <= 8 else 9,
                "reranker_first_evidence_rank": ((index - 1) % 8) + 1,
                "rrf_evidence_ranks": [index if index <= 8 else 9],
                "reranker_evidence_ranks": [((index - 1) % 8) + 1],
            }
        )
    for fact_number in (1, 2):
        rows.append(
            {
                "case_id": f"visual_quality_notice:{fact_number}",
                "document_key": "visual_quality_notice",
                "fact_number": fact_number,
                "question": "图片事实",
                "excluded": True,
                "exclusion_reason": "upstream_image_text_not_extracted",
                "rrf_first_evidence_rank": None,
                "reranker_first_evidence_rank": None,
                "rrf_evidence_ranks": [],
                "reranker_evidence_ranks": [],
            }
        )
    return rows


def _complete_report() -> dict[str, Any]:
    verifier = _verifier()
    rows = _query_rows()
    return {
        "schema_version": "m2-reranker-verification-v1",
        "synthetic_data": True,
        "offline_inference": True,
        "snapshot_verified": True,
        "model": {
            "model_id": BGE_RERANKER_MODEL_ID,
            "revision": BGE_RERANKER_REVISION,
        },
        "index": {"documents_ready": 10, "chunks": 35, "embeddings": 35},
        "corpus": {
            "questions_total": 20,
            "evaluated_questions": 18,
            "excluded_questions": 2,
            "excluded_case_ids": [
                "visual_quality_notice:1",
                "visual_quality_notice:2",
            ],
        },
        "queries": rows,
        "metrics": verifier.build_quality_metrics(rows),
        "latency": {
            "sample_count": 20,
            "hybrid_p50_ms": 40.0,
            "hybrid_p95_ms": 50.0,
            "reranker_p50_ms": 400.0,
            "reranker_p95_ms": 500.0,
            "end_to_end_p50_ms": 440.0,
            "end_to_end_p95_ms": 550.0,
            "cold_reranker_ms": 7000.0,
            "rss_peak_mib": 2050.0,
            "rss_peak_delta_mib": 1700.0,
        },
        "cleanup": {
            "baseline_restored": True,
            "remaining_publication_keys": [],
            "database_counts": {
                "files": 10,
                "documents": 10,
                "versions": 10,
                "acl": 9,
                "chunk_sets": 0,
                "index_sets": 0,
                "chunks": 0,
                "embeddings": 0,
            },
        },
    }


def test_quality_metrics_compare_the_same_fixed_eighteen_cases_at_eight() -> None:
    verifier = _verifier()
    rows = [
        {
            "excluded": False,
            "rrf_first_evidence_rank": 1,
            "reranker_first_evidence_rank": 2,
        },
        {
            "excluded": False,
            "rrf_first_evidence_rank": 9,
            "reranker_first_evidence_rank": None,
        },
        {
            "excluded": True,
            "rrf_first_evidence_rank": None,
            "reranker_first_evidence_rank": None,
        },
    ]

    metrics = verifier.build_quality_metrics(rows)

    assert metrics == {
        "denominator": 2,
        "rrf": {"hits_at_8": 1, "recall_at_8": 0.5, "mrr_at_8": 0.5},
        "reranker": {"hits_at_8": 1, "recall_at_8": 0.5, "mrr_at_8": 0.25},
        "delta": {"recall_at_8": 0.0, "mrr_at_8": -0.25},
        "quality_conclusion": "regressed",
    }


def test_completion_requires_pinned_model_fixed_cases_metrics_latency_and_restore() -> (
    None
):
    verifier = _verifier()
    report = _complete_report()

    assert verifier.reranker_verification_complete(report) is True

    mutations: list[tuple[str, str, object]] = [
        ("model", "revision", "floating-main"),
        ("corpus", "evaluated_questions", 17),
        ("corpus", "excluded_questions", 1),
        ("latency", "sample_count", 19),
        ("latency", "reranker_p95_ms", float("nan")),
        ("cleanup", "baseline_restored", False),
    ]
    changed_reports = []
    for section, field, value in mutations:
        changed = deepcopy(report)
        changed[section][field] = value
        changed_reports.append(changed)

    wrong_exclusion = deepcopy(report)
    wrong_exclusion["corpus"]["excluded_case_ids"] = ["easy:1", "easy:2"]
    changed_reports.append(wrong_exclusion)
    dishonest_metrics = deepcopy(report)
    dishonest_metrics["metrics"]["reranker"]["recall_at_8"] = 0.0
    changed_reports.append(dishonest_metrics)
    missing_query = deepcopy(report)
    missing_query["queries"].pop()
    changed_reports.append(missing_query)

    assert all(
        verifier.reranker_verification_complete(changed) is False
        for changed in changed_reports
    )


def test_known_upstream_exclusions_are_frozen() -> None:
    verifier = _verifier()

    assert verifier.KNOWN_UPSTREAM_UNRETRIEVABLE_CASE_IDS == (
        "visual_quality_notice:1",
        "visual_quality_notice:2",
    )
