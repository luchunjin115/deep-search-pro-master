"""Public-safe report contracts for the M2-22.8.2 Fake Answer run."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Literal, TypeAlias
from uuid import uuid4

from pydantic import Field, FiniteFloat, model_validator

from app.core.rag_trace import review_value
from app.evals.answer_citation_metrics import aggregate_answer_citation_results
from app.evals.ragas_generation import (
    JudgeMetricDiagnostic,
    RagasGenerationEvaluatorIdentity,
)
from app.evals.reranker_context_report import FrozenRagCorpusPublicIdentity
from app.schemas.agent import BusinessOutcome
from app.schemas.common import AgentProviderOutputStage, ErrorCode, M1Schema
from app.schemas.evaluation import (
    AnswerCitationCaseResult,
    AnswerCitationEvaluationCohort,
    AnswerCitationEvaluationPlan,
    AnswerCitationGroupedResults,
    AnswerCitationReportingCohort,
    EvaluationSourceGroup,
    ModelIdentifier,
    ProjectMetricStatus,
    RagasMetricResult,
    SafeIdentifier,
    Sha256,
    VersionLabel,
)

GenerationMetricName: TypeAlias = Literal[
    "faithfulness",
    "response_relevancy",
    "factual_correctness",
    "semantic_similarity",
]

_GENERATION_METRIC_ORDER: tuple[GenerationMetricName, ...] = (
    "faithfulness",
    "response_relevancy",
    "factual_correctness",
    "semantic_similarity",
)


class FakeAnswerProviderIdentity(M1Schema):
    """An explicit fake identity that cannot be mistaken for Qwen or DeepSeek."""

    provider: Literal["deterministic_fake"] = "deterministic_fake"
    model_id: ModelIdentifier = "fake/m2-deterministic-answer"
    revision: VersionLabel = "m2-fake-answer-v1"
    response_policy_version: Literal["golden-if-authorized-v1"] = (
        "golden-if-authorized-v1"
    )


class AnswerCitationCacheStats(M1Schema):
    """Run-local Answer cache facts; unsuccessful executions are never retained."""

    scope: Literal["current_run_only"] = "current_run_only"
    answer_requests: int = Field(strict=True, ge=0)
    cache_hits: int = Field(strict=True, ge=0)
    cache_misses: int = Field(strict=True, ge=0)
    provider_answer_calls: int = Field(strict=True, ge=0)
    cache_entries: int = Field(strict=True, ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> AnswerCitationCacheStats:
        if self.answer_requests != self.cache_hits + self.cache_misses:
            raise ValueError("Answer requests must equal cache hits plus misses")
        if self.provider_answer_calls != self.cache_misses:
            raise ValueError("each Answer cache miss must call the Provider")
        if self.cache_entries > self.provider_answer_calls:
            raise ValueError("Answer cache entries cannot exceed Provider calls")
        return self


class AnswerCitationPublicTrace(M1Schema):
    """One public per-case trace containing hashes and metrics, never private text."""

    case_id: SafeIdentifier
    source_group: EvaluationSourceGroup
    reporting_cohort: AnswerCitationReportingCohort
    should_answer: bool
    question_sha256: Sha256
    context_sha256: Sha256
    answer_rules_sha256: Sha256
    provider_request_sha256: Sha256
    answer_output_sha256: Sha256 | None = None
    result: AnswerCitationCaseResult

    @model_validator(mode="after")
    def validate_trace(self) -> AnswerCitationPublicTrace:
        if (
            self.result.case_id != self.case_id
            or self.result.source_group != self.source_group
            or self.result.reporting_cohort != self.reporting_cohort
            or self.result.should_answer != self.should_answer
        ):
            raise ValueError("Answer trace identity contradicts its metric result")
        if (self.answer_output_sha256 is None) == (
            self.result.answer_execution_status == "completed"
        ):
            raise ValueError("Answer output hash contradicts the execution status")
        return self


class AnswerCitationCaseRunResult(M1Schema):
    """One public trace plus a SHA-256 that detects later report tampering."""

    trace: AnswerCitationPublicTrace
    trace_sha256: Sha256

    @model_validator(mode="after")
    def validate_trace_hash(self) -> AnswerCitationCaseRunResult:
        if self.trace_sha256 != public_answer_trace_sha256(self.trace):
            raise ValueError("Answer trace hash does not match its payload")
        return self


class AnswerCitationEvaluationReport(M1Schema):
    """Fake-only 40-row report whose quality gate is deliberately non-numeric."""

    schema_version: Literal["m2-answer-citation-fake-report-v1"] = (
        "m2-answer-citation-fake-report-v1"
    )
    execution_mode: Literal["deterministic_fake"] = "deterministic_fake"
    run_id: SafeIdentifier
    run_status: Literal["completed"] = "completed"
    quality_gate_passed: None = None
    plan: AnswerCitationEvaluationPlan
    dataset_version: Literal["m2-cross-border-rag-smoke-v1"]
    dataset_sha256: Sha256
    input_sha256: Sha256
    provider: FakeAnswerProviderIdentity
    cohort: AnswerCitationEvaluationCohort
    case_results: list[AnswerCitationCaseRunResult] = Field(
        min_length=40,
        max_length=40,
    )
    grouped_results: AnswerCitationGroupedResults
    cache: AnswerCitationCacheStats
    trace_set_sha256: Sha256

    @model_validator(mode="after")
    def validate_report(self) -> AnswerCitationEvaluationReport:
        if self.run_id != f"m2-2282-{self.input_sha256[:16]}":
            raise ValueError("Fake Answer run ID must derive from its safe input hash")
        if (
            self.plan.dataset_version != self.dataset_version
            or self.cohort.dataset_version != self.dataset_version
        ):
            raise ValueError("Fake Answer report dataset identities do not match")
        expected_ids = [item.case_id for item in self.cohort.answerable_cases] + [
            item.case_id for item in self.cohort.safety_cases
        ]
        actual_ids = [item.trace.case_id for item in self.case_results]
        if actual_ids != expected_ids:
            raise ValueError("Fake Answer report changed the frozen 34 plus six order")
        expected_grouped = aggregate_answer_citation_results(
            [item.trace.result for item in self.case_results],
            cohort=self.cohort,
        )
        if self.grouped_results != expected_grouped:
            raise ValueError("Fake Answer grouped results contradict retained rows")
        expected_trace_set_hash = build_answer_trace_set_sha256(
            [item.trace_sha256 for item in self.case_results]
        )
        if self.trace_set_sha256 != expected_trace_set_hash:
            raise ValueError("Answer trace set hash does not match its case hashes")
        completed_count = sum(
            item.trace.result.answer_execution_status == "completed"
            for item in self.case_results
        )
        if (
            self.cache.answer_requests != len(self.case_results)
            or self.cache.cache_hits != 0
            or self.cache.cache_misses != len(self.case_results)
            or self.cache.provider_answer_calls != len(self.case_results)
            or self.cache.cache_entries != completed_count
        ):
            raise ValueError(
                "Fake Answer report must request every row once and cache only success"
            )
        return self

    def artifact_sha256(self) -> str:
        """Hash the exact canonical bytes written by the public report writer."""

        return hashlib.sha256(serialize_answer_citation_public_report(self)).hexdigest()


class GatewayFakeAnswerProviderIdentity(M1Schema):
    """Evaluation-only routing and Answer identity used behind the real Gateway."""

    provider: Literal["deterministic_gateway_fake"] = "deterministic_gateway_fake"
    model_id: ModelIdentifier = "fake/m2-gateway-answer"
    revision: VersionLabel = "m2-gateway-fake-v3"
    routing_policy_version: Literal["knowledge-search-then-answer-v3"] = (
        "knowledge-search-then-answer-v3"
    )
    response_policy_version: Literal["canonical-answer-golden-evidence-v1"] = (
        "canonical-answer-golden-evidence-v1"
    )


class FormalAnswerProviderIdentity(M1Schema):
    """Public DeepSeek Answer identity without private payloads."""

    provider: Literal["deepseek"] = "deepseek"
    model_id: ModelIdentifier
    model_version: VersionLabel = "api-alias-20260911"
    api_dialect: Literal["responses"] = "responses"
    prompt_bundle_sha256: Sha256
    answer_schema_sha256: Sha256
    reasoning_effort: Literal["none"] = "none"
    temperature: Literal[0] = 0
    routing_policy_version: Literal["knowledge-search-then-answer-v3"] = (
        "knowledge-search-then-answer-v3"
    )


class FormalModelUsage(M1Schema):
    """Safe aggregate counters; no request or response payload is retained."""

    api_calls: int = Field(default=0, strict=True, ge=0, le=10_000)
    input_tokens: int = Field(default=0, strict=True, ge=0, le=100_000_000)
    output_tokens: int = Field(default=0, strict=True, ge=0, le=100_000_000)
    total_tokens: int = Field(default=0, strict=True, ge=0, le=200_000_000)

    @model_validator(mode="after")
    def validate_total(self) -> FormalModelUsage:
        if self.total_tokens != self.input_tokens + self.output_tokens:
            raise ValueError("model total tokens must equal input plus output")
        return self


class AnswerCitationFormalCaseEvaluation(M1Schema):
    """One public Answer/Ragas row without source text."""

    case_id: SafeIdentifier
    status: Literal["completed", "calculation_failed", "skipped"]
    answer_duration_ms: int | None = Field(default=None, strict=True, ge=0)
    answer_usage: FormalModelUsage
    judge_duration_ms: int = Field(strict=True, ge=0)
    judge_usage: FormalModelUsage
    semantic_metrics: list[RagasMetricResult] = Field(min_length=4, max_length=4)
    judge_diagnostics: list[JudgeMetricDiagnostic] = Field(
        default_factory=list, max_length=4
    )

    @model_validator(mode="after")
    def validate_semantic_result(self) -> AnswerCitationFormalCaseEvaluation:
        if self.judge_diagnostics and [
            d.metric_name for d in self.judge_diagnostics
        ] != list(_GENERATION_METRIC_ORDER):
            raise ValueError("Judge diagnostics must use the frozen metric order")
        if [item.metric_name for item in self.semantic_metrics] != list(
            _GENERATION_METRIC_ORDER
        ):
            raise ValueError("formal generation metrics must use the frozen order")
        statuses = {item.status for item in self.semantic_metrics}
        expected = (
            "completed"
            if statuses == {"completed"}
            else "skipped"
            if statuses == {"skipped"}
            else "calculation_failed"
        )
        if self.status != expected:
            raise ValueError("formal semantic status contradicts metric statuses")
        if self.status == "skipped" and (
            self.judge_duration_ms != 0 or self.judge_usage.api_calls != 0
        ):
            raise ValueError("skipped semantic row cannot call the Judge")
        if self.answer_usage.api_calls and self.answer_duration_ms is None:
            raise ValueError("real Answer call requires a measured duration")
        if self.answer_usage.api_calls > 2:
            raise ValueError("one Answer compose allows at most one repair")
        return self


class FormalGenerationMetricAggregate(M1Schema):
    """One fixed semantic metric aggregate with failed rows kept in the denominator."""

    metric_name: GenerationMetricName
    eligible_case_count: int = Field(strict=True, ge=0, le=34)
    completed_case_count: int = Field(strict=True, ge=0, le=34)
    failed_case_count: int = Field(strict=True, ge=0, le=34)
    skipped_case_count: int = Field(strict=True, ge=0, le=40)
    mean: FiniteFloat | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_counts(self) -> FormalGenerationMetricAggregate:
        if self.eligible_case_count != (
            self.completed_case_count + self.failed_case_count
        ):
            raise ValueError(
                "semantic eligible count must include completed and failed"
            )
        if self.eligible_case_count + self.skipped_case_count != 40:
            raise ValueError("semantic aggregate must retain all 40 cases")
        if (self.mean is None) == (self.completed_case_count > 0):
            raise ValueError("semantic mean must exist exactly when scores exist")
        return self


class AnswerCitationGatewayRuntimeIdentity(M1Schema):
    """Public proof of the evaluation-only device and budget wiring."""

    scope: Literal["knowledge_only_evaluation"] = "knowledge_only_evaluation"
    embedding_device: Literal["cpu"] = "cpu"
    embedding_precision: Literal["float32"] = "float32"
    reranker_device: Literal["cuda"] = "cuda"
    reranker_precision: Literal["float32"] = "float32"
    root_max_evidence: Literal[12] = 12
    business_max_evidence: Literal[0] = 0
    knowledge_max_evidence: Literal[12] = 12
    search_knowledge_timeout_ms: Literal[8000] = 8000


class AnswerCitationGatewayCaseAudit(M1Schema):
    """Public counts proving one case crossed every required runtime boundary."""

    case_id: SafeIdentifier
    should_answer: bool = True
    status: ProjectMetricStatus
    api_status_code: int | None = Field(default=None, strict=True, ge=100, le=599)
    api_error_code: ErrorCode | None = None
    agent_output_stage: AgentProviderOutputStage | None = None
    gateway_status: Literal["completed"] | None = None
    gateway_business_outcome: BusinessOutcome | None = None
    tool_names: list[Literal["search_knowledge"]] = Field(
        default_factory=list,
        max_length=1,
    )
    root_run_count: int = Field(strict=True, ge=0)
    worker_run_count: int = Field(strict=True, ge=0)
    search_knowledge_tool_call_count: int = Field(strict=True, ge=0)
    allowed_successful_tool_call_count: int = Field(strict=True, ge=0)
    search_knowledge_tool_status: (
        Literal["running", "success", "error", "denied", "timeout"] | None
    ) = None
    search_knowledge_duration_ms: int | None = Field(default=None, strict=True, ge=0)
    search_knowledge_error_code: ErrorCode | None = None
    context_artifact_count: int = Field(strict=True, ge=0)
    context_segment_count: int = Field(strict=True, ge=0)
    context_evidence_count: int = Field(strict=True, ge=0)
    provider_evidence_count: int = Field(strict=True, ge=0)
    answer_evidence_count: int = Field(strict=True, ge=0)
    public_evidence_count: int = Field(strict=True, ge=0)
    context_authorization_passed: bool | None = None
    answer_citation_validator_passed: bool | None = None
    answer_mapping_passed: bool | None = None
    protected_evidence_leak_count: int | None = Field(
        default=None,
        strict=True,
        ge=0,
    )
    chain_passed: bool | None = None
    failure_summary: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def validate_chain(self) -> AnswerCitationGatewayCaseAudit:
        if self.status != "completed":
            if self.chain_passed is not False or not self.failure_summary:
                raise ValueError("failed Gateway audit requires a safe failure")
            return self
        expected = (
            self.api_status_code == 200,
            self.gateway_status == "completed",
            self.tool_names == ["search_knowledge"],
            self.root_run_count == 1,
            self.worker_run_count == 1,
            self.search_knowledge_tool_call_count == 1,
            self.allowed_successful_tool_call_count == 1,
            self.search_knowledge_tool_status == "success",
            self.search_knowledge_duration_ms is not None,
            self.api_error_code is None,
            self.agent_output_stage is None,
            self.search_knowledge_error_code is None,
            self.context_artifact_count == 1,
            self.context_segment_count == self.context_evidence_count,
            self.provider_evidence_count == self.context_evidence_count,
            self.answer_evidence_count == self.public_evidence_count,
            self.context_authorization_passed is True,
            self.answer_citation_validator_passed is True,
            self.answer_mapping_passed is True,
            self.protected_evidence_leak_count == 0,
            self.chain_passed is True,
            self.failure_summary is None,
        )
        if not all(expected):
            raise ValueError(
                "completed row did not cross the complete public Gateway chain"
            )
        if not self.should_answer and (
            self.answer_evidence_count or self.public_evidence_count
        ):
            raise ValueError("completed safety row exposed cited Evidence")
        return self


class AnswerCitationGatewayLifecycle(M1Schema):
    """Exact runtime rows created and removed without touching the frozen corpus."""

    created_thread_count: int = Field(strict=True, ge=0)
    created_root_run_count: int = Field(strict=True, ge=0)
    created_worker_run_count: int = Field(strict=True, ge=0)
    created_tool_call_count: int = Field(strict=True, ge=0)
    created_context_artifact_count: int = Field(strict=True, ge=0)
    created_evidence_count: int = Field(strict=True, ge=0)
    created_answer_evidence_count: int = Field(strict=True, ge=0)
    remaining_thread_count: int = Field(strict=True, ge=0)
    remaining_agent_run_count: int = Field(strict=True, ge=0)
    remaining_tool_call_count: int = Field(strict=True, ge=0)
    remaining_context_artifact_count: int = Field(strict=True, ge=0)
    remaining_evidence_count: int = Field(strict=True, ge=0)
    remaining_answer_evidence_count: int = Field(strict=True, ge=0)
    baseline_restored: bool

    @model_validator(mode="after")
    def validate_cleanup(self) -> AnswerCitationGatewayLifecycle:
        remaining = (
            self.remaining_thread_count,
            self.remaining_agent_run_count,
            self.remaining_tool_call_count,
            self.remaining_context_artifact_count,
            self.remaining_evidence_count,
            self.remaining_answer_evidence_count,
        )
        if self.baseline_restored != all(value == 0 for value in remaining):
            raise ValueError("Gateway lifecycle status contradicts remaining rows")
        return self


class AnswerCitationGatewayEvaluationReport(M1Schema):
    """Real-Gateway/Fake-Answer report; it deliberately has no quality score."""

    schema_version: Literal["m2-answer-citation-gateway-report-v1"] = (
        "m2-answer-citation-gateway-report-v1"
    )
    execution_mode: Literal["real_gateway_fake_answer"] = "real_gateway_fake_answer"
    run_id: SafeIdentifier
    run_status: Literal["completed", "completed_with_failures"]
    quality_gate_passed: None = None
    plan: AnswerCitationEvaluationPlan
    dataset_version: Literal["m2-cross-border-rag-smoke-v1"]
    dataset_sha256: Sha256
    input_sha256: Sha256
    provider: GatewayFakeAnswerProviderIdentity
    runtime_identity: AnswerCitationGatewayRuntimeIdentity
    corpus_before: FrozenRagCorpusPublicIdentity
    corpus_after: FrozenRagCorpusPublicIdentity
    cohort: AnswerCitationEvaluationCohort
    case_results: list[AnswerCitationCaseRunResult] = Field(
        min_length=40,
        max_length=40,
    )
    chain_audits: list[AnswerCitationGatewayCaseAudit] = Field(
        min_length=40,
        max_length=40,
    )
    grouped_results: AnswerCitationGroupedResults
    answer_compose_calls: int = Field(strict=True, ge=0)
    lifecycle: AnswerCitationGatewayLifecycle
    trace_set_sha256: Sha256

    @model_validator(mode="after")
    def validate_gateway_report(self) -> AnswerCitationGatewayEvaluationReport:
        if self.run_id != f"m2-2283-{self.input_sha256[:16]}":
            raise ValueError("Gateway Answer run ID must derive from its input hash")
        if self.corpus_before != self.corpus_after:
            raise ValueError("Gateway Answer run changed the frozen corpus")
        expected_ids = [item.case_id for item in self.cohort.answerable_cases] + [
            item.case_id for item in self.cohort.safety_cases
        ]
        result_ids = [item.trace.case_id for item in self.case_results]
        audit_ids = [item.case_id for item in self.chain_audits]
        if result_ids != expected_ids or audit_ids != expected_ids:
            raise ValueError("Gateway report changed the frozen 34 plus six order")
        grouped = aggregate_answer_citation_results(
            [item.trace.result for item in self.case_results],
            cohort=self.cohort,
        )
        if self.grouped_results != grouped:
            raise ValueError("Gateway grouped results contradict retained rows")
        trace_set = build_answer_trace_set_sha256(
            [item.trace_sha256 for item in self.case_results]
        )
        if self.trace_set_sha256 != trace_set:
            raise ValueError("Gateway trace set hash does not match its case hashes")
        all_chains_passed = all(item.chain_passed is True for item in self.chain_audits)
        complete = all_chains_passed and self.lifecycle.baseline_restored
        expected_status = "completed" if complete else "completed_with_failures"
        if self.run_status != expected_status:
            raise ValueError("Gateway run status contradicts chain and cleanup facts")
        if self.answer_compose_calls > len(self.chain_audits):
            raise ValueError("Gateway Answer compose count exceeds retained rows")
        if any(
            item.search_knowledge_duration_ms is not None
            and item.search_knowledge_duration_ms
            > self.runtime_identity.search_knowledge_timeout_ms
            for item in self.chain_audits
        ):
            raise ValueError("Gateway Tool duration exceeds its frozen timeout")
        return self

    def artifact_sha256(self) -> str:
        return hashlib.sha256(serialize_answer_citation_public_report(self)).hexdigest()


class AnswerCitationFormalEvaluationReport(M1Schema):
    """Fixed 40-row real DeepSeek Answer and Ragas report."""

    schema_version: Literal["m2-answer-citation-formal-report-v4"] = (
        "m2-answer-citation-formal-report-v4"
    )
    execution_mode: Literal["real_gateway_deepseek_answer_ragas"] = (
        "real_gateway_deepseek_answer_ragas"
    )
    run_id: SafeIdentifier
    run_status: Literal["completed", "completed_with_failures"]
    business_quality_gate_passed: bool
    ragas_quality_gate_passed: bool | None
    plan: AnswerCitationEvaluationPlan
    dataset_version: Literal["m2-cross-border-rag-smoke-v1"]
    dataset_sha256: Sha256
    input_sha256: Sha256
    provider: FormalAnswerProviderIdentity
    semantic_evaluator: RagasGenerationEvaluatorIdentity
    runtime_identity: AnswerCitationGatewayRuntimeIdentity
    corpus_before: FrozenRagCorpusPublicIdentity
    corpus_after: FrozenRagCorpusPublicIdentity
    cohort: AnswerCitationEvaluationCohort
    case_results: list[AnswerCitationCaseRunResult] = Field(
        min_length=40,
        max_length=40,
    )
    chain_audits: list[AnswerCitationGatewayCaseAudit] = Field(
        min_length=40,
        max_length=40,
    )
    formal_evaluations: list[AnswerCitationFormalCaseEvaluation] = Field(
        min_length=40,
        max_length=40,
    )
    grouped_results: AnswerCitationGroupedResults
    semantic_aggregates: list[FormalGenerationMetricAggregate] = Field(
        min_length=4,
        max_length=4,
    )
    answer_compose_calls: int = Field(strict=True, ge=0, le=40)
    answer_usage: FormalModelUsage
    judge_usage: FormalModelUsage
    lifecycle: AnswerCitationGatewayLifecycle
    trace_set_sha256: Sha256

    @model_validator(mode="after")
    def validate_formal_report(self) -> AnswerCitationFormalEvaluationReport:
        if self.run_id != f"m2-2287-{self.input_sha256[:16]}":
            raise ValueError("formal Answer run ID must derive from its input hash")
        if self.corpus_before != self.corpus_after:
            raise ValueError("formal Answer run changed the frozen corpus")
        expected_ids = [item.case_id for item in self.cohort.answerable_cases] + [
            item.case_id for item in self.cohort.safety_cases
        ]
        result_ids = [item.trace.case_id for item in self.case_results]
        audit_ids = [item.case_id for item in self.chain_audits]
        formal_ids = [item.case_id for item in self.formal_evaluations]
        if (
            result_ids != expected_ids
            or audit_ids != expected_ids
            or formal_ids != expected_ids
        ):
            raise ValueError("formal report changed the frozen 34 plus six order")
        grouped = aggregate_answer_citation_results(
            [item.trace.result for item in self.case_results],
            cohort=self.cohort,
        )
        if self.grouped_results != grouped:
            raise ValueError("formal grouped results contradict retained rows")
        trace_set = build_answer_trace_set_sha256(
            [item.trace_sha256 for item in self.case_results]
        )
        if self.trace_set_sha256 != trace_set:
            raise ValueError("formal trace set hash does not match its case hashes")
        aggregates = build_formal_metric_aggregates(self.formal_evaluations)
        if self.semantic_aggregates != aggregates:
            raise ValueError("formal semantic aggregates contradict retained rows")
        if self.answer_usage != _sum_usage(
            [item.answer_usage for item in self.formal_evaluations]
        ) or self.judge_usage != _sum_usage(
            [item.judge_usage for item in self.formal_evaluations]
        ):
            raise ValueError("formal model usage contradicts retained rows")
        if self.answer_usage.api_calls > self.answer_compose_calls * 2:
            raise ValueError("formal Answer usage exceeds one repair per compose")
        complete = (
            all(item.chain_passed is True for item in self.chain_audits)
            and self.lifecycle.baseline_restored
        )
        expected_status = "completed" if complete else "completed_with_failures"
        if self.run_status != expected_status:
            raise ValueError("formal run status contradicts execution facts")
        expected_gate = formal_quality_gate(
            run_status=self.run_status, grouped_results=self.grouped_results
        )
        if self.business_quality_gate_passed != expected_gate:
            raise ValueError("business quality gate contradicts retained metrics")
        if self.ragas_quality_gate_passed != ragas_quality_gate(
            aggregates, expected_case_count=len(self.cohort.answerable_cases)
        ):
            raise ValueError("auxiliary Ragas gate contradicts retained metrics")
        return self

    def artifact_sha256(self) -> str:
        return hashlib.sha256(serialize_answer_citation_public_report(self)).hexdigest()


def build_formal_metric_aggregates(
    rows: list[AnswerCitationFormalCaseEvaluation],
) -> list[FormalGenerationMetricAggregate]:
    """Aggregate the four fixed semantic columns without dropping failures."""

    aggregates: list[FormalGenerationMetricAggregate] = []
    for metric_name in _GENERATION_METRIC_ORDER:
        metrics = [
            next(
                item for item in row.semantic_metrics if item.metric_name == metric_name
            )
            for row in rows
        ]
        values = [
            float(item.value)
            for item in metrics
            if item.status == "completed" and item.value is not None
        ]
        failed = sum(
            item.status in {"framework_failed", "judge_failed"} for item in metrics
        )
        skipped = sum(item.status == "skipped" for item in metrics)
        aggregates.append(
            FormalGenerationMetricAggregate(
                metric_name=metric_name,
                eligible_case_count=len(values) + failed,
                completed_case_count=len(values),
                failed_case_count=failed,
                skipped_case_count=skipped,
                mean=sum(values) / len(values) if values else None,
            )
        )
    return aggregates


def _sum_usage(items: list[FormalModelUsage]) -> FormalModelUsage:
    return FormalModelUsage(
        api_calls=sum(item.api_calls for item in items),
        input_tokens=sum(item.input_tokens for item in items),
        output_tokens=sum(item.output_tokens for item in items),
        total_tokens=sum(item.total_tokens for item in items),
    )


def formal_quality_gate(
    *,
    run_status: Literal["completed", "completed_with_failures"],
    grouped_results: AnswerCitationGroupedResults,
) -> bool:
    """Keep existing business thresholds independent of auxiliary Ragas scores."""

    answerable = grouped_results.all_answerable
    safety = grouped_results.safety_acl_version
    return bool(
        run_status == "completed"
        and answerable.status == "completed"
        and answerable.citation_identity_valid_rate == 1
        and answerable.golden_citation_precision is not None
        and answerable.golden_citation_precision >= 0.95
        and safety.status == "completed"
        and safety.citation_identity_valid_rate == 1
        and safety.correct_refusal_rate is not None
        and safety.correct_refusal_rate >= 0.9
        and safety.safety_leakage_count == 0
    )


def ragas_quality_gate(
    semantic_aggregates: list[FormalGenerationMetricAggregate],
    *,
    expected_case_count: int,
) -> bool | None:
    """Advisory only: incomplete scores are unknown, never zero or a pass."""
    if any(
        item.completed_case_count != expected_case_count or item.failed_case_count
        for item in semantic_aggregates
    ):
        return None
    semantic = {item.metric_name: item for item in semantic_aggregates}
    return bool(
        semantic["faithfulness"].mean is not None
        and semantic["faithfulness"].mean >= 0.9
        and semantic["response_relevancy"].mean is not None
        and semantic["response_relevancy"].mean >= 0.85
    )


def public_answer_trace_sha256(trace: AnswerCitationPublicTrace) -> str:
    """Hash one canonical public-only trace."""

    return hashlib.sha256(_canonical_bytes(trace.model_dump(mode="json"))).hexdigest()


def build_answer_trace_set_sha256(trace_hashes: list[str]) -> str:
    """Hash the ordered 34 plus six trace hashes without exposing their text."""

    return hashlib.sha256(_canonical_bytes(trace_hashes)).hexdigest()


def serialize_answer_citation_public_report(
    report: (
        AnswerCitationEvaluationReport
        | AnswerCitationGatewayEvaluationReport
        | AnswerCitationFormalEvaluationReport
    ),
) -> bytes:
    """Serialize stable public JSON after rejecting private field names."""

    payload = report.model_dump(mode="json")
    _reject_private_report_keys(payload)
    return _canonical_bytes(payload) + b"\n"


def write_answer_citation_public_report(
    path: Path,
    report: (
        AnswerCitationEvaluationReport
        | AnswerCitationGatewayEvaluationReport
        | AnswerCitationFormalEvaluationReport
    ),
) -> str:
    """Write one deterministic public report and return its artifact SHA-256."""

    content = serialize_answer_citation_public_report(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class ReviewEvidenceWriteError(RuntimeError):
    """Safe explicit failure; never print an OS error containing local paths."""


class AnswerReviewWriter:
    """Private same-run evidence, separate from the public score report.

    The directory is git-ignored and not served by the API. Windows inherits the
    workspace ACL; this is local controlled storage, not encryption or a vault.
    """

    def __init__(self, project_root: Path, metadata: dict[str, object]) -> None:
        base = project_root.resolve() / "data/evals/runtime/private-review"
        if base.resolve() != base:
            raise ReviewEvidenceWriteError(
                "Private review directory cannot be redirected."
            )
        self.directory = base / uuid4().hex
        try:
            self.directory.mkdir(parents=True, mode=0o700)
        except OSError:
            raise ReviewEvidenceWriteError(
                "Private review initialization failed."
            ) from None
        self.write(
            "manifest.json", {"schema_version": "m2-answer-review-v1", **metadata}
        )

    def write(self, name: str, payload: dict[str, object]) -> None:
        if (
            re.fullmatch(
                r"(?:manifest|cleanup|report|case-\d{3}|score-\d{3})\.json", name
            )
            is None
        ):
            raise ReviewEvidenceWriteError("Invalid private review artifact name.")
        reviewed = review_value(payload)
        assert isinstance(reviewed, dict)
        content = (
            _canonical_bytes(
                {
                    "content_redacted": reviewed != payload,
                    "original_content_sha256": hashlib.sha256(
                        _canonical_bytes(payload)
                    ).hexdigest(),
                    **reviewed,
                }
            )
            + b"\n"
        )
        if len(content) > 2_000_000:
            raise ReviewEvidenceWriteError(
                "Private review artifact exceeds its size limit."
            )
        path = self.directory / name
        try:
            # Exclusive creation: a repeated run or duplicate case cannot overwrite.
            with path.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if path.read_bytes() != content:
                raise OSError
        except OSError:
            raise ReviewEvidenceWriteError(
                "Private review persistence failed; evaluation stopped."
            ) from None


def _reject_private_report_keys(value: object) -> None:
    forbidden = {
        "acl_fixture_id",
        "answer",
        "answer_text",
        "body_text",
        "context",
        "context_text",
        "exception",
        "local_path",
        "owner_user_id",
        "path",
        "question",
        "raw_error",
        "raw_response",
        "sql",
        "storage_key",
        "tenant_id",
        "trusted_user_fixture_id",
        "version_fixture_id",
    }
    if isinstance(value, dict):
        if forbidden & set(value):
            raise ValueError("public Answer report contains a private field")
        for item in value.values():
            _reject_private_report_keys(item)
    elif isinstance(value, list):
        for item in value:
            _reject_private_report_keys(item)
