from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.session import DatabaseRuntime, create_database_runtime
from app.models.runtime import AgentRun, Evidence, Thread, ToolCall
from app.repositories.identity import IdentityRepository
from app.repositories.inventory import InventoryRepository
from app.repositories.product import ProductRepository
from app.runtime.budget import BudgetLimits, ExecutionBudget
from app.runtime.context import RunContext, build_run_context
from app.runtime.executor import HarnessExecutor
from app.runtime.permissions import PermissionGuard
from app.runtime.trace import TraceRecorder
from app.schemas.auth import LoginRequest
from app.schemas.inventory import SearchInventoryInput
from app.schemas.product import GetProductSpecInput
from app.services.auth import AuthService
from app.services.evidence import EvidenceService
from app.services.inventory import InventoryService
from app.services.product import ProductSpecService
from app.tools.get_product_spec import GetProductSpecTool
from app.tools.registry import create_m1_tool_registry
from app.tools.search_inventory import SearchInventoryTool
from scripts.seed_m1 import seed_m1


@dataclass(frozen=True, slots=True)
class AgentToolFixture:
    settings: Settings
    runtime: DatabaseRuntime
    session_factory: sessionmaker[Session]
    business_session: Session
    context: RunContext
    recorder: TraceRecorder
    thread_id: UUID


@pytest.fixture
def agent_tool_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Generator[AgentToolFixture, None, None]:
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
    with runtime.session_factory.begin() as setup_session:
        setup_session.add(
            Thread(
                id=thread_id,
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                title="M1-15 Agent Tool Test",
            )
        )

    business_session = runtime.session_factory()
    try:
        yield AgentToolFixture(
            settings=settings,
            runtime=runtime,
            session_factory=runtime.session_factory,
            business_session=business_session,
            context=build_run_context(user, thread_id, trace_id=uuid4()),
            recorder=TraceRecorder(runtime.session_factory),
            thread_id=thread_id,
        )
    finally:
        business_session.rollback()
        business_session.close()
        with runtime.session_factory.begin() as cleanup_session:
            cleanup_session.execute(delete(Thread).where(Thread.id == thread_id))
        runtime.engine.dispose()


def harness(fixture: AgentToolFixture, run: object) -> HarnessExecutor:
    from app.runtime.trace import RunTrace

    assert isinstance(run, RunTrace)
    registry = create_m1_tool_registry()
    return HarnessExecutor(
        context=fixture.context,
        run=run,
        budget=ExecutionBudget(
            BudgetLimits(
                max_model_calls=2,
                max_tool_calls=2,
                max_repeat_tool_calls=1,
                total_timeout_ms=8_000,
            )
        ),
        registry=registry,
        permission_guard=PermissionGuard(registry),
        trace_recorder=fixture.recorder,
    )


def load_calls(fixture: AgentToolFixture, run_id: UUID) -> list[ToolCall]:
    with fixture.session_factory() as session:
        calls = list(
            session.scalars(
                select(ToolCall)
                .where(ToolCall.agent_run_id == run_id)
                .order_by(ToolCall.sequence_no)
            )
        )
        for call in calls:
            session.expunge(call)
        return calls


def test_get_product_spec_tool_uses_harness_and_real_service(
    agent_tool_fixture: AgentToolFixture,
) -> None:
    fixture = agent_tool_fixture
    with fixture.recorder.run_scope(fixture.context, "product_spec") as run:
        tool = GetProductSpecTool(
            harness(fixture, run),
            ProductSpecService(
                ProductRepository(
                    fixture.business_session,
                    fixture.settings.database_statement_timeout_ms,
                )
            ),
        )
        envelope = tool.invoke(GetProductSpecInput(product_query="LR-TL-MUSH-OR01"))
        fixture.business_session.commit()

    assert envelope.status == "success"
    assert envelope.data is not None
    assert envelope.data.sku == "LR-TL-MUSH-OR01"
    assert envelope.data.synthetic_data is True
    assert envelope.evidence_ids == []
    assert envelope.meta.tool == "get_product_spec"
    assert envelope.meta.version == "1.0.0"
    assert envelope.meta.source_time is None
    assert envelope.meta.trace_id == fixture.context.trace_id
    calls = load_calls(fixture, run.id)
    assert [
        (call.tool_name, call.permission_result, call.status) for call in calls
    ] == [("get_product_spec", "allowed", "success")]


def test_search_inventory_tool_returns_data_time_and_persisted_evidence(
    agent_tool_fixture: AgentToolFixture,
) -> None:
    fixture = agent_tool_fixture
    with fixture.recorder.run_scope(fixture.context, "inventory_query") as run:
        tool = SearchInventoryTool(
            harness(fixture, run),
            InventoryService(
                InventoryRepository(
                    fixture.business_session,
                    fixture.settings.database_statement_timeout_ms,
                ),
                EvidenceService(fixture.business_session),
            ),
        )
        envelope = tool.invoke(
            SearchInventoryInput(
                sku="LR-TL-MUSH-OR01",
                market_code="DE",
                warehouse_code="DE-FRA",
            )
        )
        fixture.business_session.commit()

    assert envelope.status == "success"
    assert envelope.data is not None
    assert envelope.data.available == 125
    assert envelope.data.synthetic_data is True
    assert envelope.meta.source_time == envelope.data.snapshot_at
    assert len(envelope.evidence_ids) == 1
    with fixture.session_factory() as session:
        evidence = session.get(Evidence, envelope.evidence_ids[0])
        assert evidence is not None
        assert evidence.agent_run_id == run.id
        assert evidence.tool_call_id == load_calls(fixture, run.id)[0].id
        assert evidence.structured_data["available"] == 125
        assert evidence.synthetic_data is True


def test_search_inventory_tool_blocks_out_of_scope_market_before_service(
    agent_tool_fixture: AgentToolFixture,
) -> None:
    fixture = agent_tool_fixture
    with fixture.recorder.run_scope(fixture.context, "inventory_query") as run:
        tool = SearchInventoryTool(
            harness(fixture, run),
            InventoryService(
                InventoryRepository(fixture.business_session),
                EvidenceService(fixture.business_session),
            ),
        )
        envelope = tool.invoke(
            SearchInventoryInput(
                sku="LR-TL-MUSH-OR01",
                market_code="FR",
                warehouse_code="FR-CDG",
            )
        )
        fixture.business_session.rollback()

    assert envelope.status == "error"
    assert envelope.error is not None
    assert envelope.error.code == "FORBIDDEN"
    assert envelope.error.field == "market_code"
    assert envelope.evidence_ids == []
    calls = load_calls(fixture, run.id)
    assert [(call.permission_result, call.status) for call in calls] == [
        ("denied", "denied")
    ]
    with fixture.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Evidence)) == 0


def test_search_inventory_tool_returns_safe_business_error_without_evidence(
    agent_tool_fixture: AgentToolFixture,
) -> None:
    fixture = agent_tool_fixture
    with fixture.recorder.run_scope(fixture.context, "inventory_query") as run:
        tool = SearchInventoryTool(
            harness(fixture, run),
            InventoryService(
                InventoryRepository(fixture.business_session),
                EvidenceService(fixture.business_session),
            ),
        )
        envelope = tool.invoke(
            SearchInventoryInput(
                sku="NOT-FOUND-SKU",
                market_code="DE",
                warehouse_code="DE-FRA",
            )
        )
        fixture.business_session.rollback()

    assert envelope.status == "error"
    assert envelope.error is not None
    assert envelope.error.code == "INVENTORY_NOT_FOUND"
    assert envelope.evidence_ids == []
    calls = load_calls(fixture, run.id)
    assert [
        (call.permission_result, call.status, call.error_code) for call in calls
    ] == [("allowed", "error", "INVENTORY_NOT_FOUND")]


def test_unknown_inventory_service_failure_is_sanitized(
    agent_tool_fixture: AgentToolFixture,
) -> None:
    class BrokenInventoryService:
        def search_inventory(self, *_args: object) -> None:
            raise RuntimeError("password=secret SQL=DROP TABLE inventory_snapshots")

    fixture = agent_tool_fixture
    with fixture.recorder.run_scope(fixture.context, "inventory_query") as run:
        tool = SearchInventoryTool(
            harness(fixture, run),
            cast(InventoryService, BrokenInventoryService()),
        )
        envelope = tool.invoke(
            SearchInventoryInput(
                sku="LR-TL-MUSH-OR01",
                market_code="DE",
                warehouse_code="DE-FRA",
            )
        )

    assert envelope.status == "error"
    assert envelope.error is not None
    assert envelope.error.model_dump() == {
        "code": "INTERNAL_ERROR",
        "message": "Tool执行失败",
        "retryable": False,
        "field": None,
    }
    serialized = envelope.model_dump_json()
    calls = load_calls(fixture, run.id)
    assert "secret" not in serialized
    assert "DROP TABLE" not in serialized
    assert calls[0].error_message == "Tool执行失败"
    assert "secret" not in (calls[0].error_message or "")
    assert "DROP TABLE" not in (calls[0].error_message or "")


def test_two_formal_tools_are_the_only_registered_agent_tools(
    agent_tool_fixture: AgentToolFixture,
) -> None:
    registry = create_m1_tool_registry()
    assert registry.names == ("get_product_spec", "search_inventory")
    assert [definition.version for definition in registry.list_definitions()] == [
        "1.0.0",
        "1.0.0",
    ]
    assert [definition.timeout_ms for definition in registry.list_definitions()] == [
        3_000,
        3_000,
    ]

    with agent_tool_fixture.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(AgentRun)) == 0
