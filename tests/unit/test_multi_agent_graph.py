from __future__ import annotations

import ast
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

from app.agents.engineered_state import EngineeredAgentState
from app.agents.graphs.engineered_multi_agent import build_engineered_multi_agent_graph
from app.agents.supervisor import (
    SupervisorAgent,
    SupervisorGuardrails,
    SupervisorRequest,
    WorkerInvoker,
)
from app.capabilities.contracts import (
    CapabilityKind,
    CapabilityParameterSchema,
    CapabilityResolution,
    ResolvedCapability,
)
from app.llm.agent_mock import AgentMockScript, DeterministicAgentMock
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
from app.schemas.agent import (
    AgentDecision,
    AgentTask,
    AskUserAction,
    BoundedJsonObject,
    CannotCompleteAction,
    DelegateTaskAction,
    EvidenceRequirement,
    FinishAction,
    ResourceUsage,
    TaskAssignment,
    TaskPlan,
    WorkerObservation,
    WorkerResult,
)

PROJECT_ROOT = Path(__file__).parents[2]
RUN_ID = UUID("00000000-0000-0000-0000-000000000401")
PLAN_ID = UUID("00000000-0000-0000-0000-000000000402")
BUSINESS_EVIDENCE_ID = UUID("00000000-0000-0000-0000-000000000403")
KNOWLEDGE_EVIDENCE_ID = UUID("00000000-0000-0000-0000-000000000404")
BUSINESS_OBSERVATION_ID = UUID("00000000-0000-0000-0000-000000000405")
KNOWLEDGE_OBSERVATION_ID = UUID("00000000-0000-0000-0000-000000000406")


def zero_usage() -> ResourceUsage:
    return ResourceUsage(
        model_calls=0,
        tool_calls=0,
        input_tokens=0,
        output_tokens=0,
        duration_ms=0,
    )


def capability(capability_id: str, *, kind: CapabilityKind) -> ResolvedCapability:
    parameters = None
    if kind == "tool":
        parameters = CapabilityParameterSchema(
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"query": {"type": "string", "maxLength": 200}},
            }
        )
    return ResolvedCapability(  # type: ignore[arg-type]
        capability_id=capability_id,
        kind=kind,
        version="1.0.0",
        description=f"安全能力 {capability_id}",
        parameters=parameters,
        side_effect="read" if kind == "tool" else "none",
        produces_evidence=kind == "tool",
        implementation_status="available",
    )


def worker_profile(worker_id: str, tool_id: str) -> WorkerCapabilityProfile:
    return WorkerCapabilityProfile(
        worker=capability(worker_id, kind="agent"),
        capabilities=CapabilityResolution(
            requesting_agent_id=worker_id,  # type: ignore[arg-type]
            capabilities=[capability(tool_id, kind="tool")],
        ),
    )


def request(
    goal: str, *, workers: tuple[WorkerCapabilityProfile, ...]
) -> SupervisorRequest:
    return SupervisorRequest(
        run_id=RUN_ID,
        goal=goal,
        public_context=BoundedJsonObject({"locale": "zh-CN", "market": "DE"}),
        available_workers=workers,
    )


def task(
    task_id: str,
    goal: str,
    *,
    worker_id: str | None,
    capability_id: str | None,
    depends_on: list[str] | None = None,
) -> AgentTask:
    return AgentTask(
        task_id=task_id,
        goal=goal,
        depends_on=depends_on or [],
        required_capabilities=[] if capability_id is None else [capability_id],
        assignment=TaskAssignment(
            status="unassigned" if worker_id is None else "assigned",
            worker_id=worker_id,  # type: ignore[arg-type]
        ),
        completion_criteria=["返回公开安全结果或明确说明无法完成"],
        evidence_requirement=EvidenceRequirement(
            required=capability_id is not None,
            minimum_count=1 if capability_id is not None else 0,
            source_types=[] if capability_id is None else ["database"],
        ),
        failure_impact="blocks_dependents",
    )


def direct_plan(goal: str) -> TaskPlan:
    return TaskPlan(
        plan_id=PLAN_ID,
        goal=goal,
        tasks=[
            task(
                "direct_answer",
                goal,
                worker_id=None,
                capability_id=None,
            )
        ],
    )


def one_worker_plan(goal: str) -> TaskPlan:
    return TaskPlan(
        plan_id=PLAN_ID,
        goal=goal,
        tasks=[
            task(
                "inventory",
                "查询德国库存",
                worker_id="business_data",
                capability_id="search_inventory",
            )
        ],
    )


def two_worker_plan(goal: str) -> TaskPlan:
    return TaskPlan(
        plan_id=PLAN_ID,
        goal=goal,
        tasks=[
            task(
                "inventory",
                "查询德国库存",
                worker_id="business_data",
                capability_id="search_inventory",
            ),
            task(
                "policy",
                "读取安全库存政策",
                worker_id="knowledge",
                capability_id="search_knowledge",
                depends_on=["inventory"],
            ).model_copy(
                update={
                    "evidence_requirement": EvidenceRequirement(
                        required=True,
                        minimum_count=1,
                        source_types=["document"],
                    )
                }
            ),
        ],
    )


def independent_two_worker_plan(goal: str) -> TaskPlan:
    plan = two_worker_plan(goal)
    policy = plan.tasks[1].model_copy(
        update={"depends_on": [], "failure_impact": "allows_partial"}
    )
    return plan.model_copy(update={"tasks": [plan.tasks[0], policy]})


def observation(
    observation_id: UUID,
    evidence_id: UUID,
    summary: str,
) -> WorkerObservation:
    return WorkerObservation(
        observation_id=observation_id,
        status="success",
        public_summary=summary,
        structured_result=BoundedJsonObject({"fact": summary}),
        evidence_ids=[evidence_id],
        resource_usage=zero_usage(),
    )


def completed_result(
    task_id: str,
    worker_id: str,
    item: WorkerObservation,
) -> WorkerResult:
    return WorkerResult(
        task_id=task_id,
        worker_id=worker_id,
        execution_status="completed",
        business_outcome="answered",
        business_result=BoundedJsonObject({"fact": item.public_summary}),
        public_summary=item.public_summary,
        observations=[item],
        evidence_ids=item.evidence_ids,
        resource_usage=zero_usage(),
    )


def failed_result(task_id: str, worker_id: str) -> WorkerResult:
    return WorkerResult(
        task_id=task_id,
        worker_id=worker_id,
        execution_status="failed",
        business_outcome="system_error",
        public_summary="Knowledge Worker执行失败。",
        safe_errors=[
            {
                "code": "INTERNAL_ERROR",
                "message": "Knowledge Worker执行失败。",
                "retryable": False,
            }
        ],
        resource_usage=zero_usage(),
    )


def handoff_for(task_id: str, goal: str, worker_id: str) -> HandoffDraft:
    return HandoffDraft(
        task_id=task_id,
        goal=goal,
        target_worker=worker_id,
        public_context=BoundedJsonObject({"market": "DE"}),
        expected_output="返回公开安全结果或明确说明无法完成",
        completion_criteria=("返回公开安全结果或明确说明无法完成",),
    )


@dataclass
class ScriptedFakeWorker:
    results: list[WorkerResult | Exception]
    received_handoffs: list[HandoffDraft] = field(default_factory=list)

    async def invoke(self, handoff: HandoffDraft) -> WorkerResult:
        self.received_handoffs.append(handoff.model_copy(deep=True))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result.model_copy(deep=True)


@dataclass
class ConcurrentBarrierWorker:
    """Fail fast unless two independent handoffs overlap at the Worker seam."""

    results: dict[str, WorkerResult]
    started: list[str] = field(default_factory=list)
    both_started: asyncio.Event = field(default_factory=asyncio.Event)

    async def invoke(self, handoff: HandoffDraft) -> WorkerResult:
        self.started.append(handoff.task_id)
        if len(self.started) == 2:
            self.both_started.set()
        await asyncio.wait_for(self.both_started.wait(), timeout=0.2)
        if handoff.task_id == "inventory":
            await asyncio.sleep(0.01)
        return self.results[handoff.task_id].model_copy(deep=True)


@dataclass
class ConcurrencyProbeWorker:
    results: dict[str, WorkerResult]
    active: int = 0
    maximum_active: int = 0

    async def invoke(self, handoff: HandoffDraft) -> WorkerResult:
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        try:
            await asyncio.sleep(0.01)
            return self.results[handoff.task_id].model_copy(deep=True)
        finally:
            self.active -= 1


@dataclass
class BatchFailureWorker:
    successful_result: WorkerResult
    started: set[str] = field(default_factory=set)
    both_started: asyncio.Event = field(default_factory=asyncio.Event)
    completed: set[str] = field(default_factory=set)

    async def invoke(self, handoff: HandoffDraft) -> WorkerResult:
        self.started.add(handoff.task_id)
        if self.started == {"inventory", "policy"}:
            self.both_started.set()
        await self.both_started.wait()
        if handoff.task_id == "inventory":
            raise RuntimeError("private worker failure")
        await asyncio.sleep(0.02)
        self.completed.add(handoff.task_id)
        return self.successful_result.model_copy(deep=True)


class RecordingProvider:
    def __init__(self, script: AgentMockScript) -> None:
        self._mock = DeterministicAgentMock(script)
        self.planner_requests: list[PlannerRequest] = []
        self.decision_requests: list[DecisionRequest] = []
        self.handoff_requests: list[HandoffRequest] = []
        self.answer_requests: list[AnswerRequest] = []

    async def create_plan(self, item: PlannerRequest) -> TaskPlan:
        self.planner_requests.append(item)
        return await self._mock.create_plan(item)

    async def choose_action(self, item: DecisionRequest) -> AgentDecision:
        self.decision_requests.append(item)
        return await self._mock.choose_action(item)

    async def prepare_handoff(self, item: HandoffRequest) -> HandoffDraft:
        self.handoff_requests.append(item)
        return await self._mock.prepare_handoff(item)

    async def compose_answer(self, item: AnswerRequest) -> AgentAnswer:
        self.answer_requests.append(item)
        return await self._mock.compose_answer(item)


@pytest.fixture
def workers() -> tuple[WorkerCapabilityProfile, WorkerCapabilityProfile]:
    return (
        worker_profile("business_data", "search_inventory"),
        worker_profile("knowledge", "search_knowledge"),
    )


@pytest.mark.asyncio
async def test_l0_uses_answer_provider_directly_without_worker(
    workers: tuple[WorkerCapabilityProfile, WorkerCapabilityProfile],
) -> None:
    goal = "解释什么是安全库存"
    provider = RecordingProvider(
        AgentMockScript(
            plans=(direct_plan(goal),),
            answers=(
                AgentAnswer(
                    action=FinishAction(
                        public_summary="安全库存是为需求和供给波动预留的库存。",
                        business_outcome="answered",
                    )
                ),
            ),
        )
    )
    worker = ScriptedFakeWorker([])

    result = await SupervisorAgent(provider=provider, worker=worker).run(
        request(goal, workers=workers)
    )

    assert result.execution_status == "completed"
    assert result.business_outcome == "answered"
    assert result.public_summary == "安全库存是为需求和供给波动预留的库存。"
    assert result.worker_results == []
    assert provider.decision_requests == []
    assert len(provider.answer_requests) == 1
    assert worker.received_handoffs == []


@pytest.mark.asyncio
async def test_l1_handoff_observation_reaches_answer_before_finish(
    workers: tuple[WorkerCapabilityProfile, WorkerCapabilityProfile],
) -> None:
    goal = "查询德国库存"
    item = observation(
        BUSINESS_OBSERVATION_ID,
        BUSINESS_EVIDENCE_ID,
        "德国仓可售库存为125件。",
    )
    provider = RecordingProvider(
        AgentMockScript(
            plans=(one_worker_plan(goal),),
            decisions=(
                AgentDecision(
                    action=DelegateTaskAction(
                        task_id="inventory",
                        target_worker="business_data",
                    )
                ),
            ),
            handoffs=(handoff_for("inventory", "查询德国库存", "business_data"),),
            answers=(
                AgentAnswer(
                    action=FinishAction(
                        public_summary="德国仓可售库存为125件 [E1]。",
                        business_outcome="answered",
                        evidence_ids=[BUSINESS_EVIDENCE_ID],
                    )
                ),
            ),
        )
    )
    worker = ScriptedFakeWorker([completed_result("inventory", "business_data", item)])

    result = await SupervisorAgent(provider=provider, worker=worker).run(
        request(goal, workers=workers)
    )

    assert result.execution_status == "completed"
    assert result.business_outcome == "answered"
    assert result.evidence_ids == [BUSINESS_EVIDENCE_ID]
    assert result.observations == [item]
    assert result.worker_results[0].task_id == "inventory"
    assert len(worker.received_handoffs) == 1
    assert worker.received_handoffs[0].model_fields_set.isdisjoint(
        {"handoff_id", "allocated_budget_ref"}
    )
    assert provider.answer_requests[0].worker_results[0].observations == [item]


@pytest.mark.asyncio
async def test_minimal_l2_runs_dependency_order_and_merges_stable_evidence(
    workers: tuple[WorkerCapabilityProfile, WorkerCapabilityProfile],
) -> None:
    goal = "查询库存并结合政策判断"
    inventory_item = observation(
        BUSINESS_OBSERVATION_ID,
        BUSINESS_EVIDENCE_ID,
        "德国仓可售库存为125件。",
    )
    policy_item = observation(
        KNOWLEDGE_OBSERVATION_ID,
        KNOWLEDGE_EVIDENCE_ID,
        "政策要求安全库存至少60件。",
    )
    provider = RecordingProvider(
        AgentMockScript(
            plans=(two_worker_plan(goal),),
            decisions=(
                AgentDecision(
                    action=DelegateTaskAction(
                        task_id="inventory",
                        target_worker="business_data",
                    )
                ),
                AgentDecision(
                    action=DelegateTaskAction(
                        task_id="policy",
                        target_worker="knowledge",
                    )
                ),
            ),
            handoffs=(
                handoff_for("inventory", "查询德国库存", "business_data"),
                handoff_for("policy", "读取安全库存政策", "knowledge"),
            ),
            answers=(
                AgentAnswer(
                    action=FinishAction(
                        public_summary="可售125件，高于60件安全库存要求。",
                        business_outcome="answered",
                        evidence_ids=[BUSINESS_EVIDENCE_ID, KNOWLEDGE_EVIDENCE_ID],
                    )
                ),
            ),
        )
    )
    worker = ScriptedFakeWorker(
        [
            completed_result("inventory", "business_data", inventory_item),
            completed_result("policy", "knowledge", policy_item),
        ]
    )

    result = await SupervisorAgent(provider=provider, worker=worker).run(
        request(goal, workers=workers)
    )

    assert [item.task_id for item in result.worker_results] == ["inventory", "policy"]
    assert [item.task_id for item in worker.received_handoffs] == [
        "inventory",
        "policy",
    ]
    assert provider.decision_requests[1].active_task_id == "policy"
    assert provider.decision_requests[1].worker_results[0].task_id == "inventory"
    assert result.evidence_ids == [BUSINESS_EVIDENCE_ID, KNOWLEDGE_EVIDENCE_ID]
    assert [item.execution_status for item in cast(TaskPlan, result.plan).tasks] == [
        "completed",
        "completed",
    ]


@pytest.mark.asyncio
async def test_independent_read_only_workers_overlap_and_merge_in_plan_order(
    workers: tuple[WorkerCapabilityProfile, WorkerCapabilityProfile],
) -> None:
    goal = "分别查询库存和安全库存政策"
    inventory_item = observation(
        BUSINESS_OBSERVATION_ID,
        BUSINESS_EVIDENCE_ID,
        "德国仓可售库存为125件。",
    )
    policy_item = observation(
        KNOWLEDGE_OBSERVATION_ID,
        KNOWLEDGE_EVIDENCE_ID,
        "政策要求安全库存至少60件。",
    )
    provider = RecordingProvider(
        AgentMockScript(
            plans=(independent_two_worker_plan(goal),),
            decisions=(
                AgentDecision(
                    action=DelegateTaskAction(
                        task_id="inventory",
                        target_worker="business_data",
                    )
                ),
                AgentDecision(
                    action=DelegateTaskAction(
                        task_id="policy",
                        target_worker="knowledge",
                    )
                ),
            ),
            handoffs=(
                handoff_for("inventory", "查询德国库存", "business_data"),
                handoff_for("policy", "读取安全库存政策", "knowledge"),
            ),
            answers=(
                AgentAnswer(
                    action=FinishAction(
                        public_summary="库存125件 [E1]，政策要求至少60件 [E2]。",
                        business_outcome="answered",
                        evidence_ids=[BUSINESS_EVIDENCE_ID, KNOWLEDGE_EVIDENCE_ID],
                    )
                ),
            ),
        )
    )
    worker = ConcurrentBarrierWorker(
        {
            "inventory": completed_result("inventory", "business_data", inventory_item),
            "policy": completed_result("policy", "knowledge", policy_item),
        }
    )

    result = await SupervisorAgent(provider=provider, worker=worker).run(
        request(goal, workers=workers)
    )

    assert worker.both_started.is_set()
    assert result.execution_status == "completed", result
    assert [item.task_id for item in result.worker_results] == ["inventory", "policy"]
    assert result.evidence_ids == [BUSINESS_EVIDENCE_ID, KNOWLEDGE_EVIDENCE_ID]


@pytest.mark.asyncio
async def test_parallel_limit_one_keeps_independent_workers_sequential(
    workers: tuple[WorkerCapabilityProfile, WorkerCapabilityProfile],
) -> None:
    goal = "分别查询库存和安全库存政策"
    second_observation_id = UUID("00000000-0000-0000-0000-000000000407")
    first = observation(
        BUSINESS_OBSERVATION_ID,
        BUSINESS_EVIDENCE_ID,
        "主库存为125件。",
    )
    second = observation(
        second_observation_id,
        KNOWLEDGE_EVIDENCE_ID,
        "政策要求安全库存至少60件。",
    )
    provider = RecordingProvider(
        AgentMockScript(
            plans=(independent_two_worker_plan(goal),),
            decisions=(
                AgentDecision(
                    action=DelegateTaskAction(
                        task_id="inventory",
                        target_worker="business_data",
                    )
                ),
                AgentDecision(
                    action=DelegateTaskAction(
                        task_id="policy",
                        target_worker="knowledge",
                    )
                ),
            ),
            handoffs=(
                handoff_for("inventory", "查询德国库存", "business_data"),
                handoff_for("policy", "读取安全库存政策", "knowledge"),
            ),
            answers=(
                AgentAnswer(
                    action=FinishAction(
                        public_summary="库存125件 [E1]，政策要求至少60件 [E2]。",
                        business_outcome="answered",
                        evidence_ids=[BUSINESS_EVIDENCE_ID, KNOWLEDGE_EVIDENCE_ID],
                    )
                ),
            ),
        )
    )
    worker = ConcurrencyProbeWorker(
        {
            "inventory": completed_result("inventory", "business_data", first),
            "policy": completed_result("policy", "knowledge", second),
        }
    )

    result = await SupervisorAgent(
        provider=provider,
        worker=worker,
        guardrails=SupervisorGuardrails(max_parallel_workers=1),
    ).run(request(goal, workers=workers))

    assert result.execution_status == "completed", result
    assert worker.maximum_active == 1
    assert [item.task_id for item in result.worker_results] == [
        "inventory",
        "policy",
    ]


@pytest.mark.asyncio
async def test_parallel_batch_waits_for_all_workers_before_safe_failure(
    workers: tuple[WorkerCapabilityProfile, WorkerCapabilityProfile],
) -> None:
    goal = "分别查询库存和安全库存政策"
    policy_item = observation(
        KNOWLEDGE_OBSERVATION_ID,
        KNOWLEDGE_EVIDENCE_ID,
        "政策要求安全库存至少60件。",
    )
    provider = RecordingProvider(
        AgentMockScript(
            plans=(independent_two_worker_plan(goal),),
            decisions=(
                AgentDecision(
                    action=DelegateTaskAction(
                        task_id="inventory",
                        target_worker="business_data",
                    )
                ),
                AgentDecision(
                    action=DelegateTaskAction(
                        task_id="policy",
                        target_worker="knowledge",
                    )
                ),
            ),
            handoffs=(
                handoff_for("inventory", "查询德国库存", "business_data"),
                handoff_for("policy", "读取安全库存政策", "knowledge"),
            ),
        )
    )
    worker = BatchFailureWorker(completed_result("policy", "knowledge", policy_item))

    result = await SupervisorAgent(provider=provider, worker=worker).run(
        request(goal, workers=workers)
    )

    assert worker.both_started.is_set()
    assert worker.completed == {"policy"}
    assert result.execution_status == "failed"
    assert result.business_outcome == "system_error"
    assert result.stop_reason == "worker_failure"
    assert "private worker failure" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_l2_allows_partial_answer_after_non_blocking_worker_failure(
    workers: tuple[WorkerCapabilityProfile, WorkerCapabilityProfile],
) -> None:
    goal = "查询库存并结合政策判断"
    inventory_item = observation(
        BUSINESS_OBSERVATION_ID,
        BUSINESS_EVIDENCE_ID,
        "德国仓可售库存为125件。",
    )
    plan = two_worker_plan(goal)
    plan.tasks[1].failure_impact = "allows_partial"
    provider = RecordingProvider(
        AgentMockScript(
            plans=(plan,),
            decisions=(
                AgentDecision(
                    action=DelegateTaskAction(
                        task_id="inventory",
                        target_worker="business_data",
                    )
                ),
                AgentDecision(
                    action=DelegateTaskAction(
                        task_id="policy",
                        target_worker="knowledge",
                    )
                ),
            ),
            handoffs=(
                handoff_for("inventory", "查询德国库存", "business_data"),
                handoff_for("policy", "读取安全库存政策", "knowledge"),
            ),
            answers=(
                AgentAnswer(
                    action=FinishAction(
                        public_summary="库存事实已查到 [E1]，但政策资料暂时不可用。",
                        business_outcome="partial",
                        evidence_ids=[BUSINESS_EVIDENCE_ID],
                    )
                ),
            ),
        )
    )
    worker = ScriptedFakeWorker(
        [
            completed_result("inventory", "business_data", inventory_item),
            failed_result("policy", "knowledge"),
        ]
    )

    result = await SupervisorAgent(provider=provider, worker=worker).run(
        request(goal, workers=workers)
    )

    assert result.execution_status == "completed"
    assert result.business_outcome == "partial"
    assert result.evidence_ids == [BUSINESS_EVIDENCE_ID]
    assert [item.task_id for item in result.worker_results] == ["inventory", "policy"]
    assert [item.execution_status for item in cast(TaskPlan, result.plan).tasks] == [
        "completed",
        "failed",
    ]
    assert len(provider.answer_requests) == 1


@pytest.mark.asyncio
async def test_supervisor_pauses_for_user_without_running_worker(
    workers: tuple[WorkerCapabilityProfile, WorkerCapabilityProfile],
) -> None:
    goal = "查询库存"
    provider = RecordingProvider(
        AgentMockScript(
            plans=(one_worker_plan(goal),),
            decisions=(
                AgentDecision(
                    action=AskUserAction(
                        question="请提供商品名称或SKU。",
                        requested_fields=["product_query"],
                    )
                ),
            ),
        )
    )
    worker = ScriptedFakeWorker([])

    result = await SupervisorAgent(provider=provider, worker=worker).run(
        request(goal, workers=workers)
    )

    assert result.execution_status == "waiting_user"
    assert result.business_outcome is None
    assert result.current_task_id == "inventory"
    assert result.public_summary == "请提供商品名称或SKU。"
    assert result.stop_reason == "waiting_for_user"
    assert worker.received_handoffs == []


@pytest.mark.asyncio
async def test_no_capability_path_returns_explicit_unsupported() -> None:
    goal = "修改外部平台售价"
    provider = RecordingProvider(
        AgentMockScript(
            plans=(direct_plan(goal),),
            answers=(
                AgentAnswer(
                    action=CannotCompleteAction(
                        public_summary="当前只提供已登记的只读能力，不能修改售价。",
                        business_outcome="unsupported",
                    )
                ),
            ),
        )
    )

    result = await SupervisorAgent(
        provider=provider,
        worker=ScriptedFakeWorker([]),
    ).run(request(goal, workers=()))

    assert result.execution_status == "completed"
    assert result.business_outcome == "unsupported"
    assert result.stop_reason == "unsupported"
    assert result.worker_results == []


@pytest.mark.asyncio
async def test_delegation_cannot_override_the_planned_worker(
    workers: tuple[WorkerCapabilityProfile, WorkerCapabilityProfile],
) -> None:
    goal = "查询德国库存"
    provider = RecordingProvider(
        AgentMockScript(
            plans=(one_worker_plan(goal),),
            decisions=(
                AgentDecision(
                    action=DelegateTaskAction(
                        task_id="inventory",
                        target_worker="knowledge",
                    )
                ),
            ),
        )
    )
    worker = ScriptedFakeWorker([])

    result = await SupervisorAgent(provider=provider, worker=worker).run(
        request(goal, workers=workers)
    )

    assert result.execution_status == "failed"
    assert result.business_outcome == "system_error"
    assert result.stop_reason == "invalid_decision"
    assert provider.handoff_requests == []
    assert worker.received_handoffs == []


@pytest.mark.asyncio
async def test_worker_failure_is_sanitized_and_cannot_leak_runtime_details(
    workers: tuple[WorkerCapabilityProfile, WorkerCapabilityProfile],
) -> None:
    goal = "查询德国库存"
    provider = RecordingProvider(
        AgentMockScript(
            plans=(one_worker_plan(goal),),
            decisions=(
                AgentDecision(
                    action=DelegateTaskAction(
                        task_id="inventory",
                        target_worker="business_data",
                    )
                ),
            ),
            handoffs=(handoff_for("inventory", "查询德国库存", "business_data"),),
        )
    )
    worker = ScriptedFakeWorker(
        [RuntimeError(r"SELECT secret FROM users at C:\\private\\db.py")]
    )

    result = await SupervisorAgent(provider=provider, worker=worker).run(
        request(goal, workers=workers)
    )

    assert result.execution_status == "failed"
    assert result.business_outcome == "system_error"
    assert result.stop_reason == "worker_failure"
    assert result.public_summary == "Agent流程未能安全完成。"
    dumped = result.model_dump_json().casefold()
    assert "select secret" not in dumped
    assert "private" not in dumped


def running_result() -> WorkerResult:
    return WorkerResult(
        task_id="inventory",
        worker_id="business_data",
        execution_status="running",
        public_summary="尚未产生可用结果。",
        resource_usage=zero_usage(),
    )


@pytest.mark.asyncio
async def test_identical_no_progress_delegation_is_terminated(
    workers: tuple[WorkerCapabilityProfile, WorkerCapabilityProfile],
) -> None:
    goal = "查询德国库存"
    repeated = AgentDecision(
        action=DelegateTaskAction(
            task_id="inventory",
            target_worker="business_data",
        )
    )
    provider = RecordingProvider(
        AgentMockScript(
            plans=(one_worker_plan(goal),),
            decisions=(repeated, repeated),
            handoffs=(handoff_for("inventory", "查询德国库存", "business_data"),),
        )
    )
    worker = ScriptedFakeWorker([running_result()])

    result = await SupervisorAgent(provider=provider, worker=worker).run(
        request(goal, workers=workers)
    )

    assert result.execution_status == "failed"
    assert result.business_outcome == "system_error"
    assert result.stop_reason == "repeated_action"
    assert len(provider.decision_requests) == 2
    assert len(worker.received_handoffs) == 1


@pytest.mark.asyncio
async def test_decision_step_limit_stops_before_another_model_call(
    workers: tuple[WorkerCapabilityProfile, WorkerCapabilityProfile],
) -> None:
    goal = "查询德国库存"
    provider = RecordingProvider(
        AgentMockScript(
            plans=(one_worker_plan(goal),),
            decisions=(
                AgentDecision(
                    action=DelegateTaskAction(
                        task_id="inventory",
                        target_worker="business_data",
                    )
                ),
            ),
            handoffs=(handoff_for("inventory", "查询德国库存", "business_data"),),
        )
    )
    worker = ScriptedFakeWorker([running_result()])

    result = await SupervisorAgent(
        provider=provider,
        worker=worker,
        guardrails=SupervisorGuardrails(max_decisions=1),
    ).run(request(goal, workers=workers))

    assert result.execution_status == "failed"
    assert result.business_outcome == "system_error"
    assert result.stop_reason == "decision_limit"
    assert len(provider.decision_requests) == 1
    assert len(worker.received_handoffs) == 1


@pytest.mark.asyncio
async def test_same_script_and_input_produce_same_safe_serializable_state(
    workers: tuple[WorkerCapabilityProfile, WorkerCapabilityProfile],
) -> None:
    goal = "解释什么是安全库存"
    script = AgentMockScript(
        plans=(direct_plan(goal),),
        answers=(
            AgentAnswer(
                action=FinishAction(
                    public_summary="安全库存用于吸收不确定性。",
                    business_outcome="answered",
                )
            ),
        ),
    )
    first = await SupervisorAgent(
        provider=DeterministicAgentMock(script),
        worker=ScriptedFakeWorker([]),
    ).run(request(goal, workers=workers))
    second = await SupervisorAgent(
        provider=DeterministicAgentMock(script),
        worker=ScriptedFakeWorker([]),
    ).run(request(goal, workers=workers))

    assert first == second
    assert EngineeredAgentState.model_validate_json(first.model_dump_json()) == first
    dumped = first.model_dump_json().casefold()
    assert "chain_of_thought" not in dumped
    assert "database_session" not in dumped
    assert "storage_key" not in dumped


def test_graph_has_only_bounded_control_nodes_and_no_real_execution_imports(
    workers: tuple[WorkerCapabilityProfile, WorkerCapabilityProfile],
) -> None:
    goal = "解释什么是安全库存"
    provider = DeterministicAgentMock(
        AgentMockScript(
            plans=(direct_plan(goal),),
            answers=(
                AgentAnswer(
                    action=FinishAction(
                        public_summary="安全库存用于吸收不确定性。",
                        business_outcome="answered",
                    )
                ),
            ),
        )
    )
    graph = build_engineered_multi_agent_graph(
        cast(EngineeredAgentProvider, provider),
        cast(WorkerInvoker, ScriptedFakeWorker([])),
        SupervisorGuardrails(),
    ).get_graph()

    assert set(graph.nodes) == {
        "__start__",
        "plan",
        "decide",
        "prepare_handoff",
        "invoke_worker",
        "compose_answer",
        "__end__",
    }

    forbidden_prefixes = (
        "sqlalchemy",
        "app.api",
        "app.models",
        "app.repositories",
        "app.services",
        "app.tools",
        "app.runtime",
    )
    forbidden_state_names = {
        "chain_of_thought",
        "reasoning",
        "prompt",
        "messages",
        "database_session",
        "tool_objects",
        "run_context",
        "user_id",
        "tenant_id",
        "roles",
        "permissions",
        "budget_limits",
        "sql",
        "local_path",
        "storage_key",
        "raw_exception",
    }
    for relative_path in (
        "app/agents/supervisor.py",
        "app/agents/graphs/engineered_multi_agent.py",
    ):
        tree = ast.parse((PROJECT_ROOT / relative_path).read_text(encoding="utf-8"))
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        )
        assert not {item for item in imports if item.startswith(forbidden_prefixes)}, (
            relative_path
        )

    from app.agents.graphs.engineered_multi_agent import SupervisorGraphState

    assert not set(SupervisorGraphState.__annotations__) & forbidden_state_names
