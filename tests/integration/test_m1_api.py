from __future__ import annotations

import hashlib
import io
from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.exc import OperationalError

from app.api.dependencies import get_engineered_agent_provider
from app.core.config import Settings
from app.core.errors import ProviderTimeoutError
from app.db.session import DatabaseRuntime, create_database_runtime
from app.llm.agent_schemas import PlannerRequest
from app.main import create_app
from app.models.catalog import Product, ProductVariant
from app.models.identity import User
from app.models.inventory import InventorySnapshot, Warehouse
from app.models.knowledge import Document, DocumentVersion, StoredFile
from app.models.runtime import (
    AgentAnswerEvidence,
    AgentCheckpoint,
    AgentRun,
    Message,
    Thread,
    ToolCall,
)
from app.repositories.inventory import InventoryRepository
from app.schemas.auth import CurrentUser
from app.services.documents.parser_service import DocumentParserService
from app.services.storage import LocalStorageBackend
from scripts.seed_m1 import seed_m1
from tests.fixtures.agent_gateway_provider import (
    CrossWorkerGatewayProvider,
    InventoryGatewayProvider,
    KnowledgeGatewayProvider,
    ResumableInventoryGatewayProvider,
    ResumableKnowledgeGatewayProvider,
)
from tests.fixtures.pdf_factory import make_text_pdf

DE_EMAIL = "de.operator@demo.deepsearch.local"
FR_EMAIL = "fr.operator@demo.deepsearch.local"
PASSWORD = "M1-demo-only-change-me"


@dataclass(frozen=True, slots=True)
class ApiFixture:
    client: TestClient
    runtime: DatabaseRuntime
    application: FastAPI
    knowledge_file_id: UUID


@pytest.fixture(scope="module")
def api_fixture(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[ApiFixture, None, None]:
    fixture_root = tmp_path_factory.mktemp("m1_api")
    settings = Settings(  # type: ignore[call-arg]
        _env_file=".env.example",
        app_env="test",
        local_storage_root=fixture_root / "storage",
    )
    seed_m1(
        settings,
        manifest_path=fixture_root / "manifest.json",
    )
    runtime = create_database_runtime(settings)
    storage = LocalStorageBackend(settings.local_storage_root)
    document_id = uuid4()
    version_id = uuid4()
    file_id = uuid4()
    source = make_text_pdf(include_empty_page=False)
    source_sha256 = hashlib.sha256(source).hexdigest()
    with runtime.session_factory.begin() as session:
        owner = session.scalar(select(User).where(User.email == DE_EMAIL))
        assert owner is not None
        storage_key = f"{owner.tenant_id}/uploads/2026/09/{file_id}.pdf"
        storage.put(storage_key, io.BytesIO(source), "application/pdf")
        session.add(
            StoredFile(
                id=file_id,
                tenant_id=owner.tenant_id,
                owner_user_id=owner.id,
                original_name="m2-21-10-gateway-manual.pdf",
                storage_key=storage_key,
                extension=".pdf",
                mime_type="application/pdf",
                size_bytes=len(source),
                sha256=source_sha256,
                category="uploads",
            )
        )
        session.add(
            Document(
                id=document_id,
                tenant_id=owner.tenant_id,
                owner_user_id=owner.id,
                title="M2-21.10 Gateway 合成手册",
                document_type="product_manual",
                language="zh-CN",
                market="DE",
                access_level="tenant",
            )
        )
        session.flush()
        session.add(
            DocumentVersion(
                id=version_id,
                tenant_id=owner.tenant_id,
                document_id=document_id,
                file_id=file_id,
                version_no=1,
                content_hash=source_sha256,
            )
        )
        user = CurrentUser(
            user_id=owner.id,
            tenant_id=owner.tenant_id,
            email=owner.email,
            display_name=owner.display_name,
            roles=["amazon_operator"],
            market_scopes=["DE"],
            synthetic_data=True,
        )
    DocumentParserService(runtime.session_factory, storage, settings).parse_version(
        user,
        document_id=document_id,
        version_id=version_id,
    )
    application = create_app(
        settings,
        runtime,
        storage,
        engineered_agent_provider_factory=InventoryGatewayProvider,
    )
    with TestClient(application) as client:
        yield ApiFixture(
            client=client,
            runtime=runtime,
            application=application,
            knowledge_file_id=file_id,
        )

    with runtime.session_factory.begin() as session:
        session.execute(delete(Thread).where(Thread.title.like("M1-18 API Test%")))
        session.execute(delete(Document).where(Document.id == document_id))
        session.execute(delete(StoredFile).where(StoredFile.id == file_id))
    runtime.engine.dispose()


def login(client: TestClient, email: str = DE_EMAIL) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_thread(client: TestClient, token: str, suffix: str) -> str:
    response = client.post(
        "/api/v1/threads",
        headers=bearer(token),
        json={"title": f"M1-18 API Test {suffix}"},
    )
    assert response.status_code == 201
    return response.json()["thread_id"]


def test_openapi_and_cors_expose_the_versioned_contract(
    api_fixture: ApiFixture,
) -> None:
    client = api_fixture.client
    openapi = client.get("/openapi.json")

    assert openapi.status_code == 200
    assert {
        "/api/v1/auth/login",
        "/api/v1/me",
        "/api/v1/threads",
        "/api/v1/threads/{thread_id}/messages",
        "/api/v1/evidence/{evidence_id}",
    }.issubset(openapi.json()["paths"])

    preflight = client.options(
        "/api/v1/threads",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_login_me_chat_and_evidence_complete_real_backend_flow(
    api_fixture: ApiFixture,
) -> None:
    client = api_fixture.client
    token = login(client)
    me = client.get("/api/v1/me", headers=bearer(token))
    assert me.status_code == 200
    assert me.json()["email"] == DE_EMAIL
    assert me.json()["market_scopes"] == ["DE"]

    thread_id = create_thread(client, token, "happy path")
    chat = client.post(
        f"/api/v1/threads/{thread_id}/messages",
        headers=bearer(token),
        json={"message": "德国仓蘑菇灯还有多少可售库存？"},
    )

    assert chat.status_code == 200, chat.text
    payload = chat.json()
    assert payload["status"] == "completed"
    assert payload["execution"]["route"] == "agent_gateway"
    assert payload["execution"]["business_outcome"] == "answered"
    assert "可售库存为125件" in payload["answer"]
    assert "合成演示数据" in payload["answer"]
    assert payload["execution"]["tool_names"] == [
        "get_product_spec",
        "search_inventory",
    ]
    assert payload["execution"]["duration_ms"] >= 0
    assert len(payload["evidence"]) == 1
    with api_fixture.runtime.session_factory() as session:
        messages = list(
            session.scalars(
                select(Message)
                .where(Message.thread_id == thread_id)
                .order_by(Message.created_at, Message.id)
            )
        )
        runs = list(
            session.scalars(
                select(AgentRun)
                .where(AgentRun.thread_id == thread_id)
                .order_by(AgentRun.depth, AgentRun.started_at)
            )
        )
        root = next(run for run in runs if run.run_kind == "supervisor")
        worker = next(run for run in runs if run.run_kind == "worker")
        tool_run_ids = list(
            session.scalars(
                select(ToolCall.agent_run_id).where(
                    ToolCall.agent_run_id.in_([run.id for run in runs])
                )
            )
        )
        checkpoint_count = len(
            list(
                session.scalars(
                    select(AgentCheckpoint).where(
                        AgentCheckpoint.root_run_id == root.id
                    )
                )
            )
        )
        answer_evidence_count = len(
            list(
                session.scalars(
                    select(AgentAnswerEvidence).where(
                        AgentAnswerEvidence.root_run_id == root.id
                    )
                )
            )
        )
    assert len(runs) == 2
    assert worker.root_run_id == root.id
    assert worker.parent_run_id == root.id
    assert tool_run_ids == [worker.id, worker.id]
    assert checkpoint_count == 2
    assert answer_evidence_count == 1
    assert {message.role for message in messages} == {"user", "assistant"}
    assistant = next(message for message in messages if message.role == "assistant")
    assert str(assistant.id) == payload["message_id"]

    evidence_id = payload["evidence"][0]["id"]
    detail = client.get(
        f"/api/v1/evidence/{evidence_id}",
        headers=bearer(token),
    )
    assert detail.status_code == 200
    assert detail.json()["structured_data"]["available"] == 125
    assert detail.json()["access_scope"]["market_codes"] == ["DE"]
    assert detail.json()["synthetic_data"] is True


def test_public_gateway_supports_l0_without_starting_a_worker(
    api_fixture: ApiFixture,
) -> None:
    token = login(api_fixture.client)
    thread_id = create_thread(api_fixture.client, token, "gateway l0")

    response = api_fixture.client.post(
        f"/api/v1/threads/{thread_id}/messages",
        headers=bearer(token),
        json={"message": "解释安全库存是什么意思"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["execution"] == {
        "trace_id": response.json()["execution"]["trace_id"],
        "route": "agent_gateway",
        "tool_names": [],
        "duration_ms": response.json()["execution"]["duration_ms"],
        "status": "completed",
        "business_outcome": "answered",
    }
    with api_fixture.runtime.session_factory() as session:
        runs = list(
            session.scalars(select(AgentRun).where(AgentRun.thread_id == thread_id))
        )
    assert [(run.run_kind, run.status) for run in runs] == [("supervisor", "completed")]


def test_public_gateway_resumes_clarification_with_bounded_memory_and_one_replan(
    api_fixture: ApiFixture,
) -> None:
    provider = ResumableInventoryGatewayProvider()

    async def override_provider() -> object:
        return provider

    application = api_fixture.application
    application.dependency_overrides[get_engineered_agent_provider] = override_provider
    try:
        token = login(api_fixture.client)
        thread_id = create_thread(api_fixture.client, token, "gateway resume")
        first_request_id = uuid4()
        first = api_fixture.client.post(
            f"/api/v1/threads/{thread_id}/messages",
            headers=bearer(token),
            json={
                "request_id": str(first_request_id),
                "message": "查询LR-TL-MUSH-OR01的库存",
            },
        )
        second_request_id = uuid4()
        second = api_fixture.client.post(
            f"/api/v1/threads/{thread_id}/messages",
            headers=bearer(token),
            json={
                "request_id": str(second_request_id),
                "message": "查询德国市场",
            },
        )
        first_replay = api_fixture.client.post(
            f"/api/v1/threads/{thread_id}/messages",
            headers=bearer(token),
            json={
                "request_id": str(first_request_id),
                "message": "查询LR-TL-MUSH-OR01的库存",
            },
        )
    finally:
        application.dependency_overrides.pop(get_engineered_agent_provider, None)

    assert first.status_code == 200, first.text
    assert first.json()["status"] == "waiting_user"
    assert first.json()["execution"]["status"] == "waiting_user"
    assert first.json()["execution"]["business_outcome"] is None
    assert "哪个市场" in first.json()["answer"]
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "completed"
    assert second.json()["execution"]["business_outcome"] == "answered"
    assert "125件" in second.json()["answer"]
    assert first_replay.json() == first.json()
    assert provider.plan_calls == 2

    with api_fixture.runtime.session_factory() as session:
        roots = list(
            session.scalars(
                select(AgentRun).where(
                    AgentRun.thread_id == thread_id,
                    AgentRun.run_kind == "supervisor",
                )
            )
        )
        checkpoints = list(
            session.scalars(
                select(AgentCheckpoint)
                .where(AgentCheckpoint.root_run_id == roots[0].id)
                .order_by(AgentCheckpoint.checkpoint_version)
            )
        )
    assert len(roots) == 1
    assert [item.checkpoint_version for item in checkpoints] == [1, 2, 3, 4]
    final_state = checkpoints[-1].state_json
    assert final_state["resume_count"] == 1
    assert final_state["replan_count"] == 1
    assert final_state["processed_request_ids"] == [
        str(first_request_id),
        str(second_request_id),
    ]
    assert final_state["memory"]["recent_turns"][-1]["content_summary"] == (
        "查询德国市场"
    )


def test_public_gateway_replays_same_request_without_duplicate_run_or_messages(
    api_fixture: ApiFixture,
) -> None:
    token = login(api_fixture.client)
    thread_id = create_thread(api_fixture.client, token, "gateway duplicate request")
    request_id = uuid4()
    body = {
        "request_id": str(request_id),
        "message": "解释安全库存是什么意思",
    }

    first = api_fixture.client.post(
        f"/api/v1/threads/{thread_id}/messages",
        headers=bearer(token),
        json=body,
    )
    second = api_fixture.client.post(
        f"/api/v1/threads/{thread_id}/messages",
        headers=bearer(token),
        json=body,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    assert first.json()["request_id"] == str(request_id)
    with api_fixture.runtime.session_factory() as session:
        root_count = len(
            list(
                session.scalars(
                    select(AgentRun).where(
                        AgentRun.thread_id == thread_id,
                        AgentRun.run_kind == "supervisor",
                    )
                )
            )
        )
        messages = list(
            session.scalars(select(Message).where(Message.thread_id == thread_id))
        )
    assert root_count == 1
    assert len(messages) == 2


def test_public_gateway_rejects_request_id_reused_with_different_message(
    api_fixture: ApiFixture,
) -> None:
    token = login(api_fixture.client)
    thread_id = create_thread(api_fixture.client, token, "gateway request collision")
    request_id = uuid4()

    first = api_fixture.client.post(
        f"/api/v1/threads/{thread_id}/messages",
        headers=bearer(token),
        json={"request_id": str(request_id), "message": "解释安全库存是什么意思"},
    )
    collision = api_fixture.client.post(
        f"/api/v1/threads/{thread_id}/messages",
        headers=bearer(token),
        json={"request_id": str(request_id), "message": "查询德国库存"},
    )

    assert first.status_code == 200
    assert collision.status_code == 409
    assert collision.json()["error"]["code"] == "AGENT_RUN_CONFLICT"
    with api_fixture.runtime.session_factory() as session:
        messages = list(
            session.scalars(select(Message).where(Message.thread_id == thread_id))
        )
    assert len(messages) == 2


def test_public_gateway_exact_sku_keeps_m1_result_with_one_business_tool(
    api_fixture: ApiFixture,
) -> None:
    token = login(api_fixture.client)
    thread_id = create_thread(api_fixture.client, token, "gateway single tool")

    response = api_fixture.client.post(
        f"/api/v1/threads/{thread_id}/messages",
        headers=bearer(token),
        json={"message": "查询LR-TL-MUSH-OR01在德国的库存"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["execution"]["tool_names"] == ["search_inventory"]
    assert "可售库存为125件" in payload["answer"]
    assert len(payload["evidence"]) == 1


def test_public_gateway_runs_one_knowledge_tool_without_business_fallback(
    api_fixture: ApiFixture,
) -> None:
    async def override_provider() -> object:
        return KnowledgeGatewayProvider(file_id=api_fixture.knowledge_file_id)

    application = api_fixture.application
    application.dependency_overrides[get_engineered_agent_provider] = override_provider
    try:
        token = login(api_fixture.client)
        thread_id = create_thread(api_fixture.client, token, "gateway knowledge")
        response = api_fixture.client.post(
            f"/api/v1/threads/{thread_id}/messages",
            headers=bearer(token),
            json={"message": "读取获权蘑菇灯手册"},
        )
    finally:
        application.dependency_overrides.pop(get_engineered_agent_provider, None)

    assert response.status_code == 200, response.text
    assert response.json()["execution"]["tool_names"] == ["read_uploaded_file"]
    with api_fixture.runtime.session_factory() as session:
        runs = list(
            session.scalars(
                select(AgentRun)
                .where(AgentRun.thread_id == thread_id)
                .order_by(AgentRun.depth)
            )
        )
    assert [run.agent_id for run in runs] == ["supervisor", "knowledge"]


def test_public_gateway_reauthorizes_replayed_artifacts_after_revocation(
    api_fixture: ApiFixture,
) -> None:
    async def override_provider() -> object:
        return KnowledgeGatewayProvider(file_id=api_fixture.knowledge_file_id)

    application = api_fixture.application
    application.dependency_overrides[get_engineered_agent_provider] = override_provider
    token = login(api_fixture.client)
    thread_id = create_thread(api_fixture.client, token, "gateway revoked replay")
    request_id = uuid4()
    body = {"request_id": str(request_id), "message": "读取获权蘑菇灯手册"}
    original_status: str | None = None
    try:
        first = api_fixture.client.post(
            f"/api/v1/threads/{thread_id}/messages",
            headers=bearer(token),
            json=body,
        )
        assert first.status_code == 200, first.text
        with api_fixture.runtime.session_factory.begin() as session:
            stored_file = session.get(StoredFile, api_fixture.knowledge_file_id)
            assert stored_file is not None
            original_status = stored_file.status
            stored_file.status = "soft_deleted"
            stored_file.deleted_at = datetime.now(UTC)

        replay = api_fixture.client.post(
            f"/api/v1/threads/{thread_id}/messages",
            headers=bearer(token),
            json=body,
        )
    finally:
        with api_fixture.runtime.session_factory.begin() as session:
            stored_file = session.get(StoredFile, api_fixture.knowledge_file_id)
            assert stored_file is not None
            assert original_status is not None
            stored_file.status = original_status
            stored_file.deleted_at = None
        application.dependency_overrides.pop(get_engineered_agent_provider, None)

    assert replay.status_code == 403
    assert replay.json()["error"]["code"] == "FORBIDDEN"
    assert "手册" not in replay.text
    with api_fixture.runtime.session_factory() as session:
        latest = session.scalar(
            select(AgentCheckpoint)
            .join(AgentRun, AgentRun.id == AgentCheckpoint.root_run_id)
            .where(
                AgentRun.thread_id == thread_id,
                AgentRun.run_kind == "supervisor",
            )
            .order_by(AgentCheckpoint.checkpoint_version.desc())
            .limit(1)
        )
    assert latest is not None
    assert latest.business_outcome == "denied"
    assert latest.state_json["evidence_ids"] == []
    assert latest.state_json["artifact_ids"] == []


def test_public_gateway_reauthorizes_again_after_tool_before_final_checkpoint(
    api_fixture: ApiFixture,
) -> None:
    with api_fixture.runtime.session_factory() as session:
        stored_file = session.get(StoredFile, api_fixture.knowledge_file_id)
        assert stored_file is not None
        original_status = stored_file.status

    def revoke_before_answer() -> None:
        with api_fixture.runtime.session_factory.begin() as session:
            stored_file = session.get(StoredFile, api_fixture.knowledge_file_id)
            assert stored_file is not None
            stored_file.status = "soft_deleted"
            stored_file.deleted_at = datetime.now(UTC)

    async def override_provider() -> object:
        return KnowledgeGatewayProvider(
            file_id=api_fixture.knowledge_file_id,
            before_answer=revoke_before_answer,
        )

    application = api_fixture.application
    application.dependency_overrides[get_engineered_agent_provider] = override_provider
    token = login(api_fixture.client)
    thread_id = create_thread(api_fixture.client, token, "gateway revocation race")
    try:
        response = api_fixture.client.post(
            f"/api/v1/threads/{thread_id}/messages",
            headers=bearer(token),
            json={"request_id": str(uuid4()), "message": "读取获权蘑菇灯手册"},
        )
    finally:
        with api_fixture.runtime.session_factory.begin() as session:
            stored_file = session.get(StoredFile, api_fixture.knowledge_file_id)
            assert stored_file is not None
            stored_file.status = original_status
            stored_file.deleted_at = None
        application.dependency_overrides.pop(get_engineered_agent_provider, None)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    with api_fixture.runtime.session_factory() as session:
        root = session.scalar(
            select(AgentRun).where(
                AgentRun.thread_id == thread_id,
                AgentRun.run_kind == "supervisor",
            )
        )
        assert root is not None
        latest = session.scalar(
            select(AgentCheckpoint)
            .where(AgentCheckpoint.root_run_id == root.id)
            .order_by(AgentCheckpoint.checkpoint_version.desc())
            .limit(1)
        )
    assert root.business_outcome == "denied"
    assert latest is not None
    assert latest.state_json["worker_results"] == []
    assert latest.state_json["evidence_ids"] == []
    assert latest.state_json["artifact_ids"] == []


def test_public_gateway_reauthorizes_retained_state_before_clarification_resume(
    api_fixture: ApiFixture,
) -> None:
    async def override_provider() -> object:
        return ResumableKnowledgeGatewayProvider(file_id=api_fixture.knowledge_file_id)

    application = api_fixture.application
    application.dependency_overrides[get_engineered_agent_provider] = override_provider
    token = login(api_fixture.client)
    thread_id = create_thread(api_fixture.client, token, "gateway revoked resume")
    with api_fixture.runtime.session_factory() as session:
        stored_file = session.get(StoredFile, api_fixture.knowledge_file_id)
        assert stored_file is not None
        original_status = stored_file.status
    try:
        first = api_fixture.client.post(
            f"/api/v1/threads/{thread_id}/messages",
            headers=bearer(token),
            json={"request_id": str(uuid4()), "message": "读取手册后询问我是否复核"},
        )
        assert first.status_code == 200, first.text
        assert first.json()["status"] == "waiting_user"
        with api_fixture.runtime.session_factory.begin() as session:
            stored_file = session.get(StoredFile, api_fixture.knowledge_file_id)
            assert stored_file is not None
            stored_file.status = "soft_deleted"
            stored_file.deleted_at = datetime.now(UTC)

        resumed = api_fixture.client.post(
            f"/api/v1/threads/{thread_id}/messages",
            headers=bearer(token),
            json={"request_id": str(uuid4()), "message": "继续复核"},
        )
    finally:
        with api_fixture.runtime.session_factory.begin() as session:
            stored_file = session.get(StoredFile, api_fixture.knowledge_file_id)
            assert stored_file is not None
            stored_file.status = original_status
            stored_file.deleted_at = None
        application.dependency_overrides.pop(get_engineered_agent_provider, None)

    assert resumed.status_code == 403
    assert resumed.json()["error"]["code"] == "FORBIDDEN"
    with api_fixture.runtime.session_factory() as session:
        runs = list(
            session.scalars(select(AgentRun).where(AgentRun.thread_id == thread_id))
        )
        root = next(run for run in runs if run.run_kind == "supervisor")
        latest = session.scalar(
            select(AgentCheckpoint)
            .where(AgentCheckpoint.root_run_id == root.id)
            .order_by(AgentCheckpoint.checkpoint_version.desc())
            .limit(1)
        )
    assert len([run for run in runs if run.run_kind == "worker"]) == 1
    assert root.business_outcome == "denied"
    assert latest is not None
    assert latest.state_json["worker_results"] == []
    assert latest.state_json["artifact_ids"] == []


@pytest.mark.parametrize(
    ("fail_knowledge", "expected_outcome", "expected_tools"),
    (
        (False, "answered", ["search_inventory", "read_uploaded_file"]),
        (True, "partial", ["search_inventory"]),
    ),
)
def test_public_gateway_runs_two_workers_and_preserves_partial_success(
    api_fixture: ApiFixture,
    fail_knowledge: bool,
    expected_outcome: str,
    expected_tools: list[str],
) -> None:
    async def override_provider() -> object:
        return CrossWorkerGatewayProvider(
            fail_knowledge=fail_knowledge,
            file_id=api_fixture.knowledge_file_id,
        )

    application = api_fixture.application
    application.dependency_overrides[get_engineered_agent_provider] = override_provider
    try:
        token = login(api_fixture.client)
        thread_id = create_thread(
            api_fixture.client,
            token,
            f"gateway cross worker {fail_knowledge}",
        )
        response = api_fixture.client.post(
            f"/api/v1/threads/{thread_id}/messages",
            headers=bearer(token),
            json={"message": "查询LR-TL-MUSH-OR01库存并由Knowledge复核"},
        )
    finally:
        application.dependency_overrides.pop(get_engineered_agent_provider, None)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["execution"]["business_outcome"] == expected_outcome
    assert payload["execution"]["tool_names"] == expected_tools
    with api_fixture.runtime.session_factory() as session:
        runs = list(
            session.scalars(
                select(AgentRun)
                .where(AgentRun.thread_id == thread_id)
                .order_by(AgentRun.depth, AgentRun.started_at)
            )
        )
        messages = list(
            session.scalars(select(Message).where(Message.thread_id == thread_id))
        )
    assert [run.agent_id for run in runs] == [
        "supervisor",
        "business_data",
        "knowledge",
    ]
    assert all(run.root_run_id == runs[0].id for run in runs)
    assert {message.role for message in messages} == {"user", "assistant"}


def test_auth_validation_and_thread_ownership_use_safe_http_errors(
    api_fixture: ApiFixture,
) -> None:
    client = api_fixture.client
    missing = client.get("/api/v1/me")
    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"
    assert missing.json()["error"]["code"] == "UNAUTHENTICATED"

    wrong_password = client.post(
        "/api/v1/auth/login",
        json={"email": DE_EMAIL, "password": "definitely-wrong"},
    )
    assert wrong_password.status_code == 401
    assert "password" not in wrong_password.text.lower()

    invalid = client.post(
        "/api/v1/threads",
        headers=bearer(login(client)),
        json={"title": ""},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"

    de_token = login(client, DE_EMAIL)
    fr_token = login(client, FR_EMAIL)
    de_thread = create_thread(client, de_token, "ownership")
    foreign_thread = client.post(
        f"/api/v1/threads/{de_thread}/messages",
        headers=bearer(fr_token),
        json={"message": "德国仓蘑菇灯还有多少库存？"},
    )
    assert foreign_thread.status_code == 404
    assert foreign_thread.json()["error"]["code"] == "THREAD_NOT_FOUND"


def test_market_denial_and_evidence_scope_are_enforced(api_fixture: ApiFixture) -> None:
    client = api_fixture.client
    de_token = login(client, DE_EMAIL)
    fr_token = login(client, FR_EMAIL)
    thread_id = create_thread(client, de_token, "market scope")

    with api_fixture.runtime.session_factory() as session:
        messages_before = len(
            list(session.scalars(select(Message).where(Message.thread_id == thread_id)))
        )

    denied = client.post(
        f"/api/v1/threads/{thread_id}/messages",
        headers=bearer(de_token),
        json={"message": "法国仓蘑菇灯还有多少库存？"},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "FORBIDDEN"
    assert denied.json()["trace_id"] is not None
    with api_fixture.runtime.session_factory() as session:
        messages_after = len(
            list(session.scalars(select(Message).where(Message.thread_id == thread_id)))
        )
    assert messages_after == messages_before

    allowed = client.post(
        f"/api/v1/threads/{thread_id}/messages",
        headers=bearer(de_token),
        json={"message": "德国仓蘑菇灯还有多少库存？"},
    )
    evidence_id = allowed.json()["evidence"][0]["id"]
    hidden = client.get(
        f"/api/v1/evidence/{evidence_id}",
        headers=bearer(fr_token),
    )
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "EVIDENCE_NOT_FOUND"


@pytest.mark.usefixtures("api_fixture")
def test_provider_timeout_maps_to_504_with_trace(api_fixture: ApiFixture) -> None:
    class TimeoutProvider:
        async def create_plan(
            self,
            _request: PlannerRequest,
        ) -> object:
            raise ProviderTimeoutError

    async def override_provider() -> object:
        return TimeoutProvider()

    client = api_fixture.client
    application = api_fixture.application
    application.dependency_overrides[get_engineered_agent_provider] = override_provider
    try:
        token = login(client)
        thread_id = create_thread(client, token, "provider timeout")
        response = client.post(
            f"/api/v1/threads/{thread_id}/messages",
            headers=bearer(token),
            json={"message": "德国仓蘑菇灯还有多少库存？"},
        )
    finally:
        application.dependency_overrides.pop(get_engineered_agent_provider, None)

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "PROVIDER_ERROR"
    assert response.json()["trace_id"] is not None


def test_zero_inventory_is_a_successful_fact_with_evidence(
    api_fixture: ApiFixture,
) -> None:
    client = api_fixture.client
    runtime = api_fixture.runtime

    with runtime.session_factory.begin() as session:
        snapshot = session.scalar(
            select(InventorySnapshot)
            .join(ProductVariant, ProductVariant.id == InventorySnapshot.variant_id)
            .join(Warehouse, Warehouse.id == InventorySnapshot.warehouse_id)
            .where(
                ProductVariant.sku == "LR-TL-MUSH-OR01",
                Warehouse.code == "DE-FRA",
            )
        )
        assert snapshot is not None
        original_quantities = (
            snapshot.on_hand,
            snapshot.reserved,
            snapshot.unsellable,
        )
        snapshot.on_hand = 0
        snapshot.reserved = 0
        snapshot.unsellable = 0

    try:
        token = login(client)
        thread_id = create_thread(client, token, "zero inventory")
        response = client.post(
            f"/api/v1/threads/{thread_id}/messages",
            headers=bearer(token),
            json={"message": "德国仓蘑菇灯还有多少可售库存？"},
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert "可售库存为0件" in payload["answer"]
        assert len(payload["evidence"]) == 1
        detail = client.get(
            f"/api/v1/evidence/{payload['evidence'][0]['id']}",
            headers=bearer(token),
        )
        assert detail.status_code == 200
        assert detail.json()["structured_data"]["available"] == 0
    finally:
        with runtime.session_factory.begin() as session:
            snapshot = session.scalar(
                select(InventorySnapshot)
                .join(ProductVariant, ProductVariant.id == InventorySnapshot.variant_id)
                .join(Warehouse, Warehouse.id == InventorySnapshot.warehouse_id)
                .where(
                    ProductVariant.sku == "LR-TL-MUSH-OR01",
                    Warehouse.code == "DE-FRA",
                )
            )
            assert snapshot is not None
            (
                snapshot.on_hand,
                snapshot.reserved,
                snapshot.unsellable,
            ) = original_quantities


def test_missing_inventory_returns_404_without_business_evidence(
    api_fixture: ApiFixture,
) -> None:
    async def override_provider() -> object:
        return InventoryGatewayProvider(forced_sku="MISSING-SKU-01")

    client = api_fixture.client
    application = api_fixture.application
    application.dependency_overrides[get_engineered_agent_provider] = override_provider
    try:
        token = login(client)
        thread_id = create_thread(client, token, "missing inventory")
        response = client.post(
            f"/api/v1/threads/{thread_id}/messages",
            headers=bearer(token),
            json={"message": "查询德国仓MISSING-SKU-01的库存"},
        )
    finally:
        application.dependency_overrides.pop(get_engineered_agent_provider, None)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "INVENTORY_NOT_FOUND"
    assert response.json()["trace_id"] is not None
    with api_fixture.runtime.session_factory() as session:
        assert (
            list(session.scalars(select(Message).where(Message.thread_id == thread_id)))
            == []
        )


def test_ambiguous_product_returns_409_before_inventory_query(
    api_fixture: ApiFixture,
) -> None:
    runtime = api_fixture.runtime
    product_id = uuid4()
    variant_id = uuid4()

    with runtime.session_factory.begin() as session:
        tenant_id = session.scalar(
            select(Product.tenant_id)
            .join(ProductVariant, ProductVariant.product_id == Product.id)
            .where(ProductVariant.sku == "LR-TL-MUSH-OR01")
        )
        assert tenant_id is not None
        session.add(
            Product(
                id=product_id,
                tenant_id=tenant_id,
                spu="M1-20-AMB-SPU",
                name_zh="合成歧义测试台灯",
                name_en="Synthetic Ambiguous Test Lamp",
                aliases=["蘑菇灯"],
                status="candidate",
                is_demo=True,
            )
        )
        session.add(
            ProductVariant(
                id=variant_id,
                tenant_id=tenant_id,
                product_id=product_id,
                sku="M1-20-AMB-SKU",
                status="candidate",
            )
        )

    try:
        token = login(api_fixture.client)
        thread_id = create_thread(api_fixture.client, token, "ambiguous product")
        response = api_fixture.client.post(
            f"/api/v1/threads/{thread_id}/messages",
            headers=bearer(token),
            json={"message": "德国仓蘑菇灯还有多少可售库存？"},
        )
    finally:
        with runtime.session_factory.begin() as session:
            session.execute(delete(Product).where(Product.id == product_id))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "AMBIGUOUS_PRODUCT"
    assert response.json()["trace_id"] is not None


def test_database_statement_timeout_maps_to_safe_504(
    api_fixture: ApiFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StatementTimeout(Exception):
        sqlstate = "57014"

    def raise_timeout(
        _repository: InventoryRepository,
        *_arguments: object,
        **_keywords: object,
    ) -> list[object]:
        raise OperationalError(
            "SELECT secret_inventory FROM internal_table",
            {},
            StatementTimeout("canceling statement due to statement timeout"),
        )

    monkeypatch.setattr(InventoryRepository, "find_latest", raise_timeout)
    token = login(api_fixture.client)
    thread_id = create_thread(api_fixture.client, token, "database timeout")
    response = api_fixture.client.post(
        f"/api/v1/threads/{thread_id}/messages",
        headers=bearer(token),
        json={"message": "德国仓蘑菇灯还有多少可售库存？"},
    )

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "DATABASE_TIMEOUT"
    assert response.json()["error"]["retryable"] is True
    assert response.json()["trace_id"] is not None
    assert "secret_inventory" not in response.text
    assert "internal_table" not in response.text
