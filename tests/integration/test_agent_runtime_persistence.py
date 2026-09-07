from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError

from app.agents.engineered_state import EngineeredAgentState
from app.agents.runtime.contracts import WorkerRunTrace
from app.core.config import Settings
from app.core.errors import (
    AgentCheckpointConflictError,
    AgentCheckpointNotFoundError,
    AgentRuntimePersistenceError,
    AgentTaskConflictError,
)
from app.db.session import DatabaseRuntime, create_database_runtime
from app.models.identity import Tenant, User
from app.models.runtime import (
    AgentAnswerEvidence,
    AgentCheckpoint,
    AgentRun,
    AgentTaskDependency,
    AgentTaskRecord,
    Evidence,
    Thread,
    ToolCall,
)
from app.repositories.agent_runtime import AgentRuntimeRepository
from app.schemas.agent import (
    AgentTask,
    BoundedJsonObject,
    EvidenceRequirement,
    ResourceUsage,
    TaskAssignment,
    TaskPlan,
    WorkerResult,
)
from app.schemas.auth import CurrentUser
from app.schemas.evidence import AnswerEvidenceMapping, AnswerEvidenceReference
from app.services.agent_runtime import AgentRuntimePersistenceService


@dataclass(frozen=True, slots=True)
class RuntimePersistenceFixture:
    settings: Settings
    runtime: DatabaseRuntime
    user: CurrentUser
    other_user: CurrentUser
    other_tenant_user: CurrentUser
    thread_id: UUID
    other_thread_id: UUID


@pytest.fixture
def runtime_persistence_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[RuntimePersistenceFixture, None, None]:
    settings = Settings(_env_file=".env.example", app_env="test")
    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    command.upgrade(Config("alembic.ini"), "head")
    runtime = create_database_runtime(settings)

    tenant_id = uuid4()
    other_tenant_id = uuid4()
    user_id = uuid4()
    other_user_id = uuid4()
    other_tenant_user_id = uuid4()
    thread_id = uuid4()
    other_thread_id = uuid4()
    with runtime.session_factory.begin() as session:
        session.add_all(
            [
                Tenant(id=tenant_id, name="M2-21.9 persistence tenant"),
                Tenant(id=other_tenant_id, name="M2-21.9 other tenant"),
            ]
        )
        session.flush()
        session.add_all(
            [
                User(
                    id=user_id,
                    tenant_id=tenant_id,
                    email="agent-runtime@example.com",
                    display_name="Agent Runtime",
                    password_hash="$argon2id$test-only",
                ),
                User(
                    id=other_user_id,
                    tenant_id=tenant_id,
                    email="other-agent-runtime@example.com",
                    display_name="Other Agent Runtime",
                    password_hash="$argon2id$test-only",
                ),
                User(
                    id=other_tenant_user_id,
                    tenant_id=other_tenant_id,
                    email="cross-tenant-agent-runtime@example.com",
                    display_name="Cross Tenant Agent Runtime",
                    password_hash="$argon2id$test-only",
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                Thread(
                    id=thread_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    title="M2-21.9 root thread",
                ),
                Thread(
                    id=other_thread_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    title="M2-21.9 other thread",
                ),
            ]
        )

    def current_user(uid: UUID, tid: UUID, email: str) -> CurrentUser:
        return CurrentUser(
            user_id=uid,
            tenant_id=tid,
            email=email,
            display_name="Runtime Test",
            roles=["company_owner"],
            market_scopes=["DE"],
        )

    try:
        yield RuntimePersistenceFixture(
            settings=settings,
            runtime=runtime,
            user=current_user(user_id, tenant_id, "agent-runtime@example.com"),
            other_user=current_user(
                other_user_id,
                tenant_id,
                "other-agent-runtime@example.com",
            ),
            other_tenant_user=current_user(
                other_tenant_user_id,
                other_tenant_id,
                "cross-tenant-agent-runtime@example.com",
            ),
            thread_id=thread_id,
            other_thread_id=other_thread_id,
        )
    finally:
        with runtime.session_factory.begin() as session:
            session.execute(
                delete(Tenant).where(Tenant.id.in_([tenant_id, other_tenant_id]))
            )
        runtime.engine.dispose()


def _plan() -> TaskPlan:
    return TaskPlan(
        plan_id=uuid4(),
        goal="先查业务库存，再核对知识文档",
        tasks=[
            AgentTask(
                task_id="business_lookup",
                goal="查询业务库存",
                required_capabilities=["search_inventory"],
                assignment=TaskAssignment(
                    status="assigned",
                    worker_id="business_data",
                ),
                completion_criteria=["返回库存事实"],
                evidence_requirement=EvidenceRequirement(
                    required=True,
                    minimum_count=1,
                    source_types=["database"],
                ),
                failure_impact="blocks_dependents",
            ),
            AgentTask(
                task_id="knowledge_lookup",
                goal="查询知识证据",
                depends_on=["business_lookup"],
                required_capabilities=["search_knowledge"],
                assignment=TaskAssignment(
                    status="assigned",
                    worker_id="knowledge",
                ),
                completion_criteria=["返回文档事实"],
                evidence_requirement=EvidenceRequirement(
                    required=True,
                    minimum_count=1,
                    source_types=["document"],
                ),
                failure_impact="allows_partial",
            ),
        ],
    )


def _completed_result(task_id: str, worker_id: str) -> WorkerResult:
    return WorkerResult(
        task_id=task_id,
        worker_id=worker_id,
        execution_status="completed",
        business_outcome="answered",
        business_result=BoundedJsonObject({"status": "verified"}),
        public_summary=f"{task_id} 已完成",
        resource_usage=ResourceUsage(
            model_calls=1,
            tool_calls=1,
            input_tokens=120,
            output_tokens=40,
            duration_ms=15,
        ),
    )


def _service(
    fixture: RuntimePersistenceFixture,
    session: object,
) -> AgentRuntimePersistenceService:
    return AgentRuntimePersistenceService(
        AgentRuntimeRepository(
            session,  # type: ignore[arg-type]
            fixture.settings.database_statement_timeout_ms,
        )
    )


def test_persists_run_tree_task_board_checkpoint_and_answer_evidence(
    runtime_persistence_fixture: RuntimePersistenceFixture,
) -> None:
    fixture = runtime_persistence_fixture
    plan = _plan()
    root_run_id = uuid4()
    trace_id = uuid4()
    evidence_id = uuid4()

    with fixture.runtime.session_factory.begin() as session:
        service = _service(fixture, session)
        root = service.start_root_run(
            fixture.user,
            thread_id=fixture.thread_id,
            run_id=root_run_id,
            trace_id=trace_id,
            plan=plan,
        )
        assert root.root_run_id == root_run_id
        assert root.run_kind == "supervisor"

        tasks = list(
            session.scalars(
                select(AgentTaskRecord)
                .where(AgentTaskRecord.root_run_id == root_run_id)
                .order_by(AgentTaskRecord.sequence_no)
            )
        )
        dependencies = list(
            session.scalars(
                select(AgentTaskDependency).where(
                    AgentTaskDependency.root_run_id == root_run_id
                )
            )
        )
        assert [task.task_id for task in tasks] == [
            "business_lookup",
            "knowledge_lookup",
        ]
        assert [(edge.task_id, edge.depends_on_task_id) for edge in dependencies] == [
            ("knowledge_lookup", "business_lookup")
        ]

        business_trace = WorkerRunTrace(
            run_id=uuid4(),
            parent_run_id=root_run_id,
            root_run_id=root_run_id,
            trace_id=trace_id,
            budget_ref=uuid4(),
            depth=1,
        )
        service.start_worker_run(
            fixture.user,
            thread_id=fixture.thread_id,
            worker_run=business_trace,
            task_id="business_lookup",
            worker_id="business_data",
        )
        service.record_worker_result(
            fixture.user,
            thread_id=fixture.thread_id,
            root_run_id=root_run_id,
            worker_run_id=business_trace.run_id,
            result=_completed_result("business_lookup", "business_data"),
            expected_task_version=2,
        )
        with pytest.raises(AgentTaskConflictError):
            service.record_worker_result(
                fixture.user,
                thread_id=fixture.thread_id,
                root_run_id=root_run_id,
                worker_run_id=business_trace.run_id,
                result=_completed_result("business_lookup", "business_data"),
                expected_task_version=2,
            )

        tool_call = ToolCall(
            tenant_id=fixture.user.tenant_id,
            agent_run_id=business_trace.run_id,
            sequence_no=1,
            tool_name="search_inventory",
            tool_version="1.0.0",
            arguments_summary={"sku": "LR-TL-MUSH-OR01", "market_code": "DE"},
            permission_result="allowed",
            status="success",
        )
        session.add(tool_call)
        session.flush()
        session.add(
            Evidence(
                id=evidence_id,
                tenant_id=fixture.user.tenant_id,
                agent_run_id=business_trace.run_id,
                tool_call_id=tool_call.id,
                source_type="database",
                source_name="synthetic_inventory",
                source_locator=f"inventory_snapshots/{uuid4()}",
                title="德国仓库存",
                excerpt="可售库存 42",
                query_summary={"sku": "LR-TL-MUSH-OR01", "market_code": "DE"},
                structured_data={"available_quantity": 42},
                observed_at=datetime.now(UTC),
                access_scope={
                    "tenant_id": str(fixture.user.tenant_id),
                    "market_codes": ["DE"],
                },
            )
        )
        session.flush()

        knowledge_trace = WorkerRunTrace(
            run_id=uuid4(),
            parent_run_id=root_run_id,
            root_run_id=root_run_id,
            trace_id=trace_id,
            budget_ref=uuid4(),
            depth=1,
        )
        service.start_worker_run(
            fixture.user,
            thread_id=fixture.thread_id,
            worker_run=knowledge_trace,
            task_id="knowledge_lookup",
            worker_id="knowledge",
        )
        service.record_worker_result(
            fixture.user,
            thread_id=fixture.thread_id,
            root_run_id=root_run_id,
            worker_run_id=knowledge_trace.run_id,
            result=_completed_result("knowledge_lookup", "knowledge"),
            expected_task_version=2,
        )

        state = EngineeredAgentState(
            run_id=root_run_id,
            goal=plan.goal,
            public_context={"market": "DE"},
            plan=plan,
            execution_status="completed",
            business_outcome="answered",
            evidence_ids=[evidence_id],
            public_summary="库存和知识核对完成",
            stop_reason="finished",
            resource_usage=ResourceUsage(
                model_calls=2,
                tool_calls=2,
                input_tokens=240,
                output_tokens=80,
                duration_ms=30,
            ),
        )
        checkpoint = service.save_checkpoint(
            fixture.user,
            thread_id=fixture.thread_id,
            state=state,
            expected_version=0,
        )
        assert checkpoint.checkpoint_version == 1
        with pytest.raises(AgentCheckpointConflictError):
            service.save_checkpoint(
                fixture.user,
                thread_id=fixture.thread_id,
                state=state,
                expected_version=0,
            )

        loaded = service.load_latest_checkpoint(
            fixture.user,
            thread_id=fixture.thread_id,
            root_run_id=root_run_id,
        )
        assert loaded.state == state
        assert loaded.checkpoint_version == 1

        checkpoint_row = session.scalar(
            select(AgentCheckpoint).where(AgentCheckpoint.root_run_id == root_run_id)
        )
        assert checkpoint_row is not None
        savepoint = session.begin_nested()
        checkpoint_row.state_json = {
            **checkpoint_row.state_json,
            "goal": "被篡改但未重算哈希的目标",
        }
        session.flush()
        with pytest.raises(AgentRuntimePersistenceError):
            service.load_latest_checkpoint(
                fixture.user,
                thread_id=fixture.thread_id,
                root_run_id=root_run_id,
            )
        savepoint.rollback()
        session.expire_all()

        mapping = AnswerEvidenceMapping(
            root_run_id=root_run_id,
            references=[
                AnswerEvidenceReference(
                    citation_label="[E1]",
                    evidence_id=evidence_id,
                )
            ],
        )
        service.save_answer_evidence(
            fixture.user,
            thread_id=fixture.thread_id,
            mapping=mapping,
        )
        assert (
            service.load_answer_evidence(
                fixture.user,
                thread_id=fixture.thread_id,
                root_run_id=root_run_id,
            )
            == mapping
        )

        child_runs = list(
            session.scalars(
                select(AgentRun).where(
                    AgentRun.root_run_id == root_run_id,
                    AgentRun.run_kind == "worker",
                )
            )
        )
        assert len(child_runs) == 2
        assert {child.trace_id for child in child_runs} == {trace_id}
        assert session.scalar(
            select(AgentCheckpoint).where(AgentCheckpoint.root_run_id == root_run_id)
        )
        assert session.scalar(
            select(AgentAnswerEvidence).where(
                AgentAnswerEvidence.root_run_id == root_run_id
            )
        )

    for user, thread_id in (
        (fixture.other_user, fixture.thread_id),
        (fixture.other_tenant_user, fixture.thread_id),
        (fixture.user, fixture.other_thread_id),
    ):
        with (
            fixture.runtime.session_factory() as session,
            pytest.raises(AgentCheckpointNotFoundError),
        ):
            _service(fixture, session).load_latest_checkpoint(
                user,
                thread_id=thread_id,
                root_run_id=root_run_id,
            )


def test_database_rejects_missing_self_and_cyclic_task_dependencies(
    runtime_persistence_fixture: RuntimePersistenceFixture,
) -> None:
    fixture = runtime_persistence_fixture
    root_run_id = uuid4()
    with fixture.runtime.session_factory.begin() as session:
        service = _service(fixture, session)
        service.start_root_run(
            fixture.user,
            thread_id=fixture.thread_id,
            run_id=root_run_id,
            trace_id=uuid4(),
            plan=_plan(),
        )

        invalid_edges = [
            AgentTaskDependency(
                tenant_id=fixture.user.tenant_id,
                root_run_id=root_run_id,
                task_id="business_lookup",
                depends_on_task_id="missing_task",
            ),
            AgentTaskDependency(
                tenant_id=fixture.user.tenant_id,
                root_run_id=root_run_id,
                task_id="business_lookup",
                depends_on_task_id="business_lookup",
            ),
            AgentTaskDependency(
                tenant_id=fixture.user.tenant_id,
                root_run_id=root_run_id,
                task_id="business_lookup",
                depends_on_task_id="knowledge_lookup",
            ),
        ]
        for edge in invalid_edges:
            with pytest.raises(SQLAlchemyError), session.begin_nested():
                session.add(edge)
                session.flush()
