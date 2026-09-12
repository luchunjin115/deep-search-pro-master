"""Budget adapter for the four existing Supervisor provider operations."""

from __future__ import annotations

from app.llm.agent_provider import EngineeredAgentProvider
from app.llm.agent_schemas import (
    AgentAnswer,
    AnswerRequest,
    DecisionRequest,
    HandoffDraft,
    HandoffRequest,
    PlannerRequest,
)
from app.llm.agent_structured import answer_repair_call_budget
from app.runtime.budget import AgentBudgetTree
from app.schemas.agent import AgentDecision, TaskPlan


class BudgetedAgentProvider:
    """Reserve a trusted root model-call budget before each provider call."""

    def __init__(
        self,
        *,
        provider: EngineeredAgentProvider,
        budget: AgentBudgetTree,
    ) -> None:
        self._provider = provider
        self._budget = budget
        self._last_answer_model_calls = 0

    @property
    def last_answer_model_calls(self) -> int:
        return self._last_answer_model_calls

    async def create_plan(self, request: PlannerRequest) -> TaskPlan:
        self._budget.reserve_root_model_call()
        return await self._provider.create_plan(request)

    async def choose_action(self, request: DecisionRequest) -> AgentDecision:
        self._budget.reserve_root_model_call()
        return await self._provider.choose_action(request)

    async def prepare_handoff(self, request: HandoffRequest) -> HandoffDraft:
        self._budget.reserve_root_model_call()
        return await self._provider.prepare_handoff(request)

    async def compose_answer(self, request: AnswerRequest) -> AgentAnswer:
        self._last_answer_model_calls = 0
        self._budget.reserve_root_model_call()
        self._last_answer_model_calls = 1

        def reserve_repair() -> None:
            self._budget.reserve_root_model_call()
            self._last_answer_model_calls += 1

        with answer_repair_call_budget(reserve_repair):
            return await self._provider.compose_answer(request)
