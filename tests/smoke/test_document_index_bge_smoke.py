from __future__ import annotations

import os

import pytest

from app.core.config import BGE_M3_MODEL_ID, BGE_M3_REVISION, Settings
from scripts.verify_m2_index_pipeline import (
    bge_index_smoke_complete,
    run_bge_index_smoke,
)

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_BGE_M3_INDEX_SMOKE") != "1",
    reason="set RUN_BGE_M3_INDEX_SMOKE=1 to run the pinned offline index Smoke",
)


def test_real_bge_m3_indexes_one_document_idempotently_and_restores_seed() -> None:
    settings = Settings(  # type: ignore[call-arg]
        embedding_backend="bge",
        embedding_model=BGE_M3_MODEL_ID,
        embedding_revision=BGE_M3_REVISION,
        model_local_files_only=True,
        docling_backend="disabled",
    )

    report = run_bge_index_smoke(settings)

    assert bge_index_smoke_complete(report) is True
    assert report["model"] == {
        "model_id": BGE_M3_MODEL_ID,
        "revision": BGE_M3_REVISION,
        "dimensions": 1024,
    }
    assert report["index"]["database_identities"] == [
        [BGE_M3_MODEL_ID, BGE_M3_REVISION]
    ]
    assert report["cleanup"]["baseline_restored"] is True
