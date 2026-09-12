"""Real public-Gateway wiring evaluation with deterministic routing and Answer."""

from __future__ import annotations

import asyncio
import hashlib
import json
import unicodedata
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from time import perf_counter
from typing import Any, Literal, cast
from uuid import UUID, uuid4

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.agents.gateway import AgentGateway, AgentGatewayLimits
from app.api.dependencies import get_agent_gateway
from app.core import errors as core_errors
from app.core.config import Settings
from app.core.rag_trace import RagReviewTrace, rag_review_trace
from app.db.session import DatabaseRuntime
from app.evals.answer_citation_metrics import (
    aggregate_answer_citation_results,
    evaluate_answer_citation_case,
    freeze_answer_citation_cohort,
)
from app.evals.answer_citation_report import (
    AnswerCitationCaseRunResult,
    AnswerCitationFormalCaseEvaluation,
    AnswerCitationFormalEvaluationReport,
    AnswerCitationGatewayCaseAudit,
    AnswerCitationGatewayEvaluationReport,
    AnswerCitationGatewayLifecycle,
    AnswerCitationGatewayRuntimeIdentity,
    AnswerCitationPublicTrace,
    AnswerReviewWriter,
    FormalAnswerProviderIdentity,
    FormalModelUsage,
    GatewayFakeAnswerProviderIdentity,
    build_answer_trace_set_sha256,
    build_formal_metric_aggregates,
    formal_quality_gate,
    public_answer_trace_sha256,
    ragas_quality_gate,
)
from app.evals.rag_runner import (
    DEFAULT_DATASET_PATH,
    PROJECT_ROOT,
    _load_cases,
    _login_evaluation_owner,
)
from app.evals.ragas_generation import (
    RAGAS_GENERATION_METRICS,
    JudgeMetricDiagnostic,
    JudgeRequestDiagnostic,
    RagasGenerationAdapter,
    RagasGenerationInput,
    _active_judge_metric,
    _active_judge_request,
)
from app.evals.reranker_context_corpus import (
    FrozenRagCorpusSnapshot,
    load_existing_m2_reranker_context_corpus,
)
from app.evals.reranker_context_report import FrozenRagCorpusPublicIdentity
from app.evals.retrieval_runner import (
    _case_database_state,
    _evaluation_users,
    case_reporting_cohort,
)
from app.llm.agent_deepseek import DeepSeekAgentProvider, DeepSeekUsage
from app.llm.agent_evidence import build_answer_evidence_set
from app.llm.agent_schemas import (
    AgentAnswer,
    AnswerRequest,
    DecisionRequest,
    HandoffDraft,
    HandoffRequest,
    PlannerRequest,
)
from app.llm.agent_structured import current_answer_output_schema_sha256
from app.main import create_app
from app.models.runtime import (
    AgentAnswerEvidence,
    AgentCheckpoint,
    AgentRun,
    ContextArtifact,
    Evidence,
    Thread,
    ToolCall,
    ToolContextLink,
)
from app.repositories.evidence import KnowledgeEvidenceRepository
from app.schemas.agent import (
    AgentDecision,
    AgentTask,
    BoundedJsonObject,
    BusinessOutcome,
    CannotCompleteAction,
    DelegateTaskAction,
    EvidenceRequirement,
    ExecuteCapabilityAction,
    FinishAction,
    TaskAssignment,
    TaskPlan,
)
from app.schemas.auth import CurrentUser
from app.schemas.chat import ChatSuccessResponse
from app.schemas.common import ApiErrorResponse, ErrorCode
from app.schemas.evaluation import (
    AnswerCitationEvaluationPlan,
    AnswerCitationEvidenceBinding,
    AnswerCitationReportingCohort,
    AnswerExecutionRecord,
    AnswerKeyPointRule,
    EvaluationCase,
    RagasMetricResult,
)
from app.services.retrieval import EmbeddingProvider, EmbeddingPurpose, RerankerProvider
from app.services.storage import StorageBackend
from app.tools.registry import create_m2_tool_registry

_SAFE_GATEWAY_FAILURE = "Public Gateway evaluation failed."
_SAFE_CHAIN_FAILURE = "Public Gateway chain audit failed."
_SAFE_SEMANTIC_SKIP = "Semantic generation input was unavailable."


@dataclass(slots=True)
class ExternalUsageRecorder:
    """Count Judge calls and tokens without keeping request or response bodies."""

    max_api_calls: int
    api_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    stopped: bool = False

    def __post_init__(self) -> None:
        if self.max_api_calls < 1:
            raise ValueError("Judge call budget must be positive")

    async def capture_request(self, _request: httpx.Request) -> None:
        if self.stopped or self.api_calls >= self.max_api_calls:
            raise RuntimeError("Judge call budget stopped this request")
        self.api_calls += 1
        metric = _active_judge_metric.get()
        if metric is not None:
            diagnostic = JudgeRequestDiagnostic(request_index=self.api_calls)
            metric.requests.append(diagnostic)
            _active_judge_request.set(diagnostic)

    async def capture_response(self, response: httpx.Response) -> None:
        await response.aread()
        diagnostic = _active_judge_request.get()
        if isinstance(diagnostic, JudgeRequestDiagnostic):
            diagnostic.http_status = (
                response.status_code if 100 <= response.status_code <= 599 else None
            )
            diagnostic.response_state = "received"
        if response.status_code >= 400:
            self.stopped = True
            return
        try:
            payload = response.json()
        except ValueError:
            if isinstance(diagnostic, JudgeRequestDiagnostic):
                diagnostic.response_state = "invalid_json"
            return
        if isinstance(diagnostic, JudgeRequestDiagnostic):
            choices = payload.get("choices") if isinstance(payload, dict) else None
            choice = choices[0] if isinstance(choices, list) and choices else None
            message = choice.get("message") if isinstance(choice, dict) else None
            if not isinstance(choice, dict) or not isinstance(message, dict):
                diagnostic.response_state = "invalid_envelope"
            else:
                reason = choice.get("finish_reason")
                diagnostic.finish_reason = (
                    reason
                    if reason
                    in (
                        "stop",
                        "length",
                        "content_filter",
                        "tool_calls",
                        "function_call",
                    )
                    else "other"
                )
                content = message.get("content")
                if content is None or isinstance(content, str):
                    diagnostic.content_empty = content is None or not content.strip()
                else:
                    diagnostic.response_state = "invalid_envelope"
        usage = payload.get("usage") if isinstance(payload, dict) else None
        if not isinstance(usage, dict):
            return
        input_tokens = _first_usage_value(usage, "input_tokens", "prompt_tokens")
        output_tokens = _first_usage_value(usage, "output_tokens", "completion_tokens")
        if isinstance(diagnostic, JudgeRequestDiagnostic):
            diagnostic.input_tokens = (
                input_tokens if type(input_tokens) is int else None
            )
            diagnostic.output_tokens = (
                output_tokens if type(output_tokens) is int else None
            )
        if input_tokens is None or output_tokens is None:
            return
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.total_tokens += input_tokens + output_tokens

    def stop(self) -> None:
        self.stopped = True

    def snapshot(self) -> FormalModelUsage:
        return FormalModelUsage(
            api_calls=self.api_calls,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            total_tokens=self.total_tokens,
        )


@dataclass(frozen=True, slots=True)
class FormalEvaluationRuntime:
    """The shared Agent Provider and separate Judge boundary for M2-22.8.7."""

    answer_provider: DeepSeekAgentProvider
    semantic_adapter: RagasGenerationAdapter
    judge_usage: ExternalUsageRecorder


def _first_usage_value(usage: Mapping[str, object], *keys: str) -> int | None:
    for key in keys:
        value = usage.get(key)
        if isinstance(value, int) and value >= 0:
            return value
    return None


def _case_outcome_contract_passed(
    *,
    should_answer: bool,
    business_outcome: BusinessOutcome | None,
) -> bool:
    """Safety cases may expose candidates to Answer but must still refuse."""

    return should_answer or business_outcome in {
        "no_evidence",
        "unsupported",
        "denied",
    }


def _paid_case_requires_stop(
    audit: AnswerCitationGatewayCaseAudit,
) -> bool:
    """Keep final citation failures local to a case, not a successful answer."""

    return audit.status == "calculation_failed" and not (
        audit.agent_output_stage == "citation_contract"
        and audit.api_status_code == 422
        and audit.api_error_code == "PROVIDER_ERROR"
        and audit.search_knowledge_tool_status == "success"
        and audit.allowed_successful_tool_call_count == 1
        and audit.search_knowledge_error_code is None
    )


def evaluation_gateway_limits() -> AgentGatewayLimits:
    """Give the Knowledge-only evaluation all 12 root Evidence slots."""

    production = AgentGatewayLimits()
    return AgentGatewayLimits(
        root=production.root,
        business_child=replace(production.business_child, max_evidence=0),
        knowledge_child=replace(production.knowledge_child, max_evidence=12),
    )


def _gateway_runtime_identity(
    embedding_provider: EmbeddingProvider,
    reranker_provider: RerankerProvider,
    limits: AgentGatewayLimits,
) -> AnswerCitationGatewayRuntimeIdentity:
    return AnswerCitationGatewayRuntimeIdentity.model_validate(
        {
            "embedding_device": cast(Any, embedding_provider).actual_device,
            "embedding_precision": embedding_provider.identity.precision,
            "reranker_device": cast(Any, reranker_provider).actual_device,
            "reranker_precision": reranker_provider.identity.precision,
            "root_max_evidence": limits.root.max_evidence,
            "business_max_evidence": limits.business_child.max_evidence,
            "knowledge_max_evidence": limits.knowledge_child.max_evidence,
            "search_knowledge_timeout_ms": (
                create_m2_tool_registry().get("search_knowledge").timeout_ms
            ),
        }
    )


class DeterministicKnowledgeGatewayProvider:
    """Freeze routing/search, forward every candidate, then delegate final Answer."""

    identity = GatewayFakeAnswerProviderIdentity()

    def __init__(
        self,
        case: EvaluationCase,
        answer_provider: DeepSeekAgentProvider | None = None,
    ) -> None:
        self._case = case
        self._answer_provider = answer_provider
        self.answer_compose_calls = 0
        self.last_answer_duration_ms: int | None = None
        self.last_answer_usage = FormalModelUsage()
        self.last_answer_request: AnswerRequest | None = None
        self.last_answer: AgentAnswer | None = None

    async def create_plan(self, request: PlannerRequest) -> TaskPlan:
        return TaskPlan(
            plan_id=uuid4(),
            goal=request.goal,
            tasks=[
                AgentTask(
                    task_id="search_frozen_knowledge",
                    goal=request.goal,
                    required_capabilities=["search_knowledge"],
                    assignment=TaskAssignment(
                        status="assigned",
                        worker_id="knowledge",
                    ),
                    completion_criteria=["返回当前获权Context或明确无证据"],
                    evidence_requirement=EvidenceRequirement(
                        required=False,
                        minimum_count=0,
                        source_types=["document"],
                    ),
                    failure_impact="blocks_dependents",
                )
            ],
        )

    async def choose_action(self, request: DecisionRequest) -> AgentDecision:
        if request.available_capabilities.requesting_agent_id is None:
            return AgentDecision(
                action=DelegateTaskAction(
                    task_id=request.active_task_id,
                    target_worker="knowledge",
                )
            )
        if not request.observations:
            return AgentDecision(
                action=ExecuteCapabilityAction(
                    capability_id="search_knowledge",
                    arguments=BoundedJsonObject({"query": self._case.question}),
                )
            )
        if any(item.status != "success" for item in request.observations):
            return AgentDecision(
                action=CannotCompleteAction(
                    public_summary="Knowledge检索未能安全完成。",
                    business_outcome="system_error",
                )
            )
        evidence_ids = list(
            dict.fromkeys(
                evidence_id
                for observation in request.observations
                for evidence_id in observation.evidence_ids
            )
        )
        if not evidence_ids:
            return AgentDecision(
                action=FinishAction(
                    public_summary="Knowledge Worker未检索到获权候选。",
                    business_outcome="no_evidence",
                )
            )
        return AgentDecision(
            action=FinishAction(
                public_summary="Knowledge Worker已完成获权检索。",
                business_outcome="answered",
                evidence_ids=evidence_ids,
            )
        )

    async def prepare_handoff(self, request: HandoffRequest) -> HandoffDraft:
        task = request.delegated_task
        return HandoffDraft(
            task_id=task.task_id,
            goal=task.goal,
            target_worker="knowledge",
            public_context=BoundedJsonObject({"knowledge_query": self._case.question}),
            constraints=("只读且必须经过Harness",),
            expected_output="返回当前获权Context或明确无证据",
            completion_criteria=tuple(task.completion_criteria),
        )

    async def compose_answer(self, request: AnswerRequest) -> AgentAnswer:
        self.answer_compose_calls += 1
        self.last_answer_request = request.model_copy(deep=True)
        started_at = perf_counter()
        if self._answer_provider is not None:
            usage_before = _formal_usage(self._answer_provider.total_usage)
            try:
                answer = await self._answer_provider.compose_answer(request)
            finally:
                self.last_answer_duration_ms = round(
                    (perf_counter() - started_at) * 1000
                )
                self.last_answer_usage = _usage_delta(
                    _formal_usage(self._answer_provider.total_usage),
                    usage_before,
                )
        elif not self._case.should_answer:
            answer = AgentAnswer(
                action=CannotCompleteAction(
                    public_summary="现有获权证据不足，无法安全回答该问题。",
                    business_outcome="no_evidence",
                )
            )
        else:
            evidence = build_answer_evidence_set(request)
            golden_texts = tuple(
                _normalize(span.exact_text)
                for span in self._case.expected_evidence_spans
            )
            cited_items = tuple(
                item
                for item in evidence.items
                if any(
                    golden_text
                    in _normalize(str(item.supporting_data.root.get("text", "")))
                    for golden_text in golden_texts
                )
            )
            if not cited_items:
                answer = AgentAnswer(
                    action=FinishAction(
                        public_summary="现有获权证据不足，无法安全回答该问题。",
                        business_outcome="no_evidence",
                    )
                )
            else:
                labels = [item.citation_label for item in cited_items]
                summary = "；".join(self._case.answer_key_points)
                summary = f"{summary} {' '.join(labels)}"
                answer = AgentAnswer(
                    action=FinishAction(
                        public_summary=summary,
                        business_outcome="answered",
                        evidence_ids=[item.evidence_id for item in cited_items],
                    )
                )
        if self.last_answer_duration_ms is None:
            self.last_answer_duration_ms = round((perf_counter() - started_at) * 1000)
        self.last_answer = answer.model_copy(deep=True)
        return answer


@dataclass(frozen=True, slots=True)
class _CaseArtifacts:
    audit: AnswerCitationGatewayCaseAudit
    context_sha256: str
    authorized_evidence: tuple[AnswerCitationEvidenceBinding, ...]
    execution: AnswerExecutionRecord
    provider_request_sha256: str
    semantic_input: RagasGenerationInput | None = None


@dataclass(frozen=True, slots=True)
class _RuntimeRows:
    root_ids: frozenset[UUID]
    worker_ids: frozenset[UUID]
    tool_call_ids: frozenset[UUID]
    context_ids: frozenset[UUID]
    evidence_ids: frozenset[UUID]
    answer_evidence_ids: frozenset[UUID]


def run_m2_answer_citation_gateway_evaluation(
    *,
    settings: Settings,
    runtime: DatabaseRuntime,
    storage: StorageBackend,
    snapshot: FrozenRagCorpusSnapshot,
    embedding_provider: EmbeddingProvider,
    reranker_provider: RerankerProvider,
    evidence_ids_by_chunk: Mapping[UUID, frozenset[str]],
    project_root: Path = PROJECT_ROOT,
    formal_runtime: FormalEvaluationRuntime | None = None,
    selected_case_ids: frozenset[str] | None = None,
) -> AnswerCitationGatewayEvaluationReport | AnswerCitationFormalEvaluationReport:
    """Run the fixed 34+6 set through the public API and clean only new runtime rows."""

    plan = AnswerCitationEvaluationPlan()
    _validate_runtime_configuration(settings, snapshot, plan)
    dataset_path = project_root / DEFAULT_DATASET_PATH.relative_to(PROJECT_ROOT)
    dataset_content = dataset_path.read_bytes()
    cases = _load_cases(dataset_path)
    known_case_ids = frozenset(case.case_id for case in cases)
    if selected_case_ids is not None and (
        not selected_case_ids or not selected_case_ids <= known_case_ids
    ):
        raise ValueError("selected formal cases must be a non-empty frozen subset")
    if formal_runtime is None and selected_case_ids is not None:
        raise ValueError("case selection is only allowed for formal preflight")
    cohort = freeze_answer_citation_cohort(cases)
    dataset_sha256 = hashlib.sha256(dataset_content).hexdigest()
    corpus_before = _public_corpus(snapshot)
    gateway_limits = evaluation_gateway_limits()
    runtime_identity = _gateway_runtime_identity(
        embedding_provider,
        reranker_provider,
        gateway_limits,
    )
    provider_identity = (
        _formal_answer_provider_identity(formal_runtime.answer_provider)
        if formal_runtime is not None
        else DeterministicKnowledgeGatewayProvider.identity
    )
    input_sha256 = _sha256_value(
        {
            "plan": plan.model_dump(mode="json"),
            **(
                {"evaluation_policy": "business-with-auxiliary-ragas-v1"}
                if formal_runtime is not None
                else {}
            ),
            "cohort": cohort.model_dump(mode="json"),
            "dataset_sha256": dataset_sha256,
            "corpus": corpus_before.model_dump(mode="json"),
            "provider": provider_identity.model_dump(mode="json"),
            "semantic_evaluator": (
                formal_runtime.semantic_adapter.evaluator_identity.model_dump(
                    mode="json"
                )
                if formal_runtime is not None
                and formal_runtime.semantic_adapter is not None
                else None
            ),
            "selected_case_ids": (
                sorted(selected_case_ids) if selected_case_ids is not None else None
            ),
            "golden_map_sha256": _golden_map_sha256(evidence_ids_by_chunk),
            "runtime_identity": runtime_identity.model_dump(mode="json"),
        }
    )
    review_writer = (
        AnswerReviewWriter(
            project_root,
            {
                "input_sha256": input_sha256,
                "dataset_sha256": dataset_sha256,
                "dataset_version": cohort.dataset_version,
                "implementation_sha256": _evaluation_implementation_sha256(),
                "document_aliases": {
                    str(key): value
                    for key, value in snapshot.logical_document_ids.items()
                },
                "golden_evidence_map": {
                    str(key): sorted(value)
                    for key, value in evidence_ids_by_chunk.items()
                },
                "plan": plan.model_dump(mode="json"),
                "corpus": corpus_before.model_dump(mode="json"),
                "provider": provider_identity.model_dump(mode="json"),
                "runtime_identity": runtime_identity.model_dump(mode="json"),
                "semantic_evaluator": formal_runtime.semantic_adapter.evaluator_identity.model_dump(
                    mode="json"
                ),
                "selected_case_ids": sorted(selected_case_ids)
                if selected_case_ids
                else None,
                "cost_amount": None,
                "cost_note": "Token usage is recorded; billed currency amount is unavailable.",
                "privacy_note": "Private untrusted business text; do not publish. Missing stages are null, not empty retrieval.",
            },
        )
        if formal_runtime is not None
        else None
    )
    _warm_gateway_retrieval_models(embedding_provider, reranker_provider)
    users = _evaluation_users(
        runtime,
        tenant_id=snapshot.tenant_id,
        run_id=f"m2-2273-{snapshot.corpus_sha256[:16]}",
    )
    document_ids = {
        logical_id: document_id
        for document_id, logical_id in snapshot.logical_document_ids.items()
    }
    before_context_ids = _tenant_context_ids(runtime, snapshot.tenant_id)
    thread_ids: list[UUID] = []
    case_results: list[AnswerCitationCaseRunResult] = []
    audits: list[AnswerCitationGatewayCaseAudit] = []
    formal_evaluations: list[AnswerCitationFormalCaseEvaluation] = []
    answer_compose_calls = 0
    active_provider: DeterministicKnowledgeGatewayProvider | None = None
    paid_execution_stopped = False
    semantic_loop = asyncio.new_event_loop() if formal_runtime is not None else None

    def provider_factory() -> DeterministicKnowledgeGatewayProvider:
        if active_provider is None:
            raise RuntimeError("evaluation Provider was not bound to a case")
        return active_provider

    application = create_app(
        settings,
        runtime,
        storage,
        engineered_agent_provider_factory=provider_factory,
    )
    application.state.embedding_provider = embedding_provider
    application.state.reranker_provider = reranker_provider

    def evaluation_gateway() -> AgentGateway:
        return AgentGateway(
            provider=provider_factory(),
            session_factory=runtime.session_factory,
            settings=settings,
            storage=storage,
            embedding_provider=embedding_provider,
            reranker_provider=reranker_provider,
            limits=gateway_limits,
        )

    application.dependency_overrides[get_agent_gateway] = evaluation_gateway
    try:
        with TestClient(application) as client:
            tokens: dict[str, str] = {}
            for case_index, case in enumerate(cases, start=1):
                review_trace = RagReviewTrace()
                case_started = perf_counter()
                judge_before = (
                    formal_runtime.judge_usage.snapshot()
                    if formal_runtime is not None
                    else FormalModelUsage()
                )
                active_provider = DeterministicKnowledgeGatewayProvider(
                    case,
                    formal_runtime.answer_provider
                    if formal_runtime is not None
                    else None,
                )
                response = None
                thread_id = None
                if paid_execution_stopped or (
                    selected_case_ids is not None
                    and case.case_id not in selected_case_ids
                ):
                    artifacts = _not_run_case_artifacts(
                        case,
                        stopped=paid_execution_stopped,
                    )
                else:
                    user = users[case.trusted_user_fixture_id]
                    try:
                        token = tokens.get(case.trusted_user_fixture_id)
                        if token is None:
                            token, authenticated = _login_evaluation_owner(
                                client, user.email
                            )
                            if authenticated.user_id != user.user_id:
                                raise RuntimeError("evaluation API identity drifted")
                            tokens[case.trusted_user_fixture_id] = token
                        headers = {"Authorization": f"Bearer {token}"}
                        thread_response = client.post(
                            "/api/v1/threads",
                            headers=headers,
                            json={"title": f"M2-22.8.7 {case.case_id}"},
                        )
                        if thread_response.status_code != 201:
                            raise RuntimeError("evaluation Thread creation failed")
                        thread_id = UUID(thread_response.json()["thread_id"])
                        thread_ids.append(thread_id)
                        with (
                            _case_database_state(
                                runtime,
                                case=case,
                                document_ids=document_ids,
                            ),
                            rag_review_trace(review_trace),
                        ):
                            response = client.post(
                                f"/api/v1/threads/{thread_id}/messages",
                                headers=headers,
                                json={
                                    "request_id": str(uuid4()),
                                    "message": case.question,
                                },
                            )
                        artifacts = _inspect_case(
                            runtime=runtime,
                            tenant_id=snapshot.tenant_id,
                            current_user=user,
                            thread_id=thread_id,
                            case=case,
                            response=response,
                            provider=active_provider,
                            evidence_ids_by_chunk=evidence_ids_by_chunk,
                        )
                    except Exception:  # noqa: BLE001 - retain a safe failed row
                        artifacts = _failed_case_artifacts(
                            case=case,
                            response=response,
                            runtime=runtime,
                            tenant_id=snapshot.tenant_id,
                            thread_id=thread_id,
                        )
                answer_compose_calls += active_provider.answer_compose_calls
                trace = _case_trace(case, artifacts)
                case_results.append(
                    AnswerCitationCaseRunResult(
                        trace=trace,
                        trace_sha256=public_answer_trace_sha256(trace),
                    )
                )
                audits.append(artifacts.audit)
                if review_writer is not None:
                    # Persist Answer before Judge or cleanup, including failed Answers.
                    # Outside the business catch: a disk error cannot become a fake row.
                    review_writer.write(
                        f"case-{case_index:03d}.json",
                        {
                            "case_id": case.case_id,
                            "question": case.question,
                            "split": case.split,
                            "should_answer": case.should_answer,
                            "reference_key_points": list(case.answer_key_points),
                            "expected_evidence_spans": [
                                item.model_dump(mode="json")
                                for item in case.expected_evidence_spans
                            ],
                            "trace_sha256": case_results[-1].trace_sha256,
                            "answer_text": artifacts.execution.answer_text,
                            "execution_status": artifacts.execution.status,
                            "audit": artifacts.audit.model_dump(mode="json"),
                            "observed": asdict(review_trace),
                            "answer_usage": active_provider.last_answer_usage.model_dump(
                                mode="json"
                            ),
                            "answer_duration_ms": active_provider.last_answer_duration_ms,
                            "business_elapsed_ms": round(
                                (perf_counter() - case_started) * 1000
                            ),
                            "deterministic_result": trace.result.model_dump(
                                mode="json"
                            ),
                        },
                    )
                if formal_runtime is not None:
                    assert semantic_loop is not None
                    formal_evaluation = _evaluate_formal_case(
                        case=case,
                        artifacts=artifacts,
                        provider=active_provider,
                        runtime=formal_runtime,
                        event_loop=semantic_loop,
                        judge_before=judge_before,
                    )
                    formal_evaluations.append(formal_evaluation)
                    assert review_writer is not None
                    review_writer.write(
                        f"score-{case_index:03d}.json",
                        {
                            "case_id": case.case_id,
                            "trace_sha256": case_results[-1].trace_sha256,
                            "semantic_input": artifacts.semantic_input.model_dump(
                                mode="json"
                            )
                            if artifacts.semantic_input
                            else None,
                            "evaluation": formal_evaluation.model_dump(mode="json"),
                        },
                    )
                    if _paid_case_requires_stop(artifacts.audit):
                        paid_execution_stopped = True
                        formal_runtime.judge_usage.stop()
            if formal_runtime is not None:
                if client.portal is None:
                    raise RuntimeError("formal TestClient portal was unavailable")
                client.portal.call(formal_runtime.answer_provider.aclose)
    finally:
        if semantic_loop is not None:
            if formal_runtime is not None:
                semantic_loop.run_until_complete(
                    formal_runtime.semantic_adapter.aclose()
                )
            semantic_loop.close()
        created_rows = _runtime_rows(runtime, snapshot.tenant_id, thread_ids)
        created_context_ids = created_rows.context_ids - before_context_ids
        created_evidence_ids = _context_evidence_ids(runtime, created_context_ids)
        _cleanup_runtime_rows(
            runtime=runtime,
            tenant_id=snapshot.tenant_id,
            thread_ids=frozenset(thread_ids),
            context_ids=created_context_ids,
        )
        remaining = _remaining_runtime_rows(
            runtime=runtime,
            tenant_id=snapshot.tenant_id,
            created=created_rows,
            thread_ids=frozenset(thread_ids),
            context_ids=created_context_ids,
            evidence_ids=created_evidence_ids,
        )

    lifecycle = AnswerCitationGatewayLifecycle.model_validate(
        {
            "created_thread_count": len(thread_ids),
            "created_root_run_count": len(created_rows.root_ids),
            "created_worker_run_count": len(created_rows.worker_ids),
            "created_tool_call_count": len(created_rows.tool_call_ids),
            "created_context_artifact_count": len(created_context_ids),
            "created_evidence_count": len(created_evidence_ids),
            "created_answer_evidence_count": len(created_rows.answer_evidence_ids),
            **remaining,
        }
    )
    if review_writer is not None:
        review_writer.write("cleanup.json", lifecycle.model_dump(mode="json"))
    snapshot_after = load_existing_m2_reranker_context_corpus(
        settings=settings,
        runtime=runtime,
        project_root=project_root,
        embedding_provider=embedding_provider,
    )
    corpus_after = _public_corpus(snapshot_after)
    grouped = aggregate_answer_citation_results(
        [item.trace.result for item in case_results],
        cohort=cohort,
    )
    run_status: Literal["completed", "completed_with_failures"] = (
        "completed"
        if all(item.chain_passed is True for item in audits)
        and lifecycle.baseline_restored
        and corpus_before == corpus_after
        else "completed_with_failures"
    )
    if formal_runtime is None:
        return AnswerCitationGatewayEvaluationReport(
            run_id=f"m2-2283-{input_sha256[:16]}",
            run_status=run_status,
            plan=plan,
            dataset_version=cohort.dataset_version,
            dataset_sha256=dataset_sha256,
            input_sha256=input_sha256,
            provider=DeterministicKnowledgeGatewayProvider.identity,
            runtime_identity=runtime_identity,
            corpus_before=corpus_before,
            corpus_after=corpus_after,
            cohort=cohort,
            case_results=case_results,
            chain_audits=audits,
            grouped_results=grouped,
            answer_compose_calls=answer_compose_calls,
            lifecycle=lifecycle,
            trace_set_sha256=build_answer_trace_set_sha256(
                [item.trace_sha256 for item in case_results]
            ),
        )
    semantic_aggregates = build_formal_metric_aggregates(formal_evaluations)
    answer_usage = _sum_formal_usage([item.answer_usage for item in formal_evaluations])
    judge_usage = _sum_formal_usage([item.judge_usage for item in formal_evaluations])
    quality_gate_passed = formal_quality_gate(
        run_status=run_status,
        grouped_results=grouped,
    )
    assert isinstance(provider_identity, FormalAnswerProviderIdentity)
    report = AnswerCitationFormalEvaluationReport(
        run_id=f"m2-2287-{input_sha256[:16]}",
        run_status=run_status,
        business_quality_gate_passed=quality_gate_passed,
        ragas_quality_gate_passed=ragas_quality_gate(
            semantic_aggregates, expected_case_count=len(cohort.answerable_cases)
        ),
        plan=plan,
        dataset_version=cohort.dataset_version,
        dataset_sha256=dataset_sha256,
        input_sha256=input_sha256,
        provider=provider_identity,
        semantic_evaluator=formal_runtime.semantic_adapter.evaluator_identity,
        runtime_identity=runtime_identity,
        corpus_before=corpus_before,
        corpus_after=corpus_after,
        cohort=cohort,
        case_results=case_results,
        chain_audits=audits,
        formal_evaluations=formal_evaluations,
        grouped_results=grouped,
        semantic_aggregates=semantic_aggregates,
        answer_compose_calls=answer_compose_calls,
        answer_usage=answer_usage,
        judge_usage=judge_usage,
        lifecycle=lifecycle,
        trace_set_sha256=build_answer_trace_set_sha256(
            [item.trace_sha256 for item in case_results]
        ),
    )
    assert review_writer is not None
    review_writer.write("report.json", report.model_dump(mode="json"))
    return report


def _formal_answer_provider_identity(
    provider: DeepSeekAgentProvider,
) -> FormalAnswerProviderIdentity:
    return FormalAnswerProviderIdentity(
        model_id=provider.model_name,
        prompt_bundle_sha256=provider.prompt_bundle_sha256,
        answer_schema_sha256=current_answer_output_schema_sha256(),
    )


def _evaluation_implementation_sha256() -> str:
    """Fingerprint the running Python source, including an uncommitted worktree."""
    root = Path(__file__).resolve().parents[2]
    paths = sorted((root / "app").rglob("*.py"))
    paths.append(root / "scripts/run_m2_answer_citation_evaluation.py")
    return _sha256_value(
        {
            path.relative_to(root).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in paths
        }
    )


def _evaluate_formal_case(
    *,
    case: EvaluationCase,
    artifacts: _CaseArtifacts,
    provider: DeterministicKnowledgeGatewayProvider,
    runtime: FormalEvaluationRuntime,
    event_loop: asyncio.AbstractEventLoop,
    judge_before: FormalModelUsage,
) -> AnswerCitationFormalCaseEvaluation:
    judge_started_at = perf_counter()
    diagnostics: list[JudgeMetricDiagnostic] = []
    judge_unavailable = (
        runtime.judge_usage.stopped
        or runtime.judge_usage.api_calls >= runtime.judge_usage.max_api_calls
    )
    if artifacts.semantic_input is None or judge_unavailable:
        metrics = [
            RagasMetricResult(
                metric_name=metric_name,
                status="skipped",
                value=None,
                direction="higher_is_better",
                failure_category="dependency_unavailable",
                failure_summary=(
                    "Auxiliary scoring was not run: Judge budget or service unavailable."
                    if judge_unavailable and artifacts.semantic_input is not None
                    else _SAFE_SEMANTIC_SKIP
                ),
            )
            for metric_name in RAGAS_GENERATION_METRICS
        ]
        judge_duration_ms = 0
    else:
        try:
            evaluation = event_loop.run_until_complete(
                runtime.semantic_adapter.evaluate(artifacts.semantic_input)
            )
            metrics = evaluation.metrics
            diagnostics = evaluation.judge_diagnostics
        except Exception:  # noqa: BLE001 - retain a safe non-numeric row
            metrics = [
                RagasMetricResult(
                    metric_name=metric_name,
                    status="framework_failed",
                    value=None,
                    direction="higher_is_better",
                    failure_category="framework_error",
                    failure_summary="Ragas generation evaluation failed safely",
                )
                for metric_name in RAGAS_GENERATION_METRICS
            ]
        judge_duration_ms = round((perf_counter() - judge_started_at) * 1000)
        if any(
            metric.failure_category
            in {"judge_timeout", "network_error", "rate_limited"}
            for metric in metrics
        ):
            runtime.judge_usage.stop()
    judge_after = runtime.judge_usage.snapshot()
    judge_usage = _usage_delta(judge_after, judge_before)
    metric_statuses = {item.status for item in metrics}
    status: Literal["completed", "calculation_failed", "skipped"] = (
        "completed"
        if metric_statuses == {"completed"}
        else "skipped"
        if metric_statuses == {"skipped"}
        else "calculation_failed"
    )
    return AnswerCitationFormalCaseEvaluation(
        case_id=case.case_id,
        status=status,
        answer_duration_ms=provider.last_answer_duration_ms,
        answer_usage=provider.last_answer_usage,
        judge_duration_ms=judge_duration_ms,
        judge_usage=judge_usage,
        semantic_metrics=metrics,
        judge_diagnostics=diagnostics,
    )


def _formal_usage(usage: DeepSeekUsage) -> FormalModelUsage:
    return FormalModelUsage(
        api_calls=usage.api_calls,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
    )


def _usage_delta(
    after: FormalModelUsage,
    before: FormalModelUsage,
) -> FormalModelUsage:
    return FormalModelUsage(
        api_calls=after.api_calls - before.api_calls,
        input_tokens=after.input_tokens - before.input_tokens,
        output_tokens=after.output_tokens - before.output_tokens,
        total_tokens=after.total_tokens - before.total_tokens,
    )


def _sum_formal_usage(items: list[FormalModelUsage]) -> FormalModelUsage:
    return FormalModelUsage(
        api_calls=sum(item.api_calls for item in items),
        input_tokens=sum(item.input_tokens for item in items),
        output_tokens=sum(item.output_tokens for item in items),
        total_tokens=sum(item.total_tokens for item in items),
    )


def _warm_gateway_retrieval_models(
    embedding_provider: EmbeddingProvider,
    reranker_provider: RerankerProvider,
) -> None:
    """Pay one-time local model startup cost before the public Gateway timer starts."""

    warmup_text = "cross-border knowledge retrieval warmup"
    embedding_provider.embed([warmup_text], purpose=EmbeddingPurpose.QUERY)
    reranker_provider.score(warmup_text, [warmup_text])


def _inspect_case(
    *,
    runtime: DatabaseRuntime,
    tenant_id: UUID,
    current_user: CurrentUser,
    thread_id: UUID,
    case: EvaluationCase,
    response: object,
    provider: DeterministicKnowledgeGatewayProvider,
    evidence_ids_by_chunk: Mapping[UUID, frozenset[str]],
) -> _CaseArtifacts:
    from httpx import Response

    if not isinstance(response, Response) or response.status_code != 200:
        return _failed_case_artifacts(
            case=case,
            response=response,
            runtime=runtime,
            tenant_id=tenant_id,
            thread_id=thread_id,
        )
    payload = ChatSuccessResponse.model_validate(response.json())
    request = provider.last_answer_request
    answer = provider.last_answer
    answer_skipped = (
        request is None
        and answer is None
        and payload.execution.business_outcome
        in {"no_evidence", "unsupported", "denied"}
    )
    if (request is None) != (answer is None) or (
        request is None and not answer_skipped
    ):
        return _failed_case_artifacts(
            case=case,
            response=response,
            runtime=runtime,
            tenant_id=tenant_id,
            thread_id=thread_id,
        )

    with runtime.session_factory() as session:
        roots = list(
            session.scalars(
                select(AgentRun).where(
                    AgentRun.tenant_id == tenant_id,
                    AgentRun.thread_id == thread_id,
                    AgentRun.run_kind == "supervisor",
                )
            )
        )
        root_ids = [item.id for item in roots]
        workers = list(
            session.scalars(
                select(AgentRun).where(
                    AgentRun.tenant_id == tenant_id,
                    AgentRun.thread_id == thread_id,
                    AgentRun.run_kind == "worker",
                )
            )
        )
        tool_calls = list(
            session.scalars(
                select(ToolCall)
                .join(AgentRun, AgentRun.id == ToolCall.agent_run_id)
                .where(
                    ToolCall.tenant_id == tenant_id,
                    AgentRun.thread_id == thread_id,
                )
            )
        )
        tool_ids = [item.id for item in tool_calls]
        links = (
            list(
                session.scalars(
                    select(ToolContextLink).where(
                        ToolContextLink.tenant_id == tenant_id,
                        ToolContextLink.tool_call_id.in_(tool_ids),
                    )
                )
            )
            if tool_ids
            else []
        )
        context_ids = list(dict.fromkeys(item.context_artifact_id for item in links))
        contexts = (
            list(
                session.scalars(
                    select(ContextArtifact).where(
                        ContextArtifact.tenant_id == tenant_id,
                        ContextArtifact.id.in_(context_ids),
                    )
                )
            )
            if context_ids
            else []
        )
        evidence_rows = (
            list(
                session.scalars(
                    select(Evidence)
                    .where(
                        Evidence.tenant_id == tenant_id,
                        Evidence.context_artifact_id.in_(context_ids),
                    )
                    .order_by(Evidence.citation_ordinal)
                )
            )
            if context_ids
            else []
        )
        answer_rows = (
            list(
                session.scalars(
                    select(AgentAnswerEvidence)
                    .where(
                        AgentAnswerEvidence.tenant_id == tenant_id,
                        AgentAnswerEvidence.root_run_id.in_(root_ids),
                    )
                    .order_by(AgentAnswerEvidence.citation_ordinal)
                )
            )
            if root_ids
            else []
        )
        authorization = False
        if len(contexts) == 1:
            authorized = KnowledgeEvidenceRepository(
                session
            ).load_authorized_citation_context(
                current_user,
                contexts[0].id,
            )
            authorization = authorized is not None and authorized.evidence_ids == tuple(
                item.id for item in evidence_rows
            )

    evidence_set = build_answer_evidence_set(request) if request is not None else None
    row_by_id = {item.id: item for item in evidence_rows}
    expected_golden_ids = _expected_golden_ids(case)
    bindings = tuple(
        AnswerCitationEvidenceBinding(
            citation_label=item.citation_label,
            evidence_id=item.evidence_id,
            golden_evidence_ids=sorted(
                evidence_ids_by_chunk.get(
                    cast(UUID, row_by_id[item.evidence_id].document_chunk_id),
                    frozenset(),
                )
                & expected_golden_ids
            ),
        )
        for item in (evidence_set.items if evidence_set is not None else ())
        if item.evidence_id in row_by_id
    )
    provider_ids = (
        [item.evidence_id for item in evidence_set.items]
        if evidence_set is not None
        else []
    )
    answer_ids = [item.evidence_id for item in answer_rows]
    public_ids = [item.id for item in payload.evidence]
    action_ids = (
        list(answer.action.evidence_ids)
        if answer is not None and isinstance(answer.action, FinishAction)
        else []
    )
    protected_ids = (
        _expected_golden_ids(case)
        if case.expected_non_answer_reason in {"acl_denied", "version_unavailable"}
        else frozenset()
    )
    observed_golden = {
        golden_id for binding in bindings for golden_id in binding.golden_evidence_ids
    }
    protected_leaks = len(protected_ids & observed_golden)
    actual_business_outcome = payload.execution.business_outcome
    outcome_matches_evidence = (
        actual_business_outcome in {"answered", "partial"}
        if action_ids
        else actual_business_outcome in {"no_evidence", "unsupported", "denied"}
    )
    mapping_passed = answer_ids == public_ids == action_ids
    context_segment_count = sum(item.segment_count for item in contexts)
    chain_passed = all(
        (
            payload.status == "completed",
            payload.execution.route == "agent_gateway",
            payload.execution.tool_names == ["search_knowledge"],
            outcome_matches_evidence,
            len(roots) == 1,
            len(workers) == 1,
            len(tool_calls) == 1,
            sum(
                item.tool_name == "search_knowledge"
                and item.permission_result == "allowed"
                and item.status == "success"
                for item in tool_calls
            )
            == 1,
            len(contexts) == 1,
            context_segment_count == len(evidence_rows),
            set(provider_ids) <= set(row_by_id),
            len(bindings) == len(provider_ids),
            authorization,
            mapping_passed,
            protected_leaks == 0,
            _case_outcome_contract_passed(
                should_answer=case.should_answer,
                business_outcome=actual_business_outcome,
            ),
        )
    )
    audit = AnswerCitationGatewayCaseAudit(
        case_id=case.case_id,
        should_answer=case.should_answer,
        status="completed" if chain_passed else "calculation_failed",
        api_status_code=response.status_code,
        gateway_status=cast(Literal["completed"], payload.status),
        gateway_business_outcome=cast(
            BusinessOutcome,
            payload.execution.business_outcome,
        ),
        tool_names=cast(
            list[Literal["search_knowledge"]], payload.execution.tool_names
        ),
        root_run_count=len(roots),
        worker_run_count=len(workers),
        search_knowledge_tool_call_count=sum(
            item.tool_name == "search_knowledge" for item in tool_calls
        ),
        allowed_successful_tool_call_count=sum(
            item.tool_name == "search_knowledge"
            and item.permission_result == "allowed"
            and item.status == "success"
            for item in tool_calls
        ),
        search_knowledge_tool_status=(
            cast(
                Literal["running", "success", "error", "denied", "timeout"],
                tool_calls[0].status,
            )
            if len(tool_calls) == 1
            else None
        ),
        search_knowledge_duration_ms=(
            tool_calls[0].duration_ms if len(tool_calls) == 1 else None
        ),
        search_knowledge_error_code=(
            cast(ErrorCode, tool_calls[0].error_code)
            if len(tool_calls) == 1 and tool_calls[0].error_code is not None
            else None
        ),
        context_artifact_count=len(contexts),
        context_segment_count=context_segment_count,
        context_evidence_count=len(evidence_rows),
        provider_evidence_count=len(provider_ids),
        answer_evidence_count=len(answer_ids),
        public_evidence_count=len(public_ids),
        context_authorization_passed=authorization,
        answer_citation_validator_passed=True,
        answer_mapping_passed=mapping_passed,
        protected_evidence_leak_count=protected_leaks,
        chain_passed=chain_passed,
        failure_summary=None if chain_passed else _SAFE_CHAIN_FAILURE,
    )
    response_kind: Literal["answer", "refusal"] = (
        "answer"
        if payload.execution.business_outcome in {"answered", "partial"}
        else "refusal"
    )
    retrieved_contexts = tuple(
        text
        for item in (evidence_set.items if evidence_set is not None else ())
        if (text := str(item.supporting_data.root.get("text", "")).strip())
    )
    semantic_input = (
        RagasGenerationInput(
            user_input=case.question,
            retrieved_contexts=retrieved_contexts,
            reference="；".join(case.answer_key_points),
            response=payload.answer,
        )
        if case.should_answer
        and response_kind == "answer"
        and retrieved_contexts
        and case.answer_key_points
        else None
    )
    return _CaseArtifacts(
        audit=audit,
        context_sha256=(
            contexts[0].context_sha256 if len(contexts) == 1 else _sha256_value([])
        ),
        authorized_evidence=bindings,
        execution=AnswerExecutionRecord(
            status="completed",
            response_kind=response_kind,
            answer_text=payload.answer,
        ),
        provider_request_sha256=(
            _provider_request_sha256(request)
            if request is not None
            else _sha256_value(
                {"case_id": case.case_id, "provider_request": "program_refusal"}
            )
        ),
        semantic_input=semantic_input,
    )


def _case_trace(
    case: EvaluationCase,
    artifacts: _CaseArtifacts,
) -> AnswerCitationPublicTrace:
    expected_golden = _expected_golden_ids(case) if case.should_answer else frozenset()
    rules = _key_point_rules(case) if case.should_answer else ()
    result = evaluate_answer_citation_case(
        case_id=case.case_id,
        source_group=case.source_group,
        reporting_cohort=_answer_reporting_cohort(case),
        should_answer=case.should_answer,
        expected_non_answer_reason=case.expected_non_answer_reason,
        context_status=(
            "completed"
            if artifacts.audit.context_artifact_count == 1
            and artifacts.audit.context_authorization_passed is True
            else "calculation_failed"
        ),
        expected_golden_evidence_ids=expected_golden,
        authorized_evidence=artifacts.authorized_evidence,
        key_point_rules=rules,
        forbidden_assertions=tuple(case.forbidden_claims) if case.should_answer else (),
        sensitive_phrases=tuple(case.forbidden_claims)
        if not case.should_answer
        else (),
        execution=artifacts.execution,
    )
    trace = AnswerCitationPublicTrace(
        case_id=case.case_id,
        source_group=case.source_group,
        reporting_cohort=_answer_reporting_cohort(case),
        should_answer=case.should_answer,
        question_sha256=_sha256_text(case.question),
        context_sha256=artifacts.context_sha256,
        answer_rules_sha256=_answer_rules_sha256(case),
        provider_request_sha256=artifacts.provider_request_sha256,
        answer_output_sha256=(
            _sha256_text(cast(str, artifacts.execution.answer_text))
            if artifacts.execution.status == "completed"
            else None
        ),
        result=result,
    )
    return trace


def _answer_reporting_cohort(case: EvaluationCase) -> AnswerCitationReportingCohort:
    if not case.should_answer:
        return "safety_acl_version"
    return case_reporting_cohort(case)


def _failed_case_artifacts(
    *,
    case: EvaluationCase,
    response: object = None,
    runtime: DatabaseRuntime | None = None,
    tenant_id: UUID | None = None,
    thread_id: UUID | None = None,
) -> _CaseArtifacts:
    from httpx import Response

    roots: list[AgentRun] = []
    workers: list[AgentRun] = []
    tool_calls: list[ToolCall] = []
    agent_output_stage = None
    if runtime is not None and tenant_id is not None and thread_id is not None:
        with runtime.session_factory() as session:
            runs = list(
                session.scalars(
                    select(AgentRun).where(
                        AgentRun.tenant_id == tenant_id,
                        AgentRun.thread_id == thread_id,
                    )
                )
            )
            roots = [item for item in runs if item.run_kind == "supervisor"]
            workers = [item for item in runs if item.run_kind == "worker"]
            run_ids = [item.id for item in runs]
            if run_ids:
                tool_calls = list(
                    session.scalars(
                        select(ToolCall).where(
                            ToolCall.tenant_id == tenant_id,
                            ToolCall.agent_run_id.in_(run_ids),
                        )
                    )
                )
            checkpoint = session.scalar(
                select(AgentCheckpoint)
                .where(
                    AgentCheckpoint.tenant_id == tenant_id,
                    AgentCheckpoint.thread_id == thread_id,
                )
                .order_by(AgentCheckpoint.checkpoint_version.desc())
                .limit(1)
            )
            if checkpoint is not None:
                agent_output_stage = (
                    core_errors.agent_provider_output_stage_from_stop_reason(
                        checkpoint.state_json.get("stop_reason")
                    )
                )
    tool_call = tool_calls[0] if len(tool_calls) == 1 else None
    api_error_code: ErrorCode | None = None
    response_status = response.status_code if isinstance(response, Response) else None
    if isinstance(response, Response) and response.status_code != 200:
        try:
            api_error_code = ApiErrorResponse.model_validate(response.json()).error.code
        except (TypeError, ValueError):
            api_error_code = None
    return _CaseArtifacts(
        audit=AnswerCitationGatewayCaseAudit(
            case_id=case.case_id,
            should_answer=case.should_answer,
            status="calculation_failed",
            api_status_code=response_status,
            api_error_code=api_error_code,
            agent_output_stage=agent_output_stage,
            root_run_count=len(roots),
            worker_run_count=len(workers),
            search_knowledge_tool_call_count=len(tool_calls),
            allowed_successful_tool_call_count=sum(
                item.permission_result == "allowed" and item.status == "success"
                for item in tool_calls
            ),
            search_knowledge_tool_status=(
                cast(
                    Literal["running", "success", "error", "denied", "timeout"],
                    tool_call.status,
                )
                if tool_call is not None
                else None
            ),
            search_knowledge_duration_ms=(
                tool_call.duration_ms if tool_call is not None else None
            ),
            search_knowledge_error_code=(
                cast(ErrorCode, tool_call.error_code)
                if tool_call is not None and tool_call.error_code is not None
                else None
            ),
            context_artifact_count=0,
            context_segment_count=0,
            context_evidence_count=0,
            provider_evidence_count=0,
            answer_evidence_count=0,
            public_evidence_count=0,
            chain_passed=False,
            failure_summary=_SAFE_GATEWAY_FAILURE,
        ),
        context_sha256=_sha256_value([]),
        authorized_evidence=(),
        execution=AnswerExecutionRecord(
            status="provider_failed",
            failure_category="provider_error",
            failure_summary=_SAFE_GATEWAY_FAILURE,
        ),
        provider_request_sha256=_sha256_value(
            {"case_id": case.case_id, "provider_request": "unavailable"}
        ),
    )


def _not_run_case_artifacts(
    case: EvaluationCase,
    *,
    stopped: bool = False,
) -> _CaseArtifacts:
    """Retain an explicit non-numeric row without making another paid call."""

    summary = (
        "Case was not run after a paid evaluation failure."
        if stopped
        else "Case was outside the fixed formal preflight subset."
    )
    return _CaseArtifacts(
        audit=AnswerCitationGatewayCaseAudit(
            case_id=case.case_id,
            should_answer=case.should_answer,
            status="skipped",
            root_run_count=0,
            worker_run_count=0,
            search_knowledge_tool_call_count=0,
            allowed_successful_tool_call_count=0,
            context_artifact_count=0,
            context_segment_count=0,
            context_evidence_count=0,
            provider_evidence_count=0,
            answer_evidence_count=0,
            public_evidence_count=0,
            chain_passed=False,
            failure_summary=summary,
        ),
        context_sha256=_sha256_value([]),
        authorized_evidence=(),
        execution=AnswerExecutionRecord(
            status="skipped",
            failure_category="not_run",
            failure_summary=summary,
        ),
        provider_request_sha256=_sha256_value(
            {"case_id": case.case_id, "provider_request": "not_run"}
        ),
    )


def _key_point_rules(case: EvaluationCase) -> tuple[AnswerKeyPointRule, ...]:
    return tuple(
        AnswerKeyPointRule(
            key_point_id=f"point-{index:02d}",
            canonical_text=point,
            accepted_variants=list(_variants(case, point)),
        )
        for index, point in enumerate(case.answer_key_points, start=1)
    )


def _variants(case: EvaluationCase, canonical: str) -> tuple[str, ...]:
    seen = {_normalize(canonical)}
    values: list[str] = []
    for item in case.acceptable_answer_variants:
        normalized = _normalize(item)
        if normalized not in seen:
            seen.add(normalized)
            values.append(item)
    return tuple(values)


def _expected_golden_ids(case: EvaluationCase) -> frozenset[str]:
    return frozenset(
        f"{case.case_id}-evidence-{index:03d}"
        for index in range(1, len(case.expected_evidence_spans) + 1)
    )


def _answer_rules_sha256(case: EvaluationCase) -> str:
    return _sha256_value(
        {
            "key_point_rules": [
                item.model_dump(mode="json") for item in _key_point_rules(case)
            ],
            "forbidden_assertions": list(case.forbidden_claims),
            "expected_golden_evidence_ids": sorted(
                _expected_golden_ids(case) if case.should_answer else ()
            ),
        }
    )


def _provider_request_sha256(request: AnswerRequest) -> str:
    evidence = build_answer_evidence_set(request)
    return _sha256_value(
        {
            "goal_sha256": _sha256_text(request.goal),
            "worker_results": [
                {
                    "task_id": result.task_id,
                    "worker_id": result.worker_id,
                    "execution_status": result.execution_status,
                    "business_outcome": result.business_outcome,
                    "evidence_ids": [str(item) for item in result.evidence_ids],
                }
                for result in request.worker_results
            ],
            "answer_evidence": [
                {
                    "citation_label": item.citation_label,
                    "evidence_id": str(item.evidence_id),
                    "supporting_data_sha256": _sha256_value(
                        item.supporting_data.model_dump(mode="json")
                    ),
                }
                for item in evidence.items
            ],
        }
    )


def _runtime_rows(
    runtime: DatabaseRuntime,
    tenant_id: UUID,
    thread_ids: list[UUID],
) -> _RuntimeRows:
    if not thread_ids:
        return _RuntimeRows(
            root_ids=frozenset(),
            worker_ids=frozenset(),
            tool_call_ids=frozenset(),
            context_ids=frozenset(),
            evidence_ids=frozenset(),
            answer_evidence_ids=frozenset(),
        )
    with runtime.session_factory() as session:
        runs = list(
            session.scalars(
                select(AgentRun).where(
                    AgentRun.tenant_id == tenant_id,
                    AgentRun.thread_id.in_(thread_ids),
                )
            )
        )
        root_ids = frozenset(item.id for item in runs if item.run_kind == "supervisor")
        worker_ids = frozenset(item.id for item in runs if item.run_kind == "worker")
        run_ids = [item.id for item in runs]
        tool_ids = frozenset(
            session.scalars(
                select(ToolCall.id).where(
                    ToolCall.tenant_id == tenant_id,
                    ToolCall.agent_run_id.in_(run_ids),
                )
            )
        )
        context_ids = frozenset(
            session.scalars(
                select(ToolContextLink.context_artifact_id).where(
                    ToolContextLink.tenant_id == tenant_id,
                    ToolContextLink.tool_call_id.in_(tool_ids),
                )
            )
        )
        evidence_ids = frozenset(
            session.scalars(
                select(Evidence.id).where(
                    Evidence.tenant_id == tenant_id,
                    Evidence.context_artifact_id.in_(context_ids),
                )
            )
        )
        answer_ids = frozenset(
            session.scalars(
                select(AgentAnswerEvidence.id).where(
                    AgentAnswerEvidence.tenant_id == tenant_id,
                    AgentAnswerEvidence.root_run_id.in_(root_ids),
                )
            )
        )
    return _RuntimeRows(
        root_ids=root_ids,
        worker_ids=worker_ids,
        tool_call_ids=tool_ids,
        context_ids=context_ids,
        evidence_ids=evidence_ids,
        answer_evidence_ids=answer_ids,
    )


def _cleanup_runtime_rows(
    *,
    runtime: DatabaseRuntime,
    tenant_id: UUID,
    thread_ids: frozenset[UUID],
    context_ids: frozenset[UUID],
) -> None:
    with runtime.session_factory.begin() as session:
        if thread_ids:
            session.execute(
                delete(Thread).where(
                    Thread.tenant_id == tenant_id,
                    Thread.id.in_(thread_ids),
                )
            )
        if context_ids:
            session.execute(
                delete(Evidence).where(
                    Evidence.tenant_id == tenant_id,
                    Evidence.context_artifact_id.in_(context_ids),
                )
            )
            session.execute(
                delete(ContextArtifact).where(
                    ContextArtifact.tenant_id == tenant_id,
                    ContextArtifact.id.in_(context_ids),
                )
            )


def _remaining_runtime_rows(
    *,
    runtime: DatabaseRuntime,
    tenant_id: UUID,
    created: _RuntimeRows,
    thread_ids: frozenset[UUID],
    context_ids: frozenset[UUID],
    evidence_ids: frozenset[UUID],
) -> dict[str, object]:
    with runtime.session_factory() as session:
        counts: dict[str, object] = {
            "remaining_thread_count": _count_ids(
                session, Thread, tenant_id, thread_ids
            ),
            "remaining_agent_run_count": _count_ids(
                session,
                AgentRun,
                tenant_id,
                created.root_ids | created.worker_ids,
            ),
            "remaining_tool_call_count": _count_ids(
                session,
                ToolCall,
                tenant_id,
                created.tool_call_ids,
            ),
            "remaining_context_artifact_count": _count_ids(
                session,
                ContextArtifact,
                tenant_id,
                context_ids,
            ),
            "remaining_evidence_count": _count_ids(
                session,
                Evidence,
                tenant_id,
                evidence_ids,
            ),
            "remaining_answer_evidence_count": _count_ids(
                session,
                AgentAnswerEvidence,
                tenant_id,
                created.answer_evidence_ids,
            ),
        }
    counts["baseline_restored"] = all(value == 0 for value in counts.values())
    return counts


def _count_ids(
    session: Session,
    model: type[Any],
    tenant_id: UUID,
    ids: frozenset[UUID],
) -> int:
    if not ids:
        return 0
    return int(
        session.scalar(
            select(func.count())
            .select_from(model)
            .where(model.tenant_id == tenant_id, model.id.in_(ids))
        )
        or 0
    )


def _tenant_context_ids(runtime: DatabaseRuntime, tenant_id: UUID) -> frozenset[UUID]:
    with runtime.session_factory() as session:
        return frozenset(
            session.scalars(
                select(ContextArtifact.id).where(ContextArtifact.tenant_id == tenant_id)
            )
        )


def _context_evidence_ids(
    runtime: DatabaseRuntime,
    context_ids: frozenset[UUID],
) -> frozenset[UUID]:
    if not context_ids:
        return frozenset()
    with runtime.session_factory() as session:
        return frozenset(
            session.scalars(
                select(Evidence.id).where(Evidence.context_artifact_id.in_(context_ids))
            )
        )


def _validate_runtime_configuration(
    settings: Settings,
    snapshot: FrozenRagCorpusSnapshot,
    plan: AnswerCitationEvaluationPlan,
) -> None:
    actual = (
        settings.dense_candidate_count,
        settings.lexical_candidate_count,
        settings.hybrid_candidate_count,
        settings.rrf_k,
        settings.reranker_top_k,
        settings.context_neighbor_window,
        settings.context_max_tokens,
    )
    expected = (
        plan.dense_candidate_count,
        plan.lexical_candidate_count,
        plan.hybrid_candidate_limit,
        plan.rrf_k,
        plan.reranker_top_k,
        plan.context_neighbor_window,
        plan.context_max_tokens,
    )
    if actual != expected:
        raise ValueError("Gateway evaluation settings differ from the frozen plan")
    if (
        snapshot.created
        or snapshot.source_count != 18
        or snapshot.document_count != 18
        or snapshot.chunk_set_count != 18
        or snapshot.chunk_count != 779
    ):
        raise ValueError("Gateway evaluation requires the retained 18/18/779 corpus")


def _public_corpus(snapshot: FrozenRagCorpusSnapshot) -> FrozenRagCorpusPublicIdentity:
    return FrozenRagCorpusPublicIdentity(
        corpus_sha256=snapshot.corpus_sha256,
        index_sha256=snapshot.index_sha256,
        snapshot_sha256=snapshot.snapshot_sha256,
        source_count=18,
        document_count=18,
        chunk_set_count=18,
        index_set_count=snapshot.index_set_count,
        chunk_count=779,
    )


def _golden_map_sha256(
    evidence_ids_by_chunk: Mapping[UUID, frozenset[str]],
) -> str:
    return _sha256_value(
        [
            {"chunk_id": str(chunk_id), "golden_evidence_ids": sorted(evidence_ids)}
            for chunk_id, evidence_ids in sorted(
                evidence_ids_by_chunk.items(),
                key=lambda item: str(item[0]),
            )
        ]
    )


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if not character.isspace())


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_value(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
