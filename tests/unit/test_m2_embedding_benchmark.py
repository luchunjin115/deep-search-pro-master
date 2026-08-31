from __future__ import annotations

import getpass
import json
import math
import platform
from argparse import Namespace
from pathlib import Path
from typing import Any

import pytest

import scripts.benchmark_m2_embedding as benchmark_module
from app.core.config import Settings
from app.core.errors import EmbeddingProviderError
from app.services.retrieval.embedding import (
    BGE_M3_MODEL_ID,
    BGE_M3_REQUIRED_FILES,
    BGE_M3_REVISION,
    EmbeddingPurpose,
    FakeEmbeddingProvider,
)
from scripts.benchmark_m2_embedding import (
    BENCHMARK_SCHEMA_VERSION,
    EmbeddingBenchmarkError,
    ensure_bge_snapshot,
    run_benchmark,
    validate_machine_label,
    write_report,
)


class BenchmarkFakeProvider(FakeEmbeddingProvider):
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


def _all_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [
            text
            for key, item in value.items()
            for text in [*_all_strings(key), *_all_strings(item)]
        ]
    if isinstance(value, list):
        return [text for item in value for text in _all_strings(item)]
    return []


def test_snapshot_download_requires_explicit_permission(tmp_path: Path) -> None:
    called = False

    def downloader(**_: Any) -> str:
        nonlocal called
        called = True
        return str(tmp_path)

    with pytest.raises(EmbeddingBenchmarkError, match="--allow-download"):
        ensure_bge_snapshot(
            tmp_path,
            allow_download=False,
            downloader=downloader,
        )

    assert called is False


def test_snapshot_marker_does_not_hide_missing_model_weights(tmp_path: Path) -> None:
    snapshot = tmp_path / "bge-m3" / BGE_M3_REVISION
    snapshot.mkdir(parents=True)
    (snapshot / "m2_embedding_snapshot.json").write_text(
        json.dumps({"model_id": BGE_M3_MODEL_ID, "revision": BGE_M3_REVISION}),
        encoding="utf-8",
    )

    with pytest.raises(EmbeddingBenchmarkError, match="--allow-download"):
        ensure_bge_snapshot(tmp_path, allow_download=False)


def test_snapshot_download_pins_model_revision_and_writes_manifest(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []

    def downloader(**kwargs: Any) -> str:
        calls.append(kwargs)
        local_dir = Path(kwargs["local_dir"])
        local_dir.mkdir(parents=True, exist_ok=True)
        for relative_path in BGE_M3_REQUIRED_FILES:
            (local_dir / relative_path).write_bytes(b"test")
        return str(kwargs["local_dir"])

    snapshot = ensure_bge_snapshot(
        tmp_path,
        allow_download=True,
        downloader=downloader,
    )
    manifest = json.loads(
        (snapshot / "m2_embedding_snapshot.json").read_text(encoding="utf-8")
    )

    assert calls == [
        {
            "repo_id": BGE_M3_MODEL_ID,
            "revision": BGE_M3_REVISION,
            "local_dir": snapshot,
            "token": False,
            "ignore_patterns": [
                "onnx/**",
                "imgs/**",
                "*.jpg",
                "*.webp",
                "**/.DS_Store",
            ],
            "max_workers": 1,
        }
    ]
    assert manifest == {
        "model_id": BGE_M3_MODEL_ID,
        "revision": BGE_M3_REVISION,
    }


@pytest.mark.parametrize(
    "label",
    ["", "Machine-A", "machine_a", "../machine-a", "machine-a/second", "a" * 33],
)
def test_machine_label_rejects_identifying_or_path_like_values(label: str) -> None:
    with pytest.raises(EmbeddingBenchmarkError):
        validate_machine_label(label)


def test_machine_label_rejects_username_or_hostname_substrings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(benchmark_module.getpass, "getuser", lambda: "alice")
    monkeypatch.setattr(
        benchmark_module.platform,
        "node",
        lambda: "alice-workstation",
    )

    with pytest.raises(EmbeddingBenchmarkError):
        validate_machine_label("alice-gpu")
    with pytest.raises(EmbeddingBenchmarkError):
        validate_machine_label("lab-alice-workstation")


def test_benchmark_report_has_stable_schema_without_machine_identity(
    tmp_path: Path,
) -> None:
    provider = BenchmarkFakeProvider()

    report = run_benchmark(
        _settings(tmp_path),
        machine_label="machine-a",
        provider=provider,
    )

    assert report["schema_version"] == BENCHMARK_SCHEMA_VERSION
    assert report["machine_label"] == "machine-a"
    assert report["synthetic_data"] is True
    assert report["offline_inference"] is True
    assert report["model"]["dimensions"] == 1024
    assert report["runtime"]["actual_device"] == "cpu"
    assert report["measurements"]["load_seconds"] >= 0
    assert report["measurements"]["encode_seconds"] > 0
    assert report["measurements"]["throughput_texts_per_second"] > 0
    assert report["measurements"]["rss_peak_mib"] > 0
    assert report["vectors"]["sample_count"] == 7
    assert report["vectors"]["dimension"] == 1024
    assert math.isclose(report["vectors"]["norm_min"], 1.0)
    assert report["corpus"]["long_m2_token_count"] >= 650
    assert set(report["quality"]) == {
        "chinese_related_similarity",
        "chinese_unrelated_similarity",
        "chinese_order_passed",
        "cross_language_related_similarity",
        "cross_language_unrelated_similarity",
        "cross_language_order_passed",
    }
    assert provider.load_calls == 1

    rendered = "\n".join(_all_strings(report)).casefold()
    assert str(tmp_path).casefold() not in rendered
    assert platform.node().casefold() not in rendered
    assert getpass.getuser().casefold() not in rendered


def test_report_is_written_beneath_machine_specific_output(tmp_path: Path) -> None:
    report = run_benchmark(
        _settings(tmp_path),
        machine_label="machine-b",
        provider=BenchmarkFakeProvider(),
    )

    output = write_report(report, output_root=tmp_path / "reports")

    assert output == tmp_path / "reports" / "machine-b.json"
    assert json.loads(output.read_text(encoding="utf-8")) == report


def test_fake_still_supports_both_benchmark_purposes() -> None:
    provider = BenchmarkFakeProvider()

    assert provider.embed(["doc"], purpose=EmbeddingPurpose.DOCUMENT).vectors
    assert provider.embed(["query"], purpose=EmbeddingPurpose.QUERY).vectors


def test_cli_sanitizes_provider_failures(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        benchmark_module,
        "parse_args",
        lambda: Namespace(
            machine_label="machine-a",
            allow_download=False,
            device="auto",
            batch_size=4,
            precision="float32",
        ),
    )
    monkeypatch.setattr(
        benchmark_module,
        "ensure_bge_snapshot",
        lambda *_args, **_kwargs: Path("managed-snapshot"),
    )

    def fail_benchmark(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise EmbeddingProviderError

    monkeypatch.setattr(benchmark_module, "run_benchmark", fail_benchmark)

    assert benchmark_module.main() == 1
    output = capsys.readouterr().out
    assert "M2 Embedding基准失败" in output
    assert "managed-snapshot" not in output
