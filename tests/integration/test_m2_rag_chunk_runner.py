from __future__ import annotations

import hashlib
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.core.config import Settings
from app.db.session import create_database_runtime
from app.evals.rag_runner import run_m2_chunk_evaluation
from app.models.knowledge import DocumentChunkSet
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
    "m2-complex-v1-two-column-market-brief",
}


@pytest.fixture
def chunk_runner_settings(tmp_path: Path) -> Generator[Settings, None, None]:
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


def test_chunk_runner_uses_real_services_matrix_and_restores_baseline(
    chunk_runner_settings: Settings,
) -> None:
    storage = LocalStorageBackend(chunk_runner_settings.local_storage_root)

    report = run_m2_chunk_evaluation(
        chunk_runner_settings,
        project_root=ROOT,
        source_ids=NATIVE_SOURCE_IDS,
        storage=storage,
    )

    assert report.run_status == "completed", report.model_dump(mode="json")
    assert report.documents_parsed == 5
    assert report.golden_cases_total == 10
    assert report.schema_version == "m2-chunk-quality-report-v2"
    assert report.heading_dataset_version == "m2-chunk-heading-golden-v2"
    assert (
        report.heading_dataset_sha256
        == hashlib.sha256(
            (ROOT / "data/evals/m2_cross_border_chunk_headings_v2.json").read_bytes()
        ).hexdigest()
    )
    assert report.heading_context_cases_total == 4
    assert [entry.config.config_id for entry in report.first_round] == [
        "chunk-compact",
        "chunk-medium",
        "chunk-current",
        "chunk-large",
    ]
    assert report.candidate_selection.candidate_config_ids
    assert report.candidate_selection.overlap_tokens == [80, 100, 120]
    assert len(report.overlap_sweep) == (
        len(report.candidate_selection.candidate_config_ids) * 3
    )
    assert report.quality_gate_passed == any(
        entry.quality_gate_passed
        for entry in report.overlap_sweep
        if entry.base_config_id in report.candidate_selection.candidate_config_ids
    )
    assert all(
        entry.aggregate.documents_total == 5
        for entry in [*report.first_round, *report.overlap_sweep]
    )
    assert all(
        entry.aggregate.deterministic_documents == 5
        and entry.aggregate.ordered_documents == 5
        and entry.aggregate.locator_integrity_documents == 5
        and entry.aggregate.golden_cases_located == entry.aggregate.golden_cases_total
        for entry in [*report.first_round, *report.overlap_sweep]
    )
    for entry in [*report.first_round, *report.overlap_sweep]:
        reviewed = next(
            document
            for document in entry.documents
            if document.source_id == "m2-complex-v1-two-column-market-brief"
        )
        assert reviewed.quality.structure.heading_units == 4
        assert reviewed.quality.structure.heading_units_preserved == 4
    assert report.cleanup.evaluation_chunk_sets_remaining == 0
    assert report.cleanup.evaluation_storage_objects_remaining == 0
    assert report.cleanup.formal_chunk_sets == 0
    assert report.cleanup.baseline_restored is True

    serialized = report.model_dump_json()
    for forbidden in (
        "storage_key",
        "tenant_id",
        "password",
        "D:\\\\",
        "/home/",
        "embedding",
        "reranker",
        "ragas",
    ):
        assert forbidden not in serialized.casefold()

    database = create_database_runtime(chunk_runner_settings)
    try:
        with database.session_factory() as session:
            assert session.query(DocumentChunkSet).count() == 0
    finally:
        database.engine.dispose()
