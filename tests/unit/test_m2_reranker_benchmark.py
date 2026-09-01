from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from app.core.config import BGE_RERANKER_MODEL_ID, BGE_RERANKER_REVISION, Settings
from app.services.retrieval.reranker_provider import (
    BGE_RERANKER_REQUIRED_FILES,
    RERANKER_SNAPSHOT_MANIFEST_NAME,
    FakeRerankerProvider,
)
from scripts.benchmark_m2_reranker import (
    RERANKER_BENCHMARK_SCHEMA_VERSION,
    RerankerBenchmarkError,
    run_benchmark,
    validate_machine_label,
    write_report,
)
from scripts.download_m2_reranker import (
    RerankerSnapshotError,
    ensure_reranker_snapshot,
)


class BenchmarkFakeProvider(FakeRerankerProvider):
    actual_device = "cpu"

    def __init__(self) -> None:
        super().__init__()
        self.load_calls = 0

    def load(self) -> None:
        self.load_calls += 1


def _settings(tmp_path: Path) -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        model_cache_root=tmp_path,
        docling_model_cache_root=tmp_path / "docling",
        model_device="auto",
    )


def test_snapshot_download_requires_explicit_permission(tmp_path: Path) -> None:
    called = False

    def downloader(**_: Any) -> str:
        nonlocal called
        called = True
        return str(tmp_path)

    with pytest.raises(RerankerSnapshotError, match="--allow-download"):
        ensure_reranker_snapshot(
            tmp_path,
            allow_download=False,
            downloader=downloader,
        )

    assert called is False


def test_snapshot_download_pins_revision_and_writes_file_hash_manifest(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    def downloader(**kwargs: Any) -> str:
        calls.append(kwargs)
        target = Path(kwargs["local_dir"])
        target.mkdir(parents=True, exist_ok=True)
        for relative_path in BGE_RERANKER_REQUIRED_FILES:
            path = target / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(relative_path.encode())
        return str(target)

    snapshot = ensure_reranker_snapshot(
        tmp_path,
        allow_download=True,
        downloader=downloader,
    )
    manifest = json.loads(
        (snapshot / RERANKER_SNAPSHOT_MANIFEST_NAME).read_text(encoding="utf-8")
    )

    assert calls[0]["repo_id"] == BGE_RERANKER_MODEL_ID
    assert calls[0]["revision"] == BGE_RERANKER_REVISION
    assert calls[0]["local_dir"] == snapshot
    assert calls[0]["token"] is False
    assert calls[0]["max_workers"] == 1
    assert manifest["schema_version"] == "m2-reranker-snapshot-v1"
    assert manifest["model_id"] == BGE_RERANKER_MODEL_ID
    assert manifest["revision"] == BGE_RERANKER_REVISION
    assert set(manifest["files"]) == set(BGE_RERANKER_REQUIRED_FILES)
    for relative_path, metadata in manifest["files"].items():
        content = relative_path.encode()
        assert metadata == {
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }


def test_snapshot_manifest_does_not_hide_corrupted_weights(tmp_path: Path) -> None:
    def downloader(**kwargs: Any) -> str:
        target = Path(kwargs["local_dir"])
        target.mkdir(parents=True, exist_ok=True)
        for relative_path in BGE_RERANKER_REQUIRED_FILES:
            path = target / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(relative_path.encode())
        return str(target)

    snapshot = ensure_reranker_snapshot(
        tmp_path,
        allow_download=True,
        downloader=downloader,
    )
    (snapshot / BGE_RERANKER_REQUIRED_FILES[0]).write_bytes(b"corrupt")

    with pytest.raises(RerankerSnapshotError, match="--allow-download"):
        ensure_reranker_snapshot(tmp_path, allow_download=False)


@pytest.mark.parametrize(
    "label",
    ["", "Machine-A", "machine_a", "../machine-a", "machine/a", "a" * 33],
)
def test_benchmark_machine_label_is_anonymous_and_path_safe(label: str) -> None:
    with pytest.raises(RerankerBenchmarkError):
        validate_machine_label(label)


def test_fake_benchmark_has_stable_schema_quality_latency_and_no_path(
    tmp_path: Path,
) -> None:
    provider = BenchmarkFakeProvider()

    report = run_benchmark(
        _settings(tmp_path),
        machine_label="machine-a",
        provider=provider,
        iterations=3,
    )

    assert report["schema_version"] == RERANKER_BENCHMARK_SCHEMA_VERSION
    assert report["synthetic_data"] is True
    assert report["offline_inference"] is True
    assert report["runtime"]["actual_device"] == "cpu"
    assert report["measurements"]["load_seconds"] >= 0
    assert report["measurements"]["latency_p50_seconds"] >= 0
    assert report["measurements"]["latency_p95_seconds"] >= 0
    assert report["measurements"]["rss_peak_mib"] > 0
    assert report["corpus"]["pair_count"] == 6
    assert set(report["quality"]) == {
        "chinese_order_passed",
        "english_order_passed",
        "sku_order_passed",
        "scores",
    }
    assert provider.load_calls == 1
    assert str(tmp_path) not in json.dumps(report, ensure_ascii=False)


def test_benchmark_report_writes_only_beneath_output_root(tmp_path: Path) -> None:
    report = run_benchmark(
        _settings(tmp_path),
        machine_label="machine-b",
        provider=BenchmarkFakeProvider(),
        iterations=1,
    )

    output = write_report(report, output_root=tmp_path / "reports")

    assert output == tmp_path / "reports/machine-b.json"
    assert json.loads(output.read_text(encoding="utf-8")) == report
