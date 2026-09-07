from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, cast
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import delete, select

from app.agents.definitions import create_m2_agent_definitions
from app.agents.engineered_state import EngineeredAgentState
from app.agents.runtime import (
    BudgetedAgentProvider,
    InMemoryWorkerTraceRecorder,
    TerminationPolicy,
    WorkerDispatcher,
    WorkerHarnessAdapter,
    WorkerRuntime,
    WorkerTerminationManager,
)
from app.agents.supervisor import SupervisorAgent, SupervisorRequest
from app.agents.workers import (
    BusinessDataWorker,
    SqlAlchemyBusinessCapabilityExecutorFactory,
)
from app.capabilities.catalog import create_m2_capability_catalog
from app.capabilities.contracts import CapabilitySelection
from app.capabilities.resolver import CapabilityResolver
from app.core.config import Settings
from app.db.session import DatabaseRuntime, create_database_runtime
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
from app.models.runtime import AgentRun, Evidence, Thread, ToolCall
from app.repositories.identity import IdentityRepository
from app.runtime.budget import AgentBudgetLimits, AgentBudgetTree, WorkerBudgetLimits
from app.runtime.context import RunContext, build_run_context
from app.runtime.permissions import PermissionGuard
from app.runtime.trace import RunTrace, TraceRecorder
from app.schemas.agent import (
    AgentDecision,
    AgentTask,
    BoundedJsonObject,
    CannotCompleteAction,
    DelegateTaskAction,
    EvidenceRequirement,
    ExecuteCapabilityAction,
    FinishAction,
    TaskAssignment,
    TaskPlan,
)
from app.schemas.auth import LoginRequest
from app.services.auth import AuthService
from app.tools.registry import create_m2_tool_registry
from scripts.seed_m1 import seed_m1

Scenario = Literal["product", "inventory", "combined", "denied"]


@dataclass(frozen=True, slots=True)
class BusinessWorkerFixture:
    settings: Settings
    runtime: DatabaseRuntime
    context: RunContext
    recorder: TraceRecorder
    thread_id: UUID


@pytest.fixture
def business_worker_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Generator[BusinessWorkerFixture, None, None]:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=".env.example",
        app_env="test",
    )
    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    seed_m1(settings, manifest_path=tmp_path / "m1_manifest.json")
    runtime = create_database_runtime(settings)

    with runtime.session_factory() as auth_session:
        auth = AuthService(
            IdentityRepository(
                auth_session,
                settings.database_statement_timeout_ms,
            ),
            settings,
        )
        login = auth.login(
            LoginRequest(
                email="de.operator@demo.deepsearch.local",
                password=SecretStr("M1-demo-only-change-me"),
            )
        )
        user = auth.resolve_access_token(login.access_token)
        auth_session.rollback()

    thread_id = uuid4()
    with runtime.session_factory.begin() as session:
        session.add(
            Thread(
                id=thread_id,
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                title="M2-21.6 Business Worker Test",
            )
        )
    try:
        yield BusinessWorkerFixture(
            settings=settings,
            runtime=runtime,
            context=build_run_context(user, thread_id, trace_id=uuid4()),
            recorder=TraceRecorder(runtime.session_factory),
            thread_id=thread_id,
        )
    finally:
        with runtime.session_factory.begin() as session:
            session.execute(delete(Thread).where(Thread.id == thread_id))
        runtime.engine.dispose()


class BusinessL1Provider:
    """Deterministic test Provider; it exercises contracts, not language quality."""

    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario

    async def create_plan(self, request: PlannerRequest) -> TaskPlan:
        capabilities = {
            "product": ["get_product_spec"],
            "inventory": ["search_inventory"],
            "combined": ["get_product_spec", "search_inventory"],
            "denied": ["search_inventory"],
        }[self.scenario]
        evidence_required = self.scenario != "product"
        return TaskPlan(
            plan_id=uuid4(),
            goal=request.goal,
            tasks=[
                AgentTask(
                    task_id="business_query",
                    goal=request.goal,
                    required_capabilities=capabilities,
                    assignment=TaskAssignment(
                        status="assigned",
                        worker_id="business_data",
                    ),
                    completion_criteria=["返回获权业务事实或明确失败"],
                    evidence_requirement=EvidenceRequirement(
                        required=evidence_required,
                        minimum_count=1 if evidence_required else 0,
                        source_types=["database"],
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
                    target_worker="business_data",
                )
            )

        if not request.observations:
            if self.scenario in {"inventory", "denied"}:
                if self.scenario == "denied":
                    return AgentDecision(
                        action=ExecuteCapabilityAction(
                            capability_id="search_inventory",
                            arguments=BoundedJsonObject(
                                {
                                    "sku": "LR-TL-MUSH-OR01",
                                    "market_code": "FR",
                                    "warehouse_code": "FR-CDG",
                                }
                            ),
                        )
                    )
                return _inventory_action("LR-TL-MUSH-OR01")
            return AgentDecision(
                action=ExecuteCapabilityAction(
                    capability_id="get_product_spec",
                    arguments=BoundedJsonObject({"product_query": "蘑菇灯"}),
                )
            )
        if self.scenario == "combined" and len(request.observations) == 1:
            result = request.observations[0].structured_result
            assert result is not None
            data = cast(dict[str, object], result.root["data"])
            return _inventory_action(cast(str, data["sku"]))

        if self.scenario == "denied":
            return AgentDecision(
                action=CannotCompleteAction(
                    public_summary="当前身份无权访问法国市场数据。",
                    business_outcome="denied",
                )
            )
        evidence_ids = [
            evidence_id
            for observation in request.observations
            for evidence_id in observation.evidence_ids
        ]
        return AgentDecision(
            action=FinishAction(
                public_summary="Business Worker已完成获权查询。",
                business_outcome="answered",
                evidence_ids=evidence_ids,
            )
        )

    async def prepare_handoff(self, request: HandoffRequest) -> HandoffDraft:
        task = request.delegated_task
        return HandoffDraft(
            task_id=task.task_id,
            goal=task.goal,
            target_worker="business_data",
            public_context=request.public_context,
            constraints=("只读且必须经过Harness",),
            expected_output="返回规格或库存事实及可用Evidence",
            completion_criteria=tuple(task.completion_criteria),
        )

    async def compose_answer(self, request: AnswerRequest) -> AgentAnswer:
        if request.worker_results[0].business_outcome == "denied":
            return AgentAnswer(
                action=CannotCompleteAction(
                    public_summary="当前身份无权访问法国市场数据。",
                    business_outcome="denied",
                )
            )
        evidence_ids = [
            evidence_id
            for result in request.worker_results
            for evidence_id in result.evidence_ids
        ]
        return AgentAnswer(
            action=FinishAction(
                public_summary=(
                    "已根据Business Worker结果完成回答 [E1]。"
                    if evidence_ids
                    else "已根据Business Worker结果完成回答。"
                ),
                business_outcome="answered",
                evidence_ids=evidence_ids,
            )
        )


def _inventory_action(sku: str) -> AgentDecision:
    return AgentDecision(
        action=ExecuteCapabilityAction(
            capability_id="search_inventory",
            arguments=BoundedJsonObject(
                {
                    "sku": sku,
                    "market_code": "DE",
                    "warehouse_code": "DE-FRA",
                }
            ),
        )
    )


def _public_context(scenario: Scenario) -> BoundedJsonObject:
    if scenario == "product":
        return BoundedJsonObject({"product_query": "蘑菇灯"})
    if scenario == "inventory":
        return BoundedJsonObject(
            {
                "sku": "LR-TL-MUSH-OR01",
                "market_code": "DE",
                "warehouse_code": "DE-FRA",
            }
        )
    if scenario == "denied":
        return BoundedJsonObject(
            {
                "sku": "LR-TL-MUSH-OR01",
                "market_code": "FR",
                "warehouse_code": "FR-CDG",
            }
        )
    return BoundedJsonObject(
        {
            "product_query": "蘑菇灯",
            "market_code": "DE",
            "warehouse_code": "DE-FRA",
        }
    )


def _worker_profile(
    resolver: CapabilityResolver,
    context: RunContext,
) -> WorkerCapabilityProfile:
    workers = resolver.resolve_delegation_targets(context, CapabilitySelection())
    return WorkerCapabilityProfile(
        worker=workers.capabilities[0],
        capabilities=resolver.resolve_for_agent(
            context,
            "business_data",
            CapabilitySelection(),
        ),
    )


async def _run_scenario(
    fixture: BusinessWorkerFixture,
    scenario: Scenario,
) -> tuple[EngineeredAgentState, RunTrace, AgentBudgetTree]:
    context = replace(fixture.context, trace_id=uuid4())
    root_run = fixture.recorder.start_run(context, "inventory_query")
    budget = AgentBudgetTree(
        root_run_id=root_run.id,
        limits=AgentBudgetLimits(
            max_model_calls=12,
            max_tool_calls=4,
            max_input_tokens=4_000,
            max_output_tokens=2_000,
            max_tasks=2,
            max_evidence=4,
            max_delegations=2,
            max_depth=1,
            total_timeout_ms=30_000,
        ),
    )
    resolver = CapabilityResolver(
        create_m2_capability_catalog(),
        create_m2_agent_definitions(),
    )
    raw_provider = BusinessL1Provider(scenario)
    registry = create_m2_tool_registry()
    business_worker = BusinessDataWorker(
        provider=cast(AgentDecisionProvider, raw_provider),
        resolver=resolver,
        executor_factory=SqlAlchemyBusinessCapabilityExecutorFactory(
            statement_timeout_ms=fixture.settings.database_statement_timeout_ms,
        ),
    )
    runtime = WorkerRuntime(
        trusted_context=context,
        parent_run=root_run,
        budget_tree=budget,
        child_budget_limits=WorkerBudgetLimits(
            max_model_calls=4,
            max_tool_calls=2,
            max_repeat_tool_calls=1,
            max_input_tokens=1_000,
            max_output_tokens=500,
            max_evidence=2,
            timeout_ms=15_000,
        ),
        dispatcher=WorkerDispatcher((business_worker,)),
        harness_factory=WorkerHarnessAdapter(
            registry=registry,
            permission_guard=PermissionGuard(registry),
            trace_recorder=fixture.recorder,
        ),
        session_factory=fixture.runtime.session_factory,
        trace_recorder=InMemoryWorkerTraceRecorder(),
        termination=WorkerTerminationManager(
            TerminationPolicy(max_repeat_handoffs=1, max_no_progress_results=1)
        ),
    )
    provider = BudgetedAgentProvider(
        provider=cast(EngineeredAgentProvider, raw_provider),
        budget=budget,
    )
    result = await SupervisorAgent(provider=provider, worker=runtime).run(
        SupervisorRequest(
            run_id=root_run.id,
            goal={
                "product": "查询蘑菇灯规格",
                "inventory": "查询LR-TL-MUSH-OR01在德国法兰克福仓的库存",
                "combined": "查询蘑菇灯规格和德国法兰克福仓库存",
                "denied": "查询LR-TL-MUSH-OR01在法国巴黎仓的库存",
            }[scenario],
            public_context=_public_context(scenario),
            available_workers=(_worker_profile(resolver, context),),
        )
    )
    fixture.recorder.finish_run(
        root_run,
        "denied" if result.business_outcome == "denied" else "completed",
    )
    return result, root_run, budget


@pytest.mark.asyncio
async def test_supervisor_business_worker_real_postgres_l1_matrix(
    business_worker_fixture: BusinessWorkerFixture,
) -> None:
    fixture = business_worker_fixture
    expected_tools = {
        "product": ["get_product_spec"],
        "inventory": ["search_inventory"],
        "combined": ["get_product_spec", "search_inventory"],
        "denied": ["search_inventory"],
    }

    for scenario in cast(
        tuple[Scenario, ...],
        ("product", "inventory", "combined", "denied"),
    ):
        result, run, budget = await _run_scenario(fixture, scenario)
        assert result.execution_status == "completed", (
            scenario,
            result.stop_reason,
            [item.model_dump(mode="json") for item in result.worker_results],
        )
        expected_outcome = "denied" if scenario == "denied" else "answered"
        assert result.business_outcome == expected_outcome
        assert len(result.worker_results) == 1
        assert result.worker_results[0].resource_usage.tool_calls == len(
            expected_tools[scenario]
        )
        with fixture.runtime.session_factory() as session:
            calls = list(
                session.scalars(
                    select(ToolCall)
                    .where(ToolCall.agent_run_id == run.id)
                    .order_by(ToolCall.sequence_no)
                )
            )
            assert [call.tool_name for call in calls] == expected_tools[scenario]
            if scenario == "denied":
                assert [
                    (call.permission_result, call.status, call.error_code)
                    for call in calls
                ] == [("denied", "denied", "FORBIDDEN")]
                assert result.worker_results[0].safe_errors[0].code == "FORBIDDEN"
            else:
                assert all(
                    call.permission_result == "allowed" and call.status == "success"
                    for call in calls
                )
            evidence = list(
                session.scalars(select(Evidence).where(Evidence.agent_run_id == run.id))
            )
            assert len(evidence) == (1 if scenario in {"inventory", "combined"} else 0)
            if evidence:
                assert evidence[0].tool_call_id == calls[-1].id
                assert evidence[0].structured_data is not None
                assert evidence[0].structured_data["available"] == 125
            stored_run = session.get(AgentRun, run.id)
            assert stored_run is not None
            assert stored_run.status == (
                "denied" if scenario == "denied" else "completed"
            )
            assert stored_run.tool_call_count == len(expected_tools[scenario])

        snapshot = budget.snapshot()
        assert snapshot.tool_calls == len(expected_tools[scenario])
        assert snapshot.model_calls == (7 if scenario == "combined" else 6)
        assert snapshot.evidence_count == (
            1 if scenario in {"inventory", "combined"} else 0
        )
        assert snapshot.open_children == 0
