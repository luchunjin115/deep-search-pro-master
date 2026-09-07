"""Deterministic offline Agent provider driven only by a bounded test script."""

from __future__ import annotations

from typing import TypeVar

from pydantic import ConfigDict, Field

from app.llm.agent_provider import (
    validate_answer_response,
    validate_decision_response,
    validate_handoff_response,
    validate_plan_response,
)
from app.llm.agent_schemas import (
    AgentAnswer,
    AnswerRequest,
    DecisionRequest,
    HandoffDraft,
    HandoffRequest,
    PlannerRequest,
)
from app.schemas.agent import AgentDecision, TaskPlan
from app.schemas.common import M1Schema

OutputT = TypeVar("OutputT", TaskPlan, AgentDecision, HandoffDraft, AgentAnswer)


class AgentMockScript(M1Schema):
    """A bounded output sequence; it contains no callbacks, clients, or Tools."""

    model_config = ConfigDict(frozen=True)

    plans: tuple[TaskPlan, ...] = Field(default_factory=tuple, max_length=16)
    decisions: tuple[AgentDecision, ...] = Field(default_factory=tuple, max_length=64)
    handoffs: tuple[HandoffDraft, ...] = Field(default_factory=tuple, max_length=32)
    answers: tuple[AgentAnswer, ...] = Field(default_factory=tuple, max_length=16)


class AgentMockScriptExhaustedError(RuntimeError):
    """The deterministic test scenario omitted the next expected output."""


class DeterministicAgentMock:
    """Return deep-copied scripted outputs and apply the real boundary validators."""

    def __init__(self, script: AgentMockScript) -> None:
        snapshot = script.model_copy(deep=True)
        self._outputs: dict[str, tuple[object, ...]] = {
            "plan": snapshot.plans,
            "decision": snapshot.decisions,
            "handoff": snapshot.handoffs,
            "answer": snapshot.answers,
        }
        self._positions = {name: 0 for name in self._outputs}

    def _next(self, name: str, expected_type: type[OutputT]) -> OutputT:
        position = self._positions[name]
        outputs = self._outputs[name]
        if position >= len(outputs):
            raise AgentMockScriptExhaustedError(
                f"deterministic Agent mock {name} script exhausted"
            )
        self._positions[name] = position + 1
        output = outputs[position]
        if not isinstance(output, expected_type):
            raise TypeError(
                "deterministic Agent mock script has an invalid output type"
            )
        return output.model_copy(deep=True)

    async def create_plan(self, request: PlannerRequest) -> TaskPlan:
        response = self._next("plan", TaskPlan)
        return validate_plan_response(request, response)

    async def choose_action(self, request: DecisionRequest) -> AgentDecision:
        response = self._next("decision", AgentDecision)
        return validate_decision_response(request, response)

    async def prepare_handoff(self, request: HandoffRequest) -> HandoffDraft:
        response = self._next("handoff", HandoffDraft)
        return validate_handoff_response(request, response)

    async def compose_answer(self, request: AnswerRequest) -> AgentAnswer:
        response = self._next("answer", AgentAnswer)
        return validate_answer_response(request, response)
