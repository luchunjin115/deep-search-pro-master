from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import pytest

from app.evals.reranker_context_report import (
    RerankerResourceProbeReport,
    write_reranker_resource_probe_report,
)
from app.evals.reranker_resource_probe import (
    RerankerResourceProbeError,
    build_m2_reranker_resource_probe_cases,
    run_m2_reranker_resource_probe,
)
from app.services.retrieval import (
    RerankerBatch,
    RerankerIdentity,
    RerankerPairScore,
    build_reranker_pair_key,
)


class _InjectedBgeProvider:
    def __init__(self, *, fail_on_load: bool = False) -> None:
        self.load_calls = 0
        self.score_calls = 0
        self.fail_on_load = fail_on_load
        self._identity = RerankerIdentity(
            contract_version="m2-reranker-provider-v1",
            provider="bge-reranker-local",
            model_id="BAAI/bge-reranker-v2-m3",
            revision="953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e",
            max_length=8192,
            precision="float32",
            score_transform="sigmoid",
        )

    @property
    def identity(self) -> RerankerIdentity:
        return self._identity

    @property
    def actual_device(self) -> str:
        return "cpu"

    def load(self) -> None:
        self.load_calls += 1
        if self.fail_on_load:
            raise RuntimeError("C:\\private-model\\secret-token")

    def score(self, query: str, passages: Sequence[str]) -> RerankerBatch:
        self.score_calls += 1
        scores = tuple(
            RerankerPairScore(
                pair_key=build_reranker_pair_key(
                    self.identity,
                    query,
                    passage,
                    position,
                ),
                raw_score=float(len(passages) - position),
                normalized_score=1 / (1 + math.exp(-(len(passages) - position))),
            )
            for position, passage in enumerate(passages)
        )
        return RerankerBatch(
            scores=scores,
            identity=self.identity,
            effective_batch_size=2,
        )


def test_probe_cases_freeze_six_categories_and_twenty_candidates() -> None:
    cases = build_m2_reranker_resource_probe_cases()

    assert [case.category for case in cases] == [
        "chinese",
        "english",
        "german",
        "table",
        "candidate_missing",
        "no_answer",
    ]
    assert all(len(case.candidates) == 20 for case in cases)
    assert all(
        len({item.candidate_id for item in case.candidates}) == 20 for case in cases
    )
    assert cases[-2].expected_candidate_id is None
    assert cases[-1].expected_candidate_id is None


def test_probe_scores_each_max_pool_once_then_reuses_run_cache() -> None:
    provider = _InjectedBgeProvider()

    report = run_m2_reranker_resource_probe(
        provider=provider,
        snapshot_verified=True,
        configured_batch_size=2,
    )

    assert isinstance(report, RerankerResourceProbeReport)
    assert provider.load_calls == 1
    assert provider.score_calls == 6
    assert report.cache.score_requests == 12
    assert report.cache.cache_misses == 6
    assert report.cache.cache_hits == 6
    assert report.cache.provider_score_calls == 6
    assert report.quality_gate_passed is None
    assert report.snapshot_verified is True
    assert report.offline_inference is True
    assert report.measurements.scoring_latency_p95_ms <= (
        report.measurements.scoring_latency_max_ms
    )
    assert report.measurements.rss_peak_mib >= report.measurements.rss_start_mib

    missing = next(item for item in report.cases if item.status == "candidate_missing")
    no_answer = next(item for item in report.cases if item.status == "no_answer")
    assert missing.expected_candidate_id is None
    assert missing.expected_candidate_rank is None
    assert no_answer.expected_candidate_id is None
    assert no_answer.expected_candidate_rank is None


def test_probe_report_is_public_safe_and_round_trips(tmp_path: Path) -> None:
    cases = build_m2_reranker_resource_probe_cases()
    report = run_m2_reranker_resource_probe(
        provider=_InjectedBgeProvider(),
        snapshot_verified=True,
        configured_batch_size=2,
        cases=cases,
    )

    output = write_reranker_resource_probe_report(tmp_path / "probe.json", report)
    payload = output.read_text(encoding="utf-8")

    assert RerankerResourceProbeReport.model_validate_json(payload) == report
    assert all(case.query not in payload for case in cases)
    assert all(
        candidate.body_text not in payload
        for case in cases
        for candidate in case.candidates
    )
    assert "private-model" not in payload
    assert json.loads(payload)["execution_mode"] == "pinned_local_bge_probe"


def test_probe_rejects_wrong_identity_and_sanitizes_provider_failure() -> None:
    wrong = _InjectedBgeProvider()
    wrong._identity = replace(
        wrong.identity,
        revision="main",
    )
    with pytest.raises(RerankerResourceProbeError, match="固定身份"):
        run_m2_reranker_resource_probe(
            provider=wrong,
            snapshot_verified=True,
            configured_batch_size=2,
        )

    with pytest.raises(RerankerResourceProbeError) as captured:
        run_m2_reranker_resource_probe(
            provider=_InjectedBgeProvider(fail_on_load=True),
            snapshot_verified=True,
            configured_batch_size=2,
        )
    assert "private-model" not in str(captured.value)
    assert "secret-token" not in str(captured.value)


def test_probe_requires_a_verified_local_snapshot() -> None:
    provider = _InjectedBgeProvider()

    with pytest.raises(RerankerResourceProbeError, match="快照"):
        run_m2_reranker_resource_probe(
            provider=provider,
            snapshot_verified=False,
            configured_batch_size=2,
        )

    assert provider.load_calls == 0
    assert provider.score_calls == 0
