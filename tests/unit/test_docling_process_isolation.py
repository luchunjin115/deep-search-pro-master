from __future__ import annotations

import logging
import re

import psutil  # type: ignore[import-untyped]
import pytest

from app.core.config import Settings
from app.services.documents.parsers.base import DocumentEnhancementError
from app.services.documents.parsers.docling import (
    DoclingTextSnapshot,
    LocalDoclingProvider,
)
from tests.fixtures.docling_process_worker import controlled_docling_worker


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "docling_backend": "docling",
        "docling_process_timeout_seconds": 2.0,
        "docling_process_max_rss_bytes": 512 * 1024 * 1024,
        "docling_process_max_snapshot_bytes": 1024 * 1024,
    }
    values.update(overrides)
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        **values,  # type: ignore[arg-type]
    )


def _provider(**overrides: object) -> LocalDoclingProvider:
    return LocalDoclingProvider(
        _settings(**overrides),
        worker_target=controlled_docling_worker,
    )


def test_timeout_worker_is_destroyed_and_next_document_starts_clean(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.services.documents.parsers.docling")
    provider = _provider()

    with pytest.raises(DocumentEnhancementError, match="^复杂文档增强解析失败$"):
        provider.parse(
            source_name="timeout.pdf",
            source_type="pdf",
            content=b"first",
        )

    timeout_log = next(
        record.getMessage()
        for record in caplog.records
        if "status=timeout" in record.getMessage()
    )
    timeout_pid_match = re.search(r"worker_pid=(\d+)", timeout_log)
    assert timeout_pid_match is not None
    timeout_pid = int(timeout_pid_match.group(1))
    assert not psutil.pid_exists(timeout_pid)

    snapshot = provider.parse(
        source_name="success.pdf",
        source_type="pdf",
        content=b"second",
    )

    assert len(snapshot.items) == 1
    item = snapshot.items[0]
    assert isinstance(item, DoclingTextSnapshot)
    assert "run_count=1" in item.text
    assert f"pid={timeout_pid}" not in item.text


@pytest.mark.parametrize(
    ("source_name", "expected_status"),
    (
        ("crash.pdf", "worker_crash"),
        ("oversized.pdf", "result_too_large"),
        ("lingering.pdf", "shutdown_timeout"),
    ),
)
def test_worker_crash_and_oversized_result_fail_safely(
    source_name: str,
    expected_status: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.services.documents.parsers.docling")

    with pytest.raises(DocumentEnhancementError, match="^复杂文档增强解析失败$"):
        _provider(docling_process_max_snapshot_bytes=1024).parse(
            source_name=source_name,
            source_type="pdf",
            content=b"unsafe-result",
        )

    assert any(
        f"status={expected_status}" in record.getMessage() for record in caplog.records
    )


def test_worker_exceeding_sampled_rss_limit_is_destroyed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.services.documents.parsers.docling")

    with pytest.raises(DocumentEnhancementError, match="^复杂文档增强解析失败$"):
        _provider(docling_process_max_rss_bytes=1024 * 1024).parse(
            source_name="memory.pdf",
            source_type="pdf",
            content=b"memory",
        )

    assert any(
        "status=memory_limit" in record.getMessage() for record in caplog.records
    )


def test_one_shot_worker_exits_after_sending_result_despite_lingering_thread(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="app.services.documents.parsers.docling")

    snapshot = _provider(docling_process_timeout_seconds=15.0).parse(
        source_name="hard-exit-lingering.pdf",
        source_type="pdf",
        content=b"result-is-complete",
    )

    item = snapshot.items[0]
    assert isinstance(item, DoclingTextSnapshot)
    worker_pid = int(item.text.split(";", maxsplit=1)[0].removeprefix("pid="))
    assert not psutil.pid_exists(worker_pid)
    assert any("status=success" in record.getMessage() for record in caplog.records)
