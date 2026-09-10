from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from app.core.config import Settings
from app.db.session import create_database_runtime
from app.evals.retrieval_runner import (
    FrozenChunkCandidate,
    build_frozen_chunk_candidates,
    run_m2_retrieval_evaluation,
)
from app.models.knowledge import DocumentChunk, DocumentIndexSet
from app.services.retrieval import FakeEmbeddingProvider
from app.services.storage import LocalStorageBackend
from scripts.seed_m1 import seed_m1
from scripts.seed_m2_complex_files import seed_m2_complex_files
from scripts.seed_m2_files import seed_m2_files

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def retrieval_runner_settings(tmp_path: Path) -> Generator[Settings, None, None]:
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


def test_retrieval_runner_uses_real_fts_pgvector_rrf_and_precise_cleanup(
    retrieval_runner_settings: Settings,
    tmp_path: Path,
) -> None:
    storage = LocalStorageBackend(retrieval_runner_settings.local_storage_root)
    baseline = next(
        candidate
        for candidate in build_frozen_chunk_candidates()
        if candidate.production_baseline
    )

    report = run_m2_retrieval_evaluation(
        retrieval_runner_settings,
        project_root=ROOT,
        output_root=tmp_path / "reports",
        source_ids={"m2-v1-mushroom-lamp-manual"},
        case_ids={
            "smoke-syn-001-voltage",
            "smoke-syn-002-cleaning",
            "smoke-safe-037-deleted-manual",
        },
        chunk_candidates=[
            FrozenChunkCandidate(
                config=baseline.config,
                production_baseline=True,
            )
        ],
        depths=(10,),
        rrf_constants=(60,),
        storage=storage,
        embedding_provider=FakeEmbeddingProvider(),
        run_ragas=False,
        reapply_formal_seed=False,
    )

    assert report.run_status == "completed", report.model_dump(mode="json")
    assert len(report.experiments) == 1
    experiment = report.experiments[0]
    assert experiment.index_sets == 1
    assert experiment.chunks > 0
    assert len(experiment.cases) == 9
    assert experiment.trace.route_lists == 9
    assert experiment.trace.candidates > 0
    trace_path = tmp_path / "reports" / report.run_id / experiment.trace.relative_path
    assert trace_path.is_file()
    assert len(trace_path.read_text(encoding="utf-8").splitlines()) == 3
    assert report.filter_audit.deleted_probe_routes == 2
    assert report.filter_audit.deleted_leaks == 0
    assert report.filter_audit.unstable_routes == 0
    assert report.cleanup.evaluation_database_rows_remaining == 0
    assert report.cleanup.evaluation_storage_objects_remaining == 0
    assert report.cleanup.formal_index_sets == 0
    assert report.cleanup.formal_chunks == 0
    assert report.cleanup.baseline_restored is True

    runtime = create_database_runtime(retrieval_runner_settings)
    try:
        with runtime.session_factory() as session:
            assert session.query(DocumentIndexSet).count() == 0
            assert session.query(DocumentChunk).count() == 0
    finally:
        runtime.engine.dispose()
