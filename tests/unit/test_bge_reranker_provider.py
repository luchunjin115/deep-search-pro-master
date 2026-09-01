from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.core.config import BGE_RERANKER_MODEL_ID, BGE_RERANKER_REVISION, Settings
from app.core.errors import RerankerProviderError
from app.services.retrieval.reranker_provider import (
    BGE_RERANKER_REQUIRED_FILES,
    RERANKER_SNAPSHOT_MANIFEST_NAME,
    BgeRerankerLoadRequest,
    BgeRerankerProvider,
    FakeRerankerProvider,
    create_reranker_provider,
)


class RecordingBackend:
    def __init__(self, output: object | None = None) -> None:
        self.output = output
        self.calls: list[tuple[list[tuple[str, str]], int, int, bool]] = []

    def compute_score(
        self,
        pairs: list[tuple[str, str]],
        *,
        batch_size: int,
        max_length: int,
        normalize: bool,
    ) -> object:
        self.calls.append((pairs, batch_size, max_length, normalize))
        if self.output is not None:
            return self.output
        return [float(index) for index in range(len(pairs))]


class OomThenSuccessBackend(RecordingBackend):
    def compute_score(
        self,
        pairs: list[tuple[str, str]],
        *,
        batch_size: int,
        max_length: int,
        normalize: bool,
    ) -> object:
        self.calls.append((pairs, batch_size, max_length, normalize))
        if batch_size > 1:
            raise MemoryError("private allocator details")
        return [1.0] * len(pairs)


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        model_cache_root=tmp_path,
        docling_model_cache_root=tmp_path / "docling",
        **overrides,  # type: ignore[arg-type]
    )


def _snapshot(tmp_path: Path, *, revision: str = BGE_RERANKER_REVISION) -> Path:
    snapshot = tmp_path / "bge-reranker-v2-m3" / revision
    snapshot.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict[str, object]] = {}
    for relative_path in BGE_RERANKER_REQUIRED_FILES:
        content = f"test:{relative_path}".encode()
        target = snapshot / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        files[relative_path] = {
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }
    (snapshot / RERANKER_SNAPSHOT_MANIFEST_NAME).write_text(
        json.dumps(
            {
                "schema_version": "m2-reranker-snapshot-v1",
                "model_id": BGE_RERANKER_MODEL_ID,
                "revision": revision,
                "files": files,
            }
        ),
        encoding="utf-8",
    )
    return snapshot


def _provider(
    tmp_path: Path,
    backend: object,
    *,
    device: str = "cpu",
    precision: str = "float32",
    batch_size: int = 2,
    cuda_available: bool = False,
) -> tuple[BgeRerankerProvider, list[BgeRerankerLoadRequest]]:
    requests: list[BgeRerankerLoadRequest] = []

    def loader(request: BgeRerankerLoadRequest) -> object:
        assert os.environ["HF_HUB_OFFLINE"] == "1"
        assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
        requests.append(request)
        return backend

    return (
        BgeRerankerProvider(
            snapshot_path=_snapshot(tmp_path),
            requested_device=device,
            precision=precision,  # type: ignore[arg-type]
            batch_size=batch_size,
            backend_loader=loader,
            cuda_is_available=lambda: cuda_available,
        ),
        requests,
    )


def test_bge_reranker_is_lazy_fixed_offline_and_keeps_pair_order(
    tmp_path: Path,
) -> None:
    backend = RecordingBackend(output=[2.0, -1.0])
    provider, requests = _provider(tmp_path, backend)

    assert provider.is_loaded is False
    result = provider.score("问题", ["第一段", "第二段"])

    assert provider.is_loaded is True
    assert len(requests) == 1
    assert requests[0].model_id == BGE_RERANKER_MODEL_ID
    assert requests[0].revision == BGE_RERANKER_REVISION
    assert requests[0].trust_remote_code is False
    assert requests[0].normalize is False
    assert requests[0].max_length == 8192
    assert requests[0].batch_size == 2
    assert backend.calls == [([("问题", "第一段"), ("问题", "第二段")], 2, 8192, False)]
    assert [score.raw_score for score in result.scores] == [2.0, -1.0]
    assert [score.normalized_score for score in result.scores] == pytest.approx(
        [1 / (1 + math.exp(-2)), 1 / (1 + math.exp(1))]
    )
    assert result.effective_batch_size == 2
    assert result.identity.model_id == BGE_RERANKER_MODEL_ID
    assert result.identity.revision == BGE_RERANKER_REVISION


def test_bge_reranker_concurrent_first_load_constructs_backend_once(
    tmp_path: Path,
) -> None:
    requests: list[BgeRerankerLoadRequest] = []
    barrier = threading.Barrier(8)

    def loader(request: BgeRerankerLoadRequest) -> object:
        requests.append(request)
        time.sleep(0.05)
        return RecordingBackend(output=[1.0])

    provider = BgeRerankerProvider(
        snapshot_path=_snapshot(tmp_path),
        backend_loader=loader,
        cuda_is_available=lambda: False,
    )

    def score_together(index: int) -> None:
        barrier.wait()
        provider.score("问题", [f"正文-{index}"])

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(score_together, range(8)))

    assert len(requests) == 1


def test_bge_reranker_retries_only_memory_errors_with_batch_two_then_one(
    tmp_path: Path,
) -> None:
    backend = OomThenSuccessBackend()
    provider, _ = _provider(tmp_path, backend, batch_size=2)

    result = provider.score("问题", ["第一段", "第二段"])

    assert [call[1] for call in backend.calls] == [2, 1]
    assert result.effective_batch_size == 1


def test_bge_reranker_batch_one_oom_is_retryable_and_sanitized(
    tmp_path: Path,
) -> None:
    class ExhaustedBackend(RecordingBackend):
        def compute_score(
            self,
            pairs: list[tuple[str, str]],
            *,
            batch_size: int,
            max_length: int,
            normalize: bool,
        ) -> object:
            del pairs, batch_size, max_length, normalize
            raise MemoryError("D:/private/model and secret input")

    provider, _ = _provider(tmp_path, ExhaustedBackend(), batch_size=1)

    with pytest.raises(RerankerProviderError) as captured:
        provider.score("秘密问题", ["秘密正文"])

    assert captured.value.retryable is True
    assert "private" not in str(captured.value)
    assert "秘密" not in str(captured.value)


@pytest.mark.parametrize(
    "output",
    [
        [],
        [1.0],
        [1.0, math.nan],
        [1.0, math.inf],
        [1.0, True],
        "not scores",
        {"scores": [1.0, 2.0]},
    ],
)
def test_bge_reranker_rejects_malformed_or_nonfinite_backend_output(
    tmp_path: Path,
    output: object,
) -> None:
    provider, _ = _provider(tmp_path, RecordingBackend(output=output))

    with pytest.raises(RerankerProviderError):
        provider.score("问题", ["第一段", "第二段"])


def test_bge_reranker_does_not_retry_or_leak_non_memory_failures(
    tmp_path: Path,
) -> None:
    class BrokenBackend(RecordingBackend):
        def compute_score(
            self,
            pairs: list[tuple[str, str]],
            *,
            batch_size: int,
            max_length: int,
            normalize: bool,
        ) -> object:
            self.calls.append((pairs, batch_size, max_length, normalize))
            raise RuntimeError("D:/private/model; token=secret; CUDA details")

    backend = BrokenBackend()
    provider, _ = _provider(tmp_path, backend)

    with pytest.raises(RerankerProviderError) as captured:
        provider.score("秘密问题", ["秘密正文"])

    assert [call[1] for call in backend.calls] == [2]
    assert captured.value.retryable is False
    assert "private" not in str(captured.value)
    assert "秘密" not in str(captured.value)


@pytest.mark.parametrize(
    ("device", "cuda_available", "expected"),
    [
        ("cpu", False, "cpu"),
        ("auto", False, "cpu"),
        ("auto", True, "cuda"),
        ("cuda", True, "cuda"),
    ],
)
def test_bge_reranker_selects_current_runtime_device(
    tmp_path: Path,
    device: str,
    cuda_available: bool,
    expected: str,
) -> None:
    provider, _ = _provider(
        tmp_path,
        RecordingBackend(),
        device=device,
        cuda_available=cuda_available,
    )

    assert provider.actual_device == expected


def test_bge_reranker_rejects_unavailable_cuda_and_half_precision_cpu(
    tmp_path: Path,
) -> None:
    with pytest.raises(RerankerProviderError):
        _provider(
            tmp_path / "cuda",
            RecordingBackend(),
            device="cuda",
            cuda_available=False,
        )
    with pytest.raises(RerankerProviderError):
        _provider(
            tmp_path / "half",
            RecordingBackend(),
            precision="float16",
        )


def test_bge_reranker_rejects_tampered_snapshot_without_leaking_path(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(tmp_path)
    (snapshot / BGE_RERANKER_REQUIRED_FILES[0]).write_bytes(b"tampered")

    with pytest.raises(RerankerProviderError) as captured:
        BgeRerankerProvider(snapshot_path=snapshot)

    assert str(snapshot) not in str(captured.value)


def test_reranker_factory_keeps_fake_default_and_constructs_real_lazily(
    tmp_path: Path,
) -> None:
    assert isinstance(
        create_reranker_provider(_settings(tmp_path)),
        FakeRerankerProvider,
    )
    _snapshot(tmp_path)
    provider = create_reranker_provider(
        _settings(
            tmp_path,
            reranker_backend="bge",
            reranker_model=BGE_RERANKER_MODEL_ID,
            reranker_revision=BGE_RERANKER_REVISION,
        )
    )

    assert isinstance(provider, BgeRerankerProvider)
    assert provider.is_loaded is False


def test_backend_array_adapter_preserves_count_and_order(tmp_path: Path) -> None:
    class ArrayLike:
        def tolist(self) -> list[float]:
            return [3.0, -2.0]

    provider, _ = _provider(tmp_path, RecordingBackend(output=ArrayLike()))

    result = provider.score("问题", ["第一段", "第二段"])

    assert [score.raw_score for score in result.scores] == [3.0, -2.0]
