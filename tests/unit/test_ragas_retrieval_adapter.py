from __future__ import annotations

import pytest

from app.evals.ragas_retrieval import (
    RAGAS_PROMPT_BUNDLE_SHA256,
    RagasJudgeProviderError,
    RagasJudgeRuntime,
    RagasJudgeTimeoutError,
    RagasNetworkError,
    RagasRateLimitError,
    RagasRetrievalAdapter,
    RagasRetrievalInput,
    _raise_classified_judge_error,
    current_ragas_prompt_bundle_sha256,
)


class RecordingBackend:
    framework_version = "0.4.3"

    def __init__(self) -> None:
        self.calls: list[tuple[str, RagasRetrievalInput]] = []

    def score(self, metric_name: str, sample: RagasRetrievalInput) -> float:
        self.calls.append((metric_name, sample))
        return {
            "context_precision": 0.75,
            "context_recall": 1.0,
            "context_relevancy": 0.5,
        }[metric_name]


def judge_runtime() -> RagasJudgeRuntime:
    return RagasJudgeRuntime(
        provider="qwen-openai-compatible",
        model="qwen3.8-max",
        model_version="api-alias-20260909",
        temperature=0.0,
        top_p=1.0,
        max_output_tokens=2048,
        seed=20260909,
        max_attempts=2,
        timeout_ms=30_000,
    )


def test_ragas_adapter_runs_only_retrieval_semantics_and_keeps_failures_non_numeric() -> (
    None
):
    backend = RecordingBackend()
    adapter = RagasRetrievalAdapter(backend=backend, judge=judge_runtime())
    sample = RagasRetrievalInput(
        user_input="What date applies?",
        retrieved_contexts=("The applicable date is 13 December 2024.",),
        reference="The applicable date is 13 December 2024.",
        reference_contexts=("The applicable date is 13 December 2024.",),
        response=None,
    )

    report = adapter.evaluate(sample)

    assert [metric.metric_name for metric in report.metrics] == [
        "context_precision",
        "context_recall",
        "context_relevancy",
        "noise_sensitivity",
    ]
    assert [name for name, _sample in backend.calls] == [
        "context_precision",
        "context_recall",
        "context_relevancy",
    ]
    noise = report.metrics[-1]
    assert noise.status == "skipped"
    assert noise.value is None
    assert noise.failure_category == "input_invalid"
    assert report.evaluator_identity.judge == judge_runtime()
    assert "reasoning" not in report.model_dump_json().casefold()


def test_ragas_adapter_does_not_turn_framework_or_judge_failures_into_zero() -> None:
    class FailingBackend(RecordingBackend):
        def score(self, metric_name: str, sample: RagasRetrievalInput) -> float:
            raise TimeoutError

    adapter = RagasRetrievalAdapter(
        backend=FailingBackend(),
        judge=judge_runtime(),
    )
    report = adapter.evaluate(
        RagasRetrievalInput(
            user_input="Question",
            retrieved_contexts=("Context",),
            reference="Reference",
            reference_contexts=("Reference",),
        )
    )

    for metric in report.metrics[:3]:
        assert metric.status == "judge_failed"
        assert metric.value is None
        assert metric.failure_category == "judge_timeout"

    class SwallowedProviderFailureBackend(RecordingBackend):
        def score(self, metric_name: str, sample: RagasRetrievalInput) -> float:
            raise RagasJudgeProviderError

    swallowed = RagasRetrievalAdapter(
        backend=SwallowedProviderFailureBackend(),
        judge=judge_runtime(),
    ).evaluate(
        RagasRetrievalInput(
            user_input="Question",
            retrieved_contexts=("Context",),
            reference="Reference",
            reference_contexts=("Reference",),
        )
    )
    assert all(
        metric.failure_category == "judge_provider_error"
        for metric in swallowed.metrics[:3]
    )


def test_ragas_adapter_rejects_wrong_framework_version_and_out_of_range_score() -> None:
    backend = RecordingBackend()
    backend.framework_version = "0.4.2"
    with pytest.raises(ValueError, match="0.4.3"):
        RagasRetrievalAdapter(backend=backend, judge=judge_runtime())

    class BadScoreBackend(RecordingBackend):
        def score(self, metric_name: str, sample: RagasRetrievalInput) -> float:
            return 1.1

    report = RagasRetrievalAdapter(
        backend=BadScoreBackend(),
        judge=judge_runtime(),
    ).evaluate(
        RagasRetrievalInput(
            user_input="Question",
            retrieved_contexts=("Context",),
            reference="Reference",
            reference_contexts=("Reference",),
        )
    )
    assert all(metric.status == "framework_failed" for metric in report.metrics[:3])
    assert all(metric.value is None for metric in report.metrics[:3])


def test_ragas_adapter_separates_network_from_judge_and_framework_failures() -> None:
    class NetworkBackend(RecordingBackend):
        def score(self, metric_name: str, sample: RagasRetrievalInput) -> float:
            raise RagasNetworkError

    report = RagasRetrievalAdapter(
        backend=NetworkBackend(),
        judge=judge_runtime(),
    ).evaluate(
        RagasRetrievalInput(
            user_input="Question",
            retrieved_contexts=("Context",),
            reference="Reference",
        )
    )

    assert all(metric.status == "judge_failed" for metric in report.metrics[:3])
    assert all(
        metric.failure_category == "network_error" for metric in report.metrics[:3]
    )
    assert all(metric.value is None for metric in report.metrics[:3])


def test_ragas_prompt_sources_match_the_frozen_installed_bundle() -> None:
    assert RAGAS_PROMPT_BUNDLE_SHA256 == (
        "fc347923599df1a73f285372856a462e4ebbdf5a3e7bffdc40fc5a7332323845"
    )
    assert current_ragas_prompt_bundle_sha256() == RAGAS_PROMPT_BUNDLE_SHA256


@pytest.mark.parametrize(
    ("error_name", "expected"),
    (
        ("APITimeoutError", RagasJudgeTimeoutError),
        ("RateLimitError", RagasRateLimitError),
        ("APIConnectionError", RagasNetworkError),
        ("AuthenticationError", RagasJudgeProviderError),
    ),
)
def test_ragas_backend_classifies_provider_exception_names_without_raw_details(
    error_name: str,
    expected: type[Exception],
) -> None:
    error_type = type(error_name, (Exception,), {})

    with pytest.raises(expected) as captured:
        _raise_classified_judge_error(error_type("private endpoint and payload"))

    assert "private" not in str(captured.value)
