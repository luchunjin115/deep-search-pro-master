"""Replaceable Agent provider protocols and deterministic output validation."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from jsonschema.exceptions import SchemaError  # type: ignore[import-untyped]
from jsonschema.exceptions import (  # type: ignore[import-untyped]
    ValidationError as JsonSchemaError,
)
from jsonschema.validators import validator_for  # type: ignore[import-untyped]

from app.core.errors import AgentProviderOutputError
from app.llm.agent_evidence import validate_answer_citations
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
    DelegateTaskAction,
    ExecuteCapabilityAction,
    FinishAction,
    TaskPlan,
)


def _candidate_ids(request: DecisionRequest) -> dict[str, str]:
    return {
        item.capability_id: item.kind
        for item in request.available_capabilities.capabilities
    }


def validate_plan_response(request: PlannerRequest, response: TaskPlan) -> TaskPlan:
    """Reject goal drift and references outside the supplied safe candidates."""

    capabilities_by_worker = {
        profile.worker.capability_id: {
            item.capability_id for item in profile.capabilities.capabilities
        }
        for profile in request.available_workers
    }
    all_capabilities = set().union(*capabilities_by_worker.values())
    if response.goal != request.goal:
        raise AgentProviderOutputError
    direct_tasks = [
        task
        for task in response.tasks
        if task.assignment.status == "unassigned" and not task.required_capabilities
    ]
    if direct_tasks and len(response.tasks) != 1:
        raise AgentProviderOutputError
    if not direct_tasks and any(
        task.assignment.status != "assigned" or not task.required_capabilities
        for task in response.tasks
    ):
        raise AgentProviderOutputError
    assigned_worker_ids = [
        task.assignment.worker_id
        for task in response.tasks
        if task.assignment.worker_id is not None
    ]
    if len(assigned_worker_ids) != len(set(assigned_worker_ids)):
        raise AgentProviderOutputError
    for task in response.tasks:
        worker_id = task.assignment.worker_id
        allowed_capabilities = (
            all_capabilities
            if worker_id is None
            else capabilities_by_worker.get(worker_id)
        )
        if allowed_capabilities is None:
            raise AgentProviderOutputError
        if not set(task.required_capabilities) <= allowed_capabilities:
            raise AgentProviderOutputError
    return response.model_copy(deep=True)


def validate_decision_response(
    request: DecisionRequest,
    response: AgentDecision,
) -> AgentDecision:
    """Bind a structured action to the current task, candidates, and known refs."""

    candidates = _candidate_ids(request)
    action = response.action
    if isinstance(action, ExecuteCapabilityAction):
        if candidates.get(action.capability_id) not in {"tool", "skill", "runtime"}:
            raise AgentProviderOutputError
        capability = next(
            (
                item
                for item in request.available_capabilities.capabilities
                if item.capability_id == action.capability_id
            ),
            None,
        )
        if capability is None or capability.parameters is None:
            raise AgentProviderOutputError
        try:
            validator_type = validator_for(capability.parameters.root)
            validator_type.check_schema(capability.parameters.root)
            validator_type(capability.parameters.root).validate(action.arguments.root)
        except (JsonSchemaError, SchemaError, TypeError, ValueError):
            raise AgentProviderOutputError from None
    elif isinstance(action, DelegateTaskAction):
        if action.task_id != request.active_task_id:
            raise AgentProviderOutputError
        if candidates.get(action.target_worker) != "agent":
            raise AgentProviderOutputError
    elif isinstance(action, FinishAction):
        evidence_ids, artifact_ids = request.reference_ids
        if not set(action.evidence_ids) <= evidence_ids:
            raise AgentProviderOutputError
        if not set(action.artifact_ids) <= artifact_ids:
            raise AgentProviderOutputError
        evidence_requirement = request.active_task.evidence_requirement
        if (
            action.business_outcome == "answered"
            and evidence_requirement.required
            and len(action.evidence_ids) < evidence_requirement.minimum_count
        ):
            raise AgentProviderOutputError
    return response.model_copy(deep=True)


def validate_handoff_response(
    request: HandoffRequest,
    response: HandoffDraft,
) -> HandoffDraft:
    """Keep model-authored Handoff content inside the delegated task and ref pool."""

    task = request.delegated_task
    if response.task_id != request.delegation.task_id:
        raise AgentProviderOutputError
    if response.target_worker != request.delegation.target_worker:
        raise AgentProviderOutputError
    if response.goal != task.goal:
        raise AgentProviderOutputError
    if response.completion_criteria != tuple(task.completion_criteria):
        raise AgentProviderOutputError
    evidence_ids, artifact_ids = request.reference_ids
    if not set(response.evidence_ids) <= evidence_ids:
        raise AgentProviderOutputError
    if not set(response.artifact_ids) <= artifact_ids:
        raise AgentProviderOutputError
    return response.model_copy(deep=True)


def validate_answer_response(
    request: AnswerRequest,
    response: AgentAnswer,
) -> AgentAnswer:
    """Reject Evidence or Artifact IDs not supplied by validated Worker results."""

    if isinstance(response.action, FinishAction):
        evidence_ids, artifact_ids = request.reference_ids
        if not set(response.action.evidence_ids) <= evidence_ids:
            raise AgentProviderOutputError
        if not set(response.action.artifact_ids) <= artifact_ids:
            raise AgentProviderOutputError
    return validate_answer_citations(request, response)


@runtime_checkable
class AgentPlannerProvider(Protocol):
    """Create a bounded Task DAG without executing capabilities."""

    async def create_plan(self, request: PlannerRequest) -> TaskPlan: ...


@runtime_checkable
class AgentDecisionProvider(Protocol):
    """Choose exactly one structured action for the current task."""

    async def choose_action(self, request: DecisionRequest) -> AgentDecision: ...


@runtime_checkable
class AgentHandoffProvider(Protocol):
    """Prepare only public Handoff content; Runtime owns IDs and budget."""

    async def prepare_handoff(self, request: HandoffRequest) -> HandoffDraft: ...


@runtime_checkable
class AgentAnswerProvider(Protocol):
    """Compose one terminal action from public, validated Worker results."""

    async def compose_answer(self, request: AnswerRequest) -> AgentAnswer: ...


@runtime_checkable
class EngineeredAgentProvider(
    AgentPlannerProvider,
    AgentDecisionProvider,
    AgentHandoffProvider,
    AgentAnswerProvider,
    Protocol,
):
    """Composite protocol implemented by Mock, Qwen, and DeepSeek providers."""
