from __future__ import annotations

import importlib
from copy import deepcopy
from types import ModuleType
from typing import Any

import pytest

from app.core.config import BGE_M3_MODEL_ID, BGE_M3_REVISION


def _verifier() -> ModuleType:
    try:
        return importlib.import_module("scripts.verify_m2_retrieval")
    except ModuleNotFoundError:
        pytest.fail("M2-16.7 retrieval verifier is missing")


def _complete_fake_report() -> dict[str, Any]:
    return {
        "schema_version": "m2-retrieval-report-v1",
        "provider": {
            "model_id": "fake/m2-deterministic",
            "revision": "m2-fake-v1",
        },
        "index": {"documents_ready": 10, "chunks": 35, "embeddings": 35},
        "retrieval": {
            "questions_total": 20,
            "dense_document_hits": 9,
            "lexical_document_hits": 18,
            "hybrid_document_hits": 18,
            "hybrid_evidence_hits": 18,
            "hybrid_locator_hits": 18,
            "deterministic_queries": 20,
            "known_unretrievable_facts": 2,
        },
        "security": {
            "owner_can_access_all": True,
            "de_market_acl_allowed": True,
            "fr_market_mismatch_denied": True,
            "role_acl_allowed": True,
            "role_acl_mismatch_denied": True,
            "inactive_version_denied": True,
            "inactive_index_set_denied": True,
            "soft_deleted_document_denied": True,
            "soft_deleted_file_denied": True,
        },
        "indexes": {"gin_available": True, "hnsw_available": True},
        "latency": {
            "sample_count": 20,
            "dense_p95_ms": 4.2,
            "lexical_p95_ms": 2.1,
            "hybrid_p95_ms": 6.8,
            "routing_conclusion": "insufficient_scale_keep_default_hybrid",
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


def test_fake_retrieval_decision_requires_quality_security_indexes_and_restore() -> (
    None
):
    verifier = _verifier()
    report = _complete_fake_report()

    assert verifier.fake_retrieval_verification_complete(report) is True

    mutations = []
    for section, field, bad_value in (
        ("index", "chunks", 34),
        ("retrieval", "questions_total", 19),
        ("retrieval", "hybrid_document_hits", 17),
        ("retrieval", "hybrid_evidence_hits", 17),
        ("retrieval", "hybrid_locator_hits", 17),
        ("retrieval", "deterministic_queries", 19),
        ("security", "fr_market_mismatch_denied", False),
        ("security", "inactive_index_set_denied", False),
        ("indexes", "gin_available", False),
        ("latency", "sample_count", 19),
        ("cleanup", "baseline_restored", False),
    ):
        changed = deepcopy(report)
        changed[section][field] = bad_value
        mutations.append(changed)

    assert all(
        verifier.fake_retrieval_verification_complete(changed) is False
        for changed in mutations
    )


def test_bge_retrieval_decision_requires_pinned_offline_hybrid_evidence() -> None:
    verifier = _verifier()
    report: dict[str, Any] = {
        "schema_version": "m2-retrieval-bge-smoke-v1",
        "offline_inference": True,
        "model": {
            "model_id": BGE_M3_MODEL_ID,
            "revision": BGE_M3_REVISION,
            "dimensions": 1024,
        },
        "retrieval": {
            "query": "这款台灯需要多少伏特供电？",
            "dense_hit": True,
            "hybrid_hit": True,
            "evidence_hit": True,
            "has_dense_score": True,
            "has_lexical_score": True,
        },
        "cleanup": {"baseline_restored": True},
    }

    assert verifier.bge_retrieval_smoke_complete(report) is True

    wrong_revision = deepcopy(report)
    wrong_revision["model"]["revision"] = "floating-main"
    missing_evidence = deepcopy(report)
    missing_evidence["retrieval"]["evidence_hit"] = False
    online = deepcopy(report)
    online["offline_inference"] = False

    assert verifier.bge_retrieval_smoke_complete(wrong_revision) is False
    assert verifier.bge_retrieval_smoke_complete(missing_evidence) is False
    assert verifier.bge_retrieval_smoke_complete(online) is False
