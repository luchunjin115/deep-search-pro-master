from __future__ import annotations

from dataclasses import dataclass, replace
from typing import cast
from uuid import uuid4

from app.core.errors import EvidenceNotFoundError
from app.runtime.budget import BudgetLimits, ExecutionBudget
from app.runtime.executor import HarnessExecutor
from app.runtime.permissions import PermissionGuard
from app.schemas.auth import CurrentUser
from app.schemas.evidence import GetEvidenceDetailInput, GetEvidenceDetailResult
from app.services.evidence import EvidenceQueryService
from app.tools.get_evidence_detail import GetEvidenceDetailTool
from app.tools.registry import create_m2_tool_registry
from tests.integration.test_agent_tools import AgentToolFixture, load_calls
from tests.unit.test_file_evidence_tool_contracts import document_evidence_detail

pytest_plugins = ("tests.integration.test_agent_tools",)


def _user(fixture: AgentToolFixture) -> CurrentUser:
    return CurrentUser(
        user_id=fixture.context.user_id,
        tenant_id=fixture.context.tenant_id,
        email="de.operator@demo.deepsearch.local",
        display_name="德国站运营",
        roles=list(fixture.context.roles),
        market_scopes=list(fixture.context.market_scopes),
        synthetic_data=True,
    )


@dataclass(slots=True)
class ControlledEvidenceService:
    result: GetEvidenceDetailResult
    failure: Exception | None = None
    advance: object | None = None
    calls: int = 0

    def get_tool_detail(
        self,
        _current_user: CurrentUser,
        _request: GetEvidenceDetailInput,
    ) -> GetEvidenceDetailResult:
        self.calls += 1
        if callable(self.advance):
            self.advance()
        if self.failure is not None:
            raise self.failure
        return self.result


def _harness(
    fixture: AgentToolFixture,
    run: object,
    *,
    context: object | None = None,
    budget: ExecutionBudget | None = None,
) -> HarnessExecutor:
    from app.runtime.context import RunContext
    from app.runtime.trace import RunTrace

    assert isinstance(run, RunTrace)
    trusted_context = context or fixture.context
    assert isinstance(trusted_context, RunContext)
    registry = create_m2_tool_registry()
    return HarnessExecutor(
        context=trusted_context,
        run=run,
        budget=budget
        or ExecutionBudget(
            BudgetLimits(
                max_model_calls=2,
                max_tool_calls=2,
                max_repeat_tool_calls=1,
                total_timeout_ms=20_000,
            )
        ),
        registry=registry,
        permission_guard=PermissionGuard(registry),
        trace_recorder=fixture.recorder,
    )


def _tool(
    fixture: AgentToolFixture,
    run: object,
    service: ControlledEvidenceService,
    *,
    user: CurrentUser | None = None,
    context: object | None = None,
    budget: ExecutionBudget | None = None,
) -> GetEvidenceDetailTool:
    return GetEvidenceDetailTool(
        _harness(fixture, run, context=context, budget=budget),
        cast(EvidenceQueryService, service),
        user or _user(fixture),
    )


def _service() -> ControlledEvidenceService:
    return ControlledEvidenceService(
        GetEvidenceDetailResult(detail=document_evidence_detail())
    )


def test_real_harness_persists_success_trace_and_public_evidence_id(
    agent_tool_fixture: AgentToolFixture,
) -> None:
    fixture = agent_tool_fixture
    service = _service()
    request = GetEvidenceDetailInput(evidence_id=service.result.evidence_id)

    with fixture.recorder.run_scope(fixture.context, "knowledge_query") as run:
        envelope = _tool(fixture, run, service).invoke(request)

    calls = load_calls(fixture, run.id)
    assert envelope.status == "success", envelope.model_dump()
    assert envelope.data == service.result
    assert envelope.evidence_ids == [request.evidence_id]
    assert envelope.meta.tool == "get_evidence_detail"
    assert [(call.permission_result, call.status) for call in calls] == [
        ("allowed", "success")
    ]
    assert calls[0].arguments_summary == {"evidence_id": str(request.evidence_id)}
    assert "tenant" not in str(calls[0].arguments_summary).lower()


def test_role_denial_is_traced_before_evidence_service(
    agent_tool_fixture: AgentToolFixture,
) -> None:
    fixture = agent_tool_fixture
    service = _service()
    denied_context = replace(fixture.context, roles=())

    with fixture.recorder.run_scope(denied_context, "knowledge_query") as run:
        envelope = _tool(
            fixture,
            run,
            service,
            context=denied_context,
        ).invoke(GetEvidenceDetailInput(evidence_id=service.result.evidence_id))

    calls = load_calls(fixture, run.id)
    assert envelope.status == "error"
    assert envelope.error is not None
    assert envelope.error.code == "FORBIDDEN"
    assert service.calls == 0
    assert [(call.permission_result, call.status) for call in calls] == [
        ("denied", "denied")
    ]


def test_bound_identity_mismatch_is_traced_without_evidence_read(
    agent_tool_fixture: AgentToolFixture,
) -> None:
    fixture = agent_tool_fixture
    service = _service()
    mismatched_user = _user(fixture).model_copy(update={"tenant_id": uuid4()})

    with fixture.recorder.run_scope(fixture.context, "knowledge_query") as run:
        envelope = _tool(fixture, run, service, user=mismatched_user).invoke(
            GetEvidenceDetailInput(evidence_id=service.result.evidence_id)
        )

    calls = load_calls(fixture, run.id)
    assert envelope.status == "error"
    assert envelope.error is not None
    assert envelope.error.code == "FORBIDDEN"
    assert envelope.error.field == "tenant_id"
    assert service.calls == 0
    assert [(call.permission_result, call.status) for call in calls] == [
        ("allowed", "error")
    ]


def test_repeated_evidence_call_is_denied_before_second_service_execution(
    agent_tool_fixture: AgentToolFixture,
) -> None:
    fixture = agent_tool_fixture
    service = _service()
    request = GetEvidenceDetailInput(evidence_id=service.result.evidence_id)

    with fixture.recorder.run_scope(fixture.context, "knowledge_query") as run:
        tool = _tool(fixture, run, service)
        first = tool.invoke(request)
        second = tool.invoke(request)

    calls = load_calls(fixture, run.id)
    assert first.status == "success"
    assert second.status == "error"
    assert second.error is not None
    assert second.error.code == "BUDGET_EXCEEDED"
    assert service.calls == 1
    assert [call.status for call in calls] == ["success", "denied"]


@dataclass(slots=True)
class ManualClock:
    value: float = 100.0

    def monotonic(self) -> float:
        return self.value

    def advance_past_evidence_tool_limit(self) -> None:
        self.value += 3.001


def test_evidence_tool_timeout_keeps_safe_trace_status(
    agent_tool_fixture: AgentToolFixture,
) -> None:
    fixture = agent_tool_fixture
    clock = ManualClock()
    service = _service()
    service.advance = clock.advance_past_evidence_tool_limit
    request = GetEvidenceDetailInput(evidence_id=service.result.evidence_id)
    budget = ExecutionBudget(
        BudgetLimits(
            max_model_calls=2,
            max_tool_calls=2,
            max_repeat_tool_calls=1,
            total_timeout_ms=20_000,
        ),
        clock.monotonic,
    )

    with fixture.recorder.run_scope(fixture.context, "knowledge_query") as run:
        envelope = _tool(fixture, run, service, budget=budget).invoke(request)

    calls = load_calls(fixture, run.id)
    assert envelope.status == "error"
    assert envelope.error is not None
    assert envelope.error.code == "BUDGET_EXCEEDED"
    assert [(call.status, call.error_code) for call in calls] == [
        ("timeout", "BUDGET_EXCEEDED")
    ]


def test_known_evidence_error_keeps_safe_trace_status(
    agent_tool_fixture: AgentToolFixture,
) -> None:
    fixture = agent_tool_fixture
    service = _service()
    service.failure = EvidenceNotFoundError()
    request = GetEvidenceDetailInput(evidence_id=service.result.evidence_id)

    with fixture.recorder.run_scope(fixture.context, "knowledge_query") as run:
        envelope = _tool(fixture, run, service).invoke(request)

    calls = load_calls(fixture, run.id)
    assert envelope.status == "error"
    assert envelope.error is not None
    assert envelope.error.code == "EVIDENCE_NOT_FOUND"
    assert envelope.evidence_ids == []
    assert [(call.status, call.error_code) for call in calls] == [
        ("error", "EVIDENCE_NOT_FOUND")
    ]
