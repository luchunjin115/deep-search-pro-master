from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import pytest

from app.evals.reranker_context_report import FakeRerankerIdentity
from app.evals.reranker_context_runner import (
    DeterministicFakeReranker,
    InMemoryFakeContextReader,
    RunScoringCache,
    build_fake_case_inputs_from_dataset,
    run_m2_reranker_context_fake_evaluation,
)

ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "data" / "evals" / "m2_cross_border_rag_smoke_v1.jsonl"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_fake_runner_uses_one_provider_call_per_case_and_the_bounded_plan() -> None:
    cases, dataset_version, dataset_sha256 = build_fake_case_inputs_from_dataset(
        DATASET_PATH
    )
    scorer = DeterministicFakeReranker()
    context_reader = InMemoryFakeContextReader()

    report = run_m2_reranker_context_fake_evaluation(
        cases=cases,
        dataset_version=dataset_version,
        dataset_sha256=dataset_sha256,
        selected_top_k=5,
        scorer=scorer,
        context_reader=context_reader,
    )

    assert report.execution_mode == "deterministic_fake"
    assert report.run_status == "completed"
    assert report.quality_gate_passed is None
    assert len(report.experiment_points) == 8
    assert len(report.answerable_results) == 34
    assert len(report.safety_results) == 6
    assert all(len(item.trace.comparisons) == 2 for item in report.answerable_results)
    assert all(
        len(item.trace.context_results) == 6 for item in report.answerable_results
    )
    assert scorer.call_count == 40
    assert context_reader.call_count == 34 * 6 + 6
    assert report.cache.score_requests == 34 * 8 + 6
    assert report.cache.cache_misses == 40
    assert report.cache.cache_hits == 34 * 7
    assert report.cache.provider_score_calls == 40
    assert report.cache.cache_entries == 40


def test_fake_runner_is_byte_deterministic_and_keeps_an_upstream_miss() -> None:
    cases, dataset_version, dataset_sha256 = build_fake_case_inputs_from_dataset(
        DATASET_PATH
    )
    first_case = cases[0]
    candidates_without_golden = tuple(
        replace(candidate, evidence_ids=frozenset())
        for candidate in first_case.candidates
    )
    cases_with_miss = (
        replace(first_case, candidates=candidates_without_golden),
        *cases[1:],
    )

    first = run_m2_reranker_context_fake_evaluation(
        cases=cases_with_miss,
        dataset_version=dataset_version,
        dataset_sha256=dataset_sha256,
        selected_top_k=8,
        scorer=DeterministicFakeReranker(),
        context_reader=InMemoryFakeContextReader(),
    )
    second = run_m2_reranker_context_fake_evaluation(
        cases=cases_with_miss,
        dataset_version=dataset_version,
        dataset_sha256=dataset_sha256,
        selected_top_k=8,
        scorer=DeterministicFakeReranker(),
        context_reader=InMemoryFakeContextReader(),
    )

    assert first.model_dump_json() == second.model_dump_json()
    missed = first.answerable_results[0].trace.comparisons
    assert [item.rank_change for item in missed] == [
        "candidate_missing",
        "candidate_missing",
    ]
    assert all(item.reranker_first_golden_rank is None for item in missed)
    assert all(item.trace_sha256 for item in first.answerable_results)
    assert all(item.trace_sha256 for item in first.safety_results)


def test_run_cache_key_binds_query_ordered_body_hashes_and_model_identity() -> None:
    cases, _dataset_version, _dataset_sha256 = build_fake_case_inputs_from_dataset(
        DATASET_PATH
    )
    case = cases[0]
    candidates = case.candidates[:2]
    cache = RunScoringCache()
    scorer = DeterministicFakeReranker()

    first = cache.get_or_score(
        query=case.question,
        candidates=candidates,
        scorer=scorer,
    )
    repeated = cache.get_or_score(
        query=case.question,
        candidates=candidates,
        scorer=scorer,
    )
    cache.get_or_score(
        query=f"{case.question}?",
        candidates=candidates,
        scorer=scorer,
    )
    cache.get_or_score(
        query=case.question,
        candidates=tuple(reversed(candidates)),
        scorer=scorer,
    )
    changed_body = f"{candidates[0].body_text} changed"
    cache.get_or_score(
        query=case.question,
        candidates=(
            replace(
                candidates[0],
                body_text=changed_body,
                body_text_sha256=_sha256(changed_body),
            ),
            candidates[1],
        ),
        scorer=scorer,
    )
    other_identity = DeterministicFakeReranker(
        identity=FakeRerankerIdentity(
            model_id="fake/m2-deterministic-reranker-alt",
            revision="m2-fake-v2",
        )
    )
    cache.get_or_score(
        query=case.question,
        candidates=candidates,
        scorer=other_identity,
    )

    assert first == repeated
    assert scorer.call_count == 4
    assert other_identity.call_count == 1
    assert cache.stats().score_requests == 6
    assert cache.stats().cache_hits == 1
    assert cache.stats().cache_misses == 5
    assert cache.stats().cache_entries == 5


class _FailOnceScorer:
    identity = FakeRerankerIdentity(
        model_id="fake/m2-fail-once",
        revision="m2-fake-v1",
    )

    def __init__(self) -> None:
        self.call_count = 0

    def score(self, query: str, documents: Sequence[str]) -> tuple[float, ...]:
        del query
        self.call_count += 1
        if self.call_count == 1:
            raise RuntimeError("expected fake scorer failure")
        return tuple(float(index) for index, _document in enumerate(documents))


def test_failed_score_is_not_cached() -> None:
    cases, _dataset_version, _dataset_sha256 = build_fake_case_inputs_from_dataset(
        DATASET_PATH
    )
    case = cases[0]
    scorer = _FailOnceScorer()
    cache = RunScoringCache()

    with pytest.raises(RuntimeError, match="expected fake scorer failure"):
        cache.get_or_score(
            query=case.question,
            candidates=case.candidates,
            scorer=scorer,
        )
    scores = cache.get_or_score(
        query=case.question,
        candidates=case.candidates,
        scorer=scorer,
    )

    assert len(scores) == len(case.candidates)
    assert scorer.call_count == 2
    assert cache.stats().cache_entries == 1
    assert cache.stats().cache_misses == 2
