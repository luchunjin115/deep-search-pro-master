from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal, cast
from uuid import UUID, uuid4

import pytest

from app.agents.definitions import create_m2_agent_definitions
from app.agents.engineered_state import EngineeredAgentState
from app.agents.runtime import (
    BudgetedAgentProvider,
    InMemoryWorkerTraceRecorder,
    TerminationPolicy,
    WorkerDispatcher,
    WorkerExecutionContext,
    WorkerHarnessAdapter,
    WorkerRuntime,
    WorkerRunTrace,
    WorkerTerminationManager,
)
from app.agents.supervisor import SupervisorAgent, SupervisorRequest
from app.agents.workers import (
    BusinessDataWorker,
    KnowledgeWorker,
    SqlAlchemyBusinessCapabilityExecutorFactory,
    SqlAlchemyKnowledgeCapabilityExecutorFactory,
)
from app.capabilities.catalog import create_m2_capability_catalog
from app.capabilities.contracts import CapabilitySelection
from app.capabilities.resolver import CapabilityResolver
from app.core.config import Settings
from app.llm.agent_provider import AgentDecisionProvider, EngineeredAgentProvider
from app.llm.agent_schemas import (
    AgentAnswer,
    AnswerRequest,
    DecisionRequest,
    HandoffDraft,
    HandoffRequest,
    PlannerRequest,
    WorkerCapabilityProfile,
)
from app.models.knowledge import Document
from app.models.runtime import Thread, ToolCall
from app.runtime.budget import AgentBudgetLimits, AgentBudgetTree, WorkerBudgetLimits
from app.runtime.context import build_run_context
from app.runtime.permissions import PermissionGuard
from app.runtime.trace import TraceRecorder
from app.schemas.agent import (
    AgentDecision,
    AgentHandoff,
    AgentTask,
    BoundedJsonObject,
    CannotCompleteAction,
    DelegateTaskAction,
    EvidenceRequirement,
    ExecuteCapabilityAction,
    FinishAction,
    ResourceUsage,
    TaskAssignment,
    TaskPlan,
    WorkerResult,
)
from app.services.retrieval import (
    EmbeddingBatch,
    EmbeddingIdentity,
    EmbeddingPurpose,
    FakeEmbeddingProvider,
    FakeRerankerProvider,
)
from app.services.retrieval.embedding import build_embedding_cache_key
from app.services.storage import LocalStorageBackend
from app.tools.registry import create_m2_tool_registry
from tests.integration.m2_20_matrix_support import M2FileEvidenceToolMatrix
from tests.integration.test_agent_tools import AgentToolFixture
from tests.integration.test_retrieval_repository_scope import RetrievalScopeFixture

pytest_plugins = (
    "tests.integration.test_agent_tools",
    "tests.integration.test_search_knowledge_tool",
)


class FixedQueryEmbeddingProvider:
    """Use the seeded document identity and a deterministic query vector."""

    def __init__(self) -> None:
        self._identity = FakeEmbeddingProvider().identity

    @property
    def identity(self) -> EmbeddingIdentity:
        return self._identity

    def embed(
        self,
        texts: Sequence[str],
        *,
        purpose: EmbeddingPurpose,
    ) -> EmbeddingBatch:
        return EmbeddingBatch(
            vectors=tuple((1.0,) + (0.0,) * 1023 for _ in texts),
            cache_keys=tuple(
                build_embedding_cache_key(self.identity, purpose, text)
                for text in texts
            ),
            purpose=purpose,
            identity=self.identity,
            effective_batch_size=len(texts),
        )


@dataclass
class KnowledgeProvider:
    scenario: Literal["search", "file", "detail"]
    query: str
    file_id: UUID
    evidence_id: UUID

    async def choose_action(self, request: DecisionRequest) -> AgentDecision:
        if not request.observations:
            if self.scenario == "search":
                return _execute("search_knowledge", {"query": self.query})
            if self.scenario == "file":
                return _execute(
                    "read_uploaded_file",
                    {
                        "file_id": str(self.file_id),
                        "locator": {"source_type": "pdf", "page_start": 1},
                    },
                )
            return _execute(
                "get_evidence_detail", {"evidence_id": str(self.evidence_id)}
            )

        observation = request.observations[-1]
        if observation.status == "success":
            outcome = (
                "no_evidence"
                if self.scenario == "search" and not observation.evidence_ids
                else "answered"
            )
            return AgentDecision(
                action=FinishAction(
                    public_summary="Knowledge Worker完成获权知识读取。",
                    business_outcome=outcome,
                    evidence_ids=_observation_evidence(request),
                    artifact_ids=_observation_artifacts(request),
                )
            )
        return AgentDecision(
            action=CannotCompleteAction(
                public_summary="当前没有可安全返回的知识结果。",
                business_outcome=(
                    "denied" if observation.status == "rejected" else "no_evidence"
                ),
            )
        )


def _execute(capability_id: str, arguments: dict[str, object]) -> AgentDecision:
    return AgentDecision(
        action=ExecuteCapabilityAction(
            capability_id=capability_id,
            arguments=BoundedJsonObject(arguments),
        )
    )


def _observation_evidence(request: DecisionRequest) -> list[UUID]:
    return list(
        dict.fromkeys(
            evidence_id
            for observation in request.observations
            for evidence_id in observation.evidence_ids
        )
    )


def _observation_artifacts(request: DecisionRequest) -> list[UUID]:
    return list(
        dict.fromkeys(
            artifact_id
            for observation in request.observations
            for artifact_id in observation.artifact_ids
        )
    )


def _identity_sha256(identity: EmbeddingIdentity) -> str:
    payload = json.dumps(
        asdict(identity),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _prepare_search_identity(
    matrix: M2FileEvidenceToolMatrix,
    provider: FixedQueryEmbeddingProvider,
) -> None:
    matrix.index_set.embedding_identity_json = asdict(provider.identity)
    matrix.index_set.embedding_identity_sha256 = _identity_sha256(provider.identity)
    matrix.fixture.business_session.flush()


async def _run_knowledge(
    matrix: M2FileEvidenceToolMatrix,
    scenario: Literal["search", "file", "detail"],
    *,
    query: str = "M2-20.6合成整链证据 清洁",
) -> tuple[WorkerResult, UUID]:
    fixture = matrix.fixture
    embedding = FixedQueryEmbeddingProvider()
    _prepare_search_identity(matrix, embedding)
    root_run = fixture.recorder.start_run(matrix.context, "knowledge_query")
    budget_tree = AgentBudgetTree(
        root_run_id=root_run.id,
        limits=AgentBudgetLimits(
            max_model_calls=8,
            max_tool_calls=4,
            max_input_tokens=2_000,
            max_output_tokens=1_000,
            max_tasks=2,
            max_evidence=4,
            max_delegations=2,
            max_depth=1,
            total_timeout_ms=30_000,
        ),
    )
    worker_run_id = uuid4()
    child = budget_tree.allocate_child(
        parent_run_id=root_run.id,
        child_run_id=worker_run_id,
        task_id="knowledge_task",
        limits=WorkerBudgetLimits(
            max_model_calls=5,
            max_tool_calls=3,
            max_repeat_tool_calls=1,
            max_input_tokens=1_000,
            max_output_tokens=500,
            max_evidence=4,
            timeout_ms=15_000,
        ),
    )
    harness = WorkerHarnessAdapter(
        registry=create_m2_tool_registry(),
        permission_guard=PermissionGuard(create_m2_tool_registry()),
        trace_recorder=fixture.recorder,
    ).create(matrix.context, root_run, child)
    execution = WorkerExecutionContext(
        trusted_context=matrix.context,
        worker_run=WorkerRunTrace(
            run_id=worker_run_id,
            parent_run_id=root_run.id,
            root_run_id=root_run.id,
            trace_id=matrix.context.trace_id,
            budget_ref=child.budget_ref,
            depth=1,
        ),
        budget=child,
        harness=harness,
        session=fixture.business_session,
    )
    provider = KnowledgeProvider(
        scenario, query, matrix.file_row.id, matrix.evidence_id
    )
    worker = KnowledgeWorker(
        provider=cast(AgentDecisionProvider, provider),
        resolver=CapabilityResolver(
            create_m2_capability_catalog(), create_m2_agent_definitions()
        ),
        executor_factory=SqlAlchemyKnowledgeCapabilityExecutorFactory(
            settings=fixture.settings,
            storage=matrix.storage,
            embedding_provider=embedding,
            reranker_provider=FakeRerankerProvider(),
        ),
    )
    handoff = AgentHandoff(
        handoff_id=uuid4(),
        task_id="knowledge_task",
        goal="读取获权知识",
        target_worker="knowledge",
        public_context=BoundedJsonObject(
            {"knowledge_query": query, "file_id": str(matrix.file_row.id)}
        ),
        evidence_ids=[matrix.evidence_id] if scenario == "detail" else [],
        artifact_ids=[matrix.file_row.id] if scenario == "file" else [],
        constraints=["只读且必须经过Harness"],
        expected_output="返回获权知识、Evidence或Artifact",
        completion_criteria=["返回结果或明确无证据"],
        allocated_budget_ref=child.budget_ref,
    )
    result = await worker.run(handoff, execution)
    child.close()
    fixture.recorder.finish_run(
        root_run,
        "completed" if result.execution_status == "completed" else "failed",
    )
    return result, root_run.id


async def _run_committed_search(
    fixture: RetrievalScopeFixture,
    *,
    user_label: str,
    query: str,
    storage_root: Path,
) -> tuple[WorkerResult, UUID]:
    settings = Settings(_env_file=".env.example", app_env="test")  # type: ignore[call-arg]
    user = fixture.users[user_label]
    thread_id = uuid4()
    fixture.session.add(
        Thread(
            id=thread_id,
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            title="M2-21.7 Knowledge Worker Search",
        )
    )
    fixture.session.commit()
    context = build_run_context(user, thread_id, trace_id=uuid4())
    recorder = TraceRecorder(fixture.runtime.session_factory)
    root_run = recorder.start_run(context, "knowledge_query")
    budget_tree = AgentBudgetTree(
        root_run_id=root_run.id,
        limits=AgentBudgetLimits(
            max_model_calls=8,
            max_tool_calls=4,
            max_input_tokens=2_000,
            max_output_tokens=1_000,
            max_tasks=2,
            max_evidence=12,
            max_delegations=2,
            max_depth=1,
            total_timeout_ms=30_000,
        ),
    )
    registry = create_m2_tool_registry()
    provider = KnowledgeProvider(
        "search",
        query,
        uuid4(),
        uuid4(),
    )
    worker = KnowledgeWorker(
        provider=cast(AgentDecisionProvider, provider),
        resolver=CapabilityResolver(
            create_m2_capability_catalog(), create_m2_agent_definitions()
        ),
        executor_factory=SqlAlchemyKnowledgeCapabilityExecutorFactory(
            settings=settings,
            storage=LocalStorageBackend(storage_root),
            embedding_provider=FixedQueryEmbeddingProvider(),
            reranker_provider=FakeRerankerProvider(),
        ),
    )
    runtime = WorkerRuntime(
        trusted_context=context,
        parent_run=root_run,
        budget_tree=budget_tree,
        child_budget_limits=WorkerBudgetLimits(
            max_model_calls=5,
            max_tool_calls=3,
            max_repeat_tool_calls=1,
            max_input_tokens=1_000,
            max_output_tokens=500,
            max_evidence=8,
            timeout_ms=15_000,
        ),
        dispatcher=WorkerDispatcher((worker,)),
        harness_factory=WorkerHarnessAdapter(
            registry=registry,
            permission_guard=PermissionGuard(registry),
            trace_recorder=recorder,
        ),
        session_factory=fixture.runtime.session_factory,
        trace_recorder=InMemoryWorkerTraceRecorder(),
        termination=WorkerTerminationManager(
            TerminationPolicy(max_repeat_handoffs=1, max_no_progress_results=1)
        ),
    )
    result = await runtime.invoke(
        HandoffDraft(
            task_id="knowledge_task",
            goal="检索获权知识",
            target_worker="knowledge",
            public_context=BoundedJsonObject({"knowledge_query": query}),
            constraints=["只读且必须经过Harness"],
            expected_output="返回文档Evidence或明确无证据",
            completion_criteria=("返回当前获权且active的知识",),
        )
    )
    recorder.finish_run(
        root_run,
        "completed" if result.execution_status == "completed" else "failed",
    )
    return result, root_run.id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scenario", "expected_tool"),
    (
        ("file", "read_uploaded_file"),
        ("detail", "get_evidence_detail"),
    ),
)
async def test_knowledge_worker_runs_each_real_m2_tool_through_postgres_and_storage(
    agent_tool_fixture: AgentToolFixture,
    tmp_path: Path,
    scenario: str,
    expected_tool: str,
) -> None:
    matrix = M2FileEvidenceToolMatrix.create(
        agent_tool_fixture,
        tmp_path / "storage",
        role="amazon_operator",
        access_mode="owner",
    )
    result, run_id = await _run_knowledge(
        matrix, cast(Literal["search", "file", "detail"], scenario)
    )

    assert result.execution_status == "completed", result.model_dump(mode="json")
    assert result.business_outcome == "answered", (
        result.observations[0].status,
        result.observations[0].safe_error,
        result.observations[0].structured_result,
    )
    assert [call.tool_name for call in matrix.calls(run_id)] == [expected_tool]
    if scenario == "file":
        assert result.artifact_ids == [matrix.file_row.id]
    else:
        assert result.evidence_ids == [matrix.evidence_id]
        assert result.artifact_ids == [matrix.file_row.id]


@pytest.mark.asyncio
async def test_knowledge_worker_searches_real_pgvector_and_excludes_old_active_version(
    committed_retrieval_scope: RetrievalScopeFixture,
    tmp_path: Path,
) -> None:
    fixture = committed_retrieval_scope

    result, _ = await _run_committed_search(
        fixture,
        user_label="reader",
        query="owner候选内容",
        storage_root=tmp_path / "storage",
    )

    assert result.execution_status == "completed", result.model_dump(mode="json")
    assert result.business_outcome == "answered"
    assert result.evidence_ids
    assert result.business_result is not None
    search = cast(dict[str, object], result.business_result.root["knowledge_search"])
    segments = cast(list[dict[str, object]], search["segments"])
    old_chunk_id = str(fixture.expected["old_version"])
    assert all(old_chunk_id not in json.dumps(item) for item in segments)


@pytest.mark.asyncio
async def test_knowledge_worker_returns_successful_no_evidence_with_no_active_sources(
    committed_retrieval_scope: RetrievalScopeFixture,
    tmp_path: Path,
) -> None:
    fixture = committed_retrieval_scope
    other_tenant_id = fixture.users["other_tenant"].tenant_id
    for document in fixture.session.query(Document).filter(
        Document.tenant_id == other_tenant_id
    ):
        document.active_version_id = None
    fixture.session.commit()

    result, _ = await _run_committed_search(
        fixture,
        user_label="other_tenant",
        query="不存在的合成知识",
        storage_root=tmp_path / "storage",
    )

    assert result.execution_status == "completed"
    assert result.business_outcome == "no_evidence"
    assert result.evidence_ids == []
    assert result.observations[0].status == "success", result.observations[0].safe_error


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_state", ("acl_revoked", "file_deleted"))
async def test_knowledge_worker_rechecks_acl_and_soft_delete_without_leaking_storage(
    agent_tool_fixture: AgentToolFixture,
    tmp_path: Path,
    invalid_state: str,
) -> None:
    matrix = M2FileEvidenceToolMatrix.create(
        agent_tool_fixture,
        tmp_path / "storage",
        role="amazon_operator",
        access_mode="user",
    )
    matrix.mutate(cast(Literal["acl_revoked", "file_deleted"], invalid_state))

    result, _ = await _run_knowledge(matrix, "file")

    assert result.execution_status == "completed"
    assert result.business_outcome == "no_evidence"
    assert result.evidence_ids == []
    assert result.artifact_ids == []
    dumped = result.model_dump_json().casefold()
    assert matrix.parsed_storage_key.casefold() not in dumped
    assert "storage_key" not in dumped


@dataclass
class L2Provider:
    fail_knowledge: bool = False

    async def create_plan(self, request: PlannerRequest) -> TaskPlan:
        return TaskPlan(
            plan_id=uuid4(),
            goal=request.goal,
            tasks=[
                AgentTask(
                    task_id="inventory",
                    goal="查询德国法兰克福仓库存",
                    required_capabilities=["search_inventory"],
                    assignment=TaskAssignment(
                        status="assigned", worker_id="business_data"
                    ),
                    completion_criteria=["返回库存事实和Evidence"],
                    evidence_requirement=EvidenceRequirement(
                        required=True,
                        minimum_count=1,
                        source_types=["database"],
                    ),
                    failure_impact="blocks_dependents",
                ),
                AgentTask(
                    task_id="manual",
                    goal="读取手册清洁要求",
                    depends_on=["inventory"],
                    required_capabilities=["read_uploaded_file"],
                    assignment=TaskAssignment(status="assigned", worker_id="knowledge"),
                    completion_criteria=["返回获权文件内容或明确失败"],
                    evidence_requirement=EvidenceRequirement(
                        required=False,
                        minimum_count=0,
                        source_types=["artifact"],
                    ),
                    failure_impact="allows_partial",
                ),
            ],
        )

    async def choose_action(self, request: DecisionRequest) -> AgentDecision:
        worker_id = request.available_capabilities.requesting_agent_id
        if worker_id is None:
            task = next(
                item
                for item in request.plan.tasks
                if item.task_id == request.active_task_id
            )
            assert task.assignment.worker_id is not None
            return AgentDecision(
                action=DelegateTaskAction(
                    task_id=task.task_id,
                    target_worker=task.assignment.worker_id,
                )
            )
        if not request.observations:
            if worker_id == "business_data":
                return _execute(
                    "search_inventory",
                    {
                        "sku": "LR-TL-MUSH-OR01",
                        "market_code": "DE",
                        "warehouse_code": "DE-FRA",
                    },
                )
            return _execute(
                "read_uploaded_file",
                {
                    "file_id": request.public_context.root["file_id"],
                    "locator": {"source_type": "pdf", "page_start": 1},
                },
            )
        if worker_id == "knowledge" and self.fail_knowledge:
            return AgentDecision(
                action=CannotCompleteAction(
                    public_summary="Knowledge Worker读取失败。",
                    business_outcome="system_error",
                )
            )
        return AgentDecision(
            action=FinishAction(
                public_summary=f"{worker_id}已完成。",
                business_outcome="answered",
                evidence_ids=_observation_evidence(request),
                artifact_ids=_observation_artifacts(request),
            )
        )

    async def prepare_handoff(self, request: HandoffRequest) -> HandoffDraft:
        task = request.delegated_task
        assert task.assignment.worker_id is not None
        return HandoffDraft(
            task_id=task.task_id,
            goal=task.goal,
            target_worker=task.assignment.worker_id,
            public_context=request.public_context,
            constraints=("只读且必须经过Harness",),
            expected_output="返回获权事实或明确失败",
            completion_criteria=tuple(task.completion_criteria),
        )

    async def compose_answer(self, request: AnswerRequest) -> AgentAnswer:
        partial = any(
            item.execution_status == "failed" for item in request.worker_results
        )
        evidence_ids = list(
            dict.fromkeys(
                evidence_id
                for result in request.worker_results
                for evidence_id in result.evidence_ids
            )
        )
        citation_suffix = " ".join(
            f"[E{index}]" for index in range(1, len(evidence_ids) + 1)
        )
        return AgentAnswer(
            action=FinishAction(
                public_summary=(
                    f"已返回库存事实，文件读取失败 {citation_suffix}。"
                    if partial
                    else f"已合并库存事实和手册内容 {citation_suffix}。"
                ),
                business_outcome="partial" if partial else "answered",
                evidence_ids=evidence_ids,
                artifact_ids=list(
                    dict.fromkeys(
                        artifact_id
                        for result in request.worker_results
                        for artifact_id in result.artifact_ids
                    )
                ),
            )
        )


@dataclass
class InlineRealWorkerInvoker:
    """Test seam that keeps real Workers on the fixture's rollback-only Session."""

    dispatcher: WorkerDispatcher
    matrix: M2FileEvidenceToolMatrix
    root_run_id: UUID
    budget_tree: AgentBudgetTree
    harness_factory: WorkerHarnessAdapter
    root_run: object
    received: list[str] = field(default_factory=list)

    async def invoke(self, draft: HandoffDraft) -> WorkerResult:
        from app.runtime.trace import RunTrace

        assert isinstance(self.root_run, RunTrace)
        worker = self.dispatcher.resolve(draft.target_worker)
        child_run_id = uuid4()
        child = self.budget_tree.allocate_child(
            parent_run_id=self.root_run_id,
            child_run_id=child_run_id,
            task_id=draft.task_id,
            limits=WorkerBudgetLimits(
                max_model_calls=5,
                max_tool_calls=3,
                max_repeat_tool_calls=1,
                max_input_tokens=1_000,
                max_output_tokens=500,
                max_evidence=4,
                timeout_ms=15_000,
            ),
        )
        handoff = AgentHandoff(
            handoff_id=uuid4(),
            task_id=draft.task_id,
            goal=draft.goal,
            target_worker=draft.target_worker,
            public_context=draft.public_context,
            evidence_ids=list(draft.evidence_ids),
            artifact_ids=list(draft.artifact_ids),
            constraints=list(draft.constraints),
            expected_output=draft.expected_output,
            completion_criteria=list(draft.completion_criteria),
            allocated_budget_ref=child.budget_ref,
        )
        execution = WorkerExecutionContext(
            trusted_context=self.matrix.context,
            worker_run=WorkerRunTrace(
                run_id=child_run_id,
                parent_run_id=self.root_run_id,
                root_run_id=self.root_run_id,
                trace_id=self.matrix.context.trace_id,
                budget_ref=child.budget_ref,
                depth=1,
            ),
            budget=child,
            harness=self.harness_factory.create(
                self.matrix.context, self.root_run, child
            ),
            session=self.matrix.fixture.business_session,
        )
        self.received.append(draft.task_id)
        result = await worker.run(handoff, execution)
        child.record_evidence(result.evidence_ids)
        usage = child.usage()
        child.close()
        return result.model_copy(
            update={
                "resource_usage": ResourceUsage(
                    model_calls=usage.model_calls,
                    tool_calls=usage.tool_calls,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    duration_ms=usage.duration_ms,
                )
            }
        )


def _worker_profiles(
    resolver: CapabilityResolver,
    matrix: M2FileEvidenceToolMatrix,
) -> tuple[WorkerCapabilityProfile, ...]:
    workers = resolver.resolve_delegation_targets(
        matrix.context, CapabilitySelection()
    ).capabilities
    return tuple(
        WorkerCapabilityProfile(
            worker=worker,
            capabilities=resolver.resolve_for_agent(
                matrix.context, worker.capability_id, CapabilitySelection()
            ),
        )
        for worker in workers
    )


async def _run_l2(
    matrix: M2FileEvidenceToolMatrix,
    *,
    fail_knowledge: bool,
) -> tuple[EngineeredAgentState, InlineRealWorkerInvoker, UUID]:
    fixture = matrix.fixture
    provider = L2Provider(fail_knowledge=fail_knowledge)
    resolver = CapabilityResolver(
        create_m2_capability_catalog(), create_m2_agent_definitions()
    )
    embedding = FixedQueryEmbeddingProvider()
    _prepare_search_identity(matrix, embedding)
    root_run = fixture.recorder.start_run(matrix.context, "knowledge_query")
    budget = AgentBudgetTree(
        root_run_id=root_run.id,
        limits=AgentBudgetLimits(
            max_model_calls=20,
            max_tool_calls=6,
            max_input_tokens=5_000,
            max_output_tokens=2_000,
            max_tasks=3,
            max_evidence=12,
            max_delegations=3,
            max_depth=1,
            total_timeout_ms=30_000,
        ),
    )
    registry = create_m2_tool_registry()
    business_worker = BusinessDataWorker(
        provider=cast(AgentDecisionProvider, provider),
        resolver=resolver,
        executor_factory=SqlAlchemyBusinessCapabilityExecutorFactory(
            statement_timeout_ms=fixture.settings.database_statement_timeout_ms
        ),
    )
    knowledge_worker = KnowledgeWorker(
        provider=cast(AgentDecisionProvider, provider),
        resolver=resolver,
        executor_factory=SqlAlchemyKnowledgeCapabilityExecutorFactory(
            settings=fixture.settings,
            storage=matrix.storage,
            embedding_provider=embedding,
            reranker_provider=FakeRerankerProvider(),
        ),
    )
    invoker = InlineRealWorkerInvoker(
        dispatcher=WorkerDispatcher((business_worker, knowledge_worker)),
        matrix=matrix,
        root_run_id=root_run.id,
        budget_tree=budget,
        harness_factory=WorkerHarnessAdapter(
            registry=registry,
            permission_guard=PermissionGuard(registry),
            trace_recorder=fixture.recorder,
        ),
        root_run=root_run,
    )
    result = await SupervisorAgent(
        provider=BudgetedAgentProvider(
            provider=cast(EngineeredAgentProvider, provider), budget=budget
        ),
        worker=invoker,
    ).run(
        SupervisorRequest(
            run_id=root_run.id,
            goal="查询库存并结合手册清洁要求",
            public_context=BoundedJsonObject(
                {
                    "sku": "LR-TL-MUSH-OR01",
                    "market_code": "DE",
                    "warehouse_code": "DE-FRA",
                    "file_id": str(matrix.file_row.id),
                }
            ),
            available_workers=_worker_profiles(resolver, matrix),
        )
    )
    fixture.recorder.finish_run(
        root_run,
        "completed" if result.execution_status == "completed" else "failed",
    )
    return result, invoker, root_run.id


@pytest.mark.asyncio
async def test_real_workers_run_sequential_l2_and_merge_references_stably(
    agent_tool_fixture: AgentToolFixture,
    tmp_path: Path,
) -> None:
    matrix = M2FileEvidenceToolMatrix.create(
        agent_tool_fixture,
        tmp_path / "storage",
        role="amazon_operator",
        access_mode="owner",
    )

    result, invoker, run_id = await _run_l2(matrix, fail_knowledge=False)

    assert result.execution_status == "completed", (
        result.stop_reason,
        invoker.received,
        [item.model_dump(mode="json") for item in result.worker_results],
    )
    assert result.business_outcome == "answered"
    assert invoker.received == ["inventory", "manual"]
    assert [item.worker_id for item in result.worker_results] == [
        "business_data",
        "knowledge",
    ]
    assert len(result.evidence_ids) == 1
    assert result.artifact_ids == [matrix.file_row.id]
    assert [call.tool_name for call in matrix.calls(run_id)] == [
        "search_inventory",
        "read_uploaded_file",
    ]


@pytest.mark.asyncio
async def test_real_knowledge_failure_keeps_business_result_as_partial(
    agent_tool_fixture: AgentToolFixture,
    tmp_path: Path,
) -> None:
    matrix = M2FileEvidenceToolMatrix.create(
        agent_tool_fixture,
        tmp_path / "storage",
        role="amazon_operator",
        access_mode="owner",
    )
    matrix.remove_parsed_artifact()

    result, invoker, run_id = await _run_l2(matrix, fail_knowledge=True)

    assert result.execution_status == "completed", (
        result.stop_reason,
        invoker.received,
        [item.model_dump(mode="json") for item in result.worker_results],
    )
    assert result.business_outcome == "partial"
    assert invoker.received == ["inventory", "manual"]
    assert [item.execution_status for item in result.worker_results] == [
        "completed",
        "failed",
    ]
    assert len(result.evidence_ids) == 1
    assert result.artifact_ids == []
    calls = matrix.calls(run_id)
    assert [(call.tool_name, call.status) for call in calls] == [
        ("search_inventory", "success"),
        ("read_uploaded_file", "error"),
    ]
    assert all(isinstance(call, ToolCall) for call in calls)
