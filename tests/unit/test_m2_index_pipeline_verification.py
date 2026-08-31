from __future__ import annotations

import importlib
from copy import deepcopy
from types import ModuleType
from typing import Any

import pytest

from app.core.config import BGE_M3_MODEL_ID, BGE_M3_REVISION


def _verifier() -> ModuleType:
    try:
        return importlib.import_module("scripts.verify_m2_index_pipeline")
    except ModuleNotFoundError:
        pytest.fail("M2-15.6 index pipeline verifier is missing")


def test_formal_index_chunk_counts_are_frozen_independently() -> None:
    verifier = _verifier()

    assert verifier.EXPECTED_FORMAL_CHUNK_COUNTS == {
        "mushroom_lamp_manual": 7,
        "quality_inspection_sop": 6,
        "de_compliance_checklist": 5,
        "supplier_quotes": 2,
        "monthly_operations": 1,
        "scanned_receiving_ticket": 2,
        "two_column_market_brief": 4,
        "merged_header_cost_table": 2,
        "visual_quality_notice": 4,
        "multi_region_replenishment": 2,
    }
    assert sum(verifier.EXPECTED_FORMAL_CHUNK_COUNTS.values()) == 35


def test_fake_decision_requires_retry_rows_reuse_and_clean_restore() -> None:
    verifier = _verifier()
    report: dict[str, Any] = {
        "schema_version": "m2-index-pipeline-report-v1",
        "provider": {
            "model_id": "fake/m2-deterministic",
            "revision": "m2-fake-v1",
        },
        "aggregate": {
            "documents_total": 10,
            "documents_ready": 10,
            "chunk_count": 35,
            "text_chunk_count": 27,
            "table_chunk_count": 8,
            "embedding_count": 35,
            "fts_count": 35,
            "row_audits_passed": 10,
            "repeat_reused": 10,
            "index_set_count_after_repeat": 10,
            "chunk_count_after_repeat": 35,
            "failure_recorded": True,
            "failure_retry_succeeded": True,
            "retried_attempt_count": 2,
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

    assert verifier.fake_index_pipeline_complete(report) is True

    mutations = []
    for section, field, bad_value in (
        ("aggregate", "documents_ready", 9),
        ("aggregate", "chunk_count", 34),
        ("aggregate", "embedding_count", 34),
        ("aggregate", "row_audits_passed", 9),
        ("aggregate", "repeat_reused", 9),
        ("aggregate", "failure_retry_succeeded", False),
        ("aggregate", "retried_attempt_count", 1),
        ("cleanup", "baseline_restored", False),
    ):
        changed = deepcopy(report)
        changed[section][field] = bad_value
        mutations.append(changed)

    assert all(
        verifier.fake_index_pipeline_complete(changed) is False for changed in mutations
    )


def test_bge_decision_requires_pinned_identity_vectors_reuse_and_cleanup() -> None:
    verifier = _verifier()
    report: dict[str, Any] = {
        "schema_version": "m2-index-bge-smoke-v1",
        "model": {
            "model_id": BGE_M3_MODEL_ID,
            "revision": BGE_M3_REVISION,
            "dimensions": 1024,
        },
        "index": {
            "status": "ready",
            "chunk_count": 7,
            "embedding_count": 7,
            "reused": True,
            "same_index_set": True,
        },
        "cleanup": {"baseline_restored": True},
    }

    assert verifier.bge_index_smoke_complete(report) is True

    wrong_revision = deepcopy(report)
    wrong_revision["model"]["revision"] = "floating-main"
    missing_vector = deepcopy(report)
    missing_vector["index"]["embedding_count"] = 6
    not_reused = deepcopy(report)
    not_reused["index"]["reused"] = False

    assert verifier.bge_index_smoke_complete(wrong_revision) is False
    assert verifier.bge_index_smoke_complete(missing_vector) is False
    assert verifier.bge_index_smoke_complete(not_reused) is False
