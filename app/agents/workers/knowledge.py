"""Bounded Action/Observation loop for the read-only Knowledge Worker."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, TypeAlias
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.agents.runtime import WorkerExecutionContext
from app.capabilities.contracts import CapabilitySelection
from app.capabilities.resolver import CapabilityResolver
from app.core.config import Settings
from app.core.errors import (
    AgentProviderOutputError,
    ApplicationError,
    BudgetExceededError,
)
from app.llm.agent_provider import AgentDecisionProvider, validate_decision_response
from app.llm.agent_schemas import DecisionRequest
from app.repositories.evidence import EvidenceRepository
from app.repositories.files import FileRepository
from app.repositories.retrieval import RetrievalRepository
from app.schemas.agent import (
    AgentHandoff,
    AgentTask,
    AskUserAction,
    BoundedJsonObject,
    CannotCompleteAction,
    EvidenceRequirement,
    ExecuteCapabilityAction,
    FinishAction,
    ResourceUsage,
    SafeAgentError,
    TaskAssignment,
    TaskPlan,
    WorkerObservation,
    WorkerResult,
)
from app.schemas.auth import CurrentUser
from app.schemas.common import ErrorDetail, ToolEnvelope
from app.schemas.evidence import (
    GetEvidenceDetailInput,
    GetEvidenceDetailResult,
    ToolDocumentEvidenceDetail,
)
from app.schemas.file_reading import ReadUploadedFileResult
from app.schemas.files import ReadUploadedFileInput
from app.schemas.knowledge import SearchKnowledgeInput, SearchKnowledgeResult
from app.services.evidence import EvidenceQueryService, EvidenceService
from app.services.file_reading import FileReadingService
from app.services.knowledge import KnowledgeSearchService
from app.services.retrieval import (
    ContextBuilderService,
    DenseRetrievalService,
    EmbeddingProvider,
    HybridRetrievalService,
    LexicalRetrievalService,
    RerankerProvider,
    RerankerRetrievalService,
)
from app.services.storage import StorageBackend
from app.tools.get_evidence_detail import GetEvidenceDetailTool
from app.tools.read_uploaded_file import ReadUploadedFileTool
from app.tools.search_knowledge import SearchKnowledgeTool

KnowledgeEnvelope: TypeAlias = (
    ToolEnvelope[SearchKnowledgeResult]
    | ToolEnvelope[ReadUploadedFileResult]
    | ToolEnvelope[GetEvidenceDetailResult]
)


class KnowledgeCapabilityExecutor(Protocol):
    """Execute one validated Knowledge capability through its registered Tool."""

    def execute(self, action: ExecuteCapabilityAction) -> KnowledgeEnvelope: ...


class KnowledgeCapabilityExecutorFactory(Protocol):
    """Bind Knowledge Tools to one Worker's trusted resources."""

    def create(
        self,
        execution_context: WorkerExecutionContext,
    ) -> KnowledgeCapabilityExecutor: ...


@dataclass(frozen=True, slots=True)
class KnowledgeWorkerGuardrails:
    """Server-owned decision bound for one Knowledge Worker attempt."""

    max_decisions: int = 5

    def __post_init__(self) -> None:
        if isinstance(self.max_decisions, bool) or not 1 <= self.max_decisions <= 8:
            raise ValueError("max_decisions must be 1-8")


class SqlAlchemyKnowledgeCapabilityExecutorFactory:
    """Build the three existing M2 knowledge Tools over one Worker Session."""

    def __init__(
        self,
        *,
        settings: Settings,
        storage: StorageBackend,
        embedding_provider: EmbeddingProvider,
        reranker_provider: RerankerProvider,
    ) -> None:
        self._settings = settings
        self._storage = storage
        self._embedding_provider = embedding_provider
        self._reranker_provider = reranker_provider

    def create(
        self,
        execution_context: WorkerExecutionContext,
    ) -> KnowledgeCapabilityExecutor:
        settings = self._settings
        session = execution_context.session
        retrieval = RetrievalRepository(
            session,
            statement_timeout_ms=settings.database_statement_timeout_ms,
        )
        dense = DenseRetrievalService(
            retrieval,
            self._embedding_provider,
            query_max_characters=settings.retrieval_query_max_characters,
            candidate_count=settings.dense_candidate_count,
        )
        lexical = LexicalRetrievalService(
            retrieval,
            query_max_characters=settings.retrieval_query_max_characters,
            candidate_count=settings.lexical_candidate_count,
        )
        hybrid = HybridRetrievalService(
            dense,
            lexical,
            rrf_k=settings.rrf_k,
            candidate_count=settings.hybrid_candidate_count,
        )
        reranker = RerankerRetrievalService(
            hybrid,
            self._reranker_provider,
            top_k=settings.reranker_top_k,
        )
        current_user = _current_user(execution_context)
        search_tool = SearchKnowledgeTool(
            execution_context.harness,
            KnowledgeSearchService(
                reranker,
                ContextBuilderService(
                    retrieval,
                    max_tokens=settings.context_max_tokens,
                    max_segments=settings.context_max_segments,
                    neighbor_window=settings.context_neighbor_window,
                ),
                EvidenceService(session),
            ),
            current_user,
        )
        file_tool = ReadUploadedFileTool(
            execution_context.harness,
            FileReadingService(
                FileRepository(session, settings.database_statement_timeout_ms),
                self._storage,
                maximum_artifact_bytes=settings.file_read_max_artifact_bytes,
            ),
            current_user,
        )
        evidence_tool = GetEvidenceDetailTool(
            execution_context.harness,
            EvidenceQueryService(
                EvidenceRepository(session, settings.database_statement_timeout_ms)
            ),
            current_user,
        )
        return _SqlAlchemyKnowledgeCapabilityExecutor(
            search_tool,
            file_tool,
            evidence_tool,
        )


@dataclass(frozen=True, slots=True)
class _SqlAlchemyKnowledgeCapabilityExecutor:
    search_tool: SearchKnowledgeTool
    file_tool: ReadUploadedFileTool
    evidence_tool: GetEvidenceDetailTool

    def execute(self, action: ExecuteCapabilityAction) -> KnowledgeEnvelope:
        try:
            if action.capability_id == "search_knowledge":
                search_request = SearchKnowledgeInput.model_validate(
                    action.arguments.root
                )
                return self.search_tool.invoke(search_request)
            if action.capability_id == "read_uploaded_file":
                file_request = ReadUploadedFileInput.model_validate(
                    action.arguments.root
                )
                return self.file_tool.invoke(file_request)
            if action.capability_id == "get_evidence_detail":
                evidence_request = GetEvidenceDetailInput.model_validate(
                    action.arguments.root
                )
                return self.evidence_tool.invoke(evidence_request)
        except ValidationError:
            raise AgentProviderOutputError from None
        raise AgentProviderOutputError


class KnowledgeWorker:
    """Select bounded knowledge actions and expose only safe public results."""

    worker_id = "knowledge"

    def __init__(
        self,
        *,
        provider: AgentDecisionProvider,
        resolver: CapabilityResolver,
        executor_factory: KnowledgeCapabilityExecutorFactory,
        guardrails: KnowledgeWorkerGuardrails | None = None,
        id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._provider = provider
        self._resolver = resolver
        self._executor_factory = executor_factory
        self._guardrails = guardrails or KnowledgeWorkerGuardrails()
        self._id_factory = id_factory

    async def run(
        self,
        handoff: AgentHandoff,
        execution: WorkerExecutionContext,
    ) -> WorkerResult:
        """Run one non-delegating knowledge loop inside the common Runtime."""

        observations: list[WorkerObservation] = []
        try:
            self._validate_runtime_binding(handoff, execution)
            capabilities = self._resolver.resolve_for_agent(
                execution.trusted_context,
                self.worker_id,
                CapabilitySelection(),
            )
            plan = _worker_plan(handoff)
            executor = self._executor_factory.create(execution)
            action_signatures: set[str] = set()

            for _ in range(self._guardrails.max_decisions):
                request = DecisionRequest(
                    plan=plan,
                    active_task_id=handoff.task_id,
                    available_capabilities=capabilities,
                    public_context=handoff.public_context,
                    observations=tuple(observations),
                )
                execution.harness.reserve_model_call()
                decision = validate_decision_response(
                    request,
                    await self._provider.choose_action(request),
                )
                action = decision.action

                if isinstance(action, ExecuteCapabilityAction):
                    _validate_action_arguments(action)
                    _validate_action_scope(action, handoff, observations)
                    signature = _action_signature(action)
                    if signature in action_signatures:
                        raise BudgetExceededError(
                            "repeated_tool_call",
                            "检测到重复Tool调用，已停止Worker执行。",
                        )
                    action_signatures.add(signature)
                    observation = _observation_from_envelope(
                        self._id_factory(),
                        action,
                        executor.execute(action),
                    )
                    observations.append(observation)
                    if observation.status == "timeout":
                        return _failed_result(
                            handoff,
                            observations,
                            _timeout_error(observation),
                            outcome="timed_out",
                        )
                    continue

                if isinstance(action, AskUserAction):
                    return _waiting_user_result(handoff, observations, action)
                if isinstance(action, FinishAction):
                    return _finished_result(handoff, observations, action)
                if isinstance(action, CannotCompleteAction):
                    return _cannot_complete_result(handoff, observations, action)
                raise AgentProviderOutputError

            raise BudgetExceededError(
                "worker_decision_limit",
                "Worker决策次数已达到上限。",
            )
        except ApplicationError as error:
            return _failed_result(handoff, observations, error)
        except Exception:  # noqa: BLE001 - Worker is the sanitization boundary
            return _failed_result(handoff, observations, _internal_worker_error())

    def _validate_runtime_binding(
        self,
        handoff: AgentHandoff,
        execution: WorkerExecutionContext,
    ) -> None:
        if handoff.target_worker != self.worker_id:
            raise AgentProviderOutputError
        if handoff.allocated_budget_ref != execution.worker_run.budget_ref:
            raise AgentProviderOutputError
        if execution.can_delegate:
            raise AgentProviderOutputError


def _current_user(execution: WorkerExecutionContext) -> CurrentUser:
    context = execution.trusted_context
    return CurrentUser.model_validate(
        {
            "user_id": context.user_id,
            "tenant_id": context.tenant_id,
            "email": "agent-runtime@deepsearch.local",
            "display_name": "Agent Runtime Identity",
            "roles": list(context.roles),
            "market_scopes": list(context.market_scopes),
            "synthetic_data": True,
        }
    )


def _worker_plan(handoff: AgentHandoff) -> TaskPlan:
    return TaskPlan(
        plan_id=handoff.handoff_id,
        goal=handoff.goal,
        tasks=[
            AgentTask(
                task_id=handoff.task_id,
                goal=handoff.goal,
                required_capabilities=[],
                assignment=TaskAssignment(
                    status="assigned",
                    worker_id=handoff.target_worker,
                ),
                execution_status="running",
                completion_criteria=list(handoff.completion_criteria),
                evidence_requirement=EvidenceRequirement(
                    required=False,
                    minimum_count=0,
                    source_types=["document", "artifact"],
                ),
                failure_impact="allows_partial",
            )
        ],
    )


def _validate_action_arguments(action: ExecuteCapabilityAction) -> None:
    try:
        if action.capability_id == "search_knowledge":
            SearchKnowledgeInput.model_validate(action.arguments.root)
            return
        if action.capability_id == "read_uploaded_file":
            ReadUploadedFileInput.model_validate(action.arguments.root)
            return
        if action.capability_id == "get_evidence_detail":
            GetEvidenceDetailInput.model_validate(action.arguments.root)
            return
    except ValidationError:
        raise AgentProviderOutputError from None
    raise AgentProviderOutputError


def _validate_action_scope(
    action: ExecuteCapabilityAction,
    handoff: AgentHandoff,
    observations: Sequence[WorkerObservation],
) -> None:
    arguments = action.arguments.root
    context = handoff.public_context.root
    if action.capability_id == "search_knowledge":
        expected_query = context.get("knowledge_query", context.get("query"))
        if expected_query is None or arguments.get("query") != expected_query:
            raise AgentProviderOutputError
        return

    if action.capability_id == "read_uploaded_file":
        requested = _uuid_argument(arguments.get("file_id"))
        if requested not in _allowed_file_ids(handoff):
            raise AgentProviderOutputError
        return

    requested = _uuid_argument(arguments.get("evidence_id"))
    allowed_evidence = {
        *handoff.evidence_ids,
        *(
            evidence_id
            for observation in observations
            for evidence_id in observation.evidence_ids
        ),
    }
    if requested not in allowed_evidence:
        raise AgentProviderOutputError


def _allowed_file_ids(handoff: AgentHandoff) -> set[UUID]:
    allowed = set(handoff.artifact_ids)
    context = handoff.public_context.root
    values: list[object] = []
    if "file_id" in context:
        values.append(context["file_id"])
    file_ids = context.get("file_ids")
    if isinstance(file_ids, list):
        values.extend(file_ids)
    try:
        allowed.update(_uuid_argument(value) for value in values)
    except (TypeError, ValueError):
        raise AgentProviderOutputError from None
    return allowed


def _uuid_argument(value: object) -> UUID:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        return UUID(value)
    raise AgentProviderOutputError


def _action_signature(action: ExecuteCapabilityAction) -> str:
    return json.dumps(
        {
            "capability_id": action.capability_id,
            "arguments": action.arguments.root,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _observation_from_envelope(
    observation_id: UUID,
    action: ExecuteCapabilityAction,
    envelope: KnowledgeEnvelope,
) -> WorkerObservation:
    if envelope.meta.tool != action.capability_id:
        raise AgentProviderOutputError
    usage = ResourceUsage(
        model_calls=0,
        tool_calls=1,
        input_tokens=0,
        output_tokens=0,
        duration_ms=envelope.meta.duration_ms,
    )
    if envelope.status == "success":
        if envelope.data is None:
            raise AgentProviderOutputError
        data = _public_result_data(action.capability_id, envelope.data)
        return WorkerObservation(
            observation_id=observation_id,
            status="success",
            public_summary=f"{action.capability_id}执行成功。",
            structured_result=BoundedJsonObject(
                {"capability_id": action.capability_id, "data": data}
            ),
            evidence_ids=list(envelope.evidence_ids),
            artifact_ids=_artifact_ids(action.capability_id, data),
            resource_usage=usage,
        )

    if envelope.error is None:
        raise AgentProviderOutputError
    return WorkerObservation(
        observation_id=observation_id,
        status=_observation_error_status(envelope.error),
        public_summary=envelope.error.message,
        safe_error=_safe_error(envelope.error),
        resource_usage=usage,
    )


def _public_result_data(
    capability_id: str,
    data: SearchKnowledgeResult | ReadUploadedFileResult | GetEvidenceDetailResult,
) -> dict[str, object]:
    """Flatten existing public Tool results to the Agent JSON depth/size contract."""

    if capability_id == "search_knowledge" and isinstance(data, SearchKnowledgeResult):
        context = data.context

        def search_data(text_limit: int) -> dict[str, object]:
            return {
                "context_id": str(context.context_id),
                "supported": context.supported,
                "segments": [
                    {
                        "evidence_id": str(segment.evidence_id),
                        "citation_label": segment.citation_label,
                        "source_type": segment.source_type,
                        "title": segment.document.title,
                        "text": segment.text[:text_limit],
                        "source_locator_json": segment.source_locator.model_dump_json()[
                            :384
                        ],
                        "document_id": str(segment.identity.document_id),
                        "version_id": str(segment.identity.version_id),
                        "index_set_id": str(segment.identity.index_set_id),
                        "chunk_id": str(segment.identity.chunk_id),
                    }
                    for segment in context.segments
                ],
            }

        def fits_agent_json(candidate: dict[str, object]) -> bool:
            try:
                BoundedJsonObject({"capability_id": capability_id, "data": candidate})
            except ValueError:
                return False
            return True

        full = search_data(1200)
        if fits_agent_json(full):
            return full

        low = 0
        high = 1199
        while low < high:
            middle = (low + high + 1) // 2
            if fits_agent_json(search_data(middle)):
                low = middle
            else:
                high = middle - 1
        bounded = search_data(low)
        if not fits_agent_json(bounded):
            raise AgentProviderOutputError
        return bounded
    if capability_id == "read_uploaded_file" and isinstance(
        data, ReadUploadedFileResult
    ):
        return {
            "file_id": str(data.file_id),
            "document_id": str(data.document_id),
            "version_id": str(data.version_id),
            "original_name": data.original_name,
            "source_type": data.source_type,
            "is_active_version": data.is_active_version,
            "sections": [
                {
                    "kind": section.kind,
                    "content": section.content[:1800],
                    "source_locator_json": section.locator.model_dump_json()[:384],
                    "truncated": section.truncated or len(section.content) > 1800,
                }
                for section in data.sections
            ],
            "truncated": data.truncated,
        }
    if capability_id == "get_evidence_detail" and isinstance(
        data, GetEvidenceDetailResult
    ):
        detail = data.detail
        public: dict[str, object] = {
            "evidence_id": str(detail.id),
            "source_type": detail.source_type,
            "title": detail.title,
            "excerpt": detail.excerpt,
            "observed_at": detail.observed_at.isoformat(),
        }
        if isinstance(detail, ToolDocumentEvidenceDetail):
            public["citation_label"] = detail.citation_label
            public["source_locator_json"] = detail.source_locator.model_dump_json()[
                :1000
            ]
            public["file_id"] = str(detail.file_id)
        return public
    raise AgentProviderOutputError


def _artifact_ids(capability_id: str, data: dict[str, object]) -> list[UUID]:
    if capability_id == "read_uploaded_file":
        return [_uuid_argument(data.get("file_id"))]
    if capability_id == "get_evidence_detail" and data.get("source_type") in {
        "knowledge",
        "user_file",
    }:
        return [_uuid_argument(data.get("file_id"))]
    return []


def _observation_error_status(
    error: ErrorDetail,
) -> Literal["error", "rejected", "timeout"]:
    if error.code in {"DATABASE_TIMEOUT", "BUDGET_EXCEEDED"}:
        return "timeout"
    if error.code == "FORBIDDEN":
        return "rejected"
    return "error"


def _finished_result(
    handoff: AgentHandoff,
    observations: Sequence[WorkerObservation],
    action: FinishAction,
) -> WorkerResult:
    successful = [item for item in observations if item.status == "success"]
    failed = [item for item in observations if item.status != "success"]
    available_evidence_ids = _unique_evidence_ids(observations)
    artifact_ids = _unique_artifact_ids(observations)
    if (
        action.evidence_ids != available_evidence_ids
        or action.artifact_ids != artifact_ids
    ):
        raise AgentProviderOutputError
    if action.business_outcome == "answered" and (not successful or failed):
        raise AgentProviderOutputError
    if action.business_outcome == "partial" and (not successful or not failed):
        raise AgentProviderOutputError
    if action.business_outcome in {"answered", "partial"} and not (
        action.evidence_ids or action.artifact_ids
    ):
        raise AgentProviderOutputError
    if action.business_outcome == "no_evidence" and (
        not successful or available_evidence_ids or artifact_ids or failed
    ):
        raise AgentProviderOutputError

    projected_observations = _deduplicate_evidence_observations(observations)
    projected_successful = [
        item for item in projected_observations if item.status == "success"
    ]

    return WorkerResult(
        task_id=handoff.task_id,
        worker_id=handoff.target_worker,
        execution_status="completed",
        business_outcome=action.business_outcome,
        business_result=_business_result(projected_successful),
        public_summary=action.public_summary,
        observations=projected_observations,
        evidence_ids=list(action.evidence_ids),
        artifact_ids=artifact_ids,
        unknowns=_unique_unknowns(observations),
        safe_errors=(
            _safe_errors(observations) if action.business_outcome == "partial" else []
        ),
        resource_usage=_zero_usage(),
    )


def _waiting_user_result(
    handoff: AgentHandoff,
    observations: Sequence[WorkerObservation],
    action: AskUserAction,
) -> WorkerResult:
    return WorkerResult(
        task_id=handoff.task_id,
        worker_id=handoff.target_worker,
        execution_status="waiting_user",
        business_outcome=None,
        business_result=None,
        public_summary=action.question,
        observations=_without_references(observations),
        evidence_ids=[],
        artifact_ids=[],
        unknowns=list(
            dict.fromkeys((*_unique_unknowns(observations), *action.requested_fields))
        ),
        safe_errors=[],
        resource_usage=_zero_usage(),
    )


def _cannot_complete_result(
    handoff: AgentHandoff,
    observations: Sequence[WorkerObservation],
    action: CannotCompleteAction,
) -> WorkerResult:
    if action.business_outcome in {"timed_out", "system_error"}:
        outcome: Literal["timed_out", "system_error"] = (
            "timed_out" if action.business_outcome == "timed_out" else "system_error"
        )
        safe_error = next(
            (item.safe_error for item in reversed(observations) if item.safe_error),
            None,
        )
        error = (
            ApplicationError(
                safe_error.code,
                safe_error.message,
                retryable=safe_error.retryable,
                field=safe_error.field,
            )
            if safe_error is not None
            else _internal_worker_error()
        )
        return _failed_result(
            handoff,
            observations,
            error,
            outcome=outcome,
            summary=action.public_summary,
        )

    if action.business_outcome == "denied" and not any(
        item.status == "rejected" for item in observations
    ):
        raise AgentProviderOutputError
    if action.business_outcome in {"unsupported", "denied"} and any(
        item.status == "success" for item in observations
    ):
        raise AgentProviderOutputError
    if action.business_outcome == "no_evidence" and (
        _unique_evidence_ids(observations) or _unique_artifact_ids(observations)
    ):
        raise AgentProviderOutputError
    return WorkerResult(
        task_id=handoff.task_id,
        worker_id=handoff.target_worker,
        execution_status="completed",
        business_outcome=action.business_outcome,
        business_result=None,
        public_summary=action.public_summary,
        observations=list(observations),
        evidence_ids=_unique_evidence_ids(observations),
        artifact_ids=_unique_artifact_ids(observations),
        unknowns=_unique_unknowns(observations),
        safe_errors=(
            _safe_errors(observations) if action.business_outcome == "denied" else []
        ),
        resource_usage=_zero_usage(),
    )


def _deduplicate_evidence_observations(
    observations: Sequence[WorkerObservation],
) -> list[WorkerObservation]:
    """Prefer an Evidence detail over its duplicate search-result copy."""

    selected_evidence = set(_unique_evidence_ids(observations))
    detail_evidence = {
        evidence_id
        for observation in observations
        if _observation_capability_id(observation) == "get_evidence_detail"
        for evidence_id in observation.evidence_ids
        if evidence_id in selected_evidence
    }
    projected: list[WorkerObservation] = []
    for observation in observations:
        capability_id = _observation_capability_id(observation)
        kept_evidence = [
            evidence_id
            for evidence_id in observation.evidence_ids
            if evidence_id in selected_evidence
            and not (
                capability_id == "search_knowledge" and evidence_id in detail_evidence
            )
        ]
        if observation.evidence_ids and not kept_evidence:
            continue

        structured_result = observation.structured_result
        if capability_id == "search_knowledge" and structured_result is not None:
            root = structured_result.root
            data = root.get("data")
            if not isinstance(data, dict) or not isinstance(data.get("segments"), list):
                raise AgentProviderOutputError
            selected_strings = {str(value) for value in kept_evidence}
            selected_segments = [
                segment
                for segment in data["segments"]
                if isinstance(segment, dict)
                and segment.get("evidence_id") in selected_strings
            ]
            projected_data = dict(data)
            projected_data["segments"] = selected_segments
            projected_data["supported"] = bool(selected_segments)
            structured_result = BoundedJsonObject(
                {"capability_id": capability_id, "data": projected_data}
            )

        projected.append(
            observation.model_copy(
                update={
                    "structured_result": structured_result,
                    "evidence_ids": kept_evidence,
                },
                deep=True,
            )
        )
    return projected


def _observation_capability_id(observation: WorkerObservation) -> str | None:
    if observation.structured_result is None:
        return None
    value = observation.structured_result.root.get("capability_id")
    return value if isinstance(value, str) else None


def _failed_result(
    handoff: AgentHandoff,
    observations: Sequence[WorkerObservation],
    error: ApplicationError,
    *,
    outcome: Literal["timed_out", "system_error"] = "system_error",
    summary: str | None = None,
) -> WorkerResult:
    return WorkerResult(
        task_id=handoff.task_id,
        worker_id=handoff.target_worker,
        execution_status="failed",
        business_outcome=outcome,
        business_result=None,
        public_summary=summary or error.message,
        observations=_without_references(observations),
        evidence_ids=[],
        artifact_ids=[],
        unknowns=_unique_unknowns(observations),
        safe_errors=[
            SafeAgentError(
                code=error.code,
                message=error.message,
                retryable=error.retryable,
                field=error.field,
                diagnostic_stage=(
                    error.stage if isinstance(error, AgentProviderOutputError) else None
                ),
            )
        ],
        resource_usage=_zero_usage(),
    )


def _business_result(
    observations: Sequence[WorkerObservation],
) -> BoundedJsonObject | None:
    results: dict[str, object] = {}
    details: list[object] = []
    for observation in observations:
        if observation.structured_result is None:
            continue
        payload = observation.structured_result.root
        capability_id = payload.get("capability_id")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise AgentProviderOutputError
        if capability_id == "search_knowledge":
            results["knowledge_search"] = data
        elif capability_id == "read_uploaded_file":
            results["uploaded_file"] = data
        elif capability_id == "get_evidence_detail":
            details.append(data)
        else:
            raise AgentProviderOutputError
    if details:
        results["evidence_details"] = details
    return BoundedJsonObject(results) if results else None


def _unique_evidence_ids(observations: Sequence[WorkerObservation]) -> list[UUID]:
    return list(
        dict.fromkeys(
            evidence_id
            for observation in observations
            for evidence_id in observation.evidence_ids
        )
    )


def _unique_artifact_ids(observations: Sequence[WorkerObservation]) -> list[UUID]:
    return list(
        dict.fromkeys(
            artifact_id
            for observation in observations
            for artifact_id in observation.artifact_ids
        )
    )


def _unique_unknowns(observations: Sequence[WorkerObservation]) -> list[str]:
    return list(
        dict.fromkeys(
            unknown for observation in observations for unknown in observation.unknowns
        )
    )


def _without_references(
    observations: Sequence[WorkerObservation],
) -> list[WorkerObservation]:
    """Drop references because an incomplete Worker transaction is rolled back."""

    return [
        observation.model_copy(update={"evidence_ids": [], "artifact_ids": []})
        if observation.evidence_ids or observation.artifact_ids
        else observation.model_copy(deep=True)
        for observation in observations
    ]


def _safe_errors(observations: Sequence[WorkerObservation]) -> list[SafeAgentError]:
    results: list[SafeAgentError] = []
    seen: set[tuple[object, ...]] = set()
    for observation in observations:
        error = observation.safe_error
        if error is None:
            continue
        key = (error.code, error.message, error.retryable, error.field)
        if key not in seen:
            seen.add(key)
            results.append(error)
    return results


def _safe_error(error: ErrorDetail) -> SafeAgentError:
    return SafeAgentError(
        code=error.code,
        message=error.message,
        retryable=error.retryable,
        field=error.field,
    )


def _timeout_error(observation: WorkerObservation) -> ApplicationError:
    error = observation.safe_error
    if error is None:
        return BudgetExceededError("worker_timeout", "Worker执行超时。")
    return ApplicationError(
        error.code,
        error.message,
        retryable=error.retryable,
        field=error.field,
    )


def _internal_worker_error() -> ApplicationError:
    return ApplicationError(
        "INTERNAL_ERROR",
        "Knowledge Worker执行失败。",
        retryable=False,
    )


def _zero_usage() -> ResourceUsage:
    return ResourceUsage(
        model_calls=0,
        tool_calls=0,
        input_tokens=0,
        output_tokens=0,
        duration_ms=0,
    )
