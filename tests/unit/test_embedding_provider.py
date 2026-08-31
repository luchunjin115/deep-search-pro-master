from __future__ import annotations

import json
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import EmbeddingInputError, EmbeddingProviderError
from app.services.retrieval.embedding import (
    BGE_M3_MODEL_ID,
    BGE_M3_REQUIRED_FILES,
    BGE_M3_REVISION,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MAX_INPUT_CHARACTERS,
    EMBEDDING_MAX_TEXTS,
    SNAPSHOT_MANIFEST_NAME,
    BgeBackendLoadRequest,
    BgeM3EmbeddingProvider,
    EmbeddingPurpose,
    FakeEmbeddingProvider,
    build_embedding_cache_key,
    create_embedding_provider,
)


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


class RecordingBgeBackend:
    def __init__(self, *, output: object | None = None) -> None:
        self.output = output
        self.calls: list[tuple[str, list[str], int, int]] = []

    def encode_corpus(
        self,
        texts: list[str],
        *,
        batch_size: int,
        max_length: int,
        **_: Any,
    ) -> object:
        self.calls.append(("document", texts, batch_size, max_length))
        return self.output if self.output is not None else _dense_output(texts)

    def encode_queries(
        self,
        texts: list[str],
        *,
        batch_size: int,
        max_length: int,
        **_: Any,
    ) -> object:
        self.calls.append(("query", texts, batch_size, max_length))
        return self.output if self.output is not None else _dense_output(texts)


class OomThenSuccessBackend(RecordingBgeBackend):
    def _encode(self, texts: list[str], batch_size: int) -> object:
        if batch_size > 1:
            raise RuntimeError("CUDA out of memory")
        return _dense_output(texts)

    def encode_corpus(
        self, texts: list[str], *, batch_size: int, max_length: int, **_: Any
    ) -> object:
        self.calls.append(("document", texts, batch_size, max_length))
        return self._encode(texts, batch_size)


def _dense_output(texts: list[str]) -> dict[str, list[list[float]]]:
    vectors: list[list[float]] = []
    for text in texts:
        vector = [0.0] * EMBEDDING_DIMENSIONS
        vector[sum(text.encode("utf-8")) % EMBEDDING_DIMENSIONS] = 1.0
        vectors.append(vector)
    return {"dense_vecs": vectors}


def _snapshot(tmp_path: Path, *, revision: str = BGE_M3_REVISION) -> Path:
    snapshot = tmp_path / "bge-m3" / revision
    snapshot.mkdir(parents=True, exist_ok=True)
    (snapshot / SNAPSHOT_MANIFEST_NAME).write_text(
        json.dumps({"model_id": BGE_M3_MODEL_ID, "revision": revision}),
        encoding="utf-8",
    )
    for relative_path in BGE_M3_REQUIRED_FILES:
        (snapshot / relative_path).write_bytes(b"test")
    return snapshot


def _bge_provider(
    tmp_path: Path,
    backend: object,
    *,
    device: str = "cpu",
    batch_size: int = 4,
    precision: str = "float32",
    cuda_available: bool = False,
) -> tuple[BgeM3EmbeddingProvider, list[BgeBackendLoadRequest]]:
    requests: list[BgeBackendLoadRequest] = []

    def loader(request: BgeBackendLoadRequest) -> object:
        assert os.environ["HF_HUB_OFFLINE"] == "1"
        assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
        requests.append(request)
        return backend

    return (
        BgeM3EmbeddingProvider(
            snapshot_path=_snapshot(tmp_path),
            requested_device=device,
            precision=precision,
            batch_size=batch_size,
            backend_loader=loader,
            cuda_is_available=lambda: cuda_available,
        ),
        requests,
    )


def test_fake_embedding_is_deterministic_normalized_and_keeps_order() -> None:
    provider = FakeEmbeddingProvider()
    texts = ["alpha document", "beta document"]

    first = provider.embed(texts, purpose=EmbeddingPurpose.DOCUMENT)
    second = FakeEmbeddingProvider().embed(
        texts,
        purpose=EmbeddingPurpose.DOCUMENT,
    )
    individually = [
        provider.embed([text], purpose=EmbeddingPurpose.DOCUMENT).vectors[0]
        for text in texts
    ]

    assert first == second
    assert list(first.vectors) == individually
    assert len(first.vectors) == len(texts)
    assert all(len(vector) == EMBEDDING_DIMENSIONS for vector in first.vectors)
    assert all(math.isfinite(value) for vector in first.vectors for value in vector)
    assert all(
        math.isclose(math.sqrt(sum(value * value for value in vector)), 1.0)
        for vector in first.vectors
    )


def test_embedding_purpose_is_part_of_result_and_cache_key() -> None:
    provider = FakeEmbeddingProvider()

    document = provider.embed(["same text"], purpose=EmbeddingPurpose.DOCUMENT)
    query = provider.embed(["same text"], purpose=EmbeddingPurpose.QUERY)

    assert document.purpose is EmbeddingPurpose.DOCUMENT
    assert query.purpose is EmbeddingPurpose.QUERY
    assert document.cache_keys != query.cache_keys
    assert document.identity == query.identity


@pytest.mark.parametrize(
    "texts",
    [
        [],
        [""],
        ["   \t\n"],
        ["valid", 42],
        ["x"] * (EMBEDDING_MAX_TEXTS + 1),
        ["x" * (EMBEDDING_MAX_INPUT_CHARACTERS + 1)],
    ],
)
def test_fake_embedding_rejects_invalid_or_unbounded_texts(texts: object) -> None:
    with pytest.raises(EmbeddingInputError):
        FakeEmbeddingProvider().embed(
            texts,  # type: ignore[arg-type]
            purpose=EmbeddingPurpose.DOCUMENT,
        )


def test_default_factory_returns_offline_fake_provider() -> None:
    provider = create_embedding_provider(_settings())

    assert isinstance(provider, FakeEmbeddingProvider)
    assert provider.embed(
        ["factory remains offline"],
        purpose=EmbeddingPurpose.QUERY,
    ).vectors


def test_bge_settings_only_accept_the_fixed_model_and_revision() -> None:
    valid = _settings(
        embedding_backend="bge",
        embedding_model=BGE_M3_MODEL_ID,
        embedding_revision=BGE_M3_REVISION,
    )

    assert valid.embedding_pooling == "cls"
    assert valid.embedding_max_length == 8192
    assert valid.embedding_precision == "float32"

    with pytest.raises(ValidationError):
        _settings(
            embedding_backend="bge",
            embedding_model="BAAI/a-different-model",
            embedding_revision=BGE_M3_REVISION,
        )
    with pytest.raises(ValidationError):
        _settings(
            embedding_backend="bge",
            embedding_model=BGE_M3_MODEL_ID,
            embedding_revision="f" * 40,
        )


def test_precision_changes_embedding_cache_identity() -> None:
    provider = FakeEmbeddingProvider()
    float32_key = build_embedding_cache_key(
        provider.identity,
        EmbeddingPurpose.DOCUMENT,
        "same source text",
    )
    float16_key = build_embedding_cache_key(
        replace(provider.identity, precision="float16"),
        EmbeddingPurpose.DOCUMENT,
        "same source text",
    )

    assert float32_key.startswith("sha256:")
    assert float32_key != float16_key


def test_fake_cache_key_keeps_the_v1_golden_contract() -> None:
    result = FakeEmbeddingProvider().embed(
        ["fixed cache text"],
        purpose=EmbeddingPurpose.DOCUMENT,
    )

    assert result.cache_keys == (
        "sha256:0fc5dba28c1bb898c2d816188c04b95c399723251304cc8adaaf198de2b4eb43",
    )


def test_bge_is_lazy_loads_once_and_routes_document_and_query(tmp_path: Path) -> None:
    backend = RecordingBgeBackend()
    provider, requests = _bge_provider(tmp_path, backend)

    assert requests == []
    document = provider.embed(["alpha", "beta"], purpose=EmbeddingPurpose.DOCUMENT)
    query = provider.embed(["gamma"], purpose=EmbeddingPurpose.QUERY)

    assert len(requests) == 1
    assert requests[0].snapshot_path == provider.snapshot_path
    assert requests[0].trust_remote_code is False
    assert [call[0] for call in backend.calls] == ["document", "query"]
    assert document.vectors == tuple(
        tuple(row) for row in _dense_output(["alpha", "beta"])["dense_vecs"]
    )
    assert query.effective_batch_size == 4


def test_bge_explicit_load_is_idempotent_for_benchmarking(tmp_path: Path) -> None:
    provider, requests = _bge_provider(tmp_path, RecordingBgeBackend())

    provider.load()
    provider.load()

    assert provider.is_loaded is True
    assert len(requests) == 1


def test_bge_concurrent_first_load_constructs_backend_once(tmp_path: Path) -> None:
    requests: list[BgeBackendLoadRequest] = []
    start = threading.Barrier(8)

    def loader(request: BgeBackendLoadRequest) -> object:
        requests.append(request)
        time.sleep(0.05)
        return RecordingBgeBackend()

    provider = BgeM3EmbeddingProvider(
        snapshot_path=_snapshot(tmp_path),
        backend_loader=loader,
        cuda_is_available=lambda: False,
    )

    def load_together() -> None:
        start.wait()
        provider.load()

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _index: load_together(), range(8)))

    assert len(requests) == 1


@pytest.mark.parametrize(
    ("requested", "cuda_available", "expected"),
    [
        ("cpu", False, "cpu"),
        ("auto", False, "cpu"),
        ("auto", True, "cuda"),
        ("cuda", True, "cuda"),
    ],
)
def test_bge_selects_device_from_current_runtime_capability(
    tmp_path: Path,
    requested: str,
    cuda_available: bool,
    expected: str,
) -> None:
    provider, _ = _bge_provider(
        tmp_path,
        RecordingBgeBackend(),
        device=requested,
        cuda_available=cuda_available,
    )

    assert provider.actual_device == expected


def test_bge_rejects_unavailable_cuda_and_half_precision_cpu(tmp_path: Path) -> None:
    with pytest.raises(EmbeddingProviderError):
        _bge_provider(
            tmp_path,
            RecordingBgeBackend(),
            device="cuda",
            cuda_available=False,
        )
    with pytest.raises(EmbeddingProviderError):
        _bge_provider(
            tmp_path,
            RecordingBgeBackend(),
            device="cpu",
            precision="float16",
        )


def test_bge_rejects_snapshot_with_wrong_revision_without_leaking_path(
    tmp_path: Path,
) -> None:
    bad_snapshot = _snapshot(tmp_path, revision="f" * 40)

    with pytest.raises(EmbeddingProviderError) as captured:
        BgeM3EmbeddingProvider(snapshot_path=bad_snapshot)

    assert str(bad_snapshot) not in str(captured.value)


@pytest.mark.parametrize(
    "output",
    [
        {},
        {"dense_vecs": [[1.0] * EMBEDDING_DIMENSIONS]},
        {"dense_vecs": [[1.0] * (EMBEDDING_DIMENSIONS - 1)] * 2},
        {"dense_vecs": [[math.nan] + [0.0] * (EMBEDDING_DIMENSIONS - 1)] * 2},
        {"dense_vecs": [[2.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)] * 2},
    ],
)
def test_bge_rejects_malformed_or_unsafe_dense_output(
    tmp_path: Path,
    output: object,
) -> None:
    provider, _ = _bge_provider(tmp_path, RecordingBgeBackend(output=output))

    with pytest.raises(EmbeddingProviderError):
        provider.embed(["first", "second"], purpose=EmbeddingPurpose.DOCUMENT)


def test_bge_retries_only_memory_errors_with_halved_batch(tmp_path: Path) -> None:
    backend = OomThenSuccessBackend()
    provider, _ = _bge_provider(tmp_path, backend, batch_size=4)

    result = provider.embed(["first", "second"], purpose=EmbeddingPurpose.DOCUMENT)

    assert [call[2] for call in backend.calls] == [4, 2, 1]
    assert result.effective_batch_size == 1


def test_device_and_batch_do_not_change_embedding_cache_key(tmp_path: Path) -> None:
    cpu, _ = _bge_provider(
        tmp_path / "cpu",
        RecordingBgeBackend(),
        device="cpu",
        batch_size=1,
    )
    cuda, _ = _bge_provider(
        tmp_path / "cuda",
        RecordingBgeBackend(),
        device="cuda",
        batch_size=4,
        cuda_available=True,
    )

    cpu_result = cpu.embed(["same text"], purpose=EmbeddingPurpose.QUERY)
    cuda_result = cuda.embed(["same text"], purpose=EmbeddingPurpose.QUERY)

    assert cpu_result.identity == cuda_result.identity
    assert cpu_result.cache_keys == cuda_result.cache_keys


def test_bge_does_not_retry_non_memory_or_malformed_output_errors(
    tmp_path: Path,
) -> None:
    class BrokenBackend(RecordingBgeBackend):
        def encode_corpus(
            self, texts: list[str], *, batch_size: int, max_length: int, **_: Any
        ) -> object:
            self.calls.append(("document", texts, batch_size, max_length))
            raise RuntimeError("unrelated backend failure with private details")

    backend = BrokenBackend()
    provider, _ = _bge_provider(tmp_path, backend)

    with pytest.raises(EmbeddingProviderError) as captured:
        provider.embed(["secret input"], purpose=EmbeddingPurpose.DOCUMENT)

    assert [call[2] for call in backend.calls] == [4]
    assert "private details" not in str(captured.value)
    assert "secret input" not in str(captured.value)


def test_bge_batch_one_memory_failure_is_retryable_and_sanitized(
    tmp_path: Path,
) -> None:
    class ExhaustedBackend(RecordingBgeBackend):
        def encode_corpus(
            self, texts: list[str], *, batch_size: int, max_length: int, **_: Any
        ) -> object:
            self.calls.append(("document", texts, batch_size, max_length))
            raise MemoryError("private allocator and machine details")

    backend = ExhaustedBackend()
    provider, _ = _bge_provider(tmp_path, backend, batch_size=1)

    with pytest.raises(EmbeddingProviderError) as captured:
        provider.embed(["secret input"], purpose=EmbeddingPurpose.DOCUMENT)

    assert [call[2] for call in backend.calls] == [1]
    assert captured.value.retryable is True
    assert "private allocator" not in str(captured.value)
    assert "secret input" not in str(captured.value)


def test_bge_retries_common_pytorch_cpu_allocator_oom(tmp_path: Path) -> None:
    class CpuOomThenSuccessBackend(RecordingBgeBackend):
        def encode_corpus(
            self,
            texts: list[str],
            *,
            batch_size: int,
            max_length: int,
            **_: Any,
        ) -> object:
            self.calls.append(("document", texts, batch_size, max_length))
            if batch_size > 1:
                raise RuntimeError("DefaultCPUAllocator: not enough memory")
            return _dense_output(texts)

    backend = CpuOomThenSuccessBackend()
    provider, _ = _bge_provider(tmp_path, backend, batch_size=4)

    result = provider.embed(["first", "second"], purpose=EmbeddingPurpose.DOCUMENT)

    assert [call[2] for call in backend.calls] == [4, 2, 1]
    assert result.effective_batch_size == 1


def test_bge_sanitizes_snapshot_stat_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _snapshot(tmp_path)
    original_is_file = Path.is_file
    original_stat = Path.stat

    def controlled_is_file(path: Path) -> bool:
        if path.name == "config.json":
            return True
        return original_is_file(path)

    def controlled_stat(path: Path, *args: object, **kwargs: object) -> os.stat_result:
        if path.name == "config.json":
            raise OSError(f"private path: {path}")
        return original_stat(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "is_file", controlled_is_file)
    monkeypatch.setattr(Path, "stat", controlled_stat)

    with pytest.raises(EmbeddingProviderError) as captured:
        BgeM3EmbeddingProvider(snapshot_path=snapshot)

    assert str(snapshot) not in str(captured.value)


def test_bge_factory_constructs_without_loading_model(tmp_path: Path) -> None:
    _snapshot(tmp_path)
    settings = _settings(
        embedding_backend="bge",
        embedding_model=BGE_M3_MODEL_ID,
        embedding_revision=BGE_M3_REVISION,
        model_cache_root=tmp_path,
        docling_model_cache_root=tmp_path / "docling",
    )

    provider = create_embedding_provider(settings)

    assert isinstance(provider, BgeM3EmbeddingProvider)
    assert provider.is_loaded is False
