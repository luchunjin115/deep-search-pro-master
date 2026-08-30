from __future__ import annotations

import hashlib
import io
import zipfile
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, object_session

from app.core.config import Settings
from app.db.session import DatabaseRuntime, create_database_runtime
from app.main import create_app
from app.models.knowledge import StoredFile
from app.repositories.files import FileRepository
from app.services.storage import LocalStorageBackend
from scripts.seed_m1 import seed_m1

DE_EMAIL = "de.operator@demo.deepsearch.local"
FR_EMAIL = "fr.operator@demo.deepsearch.local"
PASSWORD = "M1-demo-only-change-me"

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
CSV_BYTES = b"sku,market,price\nSYNTH-01,DE,19.90\n"


def office_archive(*members: str) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for member in members:
            archive.writestr(member, "<synthetic />")
    return output.getvalue()


DOCX_BYTES = office_archive(
    "[Content_Types].xml",
    "_rels/.rels",
    "word/document.xml",
)
XLSX_BYTES = office_archive(
    "[Content_Types].xml",
    "_rels/.rels",
    "xl/workbook.xml",
)


@dataclass(frozen=True, slots=True)
class FileApiFixture:
    client: TestClient
    runtime: DatabaseRuntime
    application: FastAPI
    storage: LocalStorageBackend
    storage_root: Path


@pytest.fixture(scope="module")
def file_api_fixture(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[FileApiFixture, None, None]:
    root = tmp_path_factory.mktemp("m2_file_api") / "storage"
    settings = Settings(  # type: ignore[call-arg]
        _env_file=".env.example",
        app_env="test",
        local_storage_root=root,
        upload_max_file_size_bytes=1024 * 1024,
        upload_stream_chunk_size_bytes=64 * 1024,
    )
    command.upgrade(Config("alembic.ini"), "head")
    seed_m1(
        settings,
        manifest_path=tmp_path_factory.mktemp("m2_file_api_seed") / "manifest.json",
    )
    runtime = create_database_runtime(settings)
    with runtime.session_factory.begin() as session:
        session.execute(delete(StoredFile))
    storage = LocalStorageBackend(
        root,
        chunk_size_bytes=settings.upload_stream_chunk_size_bytes,
    )
    application = create_app(settings, runtime, storage)
    with TestClient(application) as client:
        yield FileApiFixture(client, runtime, application, storage, root)

    with runtime.session_factory.begin() as session:
        session.execute(delete(StoredFile))
    runtime.engine.dispose()


def login(client: TestClient, email: str = DE_EMAIL) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200
    return cast(str, response.json()["access_token"])


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def multipart_files() -> list[tuple[str, tuple[str, bytes, str]]]:
    return [
        ("files", ("合成说明书.pdf", PDF_BYTES, "application/pdf")),
        (
            "files",
            (
                "合成规格.docx",
                DOCX_BYTES,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        ),
        (
            "files",
            (
                "合成报价.xlsx",
                XLSX_BYTES,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        ),
        ("files", ("合成清单.csv", CSV_BYTES, "text/csv; charset=utf-8")),
    ]


def stored_count(fixture: FileApiFixture) -> int:
    with fixture.runtime.session_factory() as session:
        return session.scalar(select(func.count()).select_from(StoredFile)) or 0


def stored_paths(fixture: FileApiFixture) -> set[Path]:
    if not fixture.storage_root.exists():
        return set()
    return {
        path
        for path in fixture.storage_root.rglob("*")
        if path.is_file() and not path.name.endswith(".tmp")
    }


def test_upload_list_status_and_download_use_public_ids_and_safe_metadata(
    file_api_fixture: FileApiFixture,
) -> None:
    fixture = file_api_fixture
    token = login(fixture.client)
    response = fixture.client.post(
        "/api/v1/files",
        headers=bearer(token),
        files=multipart_files(),
    )

    assert response.status_code == 201, response.text
    items = response.json()["items"]
    assert len(items) == 4
    assert {item["extension"] for item in items} == {".pdf", ".docx", ".xlsx", ".csv"}
    assert all(item["status"] == "uploaded" for item in items)
    assert all("tenant_id" not in item for item in items)
    assert all("storage_key" not in item and "path" not in item for item in items)

    listed = fixture.client.get("/api/v1/files", headers=bearer(token))
    assert listed.status_code == 200
    assert {item["file_id"] for item in listed.json()["items"]} >= {
        item["file_id"] for item in items
    }

    by_extension = {item["extension"]: item for item in items}
    pdf_id = UUID(by_extension[".pdf"]["file_id"])
    status_response = fixture.client.get(
        f"/api/v1/files/{pdf_id}/status",
        headers=bearer(token),
    )
    assert status_response.status_code == 200
    assert status_response.json()["sha256"] == hashlib.sha256(PDF_BYTES).hexdigest()

    downloaded = fixture.client.get(
        f"/api/v1/files/{pdf_id}",
        headers=bearer(token),
    )
    assert downloaded.status_code == 200
    assert downloaded.content == PDF_BYTES
    assert downloaded.headers["content-type"] == "application/pdf"
    assert downloaded.headers["x-content-type-options"] == "nosniff"
    assert "filename*=UTF-8''" in downloaded.headers["content-disposition"]
    assert "storage" not in downloaded.headers["content-disposition"].lower()

    with fixture.runtime.session_factory() as session:
        rows = list(
            session.scalars(
                select(StoredFile).where(
                    StoredFile.id.in_([UUID(item["file_id"]) for item in items])
                )
            )
        )
    assert len(rows) == 4
    for row in rows:
        assert row.original_name not in row.storage_key
        assert row.storage_key.endswith(f"/{row.id}{row.extension}")
        assert fixture.storage.exists(row.storage_key)


def test_unauthorized_user_gets_404_and_soft_delete_keeps_physical_object(
    file_api_fixture: FileApiFixture,
) -> None:
    fixture = file_api_fixture
    owner_token = login(fixture.client)
    foreign_token = login(fixture.client, FR_EMAIL)
    uploaded = fixture.client.post(
        "/api/v1/files",
        headers=bearer(owner_token),
        files=[("files", ("owner-only.csv", CSV_BYTES, "text/csv"))],
    ).json()["items"][0]
    file_id = uploaded["file_id"]
    with fixture.runtime.session_factory() as session:
        row = session.get(StoredFile, UUID(file_id))
        assert row is not None
        storage_key = row.storage_key

    for method, path in (
        ("get", f"/api/v1/files/{file_id}/status"),
        ("get", f"/api/v1/files/{file_id}"),
        ("delete", f"/api/v1/files/{file_id}"),
    ):
        response = fixture.client.request(method, path, headers=bearer(foreign_token))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "FILE_NOT_FOUND"

    deleted = fixture.client.delete(
        f"/api/v1/files/{file_id}",
        headers=bearer(owner_token),
    )
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert fixture.storage.exists(storage_key)
    assert (
        fixture.client.get(
            f"/api/v1/files/{file_id}/status",
            headers=bearer(owner_token),
        ).status_code
        == 404
    )


def test_invalid_or_partial_batches_leave_no_metadata_or_storage(
    file_api_fixture: FileApiFixture,
) -> None:
    fixture = file_api_fixture
    token = login(fixture.client)
    baseline_count = stored_count(fixture)
    baseline_paths = stored_paths(fixture)
    invalid_requests = [
        [("files", ("empty.csv", b"", "text/csv"))],
        [("files", ("too-large.csv", b"a" * (1024 * 1024 + 1), "text/csv"))],
        [("files", ("fake.pdf", CSV_BYTES, "application/pdf"))],
        [("files", ("wrong-mime.pdf", PDF_BYTES, "text/csv"))],
        [
            (
                "files",
                (
                    "broken.docx",
                    b"PK\x03\x04broken",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
            )
        ],
        [("files", ("../unsafe.csv", CSV_BYTES, "text/csv"))],
        [
            ("files", ("first.csv", CSV_BYTES, "text/csv")),
            ("files", ("second.pdf", CSV_BYTES, "application/pdf")),
        ],
        [
            ("files", (f"too-many-{index}.csv", CSV_BYTES, "text/csv"))
            for index in range(6)
        ],
    ]

    for files in invalid_requests:
        response = fixture.client.post(
            "/api/v1/files",
            headers=bearer(token),
            files=files,
        )
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        assert "storage_key" not in response.text
        assert stored_count(fixture) == baseline_count
        assert stored_paths(fixture) == baseline_paths


def test_database_failure_after_storage_write_is_compensated_and_safe(
    file_api_fixture: FileApiFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = file_api_fixture
    token = login(fixture.client)
    baseline_count = stored_count(fixture)
    baseline_paths = stored_paths(fixture)

    def fail_create(*_args: object, **_kwargs: object) -> StoredFile:
        raise OperationalError(
            "INSERT INTO files(secret_storage_key)",
            {},
            RuntimeError("synthetic database failure"),
        )

    monkeypatch.setattr(FileRepository, "create_file", fail_create)
    response = fixture.client.post(
        "/api/v1/files",
        headers=bearer(token),
        files=[("files", ("db-failure.csv", CSV_BYTES, "text/csv"))],
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret_storage_key" not in response.text
    assert stored_count(fixture) == baseline_count
    assert stored_paths(fixture) == baseline_paths


def test_request_commit_failure_also_removes_the_published_object(
    file_api_fixture: FileApiFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = file_api_fixture
    token = login(fixture.client)
    baseline_count = stored_count(fixture)
    baseline_paths = stored_paths(fixture)
    original_create = FileRepository.create_file
    original_commit = Session.commit

    def mark_commit_failure(
        repository: FileRepository,
        **values: object,
    ) -> StoredFile:
        row = original_create(repository, **values)  # type: ignore[arg-type]
        session = object_session(row)
        assert session is not None
        session.info["m2_fail_commit"] = True
        return row

    def fail_marked_commit(session: Session) -> None:
        if session.info.pop("m2_fail_commit", False):
            raise OperationalError(
                "COMMIT secret_file_transaction",
                {},
                RuntimeError("synthetic commit failure"),
            )
        original_commit(session)

    monkeypatch.setattr(FileRepository, "create_file", mark_commit_failure)
    monkeypatch.setattr(Session, "commit", fail_marked_commit)
    response = fixture.client.post(
        "/api/v1/files",
        headers=bearer(token),
        files=[("files", ("commit-failure.csv", CSV_BYTES, "text/csv"))],
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret_file_transaction" not in response.text
    assert stored_count(fixture) == baseline_count
    assert stored_paths(fixture) == baseline_paths


def test_openapi_exposes_only_the_m2_06_file_routes(
    file_api_fixture: FileApiFixture,
) -> None:
    paths = file_api_fixture.client.get("/openapi.json").json()["paths"]
    assert {
        "/api/v1/files",
        "/api/v1/files/{file_id}",
        "/api/v1/files/{file_id}/status",
    } <= set(paths)
    assert "/api/v1/files/{file_id}/index" not in paths
