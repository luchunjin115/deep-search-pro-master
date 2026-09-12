from __future__ import annotations

import json
import os

import pytest

from app.db.session import create_database_runtime
from app.evals.answer_citation_formal import (
    run_m2_answer_citation_gateway_evaluation,
)
from app.evals.rag_runner import PROJECT_ROOT
from app.evals.reranker_context_corpus import (
    build_m2_reranker_context_evidence_map,
    load_existing_m2_reranker_context_corpus,
)
from app.services.retrieval import (
    BgeM3EmbeddingProvider,
    BgeRerankerProvider,
    create_embedding_provider,
    create_reranker_provider,
)
from app.services.storage import LocalStorageBackend
from scripts.run_m2_answer_citation_evaluation import _gateway_model_settings


@pytest.mark.skipif(
    os.getenv("RUN_M2_ANSWER_GATEWAY_SMOKE") != "1",
    reason="set RUN_M2_ANSWER_GATEWAY_SMOKE=1 for the retained-corpus Gateway run",
)
def test_fixed_40_cases_cross_the_real_gateway_and_clean_runtime_rows() -> None:
    settings, reranker_settings = _gateway_model_settings()
    storage = LocalStorageBackend(settings.local_storage_root)
    runtime = create_database_runtime(settings)
    try:
        embedding = create_embedding_provider(settings)
        reranker = create_reranker_provider(reranker_settings)
        assert isinstance(embedding, BgeM3EmbeddingProvider)
        assert isinstance(reranker, BgeRerankerProvider)
        snapshot = load_existing_m2_reranker_context_corpus(
            settings=settings,
            runtime=runtime,
            project_root=PROJECT_ROOT,
            embedding_provider=embedding,
        )
        evidence_map = build_m2_reranker_context_evidence_map(
            runtime=runtime,
            storage=storage,
            project_root=PROJECT_ROOT,
            snapshot=snapshot,
        )
        report = run_m2_answer_citation_gateway_evaluation(
            settings=settings,
            runtime=runtime,
            storage=storage,
            snapshot=snapshot,
            embedding_provider=embedding,
            reranker_provider=reranker,
            evidence_ids_by_chunk=evidence_map,
            project_root=PROJECT_ROOT,
        )

        assert report.execution_mode == "real_gateway_fake_answer"
        failed_audits = [
            {
                "case_id": item.case_id,
                "api_status_code": item.api_status_code,
                "api_error_code": item.api_error_code,
                "search_knowledge_tool_status": item.search_knowledge_tool_status,
                "search_knowledge_duration_ms": item.search_knowledge_duration_ms,
                "search_knowledge_error_code": item.search_knowledge_error_code,
                "failure_summary": item.failure_summary,
            }
            for item in report.chain_audits
            if item.chain_passed is not True
        ]
        tool_durations = sorted(
            item.search_knowledge_duration_ms
            for item in report.chain_audits
            if item.search_knowledge_duration_ms is not None
        )
        print(
            json.dumps(
                {
                    "run_status": report.run_status,
                    "failed_audits": failed_audits,
                    "chain_passed_cases": sum(
                        item.chain_passed is True for item in report.chain_audits
                    ),
                    "tool_duration_min_ms": min(tool_durations),
                    "tool_duration_max_ms": max(tool_durations),
                    "runtime_identity": report.runtime_identity.model_dump(mode="json"),
                    "answer_compose_calls": report.answer_compose_calls,
                    "lifecycle": report.lifecycle.model_dump(mode="json"),
                    "corpus_restored": report.corpus_before == report.corpus_after,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        assert report.run_status == "completed", failed_audits
        assert report.quality_gate_passed is None
        assert len(report.case_results) == 40
        assert len(report.chain_audits) == 40
        assert all(item.api_status_code == 200 for item in report.chain_audits)
        assert all(
            item.allowed_successful_tool_call_count == 1 for item in report.chain_audits
        )
        assert len(tool_durations) == 40
        assert max(tool_durations) < 8000
        assert all(item.chain_passed is True for item in report.chain_audits)
        assert all(
            item.protected_evidence_leak_count == 0 for item in report.chain_audits
        )
        assert report.answer_compose_calls == sum(
            item.provider_evidence_count > 0 for item in report.chain_audits
        )
        assert report.runtime_identity.embedding_device == "cpu"
        assert report.runtime_identity.reranker_device == "cuda"
        assert report.runtime_identity.business_max_evidence == 0
        assert report.runtime_identity.knowledge_max_evidence == 12
        assert report.grouped_results.all_answerable.expected_case_count == 34
        assert report.grouped_results.safety_acl_version.expected_case_count == 6
        assert report.grouped_results.safety_acl_version.safety_leakage_count == 0
        assert report.lifecycle.baseline_restored is True
        assert report.corpus_before == report.corpus_after
        assert report.corpus_after.source_count == 18
        assert report.corpus_after.document_count == 18
        assert report.corpus_after.chunk_set_count == 18
        assert report.corpus_after.chunk_count == 779
    finally:
        runtime.engine.dispose()
