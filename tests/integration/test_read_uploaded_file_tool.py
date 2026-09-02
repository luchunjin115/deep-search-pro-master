from __future__ import annotations

from dataclasses import dataclass, replace
from typing import cast
from uuid import UUID, uuid4

from app.core.errors import FileReadLocatorError
from app.runtime.budget import BudgetLimits, ExecutionBudget
from app.runtime.executor import HarnessExecutor
from app.runtime.permissions import PermissionGuard
from app.schemas.auth import CurrentUser
from app.schemas.file_reading import ReadUploadedFileResult
from app.schemas.files import ReadUploadedFileInput
from app.services.file_reading import FileReadingService
from app.tools.read_uploaded_file import ReadUploadedFileTool
from app.tools.registry import create_m2_tool_registry
from tests.integration.test_agent_tools import AgentToolFixture, load_calls

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


def _result(file_id: UUID | None = None) -> ReadUploadedFileResult:
    content = "合成上传文件中的有界内容。"
    return ReadUploadedFileResult(
        file_id=file_id or uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        version_no=1,
        original_name="synthetic-upload.pdf",
        source_type="pdf",
        is_active_version=True,
        sections=[
            {
                "kind": "text",
                "locator": {"source_type": "pdf", "page_number": 1},
                "content": content,
                "truncated": False,
            }
        ],
        total_characters=len(content),
        truncated=False,
        synthetic_data=True,
    )


@dataclass(slots=True)
class ControlledFileService:
    result: ReadUploadedFileResult
    failure: Exception | None = None
    advance: object | None = None
    calls: int = 0

    def read_uploaded_file(
        self,
        _current_user: CurrentUser,
        _request: ReadUploadedFileInput,
    ) -> ReadUploadedFileResult:
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
    service: ControlledFileService,
    *,
    user: CurrentUser | None = None,
    context: object | None = None,
    budget: ExecutionBudget | None = None,
) -> ReadUploadedFileTool:
    return ReadUploadedFileTool(
        _harness(fixture, run, context=context, budget=budget),
        cast(FileReadingService, service),
        user or _user(fixture),
    )


def test_real_harness_persists_success_trace_and_public_arguments(
    agent_tool_fixture: AgentToolFixture,
) -> None:
    fixture = agent_tool_fixture
    file_id = uuid4()
    request = ReadUploadedFileInput(
        file_id=file_id,
        locator={"source_type": "pdf", "page_start": 2, "page_end": 3},
    )
    service = ControlledFileService(_result(file_id))

    with fixture.recorder.run_scope(fixture.context, "knowledge_query") as run:
        envelope = _tool(fixture, run, service).invoke(request)

    calls = load_calls(fixture, run.id)
    assert envelope.status == "success", envelope.model_dump()
    assert envelope.data == service.result
    assert envelope.evidence_ids == []
    assert envelope.meta.tool == "read_uploaded_file"
    assert [(call.permission_result, call.status) for call in calls] == [
        ("allowed", "success")
    ]
    assert calls[0].arguments_summary == {
        "file_id": str(file_id),
        "locator": {
            "page_end": 3,
            "page_start": 2,
            "source_type": "pdf",
        },
    }
    assert "tenant" not in str(calls[0].arguments_summary).lower()
    assert "storage" not in str(calls[0].arguments_summary).lower()


def test_role_denial_is_traced_before_file_service(
    agent_tool_fixture: AgentToolFixture,
) -> None:
    fixture = agent_tool_fixture
    service = ControlledFileService(_result())
    denied_context = replace(fixture.context, roles=())

    with fixture.recorder.run_scope(denied_context, "knowledge_query") as run:
        envelope = _tool(
            fixture,
            run,
            service,
            context=denied_context,
        ).invoke(ReadUploadedFileInput(file_id=uuid4()))

    calls = load_calls(fixture, run.id)
    assert envelope.status == "error"
    assert envelope.error is not None
    assert envelope.error.code == "FORBIDDEN"
    assert service.calls == 0
    assert [(call.permission_result, call.status) for call in calls] == [
        ("denied", "denied")
    ]


def test_bound_identity_mismatch_is_traced_without_file_read(
    agent_tool_fixture: AgentToolFixture,
) -> None:
    fixture = agent_tool_fixture
    service = ControlledFileService(_result())
    mismatched_user = _user(fixture).model_copy(update={"tenant_id": uuid4()})

    with fixture.recorder.run_scope(fixture.context, "knowledge_query") as run:
        envelope = _tool(fixture, run, service, user=mismatched_user).invoke(
            ReadUploadedFileInput(file_id=uuid4())
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


def test_repeated_file_call_is_denied_before_second_service_execution(
    agent_tool_fixture: AgentToolFixture,
) -> None:
    fixture = agent_tool_fixture
    request = ReadUploadedFileInput(file_id=uuid4())
    service = ControlledFileService(_result(request.file_id))

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

    def advance_past_file_tool_limit(self) -> None:
        self.value += 3.001


def test_file_tool_timeout_keeps_safe_trace_status(
    agent_tool_fixture: AgentToolFixture,
) -> None:
    fixture = agent_tool_fixture
    clock = ManualClock()
    timeout_request = ReadUploadedFileInput(file_id=uuid4())
    timed_service = ControlledFileService(
        _result(timeout_request.file_id),
        advance=clock.advance_past_file_tool_limit,
    )
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
        timeout_envelope = _tool(
            fixture,
            run,
            timed_service,
            budget=budget,
        ).invoke(timeout_request)

    timeout_calls = load_calls(fixture, run.id)
    assert timeout_envelope.status == "error"
    assert timeout_envelope.error is not None
    assert timeout_envelope.error.code == "BUDGET_EXCEEDED"
    assert [(call.status, call.error_code) for call in timeout_calls] == [
        ("timeout", "BUDGET_EXCEEDED")
    ]


def test_known_file_error_keeps_safe_trace_status(
    agent_tool_fixture: AgentToolFixture,
) -> None:
    fixture = agent_tool_fixture
    locator_service = ControlledFileService(
        _result(),
        failure=FileReadLocatorError(),
    )
    with fixture.recorder.run_scope(fixture.context, "knowledge_query") as error_run:
        error_envelope = _tool(fixture, error_run, locator_service).invoke(
            ReadUploadedFileInput(file_id=uuid4())
        )

    error_calls = load_calls(fixture, error_run.id)
    assert error_envelope.status == "error"
    assert error_envelope.error is not None
    assert error_envelope.error.code == "VALIDATION_ERROR"
    assert [(call.status, call.error_code) for call in error_calls] == [
        ("error", "VALIDATION_ERROR")
    ]
