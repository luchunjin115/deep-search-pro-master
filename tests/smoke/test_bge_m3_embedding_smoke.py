from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from app.core.config import BGE_M3_MODEL_ID, BGE_M3_REVISION, Settings
from app.services.retrieval.embedding import (
    BgeM3EmbeddingProvider,
    create_embedding_provider,
)
from scripts.benchmark_m2_embedding import ensure_bge_snapshot, run_benchmark

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_BGE_M3_SMOKE") != "1",
    reason="set RUN_BGE_M3_SMOKE=1 to load the pinned local BGE-M3 snapshot",
)


@pytest.fixture(scope="module")
def real_report() -> Iterator[dict[str, object]]:
    settings = Settings(  # type: ignore[call-arg]
        embedding_backend="bge",
        embedding_model=BGE_M3_MODEL_ID,
        embedding_revision=BGE_M3_REVISION,
        model_local_files_only=True,
    )
    ensure_bge_snapshot(settings.model_cache_root, allow_download=False)
    provider = create_embedding_provider(settings)
    assert isinstance(provider, BgeM3EmbeddingProvider)
    report = run_benchmark(
        settings,
        machine_label="smoke-local",
        provider=provider,
    )
    yield report


def test_real_bge_m3_multilingual_similarity_and_device(
    real_report: dict[str, object],
) -> None:
    quality = real_report["quality"]
    runtime = real_report["runtime"]

    assert isinstance(quality, dict)
    assert quality["chinese_order_passed"] is True
    assert quality["cross_language_order_passed"] is True
    assert isinstance(runtime, dict)
    assert runtime["actual_device"] in {"cpu", "cuda"}
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"


def test_real_bge_m3_fixed_identity_long_text_and_vectors(
    real_report: dict[str, object],
) -> None:
    model = real_report["model"]
    corpus = real_report["corpus"]
    vectors = real_report["vectors"]

    assert isinstance(model, dict)
    assert model["model_id"] == BGE_M3_MODEL_ID
    assert model["revision"] == BGE_M3_REVISION
    assert model["dimensions"] == 1024
    assert model["normalize"] is True
    assert isinstance(corpus, dict)
    assert 650 <= corpus["long_m2_token_count"] <= 700
    assert isinstance(vectors, dict)
    assert vectors["sample_count"] == 7
    assert vectors["dimension"] == 1024
    assert vectors["norm_min"] == pytest.approx(1.0, abs=1e-3)
    assert vectors["norm_max"] == pytest.approx(1.0, abs=1e-3)
    cache_keys = vectors["cache_keys"]
    assert isinstance(cache_keys, dict)
    assert len(cache_keys) == 7
    assert all(str(value).startswith("sha256:") for value in cache_keys.values())
