"""Ragas 0.4.3 generation metrics with bounded, auditable failures."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import math
from collections.abc import Callable
from contextvars import ContextVar
from typing import Literal, Protocol, TypeAlias

from pydantic import Field, SecretStr, ValidationError, model_validator
from ragas.embeddings.base import BaseRagasEmbedding

from app.core.config import BGE_M3_MODEL_ID, BGE_M3_REVISION
from app.evals.ragas_retrieval import (
    RAGAS_VERSION,
    RagasFrameworkError,
    RagasJudgeProviderError,
    RagasJudgeRuntime,
    RagasJudgeTimeoutError,
    RagasNetworkError,
    RagasRateLimitError,
    _raise_classified_judge_error,
)
from app.schemas.common import M1Schema
from app.schemas.evaluation import RagasMetricResult, SafeIdentifier, VersionLabel
from app.services.retrieval.embedding import (
    EmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingPurpose,
)

RAGAS_GENERATION_PROMPT_BUNDLE_SHA256 = (
    "4cb3e8b85f726ad2c298b910adeb7086a2f3d92aa3615debdb2cc14957d479f7"
)
RagasGenerationMetricName: TypeAlias = Literal[
    "faithfulness",
    "response_relevancy",
    "factual_correctness",
    "semantic_similarity",
]
RAGAS_GENERATION_METRICS: tuple[RagasGenerationMetricName, ...] = (
    "faithfulness",
    "response_relevancy",
    "factual_correctness",
    "semantic_similarity",
)

JudgeFailureStage: TypeAlias = Literal[
    "request", "response", "parse", "score", "embedding", "unknown"
]


class JudgeRequestDiagnostic(M1Schema):
    """Allowlisted transport facts only; never retain bodies or exception text."""

    request_index: int = Field(strict=True, ge=1)
    http_status: int | None = Field(default=None, strict=True, ge=100, le=599)
    response_state: Literal[
        "not_received", "received", "invalid_json", "invalid_envelope"
    ] = "not_received"
    finish_reason: (
        Literal[
            "stop", "length", "content_filter", "tool_calls", "function_call", "other"
        ]
        | None
    ) = None
    content_empty: bool | None = Field(default=None, strict=True)
    input_tokens: int | None = Field(default=None, strict=True, ge=0)
    output_tokens: int | None = Field(default=None, strict=True, ge=0)
    parse_error: Literal["json", "schema", "other"] | None = None


class JudgeMetricDiagnostic(M1Schema):
    """One metric's observations, independent of score and stop policy."""

    metric_name: RagasGenerationMetricName
    failure_stage: JudgeFailureStage | None = None
    requests: list[JudgeRequestDiagnostic] = Field(default_factory=list)


# Child asyncio tasks inherit the metric, but keep their own current request.
_active_judge_metric: ContextVar[JudgeMetricDiagnostic | None] = ContextVar(
    "active_judge_metric", default=None
)
_active_judge_request: ContextVar[JudgeRequestDiagnostic | None] = ContextVar(
    "active_judge_request", default=None
)


def _capture_judge_parse_error(error: Exception, **_metadata: object) -> None:
    """Called only by Instructor's parse:error hook, not by guessing class names."""

    request = _active_judge_request.get()
    if request is None:
        return
    if isinstance(error, json.JSONDecodeError):
        request.parse_error = "json"
    elif isinstance(error, ValidationError):
        request.parse_error = (
            "json"
            if any(
                item["type"] == "json_invalid"
                for item in error.errors(
                    include_url=False, include_context=False, include_input=False
                )
            )
            else "schema"
        )
    else:
        request.parse_error = "other"


def _record_judge_failure(stage: JudgeFailureStage) -> None:
    diagnostic = _active_judge_metric.get()
    if diagnostic is not None:
        diagnostic.failure_stage = stage


def _judge_failure_stage(error: Exception) -> JudgeFailureStage:
    from instructor.core import IncompleteOutputException
    from openai import APIConnectionError, APIStatusError

    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (APIConnectionError, APIStatusError)):
            return "request"
        if isinstance(current, IncompleteOutputException):
            return "response"
        current = current.__cause__ or current.__context__
    request = _active_judge_request.get()
    if request is not None:
        if request.response_state in {"invalid_json", "invalid_envelope"}:
            return "response"
        if request.parse_error is not None:
            return "parse"
    return "unknown"


class RagasGenerationInput(M1Schema):
    """One complete answer sample; it is consumed but never copied to reports."""

    user_input: str = Field(min_length=1, max_length=2000)
    retrieved_contexts: tuple[str, ...] = Field(min_length=1, max_length=12)
    reference: str = Field(min_length=1, max_length=10_000)
    response: str = Field(min_length=1, max_length=10_000)


class RagasGenerationEvaluatorIdentity(M1Schema):
    """Serializable generation Judge and embedding identity without credentials."""

    framework: Literal["ragas"] = "ragas"
    framework_version: Literal["0.4.3"] = RAGAS_VERSION
    api_family: Literal["collections"] = "collections"
    prompt_bundle_version: VersionLabel
    prompt_bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    judge: RagasJudgeRuntime
    embedding_provider: SafeIdentifier
    embedding_model: str = Field(min_length=1, max_length=200)
    embedding_revision: VersionLabel
    answer_provider: SafeIdentifier
    answer_model: str = Field(min_length=1, max_length=200)
    same_model_bias: bool


class RagasGenerationEvaluation(M1Schema):
    """One safe semantic column; source texts stay outside the report."""

    evaluator_identity: RagasGenerationEvaluatorIdentity
    metrics: list[RagasMetricResult] = Field(min_length=4, max_length=4)
    judge_diagnostics: list[JudgeMetricDiagnostic] = Field(
        default_factory=list, max_length=4
    )

    @model_validator(mode="after")
    def validate_metric_set(self) -> RagasGenerationEvaluation:
        if [metric.metric_name for metric in self.metrics] != list(
            RAGAS_GENERATION_METRICS
        ):
            raise ValueError("Ragas generation metrics must use the frozen order")
        if self.judge_diagnostics and [
            d.metric_name for d in self.judge_diagnostics
        ] != list(RAGAS_GENERATION_METRICS):
            raise ValueError("Judge diagnostics must use the frozen metric order")
        return self


class RagasGenerationBackend(Protocol):
    framework_version: str
    prompt_bundle_version: str
    prompt_bundle_sha256: str
    embedding_provider: str
    embedding_model: str
    embedding_revision: str

    async def score(
        self,
        metric_name: str,
        sample: RagasGenerationInput,
    ) -> float: ...


class RagasGenerationTimeoutError(TimeoutError):
    """The generation Judge timed out without exposing raw details."""


class RagasGenerationNetworkError(ConnectionError):
    """The generation Judge network request failed safely."""


class RagasGenerationRateLimitError(RuntimeError):
    """The generation Judge rate limit was reached safely."""


class RagasGenerationProviderError(RuntimeError):
    """The generation Judge rejected a request without leaking its response."""


class RagasGenerationAdapter:
    """Run the four frozen generation metrics and preserve non-numeric failures."""

    def __init__(
        self,
        *,
        backend: RagasGenerationBackend,
        judge: RagasJudgeRuntime,
        answer_provider: str,
        answer_model: str,
    ) -> None:
        if backend.framework_version != RAGAS_VERSION:
            raise ValueError(f"Ragas backend must be exactly {RAGAS_VERSION}")
        self._backend = backend
        self._judge = judge
        self._answer_provider = answer_provider
        self._answer_model = answer_model

    @property
    def evaluator_identity(self) -> RagasGenerationEvaluatorIdentity:
        return RagasGenerationEvaluatorIdentity(
            prompt_bundle_version=self._backend.prompt_bundle_version,
            prompt_bundle_sha256=self._backend.prompt_bundle_sha256,
            judge=self._judge,
            embedding_provider=self._backend.embedding_provider,
            embedding_model=self._backend.embedding_model,
            embedding_revision=self._backend.embedding_revision,
            answer_provider=self._answer_provider,
            answer_model=self._answer_model,
            same_model_bias=(
                self._answer_provider.casefold()
                in self._judge.provider.casefold().split("-openai-compatible", 1)[0]
                and self._answer_model.casefold() == self._judge.model.casefold()
            ),
        )

    async def evaluate(
        self,
        sample: RagasGenerationInput,
    ) -> RagasGenerationEvaluation:
        metrics = []
        diagnostics = []
        for metric_name in RAGAS_GENERATION_METRICS:
            diagnostic = JudgeMetricDiagnostic(metric_name=metric_name)
            metric_token = _active_judge_metric.set(diagnostic)
            request_token = _active_judge_request.set(None)
            try:
                metric = await self._run_metric(metric_name, sample)
                if metric.status != "completed" and diagnostic.failure_stage is None:
                    diagnostic.failure_stage = "unknown"
                metrics.append(metric)
                diagnostics.append(diagnostic)
            finally:
                _active_judge_request.reset(request_token)
                _active_judge_metric.reset(metric_token)
        return RagasGenerationEvaluation(
            evaluator_identity=self.evaluator_identity,
            metrics=metrics,
            judge_diagnostics=diagnostics,
        )

    async def aclose(self) -> None:
        close = getattr(self._backend, "aclose", None)
        if callable(close):
            result = close()
            if inspect.isawaitable(result):
                await result

    async def _run_metric(
        self,
        metric_name: RagasGenerationMetricName,
        sample: RagasGenerationInput,
    ) -> RagasMetricResult:
        try:
            value = await self._backend.score(metric_name, sample)
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise RagasFrameworkError
            return RagasMetricResult(
                metric_name=metric_name,
                status="completed",
                value=value,
                direction="higher_is_better",
            )
        except RagasFrameworkError:
            diagnostic = _active_judge_metric.get()
            if diagnostic is not None and diagnostic.failure_stage is None:
                diagnostic.failure_stage = "score"
            return _failed_metric(
                metric_name,
                status="framework_failed",
                category="framework_error",
                summary="Ragas returned an invalid generation metric result",
            )
        except (
            RagasGenerationTimeoutError,
            RagasGenerationNetworkError,
            RagasGenerationRateLimitError,
            RagasGenerationProviderError,
        ) as error:
            if isinstance(error, RagasGenerationTimeoutError):
                return _failed_metric(
                    metric_name,
                    status="judge_failed",
                    category="judge_timeout",
                    summary="The generation Judge timed out",
                )
            if isinstance(error, RagasGenerationNetworkError):
                return _failed_metric(
                    metric_name,
                    status="judge_failed",
                    category="network_error",
                    summary="The generation Judge network request failed",
                )
            if isinstance(error, RagasGenerationRateLimitError):
                return _failed_metric(
                    metric_name,
                    status="judge_failed",
                    category="rate_limited",
                    summary="The generation Judge rate limit was reached",
                )
            return _failed_metric(
                metric_name,
                status="judge_failed",
                category="judge_provider_error",
                summary="The generation Judge request failed",
            )
        except Exception:  # noqa: BLE001 - fake backends are untrusted.
            return _failed_metric(
                metric_name,
                status="judge_failed",
                category="judge_provider_error",
                summary="The generation Judge request failed",
            )


def _failed_metric(
    metric_name: RagasGenerationMetricName,
    *,
    status: Literal["framework_failed", "judge_failed"],
    category: Literal[
        "framework_error",
        "judge_timeout",
        "network_error",
        "rate_limited",
        "judge_provider_error",
    ],
    summary: str,
) -> RagasMetricResult:
    return RagasMetricResult(
        metric_name=metric_name,
        status=status,
        value=None,
        direction="higher_is_better",
        failure_category=category,
        failure_summary=summary,
    )


class ProjectRagasEmbedding(BaseRagasEmbedding):
    """Present the existing local project EmbeddingProvider to Ragas."""

    def __init__(self, provider: EmbeddingProvider) -> None:
        super().__init__()
        self._provider = provider

    def embed_text(self, text: str, **_kwargs: object) -> list[float]:
        batch = self._provider.embed((text,), purpose=EmbeddingPurpose.QUERY)
        return list(batch.vectors[0])

    async def aembed_text(self, text: str, **kwargs: object) -> list[float]:
        return await asyncio.to_thread(self.embed_text, text, **kwargs)


class Ragas043GenerationBackend:
    """Thin wrapper around the installed Ragas collections generation API."""

    framework_version: str = RAGAS_VERSION
    prompt_bundle_version = "ragas-0.4.3-collections-generation-source-v1"
    embedding_provider = "bge-m3-local"
    embedding_model = BGE_M3_MODEL_ID
    embedding_revision = BGE_M3_REVISION

    def __init__(
        self,
        *,
        judge: RagasJudgeRuntime,
        api_key: SecretStr,
        base_url: str,
        embedding_provider: EmbeddingProvider,
        client_factory: Callable[..., object] | None = None,
    ) -> None:
        identity = embedding_provider.identity
        if (
            identity.provider != self.embedding_provider
            or identity.model_id != self.embedding_model
            or identity.revision != self.embedding_revision
            or not identity.normalize
        ):
            raise ValueError("Ragas generation requires the frozen local BGE-M3")
        from instructor.core.hooks import Hooks
        from openai import AsyncOpenAI
        from ragas.llms import llm_factory
        from ragas.metrics.collections import (
            AnswerRelevancy,
            FactualCorrectness,
            Faithfulness,
            SemanticSimilarity,
        )

        factory = client_factory or AsyncOpenAI
        self._client = factory(
            api_key=api_key.get_secret_value(),
            base_url=base_url,
            timeout=judge.timeout_ms / 1000,
            max_retries=0,
        )
        hooks = Hooks()
        hooks.on("parse:error", _capture_judge_parse_error)
        llm = llm_factory(
            judge.model,
            provider="openai",
            client=self._client,
            hooks=hooks,
            temperature=float(judge.temperature),
            top_p=float(judge.top_p),
            max_tokens=judge.max_output_tokens,
            seed=judge.seed,
        )
        embeddings = ProjectRagasEmbedding(embedding_provider)
        self._metrics = {
            "faithfulness": Faithfulness(llm=llm),
            "response_relevancy": AnswerRelevancy(
                llm=llm,
                embeddings=embeddings,
            ),
            "factual_correctness": FactualCorrectness(llm=llm, mode="f1"),
            "semantic_similarity": SemanticSimilarity(
                embeddings=embeddings,
            ),
        }
        prompt_hash = current_ragas_generation_prompt_bundle_sha256()
        if prompt_hash != RAGAS_GENERATION_PROMPT_BUNDLE_SHA256:
            raise RagasFrameworkError
        self.prompt_bundle_sha256 = prompt_hash

    async def score(
        self,
        metric_name: str,
        sample: RagasGenerationInput,
    ) -> float:
        metric = self._metrics.get(metric_name)
        if metric is None:
            raise RagasFrameworkError
        try:
            if metric_name == "faithfulness":
                result = await metric.ascore(
                    user_input=sample.user_input,
                    response=sample.response,
                    retrieved_contexts=list(sample.retrieved_contexts),
                )
            elif metric_name == "response_relevancy":
                result = await metric.ascore(
                    user_input=sample.user_input,
                    response=sample.response,
                )
            elif metric_name == "factual_correctness":
                result = await metric.ascore(
                    response=sample.response,
                    reference=sample.reference,
                )
            else:
                result = await metric.ascore(
                    reference=sample.reference,
                    response=sample.response,
                )
        except EmbeddingProviderError:
            _record_judge_failure("embedding")
            raise RagasFrameworkError from None
        except RagasFrameworkError:
            raise
        except Exception as error:  # noqa: BLE001 - Provider wrappers vary.
            _record_judge_failure(_judge_failure_stage(error))
            _raise_generation_error(error)
        try:
            value = result.value
            if value is None or not math.isfinite(float(value)):
                raise RagasFrameworkError
            return float(value)
        except Exception:
            _record_judge_failure("score")
            raise

    async def aclose(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            result = close()
            if inspect.isawaitable(result):
                await result


def current_ragas_generation_prompt_bundle_sha256() -> str:
    """Hash the exact installed generation metric sources."""

    from ragas.metrics.collections import (
        AnswerRelevancy,
        FactualCorrectness,
        Faithfulness,
        SemanticSimilarity,
    )

    sources: list[bytes] = []
    for metric_type in (
        Faithfulness,
        AnswerRelevancy,
        FactualCorrectness,
        SemanticSimilarity,
    ):
        source_path = inspect.getsourcefile(metric_type)
        if source_path is None:
            raise RagasFrameworkError
        with open(source_path, "rb") as source_file:
            sources.append(source_file.read())
    return hashlib.sha256(b"\0".join(sources)).hexdigest()


def _raise_generation_error(error: Exception) -> None:
    try:
        _raise_classified_judge_error(error)
    except RagasJudgeTimeoutError:
        raise RagasGenerationTimeoutError from None
    except RagasNetworkError:
        raise RagasGenerationNetworkError from None
    except RagasRateLimitError:
        raise RagasGenerationRateLimitError from None
    except RagasJudgeProviderError:
        raise RagasGenerationProviderError from None
