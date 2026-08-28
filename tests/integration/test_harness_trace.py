from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.errors import (
    BudgetExceededError,
    MarketPermissionDeniedError,
    ToolExecutionError,
    ToolTimeoutError,
)
from app.db.session import create_database_runtime
from app.models.runtime import AgentRun, Message, Thread, ToolCall
from app.repositories.identity import IdentityRepository
from app.runtime.budget import BudgetLimits, ExecutionBudget
from app.runtime.context import RunContext, build_run_context
from app.runtime.executor import HarnessExecutor, ToolExecutionContext
from app.runtime.permissions import PermissionGuard
from app.runtime.trace import TraceRecorder
from app.schemas.auth import LoginRequest
from app.schemas.inventory import SearchInventoryInput
from app.services.auth import AuthService
from app.tools.registry import create_m1_tool_registry
from scripts.seed_m1 import seed_m1


@dataclass(slots=True)
class ManualClock:
    monotonic_value: float = 100.0
    wall_origin: datetime = datetime(2026, 8, 28, 8, 0, tzinfo=UTC)

    def monotonic(self) -> float:
        return self.monotonic_value

    def now(self) -> datetime:
        return self.wall_origin + timedelta(seconds=self.monotonic_value - 100.0)

    def advance_ms(self, milliseconds: int) -> None:
        self.monotonic_value += milliseconds / 1000


@dataclass(frozen=True, slots=True)
class HarnessFixture:
    session_factory: sessionmaker[Session]
    context: RunContext
    recorder: TraceRecorder
    clock: ManualClock
    thread_id: UUID


@pytest.fixture
def harness_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Generator[HarnessFixture, None, None]:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=".env.example",
        app_env="test",
    )
    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    seed_m1(settings, manifest_path=tmp_path / "m1_manifest.json")
    runtime = create_database_runtime(settings)
    session_factory = runtime.session_factory

    with session_factory() as auth_session:
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
    with session_factory.begin() as setup_session:
        setup_session.add(
            Thread(
                id=thread_id,
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                title="M1-14 Harness Trace Test",
            )
        )

    runtime_context = build_run_context(user, thread_id, trace_id=uuid4())
    clock = ManualClock()
    recorder = TraceRecorder(
        session_factory,
        monotonic=clock.monotonic,
        now=clock.now,
    )
    try:
        yield HarnessFixture(
            session_factory=session_factory,
            context=runtime_context,
            recorder=recorder,
            clock=clock,
            thread_id=thread_id,
        )
    finally:
        with session_factory.begin() as cleanup_session:
            cleanup_session.execute(delete(Thread).where(Thread.id == thread_id))
        runtime.engine.dispose()


def executor(
    fixture: HarnessFixture,
    run: object,
    limits: BudgetLimits | None = None,
) -> HarnessExecutor:
    from app.runtime.trace import RunTrace

    assert isinstance(run, RunTrace)
    registry = create_m1_tool_registry()
    return HarnessExecutor(
        context=fixture.context,
        run=run,
        budget=ExecutionBudget(
            limits
            or BudgetLimits(
                max_model_calls=2,
                max_tool_calls=2,
                max_repeat_tool_calls=1,
                total_timeout_ms=8_000,
            ),
            fixture.clock.monotonic,
        ),
        registry=registry,
        permission_guard=PermissionGuard(registry),
        trace_recorder=fixture.recorder,
    )


def inventory_input(
    market_code: str = "DE",
    warehouse_code: str = "DE-FRA",
) -> SearchInventoryInput:
    return SearchInventoryInput(
        sku="LR-TL-MUSH-OR01",
        market_code=market_code,  # type: ignore[arg-type]
        warehouse_code=warehouse_code,  # type: ignore[arg-type]
    )


def load_trace(fixture: HarnessFixture) -> tuple[AgentRun, list[ToolCall]]:
    with fixture.session_factory() as session:
        run = session.scalar(
            select(AgentRun).where(AgentRun.trace_id == fixture.context.trace_id)
        )
        assert run is not None
        session.expunge(run)
        calls = list(
            session.scalars(
                select(ToolCall)
                .where(ToolCall.agent_run_id == run.id)
                .order_by(ToolCall.sequence_no)
            )
        )
        for call in calls:
            session.expunge(call)
    return run, calls


def test_success_trace_records_model_tool_permission_and_duration(
    harness_fixture: HarnessFixture,
) -> None:
    fixture = harness_fixture

    with fixture.recorder.run_scope(fixture.context, "inventory_query") as run:
        harness = executor(fixture, run)
        harness.reserve_model_call()

        def operation(context: ToolExecutionContext) -> dict[str, object]:
            fixture.clock.advance_ms(25)
            return {"tool_call_id": str(context.tool_call_id), "available": 125}

        result = harness.execute_tool(
            "search_inventory",
            inventory_input(),
            target_tenant_id=fixture.context.tenant_id,
            operation=operation,
        )
        assert result.data["available"] == 125
        assert result.context.agent_run_id == run.id

    run_row, calls = load_trace(fixture)
    assert run_row.status == "completed"
    assert run_row.model_call_count == 1
    assert run_row.tool_call_count == 1
    assert run_row.duration_ms == 25
    assert run_row.error_code is None
    assert len(calls) == 1
    assert calls[0].permission_result == "allowed"
    assert calls[0].status == "success"
    assert calls[0].duration_ms == 25
    assert calls[0].arguments_summary == {
        "market_code": "DE",
        "sku": "LR-TL-MUSH-OR01",
        "warehouse_code": "DE-FRA",
    }


def test_permission_denial_is_traced_before_operation(
    harness_fixture: HarnessFixture,
) -> None:
    fixture = harness_fixture
    operation_calls: list[str] = []

    with (
        pytest.raises(MarketPermissionDeniedError),
        fixture.recorder.run_scope(fixture.context, "inventory_query") as run,
    ):
        harness = executor(fixture, run)
        harness.execute_tool(
            "search_inventory",
            inventory_input("FR", "FR-CDG"),
            target_tenant_id=fixture.context.tenant_id,
            operation=lambda _context: operation_calls.append("called"),
        )

    run_row, calls = load_trace(fixture)
    assert operation_calls == []
    assert run_row.status == "denied"
    assert run_row.error_code == "FORBIDDEN"
    assert run_row.tool_call_count == 1
    assert len(calls) == 1
    assert calls[0].permission_result == "denied"
    assert calls[0].status == "denied"
    assert calls[0].error_code == "FORBIDDEN"


def test_repeat_and_model_limits_are_traced_without_extra_execution(
    harness_fixture: HarnessFixture,
) -> None:
    fixture = harness_fixture
    operation_count = 0

    def operation(_context: ToolExecutionContext) -> str:
        nonlocal operation_count
        operation_count += 1
        return "ok"

    with (
        pytest.raises(BudgetExceededError) as captured,
        fixture.recorder.run_scope(fixture.context, "inventory_query") as run,
    ):
        harness = executor(fixture, run)
        harness.execute_tool(
            "search_inventory",
            inventory_input(),
            target_tenant_id=fixture.context.tenant_id,
            operation=operation,
        )
        harness.execute_tool(
            "search_inventory",
            inventory_input(),
            target_tenant_id=fixture.context.tenant_id,
            operation=operation,
        )

    assert captured.value.reason == "repeated_tool_call"
    run_row, calls = load_trace(fixture)
    assert operation_count == 1
    assert run_row.status == "failed"
    assert run_row.error_code == "BUDGET_EXCEEDED"
    assert run_row.tool_call_count == 2
    assert [call.status for call in calls] == ["success", "denied"]
    assert calls[1].error_code == "BUDGET_EXCEEDED"


def test_model_limit_finishes_run_without_tool_call(
    harness_fixture: HarnessFixture,
) -> None:
    fixture = harness_fixture
    model_limits = BudgetLimits(
        max_model_calls=1,
        max_tool_calls=2,
        max_repeat_tool_calls=1,
        total_timeout_ms=8_000,
    )

    with (
        pytest.raises(BudgetExceededError) as captured,
        fixture.recorder.run_scope(fixture.context, "inventory_query") as run,
    ):
        harness = executor(fixture, run, model_limits)
        harness.reserve_model_call()
        harness.reserve_model_call()

    assert captured.value.reason == "model_call_limit"
    run_row, calls = load_trace(fixture)
    assert run_row.status == "failed"
    assert run_row.model_call_count == 1
    assert run_row.tool_call_count == 0
    assert calls == []


def test_tool_timeout_is_traced_and_result_is_not_returned(
    harness_fixture: HarnessFixture,
) -> None:
    fixture = harness_fixture

    with (
        pytest.raises(ToolTimeoutError),
        fixture.recorder.run_scope(fixture.context, "inventory_query") as run,
    ):
        harness = executor(fixture, run)

        def slow_operation(_context: ToolExecutionContext) -> int:
            fixture.clock.advance_ms(3_001)
            return 125

        harness.execute_tool(
            "search_inventory",
            inventory_input(),
            target_tenant_id=fixture.context.tenant_id,
            operation=slow_operation,
        )

    run_row, calls = load_trace(fixture)
    assert run_row.status == "timed_out"
    assert run_row.error_code == "BUDGET_EXCEEDED"
    assert calls[0].status == "timeout"
    assert calls[0].duration_ms == 3_001


def test_total_deadline_is_traced_before_operation(
    harness_fixture: HarnessFixture,
) -> None:
    fixture = harness_fixture
    operation_calls: list[str] = []

    with (
        pytest.raises(BudgetExceededError) as captured,
        fixture.recorder.run_scope(fixture.context, "inventory_query") as run,
    ):
        harness = executor(fixture, run)
        fixture.clock.advance_ms(8_000)
        harness.execute_tool(
            "search_inventory",
            inventory_input(),
            target_tenant_id=fixture.context.tenant_id,
            operation=lambda _context: operation_calls.append("called"),
        )

    assert captured.value.reason == "total_timeout"
    run_row, calls = load_trace(fixture)
    assert operation_calls == []
    assert run_row.status == "timed_out"
    assert run_row.error_code == "BUDGET_EXCEEDED"
    assert calls[0].permission_result == "denied"
    assert calls[0].status == "timeout"
    assert calls[0].error_code == "BUDGET_EXCEEDED"


def test_unknown_failure_is_sanitized_and_audit_survives_business_rollback(
    harness_fixture: HarnessFixture,
) -> None:
    fixture = harness_fixture
    business_session = fixture.session_factory()

    def failing_operation(_context: ToolExecutionContext) -> None:
        business_session.add(
            Message(
                tenant_id=fixture.context.tenant_id,
                thread_id=fixture.thread_id,
                role="user",
                content_summary="temporary message",
            )
        )
        business_session.flush()
        raise RuntimeError("password=must-not-leak; SELECT secret")

    try:
        with (
            pytest.raises(ToolExecutionError),
            fixture.recorder.run_scope(
                fixture.context,
                "inventory_query",
            ) as run,
        ):
            harness = executor(fixture, run)
            harness.execute_tool(
                "search_inventory",
                {
                    "sku": "LR-TL-MUSH-OR01",
                    "market_code": "DE",
                    "password": "must-not-leak",
                    "sql": "SELECT secret",
                },
                target_tenant_id=fixture.context.tenant_id,
                operation=failing_operation,
            )
        business_session.rollback()
    finally:
        business_session.close()

    run_row, calls = load_trace(fixture)
    with fixture.session_factory() as session:
        message_count = session.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.thread_id == fixture.thread_id)
        )
    assert message_count == 0
    assert run_row.status == "failed"
    assert run_row.error_code == "INTERNAL_ERROR"
    assert run_row.error_message == "Tool执行失败"
    assert calls[0].status == "error"
    assert calls[0].arguments_summary["password"] == "[REDACTED]"
    assert calls[0].arguments_summary["sql"] == "[REDACTED]"
    serialized = str(calls[0].arguments_summary)
    assert "must-not-leak" not in serialized
    assert "SELECT secret" not in serialized
