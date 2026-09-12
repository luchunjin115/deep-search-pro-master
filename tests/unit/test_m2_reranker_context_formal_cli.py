from __future__ import annotations

from pathlib import Path

import pytest

from scripts.run_m2_reranker_context_formal_evaluation import (
    DEFAULT_OUTPUT,
    _formal_settings,
    _parse_args,
    _validated_output,
)


def test_formal_cli_requires_explicit_real_run_flag() -> None:
    with pytest.raises(SystemExit):
        _parse_args([])

    arguments = _parse_args(["--run-real"])

    assert arguments.run_real is True
    assert arguments.keep_report is False
    assert arguments.output == DEFAULT_OUTPUT

    kept = _parse_args(["--run-real", "--keep-report"])
    assert kept.keep_report is True
    assert kept.reranker_device == "cpu"

    calibration = _parse_args(
        ["--run-real", "--keep-report", "--reranker-device", "cuda"]
    )
    assert calibration.reranker_device == "cuda"


def test_formal_cli_freezes_offline_models_and_bounded_runtime() -> None:
    settings = _formal_settings()

    assert settings.embedding_backend == "bge"
    assert settings.embedding_revision == "5617a9f61b028005a4858fdac845db406aefb181"
    assert settings.reranker_backend == "bge"
    assert settings.reranker_revision == "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
    assert settings.model_device == "cpu"
    assert settings.model_local_files_only is True
    assert settings.embedding_batch_size == 16
    assert settings.reranker_batch_size == 2
    assert settings.database_statement_timeout_ms == 30_000


def test_formal_cli_only_deletes_a_managed_temporary_report(tmp_path: Path) -> None:
    managed = DEFAULT_OUTPUT.parent / "nested" / "formal.json"

    assert _validated_output(managed) == managed.resolve()
    with pytest.raises(ValueError, match="managed report directory"):
        _validated_output(tmp_path / "unrelated.json")
