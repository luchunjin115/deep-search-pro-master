"""The only API-facing entry point for the engineered multi-Agent runtime."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from pydantic import Field
from sqlalchemy.orm import Session, sessionmaker

from app.agents.definitions import create_m2_agent_definitions
from app.agents.engineered_state import EngineeredAgentState
from app.agents.runtime import (
    BudgetedAgentProvider,
    TerminationPolicy,
    WorkerDispatcher,
    WorkerHarnessAdapter,
    WorkerRuntime,
    WorkerRunTrace,
    WorkerTerminationManager,
)
from app.agents.supervisor import SupervisorAgent, SupervisorRequest
from app.agents.workers.business_data import (
    BusinessDataWorker,
    SqlAlchemyBusinessCapabilityExecutorFactory,
)
from app.agents.workers.knowledge import (
    KnowledgeWorker,
    SqlAlchemyKnowledgeCapabilityExecutorFactory,
)
from app.capabilities.catalog import create_m2_capability_catalog
from app.capabilities.contracts import CapabilitySelection
from app.capabilities.resolver import CapabilityResolver
from app.core.config import Settings
from app.core.errors import (
    AgentRequestConflictError,
    AgentTerminalError,
    ApplicationError,
    ProviderTimeoutError,
)
from app.core.rag_trace import record_rag_stage
from app.llm.agent_provider import EngineeredAgentProvider
from app.llm.agent_schemas import (
    AgentAnswer,
    AnswerRequest,
    DecisionRequest,
    HandoffDraft,
    HandoffRequest,
    PlannerRequest,
    WorkerCapabilityProfile,
)
from app.repositories.agent_runtime import AgentRuntimeRepository
from app.repositories.conversation import ConversationRepository
from app.repositories.evidence import EvidenceRepository
from app.repositories.files import FileRepository
from app.runtime.budget import (
    AgentBudgetLimits,
    AgentBudgetRestore,
    AgentBudgetTree,
    WorkerBudgetLimits,
)
from app.runtime.context import RunContext, build_run_context
from app.runtime.permissions import PermissionGuard
from app.runtime.trace import RunTrace, TraceRecorder
from app.schemas.agent import (
    AgentConversationMemory,
    AgentDecision,
    BoundedJsonObject,
    BusinessOutcome,
    ResourceUsage,
    TaskPlan,
    WorkerResult,
)
from app.schemas.auth import CurrentUser
from app.schemas.common import ErrorDetail, M1Schema, ToolName
from app.schemas.evidence import (
    AnswerEvidenceMapping,
    AnswerEvidenceReference,
    GetEvidenceDetailInput,
)
from app.services.agent_memory import AgentMemoryService, safe_memory_text
from app.services.agent_runtime import (
    AgentRuntimePersistenceService,
    LoadedAgentCheckpoint,
)
from app.services.evidence import EvidenceQueryService
from app.services.retrieval import EmbeddingProvider, RerankerProvider
from app.services.storage import StorageBackend
from app.tools.registry import create_m2_tool_registry


class AgentGatewayResult(M1Schema):
    """Public-safe completed or clarification result returned to the API."""

    request_id: UUID
    root_run_id: UUID
    trace_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID
    answer: str = Field(min_length=1, max_length=4000)
    business_outcome: BusinessOutcome | None = None
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=12)
    artifact_ids: list[UUID] = Field(default_factory=list, max_length=12)
    tool_names: list[ToolName] = Field(default_factory=list, max_length=5)
    duration_ms: int = Field(ge=0)
    status: Literal["waiting_user", "completed"] = "completed"


@dataclass(frozen=True, slots=True)
class AgentGatewayLimits:
    """Trusted root and per-Worker limits for the public Agent path."""

    root: AgentBudgetLimits = field(
        default_factory=lambda: AgentBudgetLimits(
            max_model_calls=24,
            max_tool_calls=8,
            max_input_tokens=32_000,
            max_output_tokens=8_000,
            max_tasks=8,
            max_evidence=12,
            max_delegations=8,
            max_depth=1,
            total_timeout_ms=60_000,
        )
    )
    business_child: WorkerBudgetLimits = field(
        default_factory=lambda: WorkerBudgetLimits(
            max_model_calls=6,
            max_tool_calls=3,
            max_repeat_tool_calls=1,
            max_input_tokens=8_000,
            max_output_tokens=2_000,
            max_evidence=4,
            timeout_ms=30_000,
        )
    )
    knowledge_child: WorkerBudgetLimits = field(
        default_factory=lambda: WorkerBudgetLimits(
            max_model_calls=6,
            max_tool_calls=3,
            max_repeat_tool_calls=1,
            max_input_tokens=8_000,
            max_output_tokens=2_000,
            max_evidence=8,
            timeout_ms=30_000,
        )
    )

    def __post_init__(self) -> None:
        children = (self.business_child, self.knowledge_child)
        reserved = (
            sum(item.max_model_calls for item in children),
            sum(item.max_tool_calls for item in children),
            sum(item.max_input_tokens for item in children),
            sum(item.max_output_tokens for item in children),
            sum(item.max_evidence for item in children),
        )
        root_capacity = (
            self.root.max_model_calls,
            self.root.max_tool_calls,
            self.root.max_input_tokens,
            self.root.max_output_tokens,
            self.root.max_evidence,
        )
        if any(wanted > limit for wanted, limit in zip(reserved, root_capacity)):
            raise ValueError("parallel Worker reservations exceed the root budget")
        if any(item.timeout_ms > self.root.total_timeout_ms for item in children):
            raise ValueError("Worker timeout exceeds the root timeout")


class AgentGateway:
    """Build one trusted run tree and expose no old Graph fallback."""

    def __init__(
        self,
        *,
        provider: EngineeredAgentProvider,
        session_factory: sessionmaker[Session],
        settings: Settings,
        storage: StorageBackend,
        embedding_provider: EmbeddingProvider,
        reranker_provider: RerankerProvider,
        limits: AgentGatewayLimits | None = None,
    ) -> None:
        self._provider = provider
        self._session_factory = session_factory
        self._settings = settings
        self._storage = storage
        self._embedding_provider = embedding_provider
        self._reranker_provider = reranker_provider
        self._limits = limits or AgentGatewayLimits()

    async def run(
        self,
        user: CurrentUser,
        *,
        thread_id: UUID,
        request_id: UUID,
        message: str,
    ) -> AgentGatewayResult:
        """Start, resume, or replay exactly one trusted conversation request."""

        started = time.monotonic()
        user_message_id = _message_id(user, thread_id, request_id, "user")
        assistant_message_id = _message_id(user, thread_id, request_id, "assistant")
        memory = self._build_memory(
            user,
            thread_id=thread_id,
            current_turn_id=user_message_id,
            current_message=message,
        )
        replay = self._load_request_checkpoint(
            user,
            thread_id=thread_id,
            request_id=request_id,
        )
        if replay is not None:
            if not _request_matches(replay.state, user_message_id, message):
                raise AgentRequestConflictError
            if replay.state.execution_status == "running":
                raise AgentRequestConflictError
            if replay.state.execution_status == "failed" or (
                replay.state.business_outcome == "denied"
            ):
                raise _terminal_error(replay.state, None, replay.trace_id)
            self._authorize_or_deny(
                user,
                thread_id=thread_id,
                state=replay.state,
                trace_id=replay.trace_id,
                expected_checkpoint_version=replay.checkpoint_version,
            )
            return self._gateway_result(
                request_id=request_id,
                user_message_id=user_message_id,
                assistant_message_id=assistant_message_id,
                trace_id=replay.trace_id,
                state=replay.state,
            )

        public_context = _public_context(message, memory)
        claimed = self._claim_waiting_checkpoint(
            user,
            thread_id=thread_id,
            request_id=request_id,
            memory=memory,
            public_context=public_context,
        )
        root_run_id = claimed.state.run_id if claimed is not None else uuid4()
        context = build_run_context(
            user,
            thread_id,
            trace_id=claimed.trace_id if claimed is not None else None,
        )
        root_run = RunTrace(
            id=root_run_id,
            tenant_id=user.tenant_id,
            trace_id=context.trace_id,
            started_monotonic=started,
        )
        if claimed is None:
            initial_state = EngineeredAgentState(
                run_id=root_run_id,
                goal=message,
                public_context=public_context,
                memory=memory,
                processed_request_ids=[request_id],
                active_request_id=request_id,
                execution_status="running",
                resource_usage=_zero_usage(),
            )
            checkpoint_version = self._begin_root(
                user,
                thread_id,
                root_run,
                initial_state,
            )
            resume_state = None
            restore = None
            replan = False
        else:
            resume_state = claimed.state
            checkpoint_version = claimed.checkpoint_version
            self._authorize_or_deny(
                user,
                thread_id=thread_id,
                state=resume_state,
                trace_id=claimed.trace_id,
                expected_checkpoint_version=checkpoint_version,
            )
            restore = self._load_budget_restore(user, thread_id, resume_state)
            replan = not resume_state.worker_results and resume_state.replan_count == 0

        resolver = CapabilityResolver(
            create_m2_capability_catalog(),
            create_m2_agent_definitions(),
        )
        budget = AgentBudgetTree(
            root_run_id=root_run_id,
            limits=self._limits.root,
            restore=restore,
        )
        captured_provider = _CapturedAgentProvider(self._provider)
        supervisor_provider = _PlanPersistenceProvider(
            provider=BudgetedAgentProvider(
                provider=captured_provider,
                budget=budget,
            ),
            session_factory=self._session_factory,
            settings=self._settings,
            user=user,
            thread_id=thread_id,
            root_run_id=root_run_id,
            replace_plan=replan,
        )
        worker_runtime = self._worker_runtime(
            context=context,
            user=user,
            root_run=root_run,
            resolver=resolver,
            provider=captured_provider,
            budget=budget,
        )
        supervisor = SupervisorAgent(
            provider=supervisor_provider,
            worker=worker_runtime,
        )
        supervisor_request = SupervisorRequest(
            run_id=root_run_id,
            goal=resume_state.goal if resume_state is not None else message,
            public_context=public_context,
            available_workers=_worker_profiles(resolver, context),
        )
        state = (
            await supervisor.resume(supervisor_request, resume_state, replan=replan)
            if resume_state is not None
            else await supervisor.run(supervisor_request)
        )
        elapsed_ms = max(round((time.monotonic() - started) * 1000), 0)
        prior_duration_ms = (
            resume_state.resource_usage.duration_ms if resume_state is not None else 0
        )
        state = EngineeredAgentState.model_validate(
            state.model_dump(mode="json", round_trip=True)
            | {
                "memory": memory.model_dump(mode="json", round_trip=True),
                "processed_request_ids": (
                    list(resume_state.processed_request_ids)
                    if resume_state is not None
                    else [request_id]
                ),
                "active_request_id": request_id,
                "resume_count": resume_state.resume_count if resume_state else 0,
                "replan_count": (
                    resume_state.replan_count + int(replan) if resume_state else 0
                ),
                "resource_usage": state.resource_usage.model_copy(
                    update={"duration_ms": prior_duration_ms + elapsed_ms}
                ).model_dump(mode="json", round_trip=True),
            }
        )
        self._authorize_or_deny(
            user,
            thread_id=thread_id,
            state=state,
            trace_id=context.trace_id,
            expected_checkpoint_version=checkpoint_version,
        )
        self._finish_root(
            user,
            thread_id,
            state,
            expected_checkpoint_version=checkpoint_version,
        )
        record_rag_stage("resource_usage", state.resource_usage)

        if state.execution_status not in {"completed", "waiting_user"} or (
            state.business_outcome == "denied"
        ):
            raise _terminal_error(state, captured_provider.last_error, context.trace_id)
        assert state.public_summary is not None
        return self._gateway_result(
            request_id=request_id,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            trace_id=context.trace_id,
            state=state,
        )

    def _worker_runtime(
        self,
        *,
        context: RunContext,
        user: CurrentUser,
        root_run: RunTrace,
        resolver: CapabilityResolver,
        provider: EngineeredAgentProvider,
        budget: AgentBudgetTree,
    ) -> WorkerRuntime:
        registry = create_m2_tool_registry()
        dispatcher = WorkerDispatcher(
            (
                BusinessDataWorker(
                    provider=provider,
                    resolver=resolver,
                    executor_factory=SqlAlchemyBusinessCapabilityExecutorFactory(
                        statement_timeout_ms=(
                            self._settings.database_statement_timeout_ms
                        )
                    ),
                ),
                KnowledgeWorker(
                    provider=provider,
                    resolver=resolver,
                    executor_factory=SqlAlchemyKnowledgeCapabilityExecutorFactory(
                        settings=self._settings,
                        storage=self._storage,
                        embedding_provider=self._embedding_provider,
                        reranker_provider=self._reranker_provider,
                    ),
                ),
            )
        )
        return WorkerRuntime(
            trusted_context=context,
            parent_run=root_run,
            budget_tree=budget,
            child_budget_limits={
                "business_data": self._limits.business_child,
                "knowledge": self._limits.knowledge_child,
            },
            dispatcher=dispatcher,
            harness_factory=WorkerHarnessAdapter(
                registry=registry,
                permission_guard=PermissionGuard(registry),
                trace_recorder=TraceRecorder(self._session_factory),
            ),
            session_factory=self._session_factory,
            trace_recorder=_PersistentWorkerTraceRecorder(
                session_factory=self._session_factory,
                settings=self._settings,
                user=user,
                thread_id=context.thread_id,
            ),
            termination=WorkerTerminationManager(
                TerminationPolicy(max_repeat_handoffs=1, max_no_progress_results=1)
            ),
        )

    def _begin_root(
        self,
        user: CurrentUser,
        thread_id: UUID,
        root_run: RunTrace,
        initial_state: EngineeredAgentState,
    ) -> int:
        with self._session_factory.begin() as session:
            persistence = _persistence(session, self._settings)
            persistence.begin_root_run(
                user,
                thread_id=thread_id,
                run_id=root_run.id,
                trace_id=root_run.trace_id,
            )
            return persistence.save_checkpoint(
                user,
                thread_id=thread_id,
                state=initial_state,
                expected_version=0,
            ).checkpoint_version

    def _build_memory(
        self,
        user: CurrentUser,
        *,
        thread_id: UUID,
        current_turn_id: UUID,
        current_message: str,
    ) -> AgentConversationMemory:
        with self._session_factory.begin() as session:
            return AgentMemoryService(
                ConversationRepository(
                    session,
                    self._settings.database_statement_timeout_ms,
                )
            ).build(
                user,
                thread_id=thread_id,
                current_turn_id=current_turn_id,
                current_message=current_message,
            )

    def _load_request_checkpoint(
        self,
        user: CurrentUser,
        *,
        thread_id: UUID,
        request_id: UUID,
    ) -> LoadedAgentCheckpoint | None:
        with self._session_factory.begin() as session:
            return _persistence(session, self._settings).load_checkpoint_for_request(
                user,
                thread_id=thread_id,
                request_id=request_id,
            )

    def _claim_waiting_checkpoint(
        self,
        user: CurrentUser,
        *,
        thread_id: UUID,
        request_id: UUID,
        memory: AgentConversationMemory,
        public_context: BoundedJsonObject,
    ) -> LoadedAgentCheckpoint | None:
        with self._session_factory.begin() as session:
            return _persistence(
                session,
                self._settings,
            ).claim_latest_waiting_checkpoint(
                user,
                thread_id=thread_id,
                request_id=request_id,
                memory=memory,
                public_context=public_context,
            )

    def _load_budget_restore(
        self,
        user: CurrentUser,
        thread_id: UUID,
        state: EngineeredAgentState,
    ) -> AgentBudgetRestore:
        with self._session_factory.begin() as session:
            return _persistence(session, self._settings).load_budget_restore(
                user,
                thread_id=thread_id,
                state=state,
            )

    def _require_authorized_references(
        self,
        user: CurrentUser,
        state: EngineeredAgentState,
        trace_id: UUID,
    ) -> None:
        evidence_ids, artifact_ids = _all_state_references(state)
        if not evidence_ids and not artifact_ids:
            return
        with self._session_factory.begin() as session:
            evidence = EvidenceQueryService(
                EvidenceRepository(
                    session,
                    self._settings.database_statement_timeout_ms,
                )
            )
            files = FileRepository(
                session,
                self._settings.database_statement_timeout_ms,
            )
            try:
                for evidence_id in evidence_ids:
                    evidence.get_tool_detail(
                        user,
                        GetEvidenceDetailInput(evidence_id=evidence_id),
                    )
                for artifact_id in artifact_ids:
                    if (
                        files.find_accessible_by_id(
                            tenant_id=user.tenant_id,
                            user_id=user.user_id,
                            role_names=tuple(user.roles),
                            market_scopes=tuple(user.market_scopes),
                            file_id=artifact_id,
                        )
                        is None
                    ):
                        raise AgentTerminalError(
                            ErrorDetail(
                                code="FORBIDDEN",
                                message="当前身份已不能访问先前运行引用的数据。",
                                retryable=False,
                            ),
                            terminal_status="denied",
                            trace_id=trace_id,
                        )
            except AgentTerminalError:
                raise
            except ApplicationError:
                raise AgentTerminalError(
                    ErrorDetail(
                        code="FORBIDDEN",
                        message="当前身份已不能访问先前运行引用的数据。",
                        retryable=False,
                    ),
                    terminal_status="denied",
                    trace_id=trace_id,
                ) from None

    def _authorize_or_deny(
        self,
        user: CurrentUser,
        *,
        thread_id: UUID,
        state: EngineeredAgentState,
        trace_id: UUID,
        expected_checkpoint_version: int,
    ) -> None:
        try:
            self._require_authorized_references(user, state, trace_id)
        except AgentTerminalError:
            denied = _denied_reference_state(state)
            with self._session_factory.begin() as session:
                _persistence(session, self._settings).save_checkpoint(
                    user,
                    thread_id=thread_id,
                    state=denied,
                    expected_version=expected_checkpoint_version,
                )
            raise

    def _gateway_result(
        self,
        *,
        request_id: UUID,
        user_message_id: UUID,
        assistant_message_id: UUID,
        trace_id: UUID,
        state: EngineeredAgentState,
    ) -> AgentGatewayResult:
        if state.execution_status not in {"completed", "waiting_user"}:
            raise AgentRequestConflictError
        assert state.public_summary is not None
        status = cast(Literal["waiting_user", "completed"], state.execution_status)
        tool_names = _state_tool_names(state)
        return AgentGatewayResult(
            request_id=request_id,
            root_run_id=state.run_id,
            trace_id=trace_id,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            answer=state.public_summary,
            business_outcome=state.business_outcome,
            evidence_ids=state.evidence_ids,
            artifact_ids=state.artifact_ids,
            tool_names=cast(list[ToolName], tool_names),
            duration_ms=state.resource_usage.duration_ms,
            status=status,
        )

    def _finish_root(
        self,
        user: CurrentUser,
        thread_id: UUID,
        state: object,
        *,
        expected_checkpoint_version: int,
    ) -> list[str]:
        validated = EngineeredAgentState.model_validate(state)
        with self._session_factory.begin() as session:
            persistence = _persistence(session, self._settings)
            persistence.synchronize_task_board(
                user,
                thread_id=thread_id,
                state=validated,
            )
            persistence.save_checkpoint(
                user,
                thread_id=thread_id,
                state=validated,
                expected_version=expected_checkpoint_version,
            )
            if validated.execution_status == "completed":
                persistence.save_answer_evidence(
                    user,
                    thread_id=thread_id,
                    mapping=AnswerEvidenceMapping(
                        root_run_id=validated.run_id,
                        references=[
                            AnswerEvidenceReference(
                                citation_label=f"[E{ordinal}]",
                                evidence_id=evidence_id,
                            )
                            for ordinal, evidence_id in enumerate(
                                validated.evidence_ids,
                                start=1,
                            )
                        ],
                    ),
                )
            return persistence.list_tool_names(
                user,
                thread_id=thread_id,
                root_run_id=validated.run_id,
            )


class _CapturedAgentProvider:
    def __init__(self, provider: EngineeredAgentProvider) -> None:
        self._provider = provider
        self.last_error: ApplicationError | None = None

    async def create_plan(self, request: PlannerRequest) -> TaskPlan:
        try:
            return await self._provider.create_plan(request)
        except ApplicationError as error:
            self.last_error = error
            raise

    async def choose_action(self, request: DecisionRequest) -> AgentDecision:
        try:
            return await self._provider.choose_action(request)
        except ApplicationError as error:
            self.last_error = error
            raise

    async def prepare_handoff(self, request: HandoffRequest) -> HandoffDraft:
        try:
            return await self._provider.prepare_handoff(request)
        except ApplicationError as error:
            self.last_error = error
            raise

    async def compose_answer(self, request: AnswerRequest) -> AgentAnswer:
        try:
            return await self._provider.compose_answer(request)
        except ApplicationError as error:
            self.last_error = error
            raise


class _PlanPersistenceProvider:
    def __init__(
        self,
        *,
        provider: EngineeredAgentProvider,
        session_factory: sessionmaker[Session],
        settings: Settings,
        user: CurrentUser,
        thread_id: UUID,
        root_run_id: UUID,
        replace_plan: bool,
    ) -> None:
        self._provider = provider
        self._session_factory = session_factory
        self._settings = settings
        self._user = user
        self._thread_id = thread_id
        self._root_run_id = root_run_id
        self._replace_plan = replace_plan

    @property
    def last_answer_model_calls(self) -> int:
        value = getattr(self._provider, "last_answer_model_calls", 1)
        return value if isinstance(value, int) else 1

    async def create_plan(self, request: PlannerRequest) -> TaskPlan:
        plan = await self._provider.create_plan(request)
        with self._session_factory.begin() as session:
            persistence = _persistence(session, self._settings)
            operation = (
                persistence.replace_waiting_task_plan
                if self._replace_plan
                else persistence.save_task_plan
            )
            operation(
                self._user,
                thread_id=self._thread_id,
                root_run_id=self._root_run_id,
                plan=plan,
            )
        return plan

    async def choose_action(self, request: DecisionRequest) -> AgentDecision:
        return await self._provider.choose_action(request)

    async def prepare_handoff(self, request: HandoffRequest) -> HandoffDraft:
        return await self._provider.prepare_handoff(request)

    async def compose_answer(self, request: AnswerRequest) -> AgentAnswer:
        return await self._provider.compose_answer(request)


class _PersistentWorkerTraceRecorder:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        settings: Settings,
        user: CurrentUser,
        thread_id: UUID,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._user = user
        self._thread_id = thread_id
        self._runs: dict[UUID, WorkerRunTrace] = {}
        self._task_versions: dict[UUID, int] = {}

    def start(
        self,
        *,
        worker_run: WorkerRunTrace,
        tenant_id: UUID,
        task_id: str,
        worker_id: str,
    ) -> RunTrace:
        if tenant_id != self._user.tenant_id:
            raise ValueError("Worker trace tenant mismatch")
        with self._session_factory.begin() as session:
            started = _persistence(session, self._settings).start_worker_run(
                self._user,
                thread_id=self._thread_id,
                worker_run=worker_run,
                task_id=task_id,
                worker_id=worker_id,
            )
        self._runs[worker_run.run_id] = worker_run
        self._task_versions[worker_run.run_id] = started.task_version
        return RunTrace(
            id=worker_run.run_id,
            tenant_id=tenant_id,
            trace_id=worker_run.trace_id,
            started_monotonic=time.monotonic(),
        )

    def finish(self, worker_run_id: UUID, result: WorkerResult) -> None:
        worker_run = self._runs.get(worker_run_id)
        if worker_run is None:
            raise ValueError("Worker run was not started")
        task_version = self._task_versions.get(worker_run_id)
        if task_version is None:
            raise ValueError("Worker task version was not recorded")
        with self._session_factory.begin() as session:
            _persistence(session, self._settings).record_worker_result(
                self._user,
                thread_id=self._thread_id,
                root_run_id=worker_run.root_run_id,
                worker_run_id=worker_run_id,
                result=result,
                expected_task_version=task_version,
            )


def _worker_profiles(
    resolver: CapabilityResolver,
    context: RunContext,
) -> tuple[WorkerCapabilityProfile, ...]:
    workers = resolver.resolve_delegation_targets(
        context,
        CapabilitySelection(),
    ).capabilities
    return tuple(
        WorkerCapabilityProfile(
            worker=worker,
            capabilities=resolver.resolve_for_agent(
                context,
                worker.capability_id,
                CapabilitySelection(),
            ),
        )
        for worker in workers
    )


def _persistence(
    session: Session,
    settings: Settings,
) -> AgentRuntimePersistenceService:
    return AgentRuntimePersistenceService(
        AgentRuntimeRepository(session, settings.database_statement_timeout_ms)
    )


def _zero_usage() -> ResourceUsage:
    return ResourceUsage(
        model_calls=0,
        tool_calls=0,
        input_tokens=0,
        output_tokens=0,
        duration_ms=0,
    )


def _message_id(
    user: CurrentUser,
    thread_id: UUID,
    request_id: UUID,
    role: Literal["user", "assistant"],
) -> UUID:
    identity = (
        f"agent-message:{user.tenant_id}:{user.user_id}:{thread_id}:{request_id}:{role}"
    )
    return uuid5(NAMESPACE_URL, identity)


def _request_matches(
    state: EngineeredAgentState,
    user_message_id: UUID,
    message: str,
) -> bool:
    return any(
        turn.turn_id == user_message_id
        and turn.role == "user"
        and turn.content_summary == safe_memory_text(message)
        for turn in state.memory.recent_turns
    )


def _public_context(
    message: str,
    memory: AgentConversationMemory,
) -> BoundedJsonObject:
    question = message
    safe_summary = memory.safe_summary
    turns = [
        {
            "speaker_type": turn.role,
            "content_summary": turn.content_summary,
        }
        for turn in memory.recent_turns
    ]
    while True:
        try:
            return BoundedJsonObject(
                {
                    "question": question,
                    "conversation_memory": {
                        "safe_summary": safe_summary,
                        "summarized_turn_count": memory.summarized_turn_count,
                        "recent_turns": turns,
                    },
                }
            )
        except ValueError:
            if safe_summary is not None:
                encoded_size = len(safe_summary.encode("utf-8"))
                safe_summary = (
                    _utf8_prefix(safe_summary, encoded_size // 2)
                    if encoded_size > 256
                    else None
                )
                continue
            if turns:
                turns.pop(0)
                continue
            shortened = _utf8_prefix(question, 12_000)
            if shortened == question:
                raise
            question = shortened


def _utf8_prefix(value: str, max_bytes: int) -> str:
    return value.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")


def _all_state_references(
    state: EngineeredAgentState,
) -> tuple[list[UUID], list[UUID]]:
    evidence_ids = list(state.evidence_ids)
    artifact_ids = list(state.artifact_ids)
    for observation in state.observations:
        evidence_ids.extend(observation.evidence_ids)
        artifact_ids.extend(observation.artifact_ids)
    for result in state.worker_results:
        evidence_ids.extend(result.evidence_ids)
        artifact_ids.extend(result.artifact_ids)
        for observation in result.observations:
            evidence_ids.extend(observation.evidence_ids)
            artifact_ids.extend(observation.artifact_ids)
    return list(dict.fromkeys(evidence_ids)), list(dict.fromkeys(artifact_ids))


def _state_tool_names(state: EngineeredAgentState) -> list[ToolName]:
    allowed: set[str] = {
        "get_product_spec",
        "search_inventory",
        "search_knowledge",
        "read_uploaded_file",
        "get_evidence_detail",
    }
    values: list[ToolName] = []
    for observation in state.observations:
        result = observation.structured_result
        capability_id = result.root.get("capability_id") if result is not None else None
        if isinstance(capability_id, str) and capability_id in allowed:
            value = cast(ToolName, capability_id)
            if value not in values:
                values.append(value)
    return values


def _denied_reference_state(state: EngineeredAgentState) -> EngineeredAgentState:
    return EngineeredAgentState.model_validate(
        state.model_dump(mode="json", round_trip=True)
        | {
            "execution_status": "completed",
            "business_outcome": "denied",
            "current_task_id": None,
            "pending_action": None,
            "observations": [],
            "worker_results": [],
            "evidence_ids": [],
            "artifact_ids": [],
            "public_summary": "当前身份已不能访问先前运行引用的数据。",
            "stop_reason": "reference_authorization_lost",
        }
    )


def _terminal_error(
    state: object,
    provider_error: ApplicationError | None,
    trace_id: UUID,
) -> AgentTerminalError:
    from app.agents.engineered_state import EngineeredAgentState

    validated = EngineeredAgentState.model_validate(state)
    safe_error = next(
        (
            error
            for result in reversed(validated.worker_results)
            for error in result.safe_errors
        ),
        None,
    )
    detail = (
        ErrorDetail(
            code=safe_error.code,
            message=safe_error.message,
            retryable=safe_error.retryable,
            field=safe_error.field,
        )
        if safe_error is not None
        else provider_error.to_detail()
        if provider_error is not None
        else ErrorDetail(
            code="INTERNAL_ERROR",
            message=validated.public_summary or "Agent流程未能安全完成。",
            retryable=False,
        )
    )
    if validated.business_outcome == "denied":
        terminal_status: Literal["failed", "denied", "timed_out"] = "denied"
        if safe_error is None:
            detail = ErrorDetail(
                code="FORBIDDEN",
                message="当前身份无权完成该请求。",
                retryable=False,
            )
    elif validated.business_outcome == "timed_out" or isinstance(
        provider_error, ProviderTimeoutError
    ):
        terminal_status = "timed_out"
    else:
        terminal_status = "failed"
    return AgentTerminalError(
        detail,
        terminal_status=terminal_status,
        trace_id=trace_id,
    )
