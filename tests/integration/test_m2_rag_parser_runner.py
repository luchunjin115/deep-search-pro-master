from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.core.config import Settings
from app.db.session import create_database_runtime
from app.evals.rag_runner import run_m2_parser_evaluation
from app.models.identity import Tenant
from app.services.storage import LocalStorageBackend
from scripts.seed_m1 import seed_m1
from scripts.seed_m2_complex_files import seed_m2_complex_files
from scripts.seed_m2_files import seed_m2_files

ROOT = Path(__file__).resolve().parents[2]
NATIVE_SOURCE_IDS = {
    "m2-v1-mushroom-lamp-manual",
    "m2-v1-quality-inspection-sop",
    "m2-v1-supplier-quotes",
    "m2-v1-monthly-operations",
}


@pytest.fixture
def parser_runner_settings(tmp_path: Path) -> Generator[Settings, None, None]:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=".env.example",
        app_env="test",
        local_storage_root=tmp_path / "storage",
        docling_backend="disabled",
    )
    command.upgrade(Config("alembic.ini"), "head")
    seed_m1(settings, manifest_path=tmp_path / "m1-manifest.json")
    storage = LocalStorageBackend(settings.local_storage_root)
    seed_m2_files(
        settings,
        manifest_path=tmp_path / "m2-manifest.json",
        m1_manifest_path=tmp_path / "m1-manifest.json",
        storage=storage,
    )
    seed_m2_complex_files(
        settings,
        manifest_path=tmp_path / "m2-complex-manifest.json",
        m1_manifest_path=tmp_path / "m1-manifest.json",
        storage=storage,
    )
    yield settings


def test_runner_uses_upload_api_and_parser_then_removes_isolated_rows(
    parser_runner_settings: Settings,
) -> None:
    storage = LocalStorageBackend(parser_runner_settings.local_storage_root)

    report = run_m2_parser_evaluation(
        parser_runner_settings,
        project_root=ROOT,
        source_ids=NATIVE_SOURCE_IDS,
        storage=storage,
    )

    assert report.run_status == "completed", report.model_dump(mode="json")
    assert report.aggregate.documents_total == 4
    assert report.aggregate.uploads_accepted == 4
    assert report.aggregate.parses_completed == 4
    assert report.aggregate.routes.native == 4
    assert {document.source_type for document in report.documents} == {
        "pdf",
        "docx",
        "xlsx",
        "csv",
    }
    assert all(document.upload_status == "accepted" for document in report.documents)
    assert all(document.parse_status == "completed" for document in report.documents)
    assert all(document.route == "native" for document in report.documents)
    assert report.malformed_upload_probe.status == "rejected"
    assert report.cleanup.cleanup_attempted
    assert report.cleanup.evaluation_database_rows_remaining == 0
    assert report.cleanup.evaluation_storage_objects_remaining == 0
    assert report.cleanup.baseline_restored

    serialized = report.model_dump_json()
    for forbidden in ("storage_key", "tenant_id", "password", "D:\\\\", "/home/"):
        assert forbidden not in serialized

    database = create_database_runtime(parser_runner_settings)
    try:
        with database.session_factory() as session:
            assert (
                not session.query(Tenant)
                .filter(Tenant.name.like("M2-22.4 Parser Evaluation %"))
                .count()
            )
    finally:
        database.engine.dispose()
