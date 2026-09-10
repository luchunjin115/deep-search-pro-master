"""Ragas 0.4.3 retrieval-only adapter with explicit Judge provenance."""

from __future__ import annotations

import hashlib
import inspect
import math
from collections.abc import Callable
from typing import Literal, Never, Protocol, TypeAlias

from pydantic import Field, FiniteFloat, SecretStr, model_validator

from app.schemas.common import M1Schema
from app.schemas.evaluation import FailureCategory, SafeIdentifier, VersionLabel

RAGAS_VERSION: Literal["0.4.3"] = "0.4.3"
RAGAS_PROMPT_BUNDLE_SHA256 = (
    "fc347923599df1a73f285372856a462e4ebbdf5a3e7bffdc40fc5a7332323845"
)
RagasRetrievalMetricName: TypeAlias = Literal[
    "context_precision",
    "context_recall",
    "context_relevancy",
    "noise_sensitivity",
]
RAGAS_RETRIEVAL_METRICS: tuple[RagasRetrievalMetricName, ...] = (
    "context_precision",
    "context_recall",
    "context_relevancy",
    "noise_sensitivity",
)


class RagasRetrievalInput(M1Schema):
    """Only Golden reference material and real retrieved Chunk text."""

    user_input: str = Field(min_length=1, max_length=2000)
    retrieved_contexts: tuple[str, ...] = Field(min_length=1, max_length=20)
    reference: str | None = Field(default=None, min_length=1, max_length=10_000)
    reference_contexts: tuple[str, ...] = Field(default=(), max_length=20)
    response: str | None = Field(default=None, min_length=1, max_length=10_000)


class RagasJudgeRuntime(M1Schema):
    """Serializable Judge identity and bounded request parameters, never a key."""

    provider: SafeIdentifier
    model: str = Field(min_length=1, max_length=200)
    model_version: VersionLabel
    temperature: FiniteFloat = Field(ge=0, le=2)
    top_p: FiniteFloat = Field(gt=0, le=1)
    max_output_tokens: int = Field(ge=128, le=8192)
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    max_attempts: int = Field(ge=1, le=5)
    timeout_ms: int = Field(ge=100, le=120_000)


class RagasMetricExecution(M1Schema):
    """One semantic metric; failures and skips never carry numeric values."""

    metric_name: RagasRetrievalMetricName
    status: Literal["completed", "framework_failed", "judge_failed", "skipped"]
    value: FiniteFloat | None = None
    direction: Literal["higher_is_better", "lower_is_better"]
    failure_category: FailureCategory | None = None
    failure_summary: str | None = Field(default=None, min_length=1, max_length=300)

    @model_validator(mode="after")
    def validate_execution(self) -> RagasMetricExecution:
        expected_direction = (
            "lower_is_better"
            if self.metric_name == "noise_sensitivity"
            else "higher_is_better"
        )
        if self.direction != expected_direction:
            raise ValueError("Ragas metric direction is incorrect")
        if self.status == "completed":
            if (
                self.value is None
                or not 0 <= float(self.value) <= 1
                or self.failure_category is not None
                or self.failure_summary is not None
            ):
                raise ValueError("completed Ragas metric requires one valid score")
        elif (
            self.value is not None
            or self.failure_category is None
            or self.failure_summary is None
        ):
            raise ValueError("failed or skipped Ragas metric cannot carry a score")
        return self


class RagasEvaluatorIdentity(M1Schema):
    """Framework, metric prompt bundle, and Judge identity."""

    framework: Literal["ragas"] = "ragas"
    framework_version: Literal["0.4.3"] = RAGAS_VERSION
    api_family: Literal["collections"] = "collections"
    prompt_bundle_version: VersionLabel
    prompt_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    judge: RagasJudgeRuntime


class RagasRetrievalEvaluation(M1Schema):
    """A physically separate semantic column for one retrieval sample."""

    evaluator_identity: RagasEvaluatorIdentity
    metrics: list[RagasMetricExecution] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def validate_metric_set(self) -> RagasRetrievalEvaluation:
        if [metric.metric_name for metric in self.metrics] != list(
            RAGAS_RETRIEVAL_METRICS
        ):
            raise ValueError("Ragas retrieval metrics must use the frozen order")
        return self


class RagasRetrievalBackend(Protocol):
    framework_version: str

    def score(self, metric_name: str, sample: RagasRetrievalInput) -> float: ...


class RagasRetrievalAdapter:
    """Run only supported retrieval metrics and classify every failure."""

    def __init__(
        self,
        *,
        backend: RagasRetrievalBackend,
        judge: RagasJudgeRuntime,
    ) -> None:
        if backend.framework_version != RAGAS_VERSION:
            raise ValueError(f"Ragas backend must be exactly {RAGAS_VERSION}")
        self._backend = backend
        self._judge = judge

    def evaluate(self, sample: RagasRetrievalInput) -> RagasRetrievalEvaluation:
        metrics: list[RagasMetricExecution] = []
        for metric_name in RAGAS_RETRIEVAL_METRICS:
            direction: Literal["higher_is_better", "lower_is_better"] = (
                "lower_is_better"
                if metric_name == "noise_sensitivity"
                else "higher_is_better"
            )
            if metric_name == "noise_sensitivity" and sample.response is None:
                metrics.append(
                    RagasMetricExecution(
                        metric_name=metric_name,
                        status="skipped",
                        value=None,
                        direction=direction,
                        failure_category="input_invalid",
                        failure_summary=(
                            "Noise Sensitivity requires a response, which this "
                            "retrieval-only stage does not create"
                        ),
                    )
                )
                continue
            if metric_name in {"context_precision", "context_recall"} and (
                sample.reference is None
            ):
                metrics.append(
                    RagasMetricExecution(
                        metric_name=metric_name,
                        status="skipped",
                        value=None,
                        direction=direction,
                        failure_category="input_invalid",
                        failure_summary="This semantic metric requires a Golden reference",
                    )
                )
                continue
            metrics.append(self._run_metric(metric_name, sample, direction=direction))

        prompt_identity = str(
            getattr(
                self._backend,
                "prompt_bundle_version",
                "ragas-0.4.3-collections-retrieval-prompts-v1",
            )
        )
        prompt_hash = str(
            getattr(
                self._backend,
                "prompt_bundle_sha256",
                hashlib.sha256(prompt_identity.encode("utf-8")).hexdigest(),
            )
        )
        return RagasRetrievalEvaluation(
            evaluator_identity=RagasEvaluatorIdentity(
                prompt_bundle_version=prompt_identity,
                prompt_bundle_sha256=prompt_hash,
                judge=self._judge,
            ),
            metrics=metrics,
        )

    def _run_metric(
        self,
        metric_name: RagasRetrievalMetricName,
        sample: RagasRetrievalInput,
        *,
        direction: Literal["higher_is_better", "lower_is_better"],
    ) -> RagasMetricExecution:
        last_error: Exception | None = None
        for _attempt in range(1, self._judge.max_attempts + 1):
            try:
                value = self._backend.score(metric_name, sample)
                if not math.isfinite(value) or not 0 <= value <= 1:
                    raise RagasFrameworkError
                return RagasMetricExecution(
                    metric_name=metric_name,
                    status="completed",
                    value=value,
                    direction=direction,
                )
            except RagasFrameworkError:
                return _failed_metric(
                    metric_name,
                    direction=direction,
                    status="framework_failed",
                    category="framework_error",
                    summary="Ragas returned an invalid semantic metric result",
                )
            except RagasJudgeTimeoutError:
                last_error = TimeoutError()
            except RagasNetworkError:
                last_error = ConnectionError()
            except RagasJudgeProviderError:
                last_error = RuntimeError()
            except Exception as error:  # noqa: BLE001 - Provider exceptions vary.
                last_error = error
        assert last_error is not None
        if isinstance(last_error, TimeoutError):
            return _failed_metric(
                metric_name,
                direction=direction,
                status="judge_failed",
                category="judge_timeout",
                summary="The semantic Judge timed out after bounded retries",
            )
        if isinstance(last_error, ConnectionError):
            return _failed_metric(
                metric_name,
                direction=direction,
                status="judge_failed",
                category="network_error",
                summary="The semantic Judge network request failed after bounded retries",
            )
        if "ratelimit" in last_error.__class__.__name__.casefold():
            return _failed_metric(
                metric_name,
                direction=direction,
                status="judge_failed",
                category="rate_limited",
                summary="The semantic Judge rate limit was reached",
            )
        return _failed_metric(
            metric_name,
            direction=direction,
            status="judge_failed",
            category="judge_provider_error",
            summary="The semantic Judge request failed after bounded retries",
        )


class RagasFrameworkError(RuntimeError):
    """The framework produced a missing, non-finite, or out-of-range result."""


class RagasJudgeProviderError(RuntimeError):
    """Ragas surfaced a provider failure without exposing the raw reason."""


class RagasJudgeTimeoutError(TimeoutError):
    """Ragas surfaced a Judge timeout without exposing the raw reason."""


class RagasNetworkError(ConnectionError):
    """Ragas surfaced a network failure without exposing endpoint details."""


class RagasRateLimitError(RuntimeError):
    """Ragas surfaced a Judge rate limit without exposing raw response details."""


def _failed_metric(
    metric_name: RagasRetrievalMetricName,
    *,
    direction: Literal["higher_is_better", "lower_is_better"],
    status: Literal["framework_failed", "judge_failed"],
    category: FailureCategory,
    summary: str,
) -> RagasMetricExecution:
    return RagasMetricExecution(
        metric_name=metric_name,
        status=status,
        value=None,
        direction=direction,
        failure_category=category,
        failure_summary=summary,
    )


class Ragas043Backend:
    """Thin official collections-API wrapper; MetricResult reasons are discarded."""

    framework_version: str = RAGAS_VERSION

    def __init__(
        self,
        *,
        judge: RagasJudgeRuntime,
        api_key: SecretStr,
        base_url: str,
        client_factory: Callable[..., object] | None = None,
    ) -> None:
        from openai import AsyncOpenAI
        from ragas.llms import llm_factory
        from ragas.metrics.collections import (
            ContextPrecisionWithReference,
            ContextRecall,
            ContextRelevance,
            NoiseSensitivity,
        )

        factory = client_factory or AsyncOpenAI
        client = factory(
            api_key=api_key.get_secret_value(),
            base_url=base_url,
            timeout=judge.timeout_ms / 1000,
            max_retries=0,
        )
        llm = llm_factory(
            judge.model,
            provider="openai",
            client=client,
            temperature=float(judge.temperature),
            top_p=float(judge.top_p),
            max_tokens=judge.max_output_tokens,
            seed=judge.seed,
        )
        self._metrics = {
            "context_precision": ContextPrecisionWithReference(llm=llm),
            "context_recall": ContextRecall(llm=llm),
            "context_relevancy": ContextRelevance(llm=llm, max_retries=1),
            "noise_sensitivity": NoiseSensitivity(llm=llm),
        }
        self.prompt_bundle_version = "ragas-0.4.3-collections-source-v1"
        prompt_hash = current_ragas_prompt_bundle_sha256()
        if prompt_hash != RAGAS_PROMPT_BUNDLE_SHA256:
            raise RagasFrameworkError
        self.prompt_bundle_sha256 = prompt_hash

    def score(self, metric_name: str, sample: RagasRetrievalInput) -> float:
        metric = self._metrics.get(metric_name)
        if metric is None:
            raise RagasFrameworkError
        common = {
            "user_input": sample.user_input,
            "retrieved_contexts": list(sample.retrieved_contexts),
        }
        try:
            if metric_name in {"context_precision", "context_recall"}:
                if sample.reference is None:
                    raise RagasFrameworkError
                result = metric.score(**common, reference=sample.reference)
            elif metric_name == "context_relevancy":
                result = metric.score(**common)
            else:
                if sample.reference is None or sample.response is None:
                    raise RagasFrameworkError
                result = metric.score(
                    **common,
                    reference=sample.reference,
                    response=sample.response,
                )
        except (
            RagasFrameworkError,
            RagasJudgeProviderError,
            RagasJudgeTimeoutError,
            RagasNetworkError,
            RagasRateLimitError,
        ):
            raise
        except Exception as error:  # noqa: BLE001 - Provider wrappers vary.
            _raise_classified_judge_error(error)
        value = result.value
        if value is None or not math.isfinite(float(value)):
            reason = str(result.reason or "").casefold()
            if "timeout" in reason or "timed out" in reason:
                raise RagasJudgeTimeoutError
            if any(
                marker in reason
                for marker in (
                    "connection",
                    "api call failed",
                    "rate limit",
                    "provider",
                    "authentication",
                )
            ):
                raise RagasJudgeProviderError
            raise RagasFrameworkError
        return float(value)


def current_ragas_prompt_bundle_sha256() -> str:
    """Hash the exact installed metric sources used by the frozen adapter."""

    from ragas.metrics.collections import (
        ContextPrecisionWithReference,
        ContextRecall,
        ContextRelevance,
        NoiseSensitivity,
    )

    prompt_sources: list[bytes] = []
    for metric_type in (
        ContextPrecisionWithReference,
        ContextRecall,
        ContextRelevance,
        NoiseSensitivity,
    ):
        source_path = inspect.getsourcefile(metric_type)
        if source_path is None:
            raise RagasFrameworkError
        with open(source_path, "rb") as source_file:
            prompt_sources.append(source_file.read())
    return hashlib.sha256(b"\0".join(prompt_sources)).hexdigest()


def _raise_classified_judge_error(error: Exception) -> Never:
    """Map third-party exception chains to safe, non-overlapping categories."""

    chain: list[BaseException] = []
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__
    names = " ".join(type(item).__name__.casefold() for item in chain)
    if any(marker in names for marker in ("timeout", "timedout")):
        raise RagasJudgeTimeoutError from None
    if "ratelimit" in names:
        raise RagasRateLimitError from None
    if any(
        marker in names
        for marker in (
            "apiconnection",
            "connectionerror",
            "connecterror",
            "networkerror",
            "dns",
        )
    ):
        raise RagasNetworkError from None
    raise RagasJudgeProviderError from None
