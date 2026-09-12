from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import ClassVar

import httpx
import pytest
from instructor.core import InstructorRetryException
from pydantic import SecretStr, ValidationError
from ragas.exceptions import RagasOutputParserException

from app.evals.answer_citation_formal import ExternalUsageRecorder
from app.evals.ragas_generation import (
    RAGAS_GENERATION_METRICS,
    RAGAS_GENERATION_PROMPT_BUNDLE_SHA256,
    JudgeMetricDiagnostic,
    ProjectRagasEmbedding,
    Ragas043GenerationBackend,
    RagasGenerationAdapter,
    RagasGenerationInput,
    RagasGenerationNetworkError,
    RagasGenerationProviderError,
    RagasGenerationRateLimitError,
    RagasGenerationTimeoutError,
    _active_judge_metric,
    _active_judge_request,
    _capture_judge_parse_error,
    _raise_generation_error,
    current_ragas_generation_prompt_bundle_sha256,
)
from app.evals.ragas_retrieval import RagasFrameworkError, RagasJudgeRuntime
from app.services.retrieval.embedding import FakeEmbeddingProvider


class RecordingBackend:
    framework_version = "0.4.3"
    prompt_bundle_version = "ragas-0.4.3-collections-generation-source-v1"
    prompt_bundle_sha256 = RAGAS_GENERATION_PROMPT_BUNDLE_SHA256
    embedding_provider = "bge-m3-local"
    embedding_model = "BAAI/bge-m3"
    embedding_revision = "5617a9f61b028005a4858fdac845db406aefb181"
    scores: ClassVar[dict[str, float]] = {
        "faithfulness": 1.0,
        "response_relevancy": 0.9,
        "factual_correctness": 0.8,
        "semantic_similarity": 0.7,
    }

    def __init__(self) -> None:
        self.calls: list[tuple[str, RagasGenerationInput]] = []

    async def score(self, metric_name: str, sample: RagasGenerationInput) -> float:
        self.calls.append((metric_name, sample))
        return self.scores[metric_name]


def judge_runtime() -> RagasJudgeRuntime:
    return RagasJudgeRuntime(
        provider="deepseek-openai-compatible",
        model="deepseek-v4-flash",
        model_version="api-alias-20260911",
        temperature=0.0,
        top_p=1.0,
        max_output_tokens=2048,
        seed=None,
        max_attempts=2,
        timeout_ms=30_000,
    )


def sample() -> RagasGenerationInput:
    return RagasGenerationInput(
        user_input="德国站何时应该补货？",
        retrieved_contexts=("库存低于14天预计销量时，应启动补货。",),
        reference="库存低于14天预计销量时应启动补货。",
        response="德国站库存低于14天预计销量时应启动补货。",
    )


@pytest.mark.asyncio
async def test_generation_adapter_keeps_metrics_identity_and_inputs_separate() -> None:
    backend = RecordingBackend()
    report = await RagasGenerationAdapter(
        backend=backend,
        judge=judge_runtime(),
        answer_provider="deepseek",
        answer_model="deepseek-v4-flash",
    ).evaluate(sample())

    assert [metric.metric_name for metric in report.metrics] == list(
        RAGAS_GENERATION_METRICS
    )
    assert [metric.value for metric in report.metrics] == [1.0, 0.9, 0.8, 0.7]
    assert [name for name, _sample in backend.calls] == list(RAGAS_GENERATION_METRICS)
    assert report.evaluator_identity.judge == judge_runtime()
    assert report.evaluator_identity.same_model_bias is True
    assert report.evaluator_identity.embedding_model == "BAAI/bge-m3"
    public_json = report.model_dump_json()
    for private_text in (
        sample().user_input,
        sample().retrieved_contexts[0],
        sample().reference,
        sample().response,
        "api_key",
        "reasoning",
    ):
        assert private_text not in public_json


@pytest.mark.parametrize(
    ("error_type", "expected_status", "expected_category"),
    (
        (RagasFrameworkError, "framework_failed", "framework_error"),
        (RagasGenerationTimeoutError, "judge_failed", "judge_timeout"),
        (RagasGenerationNetworkError, "judge_failed", "network_error"),
        (RagasGenerationRateLimitError, "judge_failed", "rate_limited"),
        (RagasGenerationProviderError, "judge_failed", "judge_provider_error"),
    ),
)
@pytest.mark.asyncio
async def test_generation_adapter_keeps_failures_non_numeric(
    error_type: type[Exception],
    expected_status: str,
    expected_category: str,
) -> None:
    class FailingBackend(RecordingBackend):
        def __init__(self) -> None:
            super().__init__()

        async def score(
            self,
            metric_name: str,
            sample: RagasGenerationInput,
        ) -> float:
            self.calls.append((metric_name, sample))
            raise error_type

    backend = FailingBackend()
    report = await RagasGenerationAdapter(
        backend=backend,
        judge=judge_runtime(),
        answer_provider="qwen",
        answer_model="qwen3.8-max",
    ).evaluate(sample())

    assert all(metric.status == expected_status for metric in report.metrics)
    assert all(
        metric.failure_category == expected_category for metric in report.metrics
    )
    assert all(metric.value is None for metric in report.metrics)
    assert len(backend.calls) == len(RAGAS_GENERATION_METRICS)
    assert report.evaluator_identity.same_model_bias is False
    assert all(
        d.failure_stage == ("score" if error_type is RagasFrameworkError else "unknown")
        for d in report.judge_diagnostics
    )


@pytest.mark.asyncio
async def test_generation_adapter_does_not_repeat_a_failed_output_metric() -> None:
    class RecoveringBackend(RecordingBackend):
        async def score(
            self,
            metric_name: str,
            sample: RagasGenerationInput,
        ) -> float:
            self.calls.append((metric_name, sample))
            if (
                metric_name == "factual_correctness"
                and sum(name == metric_name for name, _sample in self.calls) == 1
            ):
                _raise_generation_error(RagasOutputParserException())
            return self.scores[metric_name]

    backend = RecoveringBackend()
    report = await RagasGenerationAdapter(
        backend=backend,
        judge=judge_runtime(),
        answer_provider="deepseek",
        answer_model="deepseek-v4-flash",
    ).evaluate(sample())

    assert [metric.status for metric in report.metrics] == [
        "completed",
        "completed",
        "judge_failed",
        "completed",
    ]
    assert report.metrics[2].value is None
    assert [name for name, _sample in backend.calls] == [
        "faithfulness",
        "response_relevancy",
        "factual_correctness",
        "semantic_similarity",
    ]


@pytest.mark.asyncio
async def test_generation_adapter_keeps_output_failures_non_numeric_without_repair() -> (
    None
):
    class OutputFailingBackend(RecordingBackend):
        async def score(
            self,
            metric_name: str,
            sample: RagasGenerationInput,
        ) -> float:
            self.calls.append((metric_name, sample))
            _raise_generation_error(RagasOutputParserException())

    backend = OutputFailingBackend()
    report = await RagasGenerationAdapter(
        backend=backend,
        judge=judge_runtime(),
        answer_provider="deepseek",
        answer_model="deepseek-v4-flash",
    ).evaluate(sample())

    assert len(backend.calls) == len(RAGAS_GENERATION_METRICS)
    assert all(metric.status == "judge_failed" for metric in report.metrics)
    assert all(
        metric.failure_category == "judge_provider_error" for metric in report.metrics
    )
    assert sample().response not in report.model_dump_json()


def test_generation_backend_preserves_pre_k_client_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm_options: dict[str, object] = {}
    client_options: dict[str, object] = {}

    def fake_client_factory(**kwargs: object) -> object:
        client_options.update(kwargs)
        return object()

    def fake_llm_factory(model: str, **kwargs: object) -> object:
        llm_options.update({"model": model, **kwargs})
        return object()

    monkeypatch.setattr("ragas.llms.llm_factory", fake_llm_factory)
    for metric_type in (
        "AnswerRelevancy",
        "FactualCorrectness",
        "Faithfulness",
        "SemanticSimilarity",
    ):
        monkeypatch.setattr(
            f"ragas.metrics.collections.{metric_type}",
            lambda **_kwargs: object(),
        )
    monkeypatch.setattr(
        "app.evals.ragas_generation.current_ragas_generation_prompt_bundle_sha256",
        lambda: RAGAS_GENERATION_PROMPT_BUNDLE_SHA256,
    )
    embedding = SimpleNamespace(
        identity=SimpleNamespace(
            provider="bge-m3-local",
            model_id="BAAI/bge-m3",
            revision="5617a9f61b028005a4858fdac845db406aefb181",
            normalize=True,
        )
    )

    Ragas043GenerationBackend(
        judge=judge_runtime(),
        api_key=SecretStr("not-sent"),
        base_url="https://deepseek.example",
        embedding_provider=embedding,  # type: ignore[arg-type]
        client_factory=fake_client_factory,
    )

    assert client_options["max_retries"] == 0
    assert "max_retries" not in llm_options


@pytest.mark.asyncio
async def test_generation_adapter_rejects_wrong_version_and_invalid_score() -> None:
    backend = RecordingBackend()
    backend.framework_version = "0.4.2"
    with pytest.raises(ValueError, match="0.4.3"):
        RagasGenerationAdapter(
            backend=backend,
            judge=judge_runtime(),
            answer_provider="deepseek",
            answer_model="deepseek-v4-flash",
        )

    class InvalidScoreBackend(RecordingBackend):
        async def score(
            self,
            metric_name: str,
            sample: RagasGenerationInput,
        ) -> float:
            return 1.1

    report = await RagasGenerationAdapter(
        backend=InvalidScoreBackend(),
        judge=judge_runtime(),
        answer_provider="deepseek",
        answer_model="deepseek-v4-flash",
    ).evaluate(sample())
    assert all(metric.status == "framework_failed" for metric in report.metrics)
    assert all(metric.value is None for metric in report.metrics)


@pytest.mark.asyncio
async def test_project_ragas_embedding_reuses_project_provider() -> None:
    embedding = ProjectRagasEmbedding(FakeEmbeddingProvider())

    sync_vector = embedding.embed_text("补货规则")
    async_vector = await embedding.aembed_text("补货规则")

    assert len(sync_vector) == 1024
    assert async_vector == sync_vector


def test_generation_prompt_sources_match_frozen_ragas_installation() -> None:
    assert RAGAS_GENERATION_PROMPT_BUNDLE_SHA256 == (
        "4cb3e8b85f726ad2c298b910adeb7086a2f3d92aa3615debdb2cc14957d479f7"
    )
    assert (
        current_ragas_generation_prompt_bundle_sha256()
        == RAGAS_GENERATION_PROMPT_BUNDLE_SHA256
    )


def test_generation_parser_failure_preserves_pre_k_safe_provider_error() -> None:
    with pytest.raises(RagasGenerationProviderError) as caught:
        _raise_generation_error(RagasOutputParserException())
    assert str(caught.value) == ""


def test_instructor_retry_preserves_pre_k_provider_failure_classification() -> None:
    output_error = InstructorRetryException(
        "not retained",
        n_attempts=1,
        total_usage=None,
        failed_attempts=[object()],  # type: ignore[list-item]
    )
    with pytest.raises(RagasGenerationProviderError):
        _raise_generation_error(output_error)

    provider_error = InstructorRetryException(
        "not retained",
        n_attempts=1,
        total_usage=None,
        failed_attempts=[],
    )
    with pytest.raises(RagasGenerationProviderError):
        _raise_generation_error(provider_error)


def test_generation_backend_rejects_fake_embedding_identity() -> None:
    with pytest.raises(ValueError, match="BGE-M3"):
        Ragas043GenerationBackend(
            judge=judge_runtime(),
            api_key=SecretStr("not-sent"),
            base_url="https://deepseek.example",
            embedding_provider=FakeEmbeddingProvider(),
        )


@pytest.mark.parametrize(
    "injected",
    [
        {"raw_response": "PRIVATE"},
        {"finish_reason": "PRIVATE"},
        {"parse_error": "PRIVATE"},
        {"input_tokens": True},
    ],
)
def test_judge_diagnostics_reject_non_allowlisted_data(
    injected: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        JudgeMetricDiagnostic.model_validate(
            {
                "metric_name": "factual_correctness",
                "requests": [{"request_index": 1, **injected}],
            }
        )


@pytest.mark.asyncio
async def test_judge_diagnostics_isolate_concurrent_samples_and_reset_context() -> None:
    recorder = ExternalUsageRecorder(max_api_calls=9)

    class InterleavedBackend(RecordingBackend):
        async def score(self, metric_name: str, sample: RagasGenerationInput) -> float:
            request = httpx.Request("POST", "https://judge.invalid")
            await recorder.capture_request(request)
            await asyncio.sleep(0)
            first = sample.user_input == "first"
            await recorder.capture_response(
                httpx.Response(
                    200,
                    request=request,
                    json={
                        "choices": [
                            {"message": {"content": "PRIVATE"}, "finish_reason": "stop"}
                        ],
                        "usage": {
                            "prompt_tokens": 10 if first else 20,
                            "completion_tokens": 1,
                        },
                    },
                )
            )
            if first:
                _capture_judge_parse_error(
                    json.JSONDecodeError("PRIVATE", "PRIVATE", 0)
                )
            return 1.0

    adapter = RagasGenerationAdapter(
        backend=InterleavedBackend(),
        judge=judge_runtime(),
        answer_provider="deepseek",
        answer_model="deepseek-v4-flash",
    )
    first, second = await asyncio.gather(
        adapter.evaluate(sample().model_copy(update={"user_input": "first"})),
        adapter.evaluate(sample().model_copy(update={"user_input": "second"})),
    )
    for report, tokens, error in ((first, 10, "json"), (second, 20, None)):
        assert len(report.judge_diagnostics) == 4
        for diagnostic in report.judge_diagnostics:
            assert len(diagnostic.requests) == 1
            assert diagnostic.requests[0].input_tokens == tokens
            assert diagnostic.requests[0].parse_error == error
        assert "PRIVATE" not in report.model_dump_json()
    assert recorder.api_calls == 8
    unrelated = httpx.Request("POST", "https://judge.invalid")
    await recorder.capture_request(unrelated)
    assert _active_judge_metric.get() is None
    assert _active_judge_request.get() is None
