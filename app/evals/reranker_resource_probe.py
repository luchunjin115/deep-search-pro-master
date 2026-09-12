"""Bounded real-BGE resource probe for M2-22.7.4.

This module intentionally receives synthetic 20-candidate pools.  It never parses,
chunks, retrieves, reads PostgreSQL, or runs the complete 40-question evaluation.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

import psutil  # type: ignore[import-untyped]

from app.core.config import BGE_RERANKER_MODEL_ID, BGE_RERANKER_REVISION
from app.evals.reranker_context_report import (
    BgeRerankerProbeIdentity,
    RerankerResourceProbeCaseResult,
    RerankerResourceProbeMeasurements,
    RerankerResourceProbeReport,
)
from app.evals.reranker_context_runner import (
    RerankerContextCandidateInput,
    RunScoringCache,
)
from app.services.retrieval import (
    RerankerBatch,
    RerankerIdentity,
    validate_reranker_batch,
)

ProbeCategory = Literal[
    "chinese",
    "english",
    "german",
    "table",
    "candidate_missing",
    "no_answer",
]
ProbeStatus = Literal["completed", "candidate_missing", "no_answer"]

_EXPECTED_CATEGORIES: tuple[ProbeCategory, ...] = (
    "chinese",
    "english",
    "german",
    "table",
    "candidate_missing",
    "no_answer",
)
_ANSWERABLE_CATEGORIES = frozenset({"chinese", "english", "german", "table"})


class RerankerResourceProbeError(RuntimeError):
    """Stable probe failure that never includes paths, source text, or raw causes."""


class ResourceProbeProvider(Protocol):
    """Only the already-implemented production BGE provider surface we need."""

    @property
    def identity(self) -> RerankerIdentity: ...

    @property
    def actual_device(self) -> str: ...

    def load(self) -> None: ...

    def score(self, query: str, passages: Sequence[str]) -> RerankerBatch: ...


@dataclass(frozen=True, slots=True)
class RerankerResourceProbeCaseInput:
    """Private synthetic input; question and body text never enter the report."""

    case_id: str
    category: ProbeCategory
    query: str
    candidates: tuple[RerankerContextCandidateInput, ...]
    expected_candidate_id: str | None


class _ProviderScorer:
    """Adapt a validated RerankerBatch to the existing run-cache score seam."""

    def __init__(
        self,
        provider: ResourceProbeProvider,
        identity: BgeRerankerProbeIdentity,
    ) -> None:
        self._provider = provider
        self._identity = identity
        self.effective_batch_sizes: list[int] = []

    @property
    def identity(self) -> BgeRerankerProbeIdentity:
        return self._identity

    def score(self, query: str, documents: Sequence[str]) -> tuple[float, ...]:
        batch = self._provider.score(query, documents)
        validated = validate_reranker_batch(
            batch,
            query=query,
            passages=documents,
            expected_identity=self._provider.identity,
        )
        self.effective_batch_sizes.append(validated.effective_batch_size)
        return tuple(item.raw_score for item in validated.scores)


class _RssSampler:
    """Sample this Python process while the local model loads and scores."""

    def __init__(self) -> None:
        self._process = psutil.Process()
        self._start_bytes = self._process.memory_info().rss
        self._peak_bytes = self._start_bytes
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._sample, daemon=True)

    @property
    def start_mib(self) -> float:
        return round(self._start_bytes / 1024 / 1024, 3)

    @property
    def peak_mib(self) -> float:
        return round(self._peak_bytes / 1024 / 1024, 3)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stopped.set()
        self._thread.join(timeout=1)
        self._peak_bytes = max(self._peak_bytes, self._process.memory_info().rss)

    def _sample(self) -> None:
        while not self._stopped.wait(0.05):
            self._peak_bytes = max(
                self._peak_bytes,
                self._process.memory_info().rss,
            )


def build_m2_reranker_resource_probe_cases() -> tuple[
    RerankerResourceProbeCaseInput, ...
]:
    """Freeze six multilingual/table/safety pools at the maximum union size 20."""

    definitions: tuple[tuple[ProbeCategory, str, str | None], ...] = (
        (
            "chinese",
            "德国市场的蘑菇灯需要遵守什么插头要求？",
            "面向德国销售的蘑菇灯应使用欧规插头，并标明额定电压。",
        ),
        (
            "english",
            "Which ports are included on the USB-C hub?",
            "The USB-C hub includes HDMI, USB 3.0, and Gigabit Ethernet ports.",
        ),
        (
            "german",
            "Welche Spannung ist für die Tischlampe angegeben?",
            "Für die Tischlampe ist eine Nennspannung von 230 Volt angegeben.",
        ),
        (
            "table",
            "What is the sellable quantity for LR-TL-MUSH-OR01 in DE-FRA?",
            "SKU | warehouse | sellable\nLR-TL-MUSH-OR01 | DE-FRA | 125",
        ),
        (
            "candidate_missing",
            "Which warranty exception applies to the missing product evidence?",
            None,
        ),
        (
            "no_answer",
            "What is the private supplier bank account number?",
            None,
        ),
    )
    return tuple(
        _build_case(category=category, query=query, relevant_text=relevant_text)
        for category, query, relevant_text in definitions
    )


def run_m2_reranker_resource_probe(
    *,
    provider: ResourceProbeProvider,
    snapshot_verified: bool,
    configured_batch_size: int,
    cases: Sequence[RerankerResourceProbeCaseInput] | None = None,
) -> RerankerResourceProbeReport:
    """Load pinned BGE once and score each fixed 20-candidate pool once."""

    if snapshot_verified is not True:
        raise RerankerResourceProbeError("本地BGE-Reranker固定快照尚未通过校验")
    if (
        not isinstance(configured_batch_size, int)
        or isinstance(configured_batch_size, bool)
        or not 1 <= configured_batch_size <= 16
    ):
        raise RerankerResourceProbeError("Reranker资源探针批大小无效")
    identity = _validated_probe_identity(provider)
    selected_cases = tuple(cases or build_m2_reranker_resource_probe_cases())
    _validate_cases(selected_cases)

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    cache = RunScoringCache()
    scorer = _ProviderScorer(provider, identity)
    sampler = _RssSampler()
    before_children = _live_child_pids()
    latencies_ms: list[float] = []
    results: list[RerankerResourceProbeCaseResult] = []
    sampler.start()
    load_started = time.perf_counter()
    try:
        provider.load()
        load_seconds = time.perf_counter() - load_started
        for case in selected_cases:
            score_started = time.perf_counter()
            scores = cache.get_or_score(
                query=case.query,
                candidates=case.candidates,
                scorer=scorer,
            )
            latencies_ms.append((time.perf_counter() - score_started) * 1000)
            cached_scores = cache.get_or_score(
                query=case.query,
                candidates=case.candidates,
                scorer=scorer,
            )
            if cached_scores != scores:
                raise RerankerResourceProbeError("Reranker运行内缓存结果不一致")
            results.append(_case_result(case, scores))
    except RerankerResourceProbeError:
        raise
    except Exception:  # noqa: BLE001 - provider/runtime details remain private.
        raise RerankerResourceProbeError("本地BGE-Reranker资源探针执行失败") from None
    finally:
        sampler.stop()

    if len(scorer.effective_batch_sizes) != len(selected_cases):
        raise RerankerResourceProbeError("Reranker实际评分批次记录不完整")
    input_sha256 = _input_sha256(selected_cases, identity)
    peak_mib = sampler.peak_mib
    start_mib = sampler.start_mib
    return RerankerResourceProbeReport(
        run_id=f"m2-2274-{input_sha256[:16]}",
        input_sha256=input_sha256,
        scorer=identity,
        cases=results,
        cache=cache.stats(),
        measurements=RerankerResourceProbeMeasurements(
            load_seconds=round(load_seconds, 6),
            scoring_latency_p50_ms=round(_percentile(latencies_ms, 0.50), 3),
            scoring_latency_p95_ms=round(_percentile(latencies_ms, 0.95), 3),
            scoring_latency_max_ms=round(max(latencies_ms), 3),
            rss_start_mib=start_mib,
            rss_peak_mib=peak_mib,
            rss_peak_delta_mib=round(max(0.0, peak_mib - start_mib), 3),
            configured_batch_size=configured_batch_size,
            effective_batch_size_min=min(scorer.effective_batch_sizes),
            effective_batch_size_max=max(scorer.effective_batch_sizes),
            new_live_child_process_count=len(_live_child_pids() - before_children),
        ),
    )


def _validated_probe_identity(
    provider: ResourceProbeProvider,
) -> BgeRerankerProbeIdentity:
    expected = RerankerIdentity(
        contract_version="m2-reranker-provider-v1",
        provider="bge-reranker-local",
        model_id=BGE_RERANKER_MODEL_ID,
        revision=BGE_RERANKER_REVISION,
        max_length=8192,
        precision="float32",
        score_transform="sigmoid",
    )
    try:
        actual_identity = provider.identity
        actual_device = provider.actual_device
    except Exception:  # noqa: BLE001 - keep provider internals private.
        raise RerankerResourceProbeError("无法确认Reranker固定身份") from None
    if actual_identity != expected or actual_device != "cpu":
        raise RerankerResourceProbeError("Reranker不是本步要求的固定身份与CPU配置")
    return BgeRerankerProbeIdentity()


def _build_case(
    *,
    category: ProbeCategory,
    query: str,
    relevant_text: str | None,
) -> RerankerResourceProbeCaseInput:
    case_id = f"probe-{category.replace('_', '-')}"
    bodies: list[str] = []
    if relevant_text is not None:
        bodies.append(relevant_text)
    while len(bodies) < 20:
        position = len(bodies) + 1
        bodies.append(
            f"Synthetic unrelated catalog note {position}: packaging color and carton size."
        )
    candidates = tuple(
        _candidate(case_id=case_id, position=position, body_text=body_text)
        for position, body_text in enumerate(bodies, start=1)
    )
    return RerankerResourceProbeCaseInput(
        case_id=case_id,
        category=category,
        query=query,
        candidates=candidates,
        expected_candidate_id=(candidates[0].candidate_id if relevant_text else None),
    )


def _candidate(
    *,
    case_id: str,
    position: int,
    body_text: str,
) -> RerankerContextCandidateInput:
    body_hash = _sha256_text(body_text)
    return RerankerContextCandidateInput(
        candidate_id=f"{case_id}-candidate-{position:02d}",
        logical_document_id=f"probe-document-{position:02d}",
        body_text=body_text,
        body_text_sha256=body_hash,
        rrf_score=1.0 / (60 + position),
    )


def _validate_cases(cases: Sequence[RerankerResourceProbeCaseInput]) -> None:
    if tuple(case.category for case in cases) != _EXPECTED_CATEGORIES:
        raise RerankerResourceProbeError("Reranker资源探针必须保留固定六类样本")
    if len({case.case_id for case in cases}) != len(cases):
        raise RerankerResourceProbeError("Reranker资源探针样本ID重复")
    for case in cases:
        if not case.query.strip() or len(case.candidates) != 20:
            raise RerankerResourceProbeError("每个资源探针必须有问题和20个候选")
        candidate_ids = [item.candidate_id for item in case.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise RerankerResourceProbeError("资源探针候选ID重复")
        if any(
            not item.body_text or item.body_text_sha256 != _sha256_text(item.body_text)
            for item in case.candidates
        ):
            raise RerankerResourceProbeError("资源探针候选正文或Hash无效")
        if case.category in _ANSWERABLE_CATEGORIES:
            if case.expected_candidate_id not in candidate_ids:
                raise RerankerResourceProbeError("可回答探针缺少预期候选")
        elif case.expected_candidate_id is not None:
            raise RerankerResourceProbeError("缺失/无答案探针不能虚构正确候选")


def _case_result(
    case: RerankerResourceProbeCaseInput,
    scores: Sequence[float],
) -> RerankerResourceProbeCaseResult:
    if len(scores) != 20 or any(not math.isfinite(score) for score in scores):
        raise RerankerResourceProbeError("Reranker必须返回20个有限分数")
    expected_rank: int | None = None
    if case.expected_candidate_id is not None:
        ranked_indexes = sorted(
            range(len(scores)),
            key=lambda index: (-scores[index], index),
        )
        expected_index = next(
            index
            for index, item in enumerate(case.candidates)
            if item.candidate_id == case.expected_candidate_id
        )
        expected_rank = ranked_indexes.index(expected_index) + 1
    status: ProbeStatus = "completed"
    if case.category == "candidate_missing":
        status = "candidate_missing"
    elif case.category == "no_answer":
        status = "no_answer"
    return RerankerResourceProbeCaseResult(
        case_id=case.case_id,
        category=case.category,
        status=status,
        expected_candidate_id=case.expected_candidate_id,
        expected_candidate_rank=expected_rank,
        scores_sha256=hashlib.sha256(_canonical_bytes(list(scores))).hexdigest(),
    )


def _input_sha256(
    cases: Sequence[RerankerResourceProbeCaseInput],
    identity: BgeRerankerProbeIdentity,
) -> str:
    payload = {
        "scorer": identity.model_dump(mode="json"),
        "cases": [
            {
                "case_id": case.case_id,
                "category": case.category,
                "query_sha256": _sha256_text(case.query),
                "expected_candidate_id": case.expected_candidate_id,
                "candidates": [
                    {
                        "candidate_id": item.candidate_id,
                        "body_text_sha256": item.body_text_sha256,
                    }
                    for item in case.candidates
                ],
            }
            for case in cases
        ],
    }
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _live_child_pids() -> set[int]:
    try:
        return {
            child.pid
            for child in psutil.Process().children(recursive=True)
            if child.is_running()
        }
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        raise RerankerResourceProbeError("无法确认Reranker子进程退出状态") from None


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
