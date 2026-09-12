from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.evals.rag_runner import _load_cases
from app.evals.reranker_context_metrics import (
    aggregate_context_quality,
    aggregate_reranker_comparisons,
)
from app.evals.reranker_context_report import (
    BgeRerankerFormalIdentity,
    FormalEvaluationMeasurements,
    FormalRerankerContextEvaluationReport,
    FrozenRagCorpusPublicIdentity,
    PostgresContextReaderIdentity,
    RerankerContextCacheStats,
    serialize_public_report,
)
from app.evals.reranker_context_runner import (
    DeterministicFakeReranker,
    InMemoryFakeContextReader,
    build_fake_case_inputs_from_dataset,
    run_m2_reranker_context_fake_evaluation,
)
from app.evals.retrieval_runner import case_reporting_cohort
from app.schemas.retrieval import RetrievalEmbeddingIdentity, RetrievalFtsIdentity

ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "data" / "evals" / "m2_cross_border_rag_smoke_v1.jsonl"
GROUPS = (
    "all-answerable",
    "real-cross-border",
    "synthetic-cross-border",
    "general-diagnostics",
)


def _formal_report() -> FormalRerankerContextEvaluationReport:
    private_cases, version, dataset_sha256 = build_fake_case_inputs_from_dataset(
        DATASET_PATH
    )
    fake = run_m2_reranker_context_fake_evaluation(
        cases=private_cases,
        dataset_version=version,
        dataset_sha256=dataset_sha256,
        selected_top_k=5,
        scorer=DeterministicFakeReranker(),
        context_reader=InMemoryFakeContextReader(),
    )
    cases = _load_cases(DATASET_PATH)
    answerable = [case for case in cases if case.should_answer]
    group_ids = {
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
    comparisons = [
        comparison
        for result in fake.answerable_results
        for comparison in result.trace.comparisons
    ]
    reranker_aggregates = [
        aggregate_reranker_comparisons(
            [
                item
                for item in comparisons
                if item.top_k == top_k and item.case_id in group_ids[group_id]
            ],
            expected_case_ids=group_ids[group_id],
            group_id=group_id,
            top_k=top_k,
        )
        for top_k in (5, 8)
        for group_id in GROUPS
    ]
    all_top5 = reranker_aggregates[0]
    all_top8 = reranker_aggregates[4]
    assert all_top5.reranker_hit_count is not None
    assert all_top8.reranker_hit_count is not None
    selected_top_k = (
        8 if all_top8.reranker_hit_count > all_top5.reranker_hit_count else 5
    )
    if selected_top_k == 8:
        fake = run_m2_reranker_context_fake_evaluation(
            cases=private_cases,
            dataset_version=version,
            dataset_sha256=dataset_sha256,
            selected_top_k=8,
            scorer=DeterministicFakeReranker(),
            context_reader=InMemoryFakeContextReader(),
        )
    contexts = [
        context
        for result in fake.answerable_results
        for context in result.trace.context_results
    ]
    context_aggregates = [
        aggregate_context_quality(
            [
                item
                for item in contexts
                if item.case_id in group_ids[group_id]
                and item.context_neighbor_window == neighbor
                and item.context_max_tokens == tokens
            ],
            expected_case_ids=group_ids[group_id],
            group_id=group_id,
            reranker_top_k=selected_top_k,
            context_neighbor_window=neighbor,
            context_max_tokens=tokens,
        )
        for neighbor in (0, 1)
        for tokens in (2000, 3000, 4000)
        for group_id in GROUPS
    ]
    real_selected = next(
        item
        for item in reranker_aggregates
        if item.group_id == "real-cross-border" and item.top_k == selected_top_k
    )
    nonempty_answerable = sum(
        bool(item.trace.candidates) for item in fake.answerable_results
    )
    nonempty_safety = sum(bool(item.trace.candidates) for item in fake.safety_results)
    input_sha256 = "a" * 64
    return FormalRerankerContextEvaluationReport(
        run_id=f"m2-2275-{input_sha256[:16]}",
        quality_gate_passed=bool(
            real_selected.reranker_hit_rate_at_k is not None
            and real_selected.reranker_hit_rate_at_k >= 0.9
        ),
        selected_top_k=selected_top_k,
        plan=fake.plan,
        experiment_points=fake.experiment_points,
        dataset_version=version,
        dataset_sha256=dataset_sha256,
        input_sha256=input_sha256,
        corpus=FrozenRagCorpusPublicIdentity(
            corpus_sha256="b" * 64,
            index_sha256="c" * 64,
            snapshot_sha256="d" * 64,
            index_set_count=36,
        ),
        retrieval_embedding=RetrievalEmbeddingIdentity(
            contract_version="m2-embedding-provider-v1",
            provider="bge-m3-local",
            model_id="BAAI/bge-m3",
            revision="5617a9f61b028005a4858fdac845db406aefb181",
            pooling="cls",
            max_length=8192,
            normalize=True,
            precision="float32",
            dimensions=1024,
        ),
        retrieval_fts=RetrievalFtsIdentity(builder_version="m2-fts-text-v1"),
        scorer=BgeRerankerFormalIdentity(),
        context_reader=PostgresContextReaderIdentity(),
        cohort=fake.cohort,
        answerable_results=fake.answerable_results,
        reranker_aggregates=reranker_aggregates,
        context_aggregates=context_aggregates,
        safety_results=fake.safety_results,
        safety_gate_passed=True,
        cache=RerankerContextCacheStats(
            score_requests=nonempty_answerable * 2 + nonempty_safety,
            cache_hits=nonempty_answerable,
            cache_misses=nonempty_answerable + nonempty_safety,
            provider_score_calls=nonempty_answerable + nonempty_safety,
            cache_entries=nonempty_answerable + nonempty_safety,
        ),
        measurements=FormalEvaluationMeasurements(
            total_elapsed_seconds=1,
            reranker_load_seconds=1,
            scoring_latency_p50_ms=1,
            scoring_latency_p95_ms=2,
            scoring_latency_max_ms=3,
            effective_batch_size_min=2,
            effective_batch_size_max=2,
            rss_start_mib=100,
            rss_peak_mib=200,
            rss_peak_delta_mib=100,
        ),
        trace_set_sha256=fake.trace_set_sha256,
    )


def test_formal_report_separates_completion_from_quality_and_stays_public() -> None:
    report = _formal_report()
    payload = json.loads(serialize_public_report(report))

    assert report.evaluation_completed is True
    assert report.quality_gate_passed in {True, False}
    assert len(report.answerable_results) == 34
    assert len(report.safety_results) == 6
    assert len(report.reranker_aggregates) == 8
    assert len(report.context_aggregates) == 24
    serialized = json.dumps(payload)
    assert all(
        f'"{key}"' not in serialized
        for key in ("question", "body_text", "tenant_id", "storage_key")
    )


def test_formal_report_rejects_a_shrunk_group_denominator() -> None:
    report = _formal_report()
    payload = report.model_dump(mode="json")
    payload["reranker_aggregates"][0]["expected_case_count"] = 33

    with pytest.raises(ValidationError):
        FormalRerankerContextEvaluationReport.model_validate(payload)
