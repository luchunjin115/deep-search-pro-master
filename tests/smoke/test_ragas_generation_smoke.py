from __future__ import annotations

import json
import os
from time import perf_counter

import httpx
import pytest
from openai import AsyncOpenAI

from app.core.config import BGE_M3_REVISION, get_settings
from app.evals.ragas_generation import (
    RAGAS_GENERATION_METRICS,
    Ragas043GenerationBackend,
    RagasGenerationAdapter,
    RagasGenerationInput,
)
from app.evals.ragas_retrieval import RagasJudgeRuntime
from app.services.retrieval.embedding import BgeM3EmbeddingProvider


def _samples() -> tuple[tuple[str, RagasGenerationInput], ...]:
    common = {
        "user_input": "德国站商品什么时候应该启动补货？",
        "retrieved_contexts": ("德国站库存低于14天预计销量时，应启动补货。",),
        "reference": "德国站库存低于14天预计销量时应启动补货。",
    }
    return (
        (
            "good_answer",
            RagasGenerationInput(
                **common,
                response="德国站库存低于14天预计销量时，应启动补货。",
            ),
        ),
        (
            "bad_answer",
            RagasGenerationInput(
                **common,
                response="巴黎今天阳光明媚，建议增加广告预算。",
            ),
        ),
    )


@pytest.mark.asyncio
async def test_real_ragas_generation_calibration_requires_explicit_opt_in() -> None:
    settings = get_settings()
    api_key = settings.deepseek_api_key
    if os.getenv("RUN_RAGAS_GENERATION_SMOKE") != "1" or api_key is None:
        pytest.skip(
            "set RUN_RAGAS_GENERATION_SMOKE=1 and DEEPSEEK_API_KEY to call paid API"
        )

    snapshot = (settings.model_cache_root / "bge-m3" / BGE_M3_REVISION).resolve()
    embedding = BgeM3EmbeddingProvider(
        snapshot_path=snapshot,
        requested_device="cpu",
        precision="float32",
        batch_size=2,
    )
    judge = RagasJudgeRuntime(
        provider="deepseek-openai-compatible",
        model=settings.deepseek_model,
        model_version="api-alias-20260911",
        temperature=0.0,
        top_p=1.0,
        max_output_tokens=2048,
        seed=None,
        max_attempts=1,
        timeout_ms=30_000,
    )

    api_usage = {
        "api_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }

    async def capture_usage(response: httpx.Response) -> None:
        await response.aread()
        api_usage["api_calls"] += 1
        if response.status_code >= 400:
            return
        try:
            payload = response.json()
        except ValueError:
            return
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            return
        for target, candidates in {
            "input_tokens": ("input_tokens", "prompt_tokens"),
            "output_tokens": ("output_tokens", "completion_tokens"),
            "total_tokens": ("total_tokens",),
        }.items():
            for candidate in candidates:
                value = usage.get(candidate)
                if isinstance(value, int) and value >= 0:
                    api_usage[target] += value
                    break

    http_client = httpx.AsyncClient(event_hooks={"response": [capture_usage]})

    def client_factory(**kwargs: object) -> AsyncOpenAI:
        return AsyncOpenAI(http_client=http_client, **kwargs)

    backend = Ragas043GenerationBackend(
        judge=judge,
        api_key=api_key,
        base_url=settings.deepseek_base_url,
        embedding_provider=embedding,
        client_factory=client_factory,
    )
    adapter = RagasGenerationAdapter(
        backend=backend,
        judge=judge,
        answer_provider="deepseek",
        answer_model=settings.deepseek_model,
    )
    safe_results: list[dict[str, object]] = []
    try:
        for case_id, sample in _samples():
            started_at = perf_counter()
            report = await adapter.evaluate(sample)
            safe_results.append(
                {
                    "case_id": case_id,
                    "duration_ms": round((perf_counter() - started_at) * 1000),
                    "scores": {
                        metric.metric_name: metric.value
                        for metric in report.metrics
                        if metric.status == "completed"
                    },
                    "statuses": {
                        metric.metric_name: metric.status for metric in report.metrics
                    },
                    "same_model_bias": (report.evaluator_identity.same_model_bias),
                }
            )
    finally:
        await backend.aclose()

    print(
        json.dumps(
            {
                "cases": safe_results,
                "judge_model": settings.deepseek_model,
                "embedding_model": "BAAI/bge-m3",
                **api_usage,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )

    assert all(
        set(case["scores"]) == set(RAGAS_GENERATION_METRICS) for case in safe_results
    )
    good_scores = safe_results[0]["scores"]
    bad_scores = safe_results[1]["scores"]
    assert isinstance(good_scores, dict)
    assert isinstance(bad_scores, dict)
    assert all(
        good_scores[name] > bad_scores[name] for name in RAGAS_GENERATION_METRICS
    )
    assert all(case["same_model_bias"] is True for case in safe_results)
