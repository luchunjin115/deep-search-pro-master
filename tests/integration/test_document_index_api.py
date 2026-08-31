from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass, field
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update

from app.api.dependencies import get_embedding_provider
from app.core.config import Settings
from app.core.errors import EmbeddingProviderError
from app.db.session import DatabaseRuntime, create_database_runtime
from app.main import create_app
from app.models.knowledge import (
    Document,
    DocumentAcl,
    DocumentChunk,
    DocumentVersion,
    StoredFile,
)
from app.services.retrieval import FakeEmbeddingProvider
from app.services.storage import LocalStorageBackend
from scripts.seed_m1 import seed_m1
from tests.fixtures.pdf_factory import make_text_pdf

DE_EMAIL = "de.operator@demo.deepsearch.local"
OWNER_EMAIL = "owner@demo.deepsearch.local"
SCOUT_EMAIL = "scout@demo.deepsearch.local"
PASSWORD = "M1-demo-only-change-me"


@dataclass(frozen=True, slots=True)
class DocumentIndexApiFixture:
    client: TestClient
    runtime: DatabaseRuntime
    application: FastAPI
    storage: LocalStorageBackend
    settings: Settings
    document_ids: set[UUID] = field(default_factory=set)
    file_ids: set[UUID] = field(default_factory=set)


@pytest.fixture(scope="module")
def document_index_api_fixture(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[DocumentIndexApiFixture, None, None]:
    root = tmp_path_factory.mktemp("m2_document_index_api") / "storage"
    settings = Settings(  # type: ignore[call-arg]
        _env_file=".env.example",
        app_env="test",
        local_storage_root=root,
        embedding_backend="fake",
    )
    command.upgrade(Config("alembic.ini"), "head")
    seed_m1(
        settings,
        manifest_path=(
            tmp_path_factory.mktemp("m2_document_index_api_seed") / "manifest.json"
        ),
    )
    runtime = create_database_runtime(settings)
    storage = LocalStorageBackend(root)
    application = create_app(settings, runtime, storage)
    with TestClient(application) as client:
        fixture = DocumentIndexApiFixture(
            client=client,
            runtime=runtime,
            application=application,
            storage=storage,
            settings=settings,
        )
        yield fixture
    with runtime.session_factory.begin() as session:
        if fixture.document_ids:
            session.execute(
                update(Document)
                .where(Document.id.in_(fixture.document_ids))
                .values(active_version_id=None)
            )
            session.execute(
                update(DocumentVersion)
                .where(DocumentVersion.document_id.in_(fixture.document_ids))
                .values(active_index_set_id=None)
            )
            session.execute(
                delete(DocumentVersion).where(
                    DocumentVersion.document_id.in_(fixture.document_ids)
                )
            )
            session.execute(
                delete(Document).where(Document.id.in_(fixture.document_ids))
            )
        if fixture.file_ids:
            session.execute(
                delete(StoredFile).where(StoredFile.id.in_(fixture.file_ids))
            )
    runtime.engine.dispose()


def login(client: TestClient, email: str = DE_EMAIL) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return cast(str, response.json()["access_token"])


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def upload_pdf(
    fixture: DocumentIndexApiFixture,
    token: str,
    *,
    suffix: bytes = b"",
) -> UUID:
    response = fixture.client.post(
        "/api/v1/files",
        headers=bearer(token),
        files=[
            (
                "files",
                (
                    f"synthetic-index-{uuid4()}.pdf",
                    make_text_pdf(include_empty_page=False) + suffix,
                    "application/pdf",
                ),
            )
        ],
    )
    assert response.status_code == 201, response.text
    file_id = UUID(response.json()["items"][0]["file_id"])
    fixture.file_ids.add(file_id)
    return file_id


def create_document(
    fixture: DocumentIndexApiFixture,
    token: str,
    file_id: UUID,
) -> dict[str, object]:
    response = fixture.client.post(
        "/api/v1/documents",
        headers=bearer(token),
        json={
            "file_id": str(file_id),
            "title": "M2-15.5 synthetic indexing manual",
            "document_type": "product_manual",
            "language": "en",
            "market": "DE",
        },
    )
    assert response.status_code == 201, response.text
    payload = cast(dict[str, object], response.json())
    fixture.document_ids.add(UUID(cast(str, payload["document_id"])))
    return payload


class FailingEmbeddingProvider(FakeEmbeddingProvider):
    def embed(self, texts, *, purpose):  # type: ignore[no-untyped-def]
        raise EmbeddingProviderError(retryable=True)


def test_documents_routes_are_registered_and_require_authentication(
    document_index_api_fixture: DocumentIndexApiFixture,
) -> None:
    fixture = document_index_api_fixture
    paths = fixture.client.get("/openapi.json").json()["paths"]
    expected = {
        "/api/v1/documents",
        "/api/v1/documents/{document_id}/versions",
        "/api/v1/documents/{document_id}/versions/{version_id}/index",
    }

    assert expected <= set(paths)
    response = fixture.client.post(
        "/api/v1/documents",
        json={
            "file_id": "00000000-0000-0000-0000-000000000001",
            "title": "合成索引说明书",
            "document_type": "product_manual",
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_create_index_repeat_and_new_version_switch_are_safe_and_atomic(
    document_index_api_fixture: DocumentIndexApiFixture,
) -> None:
    fixture = document_index_api_fixture
    operator_token = login(fixture.client)
    owner_token = login(fixture.client, OWNER_EMAIL)
    first_file_id = upload_pdf(fixture, operator_token)
    created = create_document(fixture, operator_token, first_file_id)
    document_id = UUID(cast(str, created["document_id"]))
    versions = cast(list[dict[str, object]], created["versions"])
    first_version_id = UUID(cast(str, versions[0]["version_id"]))

    assert created["active_version_id"] is None
    assert versions[0]["parse_status"] == "pending"
    assert versions[0]["index_status"] == "pending"
    assert "tenant_id" not in created

    first = fixture.client.post(
        f"/api/v1/documents/{document_id}/versions/{first_version_id}/index",
        headers=bearer(operator_token),
    )
    assert first.status_code == 200, first.text
    first_payload = first.json()
    assert first_payload["status"] == "ready"
    assert first_payload["reused"] is False
    assert first_payload["version_activated"] is True
    assert first_payload["embedding_model"] == "fake/m2-deterministic"
    assert first_payload["embedding_version"] == "m2-fake-v1"
    assert first_payload["chunk_count"] >= 1
    assert not {
        "tenant_id",
        "storage_key",
        "path",
        "vectors",
        "embeddings",
    } & set(first_payload)

    with fixture.runtime.session_factory() as session:
        first_chunk_count = session.scalar(
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.document_version_id == first_version_id)
        )
        active_after_first = session.scalar(
            select(Document.active_version_id).where(Document.id == document_id)
        )
    assert first_chunk_count == first_payload["chunk_count"]
    assert active_after_first == first_version_id

    repeated = fixture.client.post(
        f"/api/v1/documents/{document_id}/versions/{first_version_id}/index",
        headers=bearer(operator_token),
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["index_set_id"] == first_payload["index_set_id"]
    assert repeated.json()["reused"] is True
    assert repeated.json()["version_activated"] is False
    with fixture.runtime.session_factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .where(DocumentChunk.document_version_id == first_version_id)
            )
            == first_chunk_count
        )

    second_file_id = upload_pdf(fixture, operator_token, suffix=b"\n")
    version_response = fixture.client.post(
        f"/api/v1/documents/{document_id}/versions",
        headers=bearer(operator_token),
        json={"file_id": str(second_file_id)},
    )
    assert version_response.status_code == 201, version_response.text
    second_version_id = UUID(version_response.json()["version_id"])
    assert version_response.json()["version_no"] == 2
    with fixture.runtime.session_factory() as session:
        assert (
            session.scalar(
                select(Document.active_version_id).where(Document.id == document_id)
            )
            == first_version_id
        )

    second = fixture.client.post(
        f"/api/v1/documents/{document_id}/versions/{second_version_id}/index",
        headers=bearer(owner_token),
    )
    assert second.status_code == 200, second.text
    assert second.json()["version_id"] == str(second_version_id)
    assert second.json()["version_activated"] is True
    with fixture.runtime.session_factory() as session:
        assert (
            session.scalar(
                select(Document.active_version_id).where(Document.id == document_id)
            )
            == second_version_id
        )


def test_index_api_enforces_management_scope_and_rejects_bad_boundaries(
    document_index_api_fixture: DocumentIndexApiFixture,
) -> None:
    fixture = document_index_api_fixture
    operator_token = login(fixture.client)
    scout_token = login(fixture.client, SCOUT_EMAIL)
    file_id = upload_pdf(fixture, operator_token, suffix=b"\nacl")
    created = create_document(fixture, operator_token, file_id)
    document_id = UUID(cast(str, created["document_id"]))
    versions = cast(list[dict[str, object]], created["versions"])
    version_id = UUID(cast(str, versions[0]["version_id"]))

    with fixture.runtime.session_factory.begin() as session:
        tenant_id = session.scalar(
            select(Document.tenant_id).where(Document.id == document_id)
        )
        assert tenant_id is not None
        session.add(
            DocumentAcl(
                tenant_id=tenant_id,
                document_id=document_id,
                subject_type="role",
                role_name="product_scout",
                permission="read",
            )
        )

    reader_response = fixture.client.post(
        f"/api/v1/documents/{document_id}/versions/{version_id}/index",
        headers=bearer(scout_token),
    )
    assert reader_response.status_code == 404
    assert reader_response.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"

    wrong_document = fixture.client.post(
        f"/api/v1/documents/{uuid4()}/versions/{version_id}/index",
        headers=bearer(operator_token),
    )
    assert wrong_document.status_code == 404
    assert wrong_document.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"

    invalid_uuid = fixture.client.post(
        f"/api/v1/documents/{document_id}/versions/not-a-uuid/index",
        headers=bearer(operator_token),
    )
    assert invalid_uuid.status_code == 422
    assert invalid_uuid.json()["error"]["code"] == "VALIDATION_ERROR"

    unknown_field = fixture.client.post(
        "/api/v1/documents",
        headers=bearer(operator_token),
        json={
            "file_id": str(uuid4()),
            "title": "must reject tenant injection",
            "document_type": "product_manual",
            "tenant_id": str(uuid4()),
        },
    )
    assert unknown_field.status_code == 422
    assert unknown_field.json()["error"]["code"] == "VALIDATION_ERROR"

    with fixture.runtime.session_factory.begin() as session:
        session.execute(
            update(DocumentVersion)
            .where(DocumentVersion.id == version_id)
            .values(parse_status="parsing")
        )
    conflict = fixture.client.post(
        f"/api/v1/documents/{document_id}/versions/{version_id}/index",
        headers=bearer(operator_token),
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "DOCUMENT_STATE_CONFLICT"


def test_embedding_failure_is_safe_and_the_same_api_request_can_retry(
    document_index_api_fixture: DocumentIndexApiFixture,
) -> None:
    fixture = document_index_api_fixture
    operator_token = login(fixture.client)
    file_id = upload_pdf(fixture, operator_token, suffix=b"\nretry")
    created = create_document(fixture, operator_token, file_id)
    document_id = UUID(cast(str, created["document_id"]))
    versions = cast(list[dict[str, object]], created["versions"])
    version_id = UUID(cast(str, versions[0]["version_id"]))
    path = f"/api/v1/documents/{document_id}/versions/{version_id}/index"

    fixture.application.dependency_overrides[get_embedding_provider] = (
        FailingEmbeddingProvider
    )
    try:
        failed = fixture.client.post(path, headers=bearer(operator_token))
    finally:
        fixture.application.dependency_overrides.pop(get_embedding_provider, None)

    assert failed.status_code == 500
    assert failed.json()["error"] == {
        "code": "INTERNAL_ERROR",
        "message": failed.json()["error"]["message"],
        "retryable": True,
        "field": None,
    }
    serialized_error = failed.text.casefold()
    assert "storage" not in serialized_error
    assert "traceback" not in serialized_error
    assert "embedding_model" not in serialized_error

    retried = fixture.client.post(path, headers=bearer(operator_token))
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "ready"
    assert retried.json()["reused"] is False
    with fixture.runtime.session_factory() as session:
        version = session.get(DocumentVersion, version_id)
        assert version is not None
        assert version.index_status == "ready"
        assert version.active_index_set_id == UUID(retried.json()["index_set_id"])


def test_openapi_exposes_only_m2_15_write_pipeline_not_retrieval(
    document_index_api_fixture: DocumentIndexApiFixture,
) -> None:
    paths = document_index_api_fixture.client.get("/openapi.json").json()["paths"]
    forbidden_fragments = ("search", "dense", "lexical", "hybrid", "rerank", "rag")
    document_paths = {path for path in paths if path.startswith("/api/v1/documents")}

    assert document_paths == {
        "/api/v1/documents",
        "/api/v1/documents/{document_id}/versions",
        "/api/v1/documents/{document_id}/versions/{version_id}/index",
    }
    assert not any(
        fragment in path.casefold()
        for path in paths
        for fragment in forbidden_fragments
    )
