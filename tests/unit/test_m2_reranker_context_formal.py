from __future__ import annotations

import math
from collections.abc import Sequence

from app.evals.reranker_context_formal import (
    RunCachingRerankerProvider,
    select_reranker_top_k,
)
from app.schemas.evaluation import RerankerCaseComparison
from app.services.retrieval.reranker_provider import (
    RERANKER_CONTRACT_VERSION,
    RerankerBatch,
    RerankerIdentity,
    RerankerPairScore,
    build_reranker_pair_key,
)


class _PinnedBgeStub:
    def __init__(self) -> None:
        self.call_count = 0
        self._identity = RerankerIdentity(
            contract_version=RERANKER_CONTRACT_VERSION,
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

    def score(self, query: str, passages: Sequence[str]) -> RerankerBatch:
        self.call_count += 1
        return RerankerBatch(
            scores=tuple(
                RerankerPairScore(
                    pair_key=build_reranker_pair_key(
                        self.identity,
                        query,
                        passage,
                        position,
                    ),
                    raw_score=float(position),
                    normalized_score=1 / (1 + math.exp(-float(position))),
                )
                for position, passage in enumerate(passages)
            ),
            identity=self.identity,
            effective_batch_size=2,
        )


def _comparison(
    case_id: str,
    *,
    top_k: int,
    reranker_hit: bool,
) -> RerankerCaseComparison:
    golden_rank = top_k if reranker_hit else min(20, top_k + 1)
    return RerankerCaseComparison(
        case_id=case_id,
        source_group="cross_border_core",
        top_k=top_k,
        expected_evidence_count=1,
        status="completed",
        rrf_candidate_count=10,
        reranker_candidate_count=10,
        candidate_set_unchanged=True,
        rrf_first_golden_rank=golden_rank,
        reranker_first_golden_rank=golden_rank,
        rank_change="unchanged",
        rrf_hit_at_k=reranker_hit,
        reranker_hit_at_k=reranker_hit,
    )


def test_run_cache_scores_one_full_pool_once_for_top5_and_top8() -> None:
    delegate = _PinnedBgeStub()
    cache = RunCachingRerankerProvider(delegate)
    passages = ("候选一", "candidate two")

    first = cache.score("同一道问题", passages)
    second = cache.score("同一道问题", passages)

    assert first == second
    assert delegate.call_count == 1
    assert cache.stats().model_dump() == {
        "scope": "current_run_only",
        "score_requests": 2,
        "cache_hits": 1,
        "cache_misses": 1,
        "provider_score_calls": 1,
        "cache_entries": 1,
    }
    assert cache.score_latencies_ms == (cache.score_latencies_ms[0],)
    assert cache.effective_batch_sizes == (2,)


def test_topk_selection_prefers_more_hits_then_smaller_equal_topk() -> None:
    comparisons = [
        _comparison("case-a", top_k=5, reranker_hit=True),
        _comparison("case-b", top_k=5, reranker_hit=False),
        _comparison("case-a", top_k=8, reranker_hit=True),
        _comparison("case-b", top_k=8, reranker_hit=True),
    ]

    assert (
        select_reranker_top_k(
            comparisons,
            answerable_case_ids=("case-a", "case-b"),
        )
        == 8
    )

    tied = [
        _comparison("case-a", top_k=5, reranker_hit=True),
        _comparison("case-b", top_k=5, reranker_hit=False),
        _comparison("case-a", top_k=8, reranker_hit=True),
        _comparison("case-b", top_k=8, reranker_hit=False),
    ]
    assert (
        select_reranker_top_k(
            tied,
            answerable_case_ids=("case-a", "case-b"),
        )
        == 5
    )


def test_topk_selection_rejects_a_shrunk_answerable_denominator() -> None:
    comparisons = [
        _comparison("case-a", top_k=5, reranker_hit=True),
        _comparison("case-a", top_k=8, reranker_hit=True),
    ]

    try:
        select_reranker_top_k(
            comparisons,
            answerable_case_ids=("case-a", "case-b"),
        )
    except ValueError as error:
        assert "denominator" in str(error)
    else:
        raise AssertionError("a missing answerable row must not be accepted")
