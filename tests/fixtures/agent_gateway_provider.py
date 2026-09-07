"""Deterministic provider used to prove the public Gateway with real Workers."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from app.llm.agent_schemas import (
    AgentAnswer,
    AnswerRequest,
    DecisionRequest,
    HandoffDraft,
    HandoffRequest,
    PlannerRequest,
)
from app.schemas.agent import (
    AgentDecision,
    AgentTask,
    AskUserAction,
    BoundedJsonObject,
    CannotCompleteAction,
    DelegateTaskAction,
    EvidenceRequirement,
    ExecuteCapabilityAction,
    FinishAction,
    TaskAssignment,
    TaskPlan,
)

_SKU = re.compile(r"(?<![A-Z0-9-])[A-Z0-9][A-Z0-9-]{2,63}(?![A-Z0-9-])")


@dataclass
class InventoryGatewayProvider:
    """Drive the real Business Worker without embedding routing in production."""

    forced_sku: str | None = None
    goal: str = ""

    async def create_plan(self, request: PlannerRequest) -> TaskPlan:
        self.goal = request.goal
        if "解释" in self.goal:
            return TaskPlan(
                plan_id=uuid4(),
                goal=self.goal,
                tasks=[
                    AgentTask(
                        task_id="direct_answer",
                        goal=self.goal,
                        assignment=TaskAssignment(status="unassigned"),
                        completion_criteria=["返回安全的直接解释"],
                        evidence_requirement=EvidenceRequirement(
                            required=False,
                            minimum_count=0,
                            source_types=[],
                        ),
                        failure_impact="non_blocking",
                    )
                ],
            )
        exact_sku = self._sku()
        return TaskPlan(
            plan_id=uuid4(),
            goal=self.goal,
            tasks=[
                AgentTask(
                    task_id="inventory",
                    goal=self.goal,
                    required_capabilities=(
                        ["search_inventory"]
                        if exact_sku is not None
                        else ["get_product_spec", "search_inventory"]
                    ),
                    assignment=TaskAssignment(
                        status="assigned",
                        worker_id="business_data",
                    ),
                    completion_criteria=["返回库存事实和Evidence或安全失败"],
                    evidence_requirement=EvidenceRequirement(
                        required=True,
                        minimum_count=1,
                        source_types=["database"],
                    ),
                    failure_impact="blocks_dependents",
                )
            ],
        )

    async def choose_action(self, request: DecisionRequest) -> AgentDecision:
        worker_id = request.available_capabilities.requesting_agent_id
        if worker_id is None:
            if request.active_task.assignment.status == "unassigned":
                return AgentDecision(
                    action=FinishAction(
                        public_summary="安全库存是为应对需求和补货波动预留的缓冲量。",
                        business_outcome="answered",
                    )
                )
            return AgentDecision(
                action=DelegateTaskAction(
                    task_id=request.active_task_id,
                    target_worker="business_data",
                )
            )

        if request.observations:
            latest = request.observations[-1]
            if latest.status != "success":
                assert latest.safe_error is not None
                if latest.status == "rejected":
                    outcome = "denied"
                elif latest.status == "timeout":
                    outcome = "timed_out"
                else:
                    outcome = "system_error"
                return AgentDecision(
                    action=CannotCompleteAction(
                        public_summary=latest.safe_error.message,
                        business_outcome=outcome,
                    )
                )
            capability_id = latest.structured_result.root["capability_id"]
            if capability_id == "search_inventory":
                return AgentDecision(
                    action=FinishAction(
                        public_summary="库存查询已完成。",
                        business_outcome="answered",
                        evidence_ids=[
                            evidence_id
                            for item in request.observations
                            for evidence_id in item.evidence_ids
                        ],
                    )
                )
            assert capability_id == "get_product_spec"
            data = latest.structured_result.root["data"]
            assert isinstance(data, dict)
            return self._inventory_action(str(data["sku"]), request)

        exact_sku = self._sku()
        if exact_sku is not None:
            return self._inventory_action(exact_sku, request)
        return AgentDecision(
            action=ExecuteCapabilityAction(
                capability_id="get_product_spec",
                arguments=BoundedJsonObject({"product_query": "蘑菇灯"}),
            )
        )

    async def prepare_handoff(self, request: HandoffRequest) -> HandoffDraft:
        task = request.delegated_task
        market = self._market()
        context: dict[str, object] = {
            "market_code": market,
            "warehouse_code": "DE-FRA" if market == "DE" else "FR-CDG",
        }
        exact_sku = self._sku()
        if exact_sku is None:
            context["product_query"] = "蘑菇灯"
        else:
            context["sku"] = exact_sku
        return HandoffDraft(
            task_id=task.task_id,
            goal=task.goal,
            target_worker="business_data",
            public_context=BoundedJsonObject(context),
            constraints=("只读且必须经过Harness",),
            expected_output="返回库存事实和Evidence或安全失败",
            completion_criteria=tuple(task.completion_criteria),
        )

    async def compose_answer(self, request: AnswerRequest) -> AgentAnswer:
        if not request.worker_results:
            return AgentAnswer(
                action=FinishAction(
                    public_summary="安全库存是为应对需求和补货波动预留的缓冲量。",
                    business_outcome="answered",
                )
            )
        result = request.worker_results[-1]
        if result.business_outcome != "answered":
            return AgentAnswer(
                action=CannotCompleteAction(
                    public_summary=result.public_summary,
                    business_outcome=result.business_outcome or "system_error",
                )
            )
        assert result.business_result is not None
        inventory = result.business_result.root["inventory"]
        assert isinstance(inventory, dict)
        citation = " [E1]" if result.evidence_ids else ""
        return AgentAnswer(
            action=FinishAction(
                public_summary=(
                    f"{inventory['warehouse_code']}可售库存为"
                    f"{inventory['available']}件（合成演示数据）。{citation}"
                ),
                business_outcome="answered",
                evidence_ids=result.evidence_ids,
            )
        )

    def _inventory_action(
        self,
        sku: str,
        request: DecisionRequest,
    ) -> AgentDecision:
        public_context = request.public_context.root
        return AgentDecision(
            action=ExecuteCapabilityAction(
                capability_id="search_inventory",
                arguments=BoundedJsonObject(
                    {
                        "sku": sku,
                        "market_code": public_context["market_code"],
                        "warehouse_code": public_context["warehouse_code"],
                    }
                ),
            )
        )

    def _sku(self) -> str | None:
        if self.forced_sku is not None:
            return self.forced_sku
        if "法国" in self.goal:
            return "LR-TL-MUSH-OR01"
        match = _SKU.search(self.goal)
        return match.group(0) if match is not None else None

    def _market(self) -> str:
        return "FR" if "法国" in self.goal else "DE"


@dataclass
class CrossWorkerGatewayProvider(InventoryGatewayProvider):
    """Run independent Business and Knowledge reads for one combined answer."""

    fail_knowledge: bool = False
    file_id: UUID | None = None

    async def create_plan(self, request: PlannerRequest) -> TaskPlan:
        self.goal = request.goal
        return TaskPlan(
            plan_id=uuid4(),
            goal=self.goal,
            tasks=[
                AgentTask(
                    task_id="inventory",
                    goal="查询德国仓库存",
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
                    task_id="inspect_evidence",
                    goal="由Knowledge Worker读取获权手册",
                    required_capabilities=["read_uploaded_file"],
                    assignment=TaskAssignment(status="assigned", worker_id="knowledge"),
                    completion_criteria=["返回获权Evidence详情或明确失败"],
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
            assert request.active_task.assignment.worker_id is not None
            return AgentDecision(
                action=DelegateTaskAction(
                    task_id=request.active_task_id,
                    target_worker=request.active_task.assignment.worker_id,
                )
            )
        if worker_id == "business_data":
            return await super().choose_action(request)
        if self.fail_knowledge:
            return AgentDecision(
                action=CannotCompleteAction(
                    public_summary="Knowledge Worker暂时无法完成复核。",
                    business_outcome="system_error",
                )
            )
        if not request.observations:
            file_id = request.public_context.root["file_id"]
            return AgentDecision(
                action=ExecuteCapabilityAction(
                    capability_id="read_uploaded_file",
                    arguments=BoundedJsonObject(
                        {
                            "file_id": file_id,
                            "locator": {"source_type": "pdf", "page_start": 1},
                        }
                    ),
                )
            )
        return AgentDecision(
            action=FinishAction(
                public_summary="Knowledge Worker已复核Evidence。",
                business_outcome="answered",
                evidence_ids=[
                    evidence_id
                    for item in request.observations
                    for evidence_id in item.evidence_ids
                ],
                artifact_ids=[
                    artifact_id
                    for item in request.observations
                    for artifact_id in item.artifact_ids
                ],
            )
        )

    async def prepare_handoff(self, request: HandoffRequest) -> HandoffDraft:
        if request.delegation.target_worker == "business_data":
            return await super().prepare_handoff(request)
        task = request.delegated_task
        assert self.file_id is not None
        return HandoffDraft(
            task_id=task.task_id,
            goal=task.goal,
            target_worker="knowledge",
            public_context=BoundedJsonObject({"file_id": str(self.file_id)}),
            constraints=("只读且必须经过Harness",),
            expected_output="返回获权Evidence详情或明确失败",
            completion_criteria=tuple(task.completion_criteria),
        )

    async def compose_answer(self, request: AnswerRequest) -> AgentAnswer:
        evidence_ids = list(
            dict.fromkeys(
                evidence_id
                for result in request.worker_results
                for evidence_id in result.evidence_ids
            )
        )
        artifact_ids = list(
            dict.fromkeys(
                artifact_id
                for result in request.worker_results
                for artifact_id in result.artifact_ids
            )
        )
        partial = any(
            result.execution_status == "failed" for result in request.worker_results
        )
        return AgentAnswer(
            action=FinishAction(
                public_summary=(
                    "库存已返回，但Knowledge复核失败。[E1]"
                    if partial
                    else "Business与Knowledge两个Worker已完成。[E1]"
                ),
                business_outcome="partial" if partial else "answered",
                evidence_ids=evidence_ids,
                artifact_ids=artifact_ids,
            )
        )


@dataclass
class ConcurrentCrossWorkerGatewayProvider(CrossWorkerGatewayProvider):
    """Hold the first Worker until both independent Worker loops are active."""

    entered_workers: set[str] = field(default_factory=set)
    both_workers_entered: asyncio.Event = field(default_factory=asyncio.Event)

    async def choose_action(self, request: DecisionRequest) -> AgentDecision:
        worker_id = request.available_capabilities.requesting_agent_id
        if worker_id is not None and not request.observations:
            self.entered_workers.add(worker_id)
            if self.entered_workers == {"business_data", "knowledge"}:
                self.both_workers_entered.set()
            await asyncio.wait_for(self.both_workers_entered.wait(), timeout=2)
        return await super().choose_action(request)


@dataclass
class KnowledgeGatewayProvider:
    """Drive one real Knowledge Worker read through the public Gateway."""

    file_id: UUID
    before_answer: Callable[[], None] | None = None
    goal: str = ""

    async def create_plan(self, request: PlannerRequest) -> TaskPlan:
        self.goal = request.goal
        return TaskPlan(
            plan_id=uuid4(),
            goal=self.goal,
            tasks=[
                AgentTask(
                    task_id="read_manual",
                    goal=self.goal,
                    required_capabilities=["read_uploaded_file"],
                    assignment=TaskAssignment(status="assigned", worker_id="knowledge"),
                    completion_criteria=["返回获权手册内容或安全失败"],
                    evidence_requirement=EvidenceRequirement(
                        required=False,
                        minimum_count=0,
                        source_types=["artifact"],
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
                    capability_id="read_uploaded_file",
                    arguments=BoundedJsonObject(
                        {
                            "file_id": str(self.file_id),
                            "locator": {"source_type": "pdf", "page_start": 1},
                        }
                    ),
                )
            )
        return AgentDecision(
            action=FinishAction(
                public_summary="Knowledge Worker已读取手册。",
                business_outcome="answered",
                artifact_ids=[
                    artifact_id
                    for item in request.observations
                    for artifact_id in item.artifact_ids
                ],
            )
        )

    async def prepare_handoff(self, request: HandoffRequest) -> HandoffDraft:
        task = request.delegated_task
        return HandoffDraft(
            task_id=task.task_id,
            goal=task.goal,
            target_worker="knowledge",
            public_context=BoundedJsonObject({"file_id": str(self.file_id)}),
            constraints=("只读且必须经过Harness",),
            expected_output="返回获权手册内容或安全失败",
            completion_criteria=tuple(task.completion_criteria),
        )

    async def compose_answer(self, request: AnswerRequest) -> AgentAnswer:
        if self.before_answer is not None:
            self.before_answer()
        result = request.worker_results[0]
        return AgentAnswer(
            action=FinishAction(
                public_summary="已从获权手册中读取内容。",
                business_outcome="answered",
                artifact_ids=result.artifact_ids,
            )
        )


@dataclass
class ResumableKnowledgeGatewayProvider(KnowledgeGatewayProvider):
    """Complete one Knowledge task, then pause before a second task."""

    async def create_plan(self, request: PlannerRequest) -> TaskPlan:
        self.goal = request.goal
        return TaskPlan(
            plan_id=uuid4(),
            goal=request.goal,
            tasks=[
                AgentTask(
                    task_id="read_before_clarification",
                    goal="先读取当前获权手册",
                    required_capabilities=["read_uploaded_file"],
                    assignment=TaskAssignment(status="assigned", worker_id="knowledge"),
                    completion_criteria=["返回获权手册Artifact"],
                    evidence_requirement=EvidenceRequirement(
                        required=False,
                        minimum_count=0,
                        source_types=["artifact"],
                    ),
                    failure_impact="blocks_dependents",
                ),
                AgentTask(
                    task_id="confirm_followup",
                    goal="确认是否继续复核",
                    depends_on=["read_before_clarification"],
                    required_capabilities=["read_uploaded_file"],
                    assignment=TaskAssignment(status="assigned", worker_id="knowledge"),
                    completion_criteria=["获得用户确认后继续"],
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
        if (
            request.available_capabilities.requesting_agent_id is None
            and request.active_task_id == "confirm_followup"
        ):
            return AgentDecision(
                action=AskUserAction(
                    question="是否继续复核这份手册？",
                    requested_fields=["confirmation"],
                )
            )
        return await super().choose_action(request)


@dataclass
class ResumableInventoryGatewayProvider:
    """Ask for a market once, then prove clarification resume and re-planning."""

    plan_calls: int = 0
    goal: str = ""

    async def create_plan(self, request: PlannerRequest) -> TaskPlan:
        self.plan_calls += 1
        self.goal = request.goal
        return TaskPlan(
            plan_id=uuid4(),
            goal=request.goal,
            tasks=[
                AgentTask(
                    task_id="inventory_after_clarification",
                    goal=request.goal,
                    required_capabilities=["search_inventory"],
                    assignment=TaskAssignment(
                        status="assigned",
                        worker_id="business_data",
                    ),
                    completion_criteria=["返回指定市场库存和Evidence"],
                    evidence_requirement=EvidenceRequirement(
                        required=True,
                        minimum_count=1,
                        source_types=["database"],
                    ),
                    failure_impact="blocks_dependents",
                )
            ],
        )

    async def choose_action(self, request: DecisionRequest) -> AgentDecision:
        if request.available_capabilities.requesting_agent_id is None:
            memory = request.public_context.root.get("conversation_memory", {})
            turns = memory.get("recent_turns", []) if isinstance(memory, dict) else []
            clarified = any(
                isinstance(turn, dict) and "德国" in str(turn.get("content_summary"))
                for turn in turns
            )
            if not clarified:
                return AgentDecision(
                    action=AskUserAction(
                        question="请说明要查询哪个市场，例如德国或法国。",
                        requested_fields=["market_code"],
                    )
                )
            return AgentDecision(
                action=DelegateTaskAction(
                    task_id=request.active_task_id,
                    target_worker="business_data",
                )
            )
        if not request.observations:
            return AgentDecision(
                action=ExecuteCapabilityAction(
                    capability_id="search_inventory",
                    arguments=BoundedJsonObject(
                        {
                            "sku": "LR-TL-MUSH-OR01",
                            "market_code": "DE",
                            "warehouse_code": "DE-FRA",
                        }
                    ),
                )
            )
        evidence_ids = [
            evidence_id
            for observation in request.observations
            for evidence_id in observation.evidence_ids
        ]
        return AgentDecision(
            action=FinishAction(
                public_summary="德国库存查询已完成。",
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
            public_context=BoundedJsonObject(
                {
                    "sku": "LR-TL-MUSH-OR01",
                    "market_code": "DE",
                    "warehouse_code": "DE-FRA",
                }
            ),
            constraints=("只读且必须经过Harness",),
            expected_output="返回指定市场库存和Evidence",
            completion_criteria=tuple(task.completion_criteria),
        )

    async def compose_answer(self, request: AnswerRequest) -> AgentAnswer:
        evidence_ids = list(
            dict.fromkeys(
                evidence_id
                for result in request.worker_results
                for evidence_id in result.evidence_ids
            )
        )
        return AgentAnswer(
            action=FinishAction(
                public_summary="DE-FRA可售库存为125件（合成演示数据）。 [E1]",
                business_outcome="answered",
                evidence_ids=evidence_ids,
            )
        )
