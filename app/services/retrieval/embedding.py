"""Hardware-independent Embedding contract and deterministic offline fake."""

from __future__ import annotations

import hashlib
import json
import math
import os
import struct
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from numbers import Real
from pathlib import Path
from typing import Final, Protocol, cast

from app.core.config import BGE_M3_MODEL_ID, BGE_M3_REVISION, Settings
from app.core.errors import EmbeddingInputError, EmbeddingProviderError

EMBEDDING_CONTRACT_VERSION: Final = "m2-embedding-provider-v1"
EMBEDDING_DIMENSIONS: Final = 1024
EMBEDDING_MAX_TEXTS: Final = 128
EMBEDDING_MAX_INPUT_CHARACTERS: Final = 50_000
_FAKE_MODEL_ID: Final = "fake/m2-deterministic"
_FAKE_REVISION: Final = "m2-fake-v1"
SNAPSHOT_MANIFEST_NAME: Final = "m2_embedding_snapshot.json"
BGE_M3_REQUIRED_FILES: Final = (
    "config.json",
    "pytorch_model.bin",
    "sentencepiece.bpe.model",
    "tokenizer.json",
    "tokenizer_config.json",
    "colbert_linear.pt",
    "sparse_linear.pt",
)


class EmbeddingPurpose(StrEnum):
    """Whether text represents stored evidence or a retrieval query."""

    DOCUMENT = "document"
    QUERY = "query"


@dataclass(frozen=True, slots=True)
class EmbeddingIdentity:
    """Every inference setting that can change logical vector values."""

    contract_version: str
    provider: str
    model_id: str
    revision: str
    pooling: str
    max_length: int
    normalize: bool
    precision: str
    dimensions: int


@dataclass(frozen=True, slots=True)
class EmbeddingBatch:
    """Validated vectors and stable cache identities in original input order."""

    vectors: tuple[tuple[float, ...], ...]
    cache_keys: tuple[str, ...]
    purpose: EmbeddingPurpose
    identity: EmbeddingIdentity
    effective_batch_size: int


@dataclass(frozen=True, slots=True)
class BgeBackendLoadRequest:
    """Local-only settings passed to the slow FlagEmbedding constructor."""

    snapshot_path: Path
    model_id: str
    revision: str
    device: str
    precision: str
    pooling: str
    max_length: int
    normalize: bool
    trust_remote_code: bool = False


class EmbeddingProvider(Protocol):
    """Replaceable boundary shared by deterministic tests and local BGE-M3."""

    @property
    def identity(self) -> EmbeddingIdentity:
        """Return the hardware-independent inference identity."""

    def embed(
        self,
        texts: Sequence[str],
        *,
        purpose: EmbeddingPurpose,
    ) -> EmbeddingBatch:
        """Encode bounded texts without changing their count or order."""


def build_embedding_cache_key(
    identity: EmbeddingIdentity,
    purpose: EmbeddingPurpose,
    text: str,
) -> str:
    """Hash inference identity, purpose, and exact UTF-8 source-text digest."""

    payload = {
        "identity": asdict(identity),
        "purpose": purpose.value,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


class FakeEmbeddingProvider:
    """Generate repeatable normalized vectors without models, hardware, or network."""

    def __init__(self) -> None:
        self._identity = EmbeddingIdentity(
            contract_version=EMBEDDING_CONTRACT_VERSION,
            provider="fake",
            model_id=_FAKE_MODEL_ID,
            revision=_FAKE_REVISION,
            pooling="sha256-shake-v1",
            max_length=8192,
            normalize=True,
            precision="float32",
            dimensions=EMBEDDING_DIMENSIONS,
        )

    @property
    def identity(self) -> EmbeddingIdentity:
        return self._identity

    def embed(
        self,
        texts: Sequence[str],
        *,
        purpose: EmbeddingPurpose,
    ) -> EmbeddingBatch:
        validated = _validate_texts(texts)
        if not isinstance(purpose, EmbeddingPurpose):
            raise EmbeddingInputError
        vectors = tuple(self._vector(text, purpose) for text in validated)
        return EmbeddingBatch(
            vectors=vectors,
            cache_keys=tuple(
                build_embedding_cache_key(self.identity, purpose, text)
                for text in validated
            ),
            purpose=purpose,
            identity=self.identity,
            effective_batch_size=len(validated),
        )

    def _vector(self, text: str, purpose: EmbeddingPurpose) -> tuple[float, ...]:
        seed = (f"{EMBEDDING_CONTRACT_VERSION}\0{purpose.value}\0{text}").encode()
        raw = hashlib.shake_256(seed).digest(EMBEDDING_DIMENSIONS * 4)
        values = [float(value) for (value,) in struct.iter_unpack(">i", raw)]
        norm = math.sqrt(sum(value * value for value in values))
        return tuple(value / norm for value in values)


class BgeM3EmbeddingProvider:
    """Lazy, local-only BGE-M3 dense-vector adapter with strict validation."""

    def __init__(
        self,
        *,
        snapshot_path: Path,
        requested_device: str = "cpu",
        precision: str = "float32",
        batch_size: int = 4,
        pooling: str = "cls",
        max_length: int = 8192,
        normalize: bool = True,
        backend_loader: Callable[[BgeBackendLoadRequest], object] | None = None,
        cuda_is_available: Callable[[], bool] | None = None,
    ) -> None:
        self._snapshot_path = Path(snapshot_path)
        _validate_snapshot(self._snapshot_path)
        self._actual_device = _select_device(
            requested_device,
            cuda_is_available or _torch_cuda_is_available,
        )
        if precision not in {"float32", "float16", "bfloat16"}:
            raise EmbeddingProviderError
        if self._actual_device == "cpu" and precision != "float32":
            raise EmbeddingProviderError
        if pooling != "cls" or max_length != 8192 or not normalize:
            raise EmbeddingProviderError
        if not isinstance(batch_size, int) or isinstance(batch_size, bool):
            raise EmbeddingProviderError
        if not 1 <= batch_size <= 32:
            raise EmbeddingProviderError
        self._precision = precision
        self._batch_size = batch_size
        self._pooling = pooling
        self._max_length = max_length
        self._normalize = normalize
        self._backend_loader = backend_loader or _default_backend_loader
        self._backend: object | None = None
        self._load_lock = threading.Lock()
        self._identity = EmbeddingIdentity(
            contract_version=EMBEDDING_CONTRACT_VERSION,
            provider="bge-m3-local",
            model_id=BGE_M3_MODEL_ID,
            revision=BGE_M3_REVISION,
            pooling=pooling,
            max_length=max_length,
            normalize=normalize,
            precision=precision,
            dimensions=EMBEDDING_DIMENSIONS,
        )

    @property
    def identity(self) -> EmbeddingIdentity:
        return self._identity

    @property
    def snapshot_path(self) -> Path:
        """Expose the caller-supplied local path for private operational tooling."""

        return self._snapshot_path

    @property
    def actual_device(self) -> str:
        return self._actual_device

    @property
    def is_loaded(self) -> bool:
        return self._backend is not None

    def load(self) -> None:
        """Explicitly warm the lazy backend for operational benchmarking."""

        self._load_backend()

    def embed(
        self,
        texts: Sequence[str],
        *,
        purpose: EmbeddingPurpose,
    ) -> EmbeddingBatch:
        validated = _validate_texts(texts)
        if not isinstance(purpose, EmbeddingPurpose):
            raise EmbeddingInputError
        backend = self._load_backend()
        effective_batch_size = self._batch_size
        while True:
            try:
                raw_output = self._encode(
                    backend,
                    list(validated),
                    purpose,
                    effective_batch_size,
                )
                break
            except Exception as error:  # noqa: BLE001 - third-party runtimes vary.
                is_memory_error = _is_memory_error(error)
                if is_memory_error and effective_batch_size > 1:
                    effective_batch_size = max(1, effective_batch_size // 2)
                    _clear_cuda_cache_if_available(self._actual_device)
                    continue
                raise EmbeddingProviderError(retryable=is_memory_error) from None

        vectors = _validate_dense_output(raw_output, len(validated))
        return EmbeddingBatch(
            vectors=vectors,
            cache_keys=tuple(
                build_embedding_cache_key(self.identity, purpose, text)
                for text in validated
            ),
            purpose=purpose,
            identity=self.identity,
            effective_batch_size=effective_batch_size,
        )

    def _load_backend(self) -> object:
        if self._backend is None:
            with self._load_lock:
                if self._backend is None:
                    os.environ["HF_HUB_OFFLINE"] = "1"
                    os.environ["TRANSFORMERS_OFFLINE"] = "1"
                    request = BgeBackendLoadRequest(
                        snapshot_path=self._snapshot_path,
                        model_id=BGE_M3_MODEL_ID,
                        revision=BGE_M3_REVISION,
                        device=self._actual_device,
                        precision=self._precision,
                        pooling=self._pooling,
                        max_length=self._max_length,
                        normalize=self._normalize,
                    )
                    try:
                        self._backend = self._backend_loader(request)
                    except Exception as error:  # noqa: BLE001
                        raise EmbeddingProviderError(
                            retryable=_is_memory_error(error)
                        ) from None
        backend = self._backend
        if backend is None:
            raise EmbeddingProviderError
        return backend

    def _encode(
        self,
        backend: object,
        texts: list[str],
        purpose: EmbeddingPurpose,
        batch_size: int,
    ) -> object:
        method_name = (
            "encode_corpus"
            if purpose is EmbeddingPurpose.DOCUMENT
            else "encode_queries"
        )
        method = getattr(backend, method_name, None)
        if not callable(method):
            raise EmbeddingProviderError
        return method(
            texts,
            batch_size=batch_size,
            max_length=self._max_length,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )


def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    """Create the configured Provider without loading a model at factory time."""

    if settings.embedding_backend == "fake":
        return FakeEmbeddingProvider()
    return BgeM3EmbeddingProvider(
        snapshot_path=(
            settings.model_cache_root / "bge-m3" / settings.embedding_revision
        ),
        requested_device=settings.model_device,
        precision=settings.embedding_precision,
        batch_size=settings.embedding_batch_size,
        pooling=settings.embedding_pooling,
        max_length=settings.embedding_max_length,
        normalize=settings.embedding_normalize,
    )


def _select_device(
    requested_device: str,
    cuda_is_available: Callable[[], bool],
) -> str:
    if requested_device not in {"cpu", "cuda", "auto"}:
        raise EmbeddingProviderError
    try:
        cuda_available = bool(cuda_is_available())
    except Exception:  # noqa: BLE001 - runtime capability probes are untrusted.
        cuda_available = False
    if requested_device == "cuda":
        if not cuda_available:
            raise EmbeddingProviderError
        return "cuda"
    if requested_device == "auto" and cuda_available:
        return "cuda"
    return "cpu"


def _torch_cuda_is_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except (ImportError, RuntimeError):
        return False


def _default_backend_loader(request: BgeBackendLoadRequest) -> object:
    from FlagEmbedding import BGEM3FlagModel  # type: ignore[import-untyped]

    return BGEM3FlagModel(
        str(request.snapshot_path),
        normalize_embeddings=request.normalize,
        use_fp16=request.precision == "float16",
        use_bf16=request.precision == "bfloat16",
        devices=request.device,
        pooling_method=request.pooling,
        trust_remote_code=request.trust_remote_code,
        query_max_length=request.max_length,
        passage_max_length=request.max_length,
        return_dense=True,
        return_sparse=False,
        return_colbert_vecs=False,
        local_files_only=True,
    )


def _validate_snapshot(snapshot_path: Path) -> None:
    manifest_path = snapshot_path / SNAPSHOT_MANIFEST_NAME
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise EmbeddingProviderError from None
    if not isinstance(payload, dict) or payload != {
        "model_id": BGE_M3_MODEL_ID,
        "revision": BGE_M3_REVISION,
    }:
        raise EmbeddingProviderError
    try:
        required_files_valid = all(
            (snapshot_path / relative_path).is_file()
            and (snapshot_path / relative_path).stat().st_size > 0
            for relative_path in BGE_M3_REQUIRED_FILES
        )
    except OSError:
        raise EmbeddingProviderError from None
    if not required_files_valid:
        raise EmbeddingProviderError


def _validate_dense_output(
    raw_output: object,
    expected_count: int,
) -> tuple[tuple[float, ...], ...]:
    if not isinstance(raw_output, Mapping) or "dense_vecs" not in raw_output:
        raise EmbeddingProviderError
    dense = raw_output["dense_vecs"]
    if hasattr(dense, "tolist"):
        try:
            dense = dense.tolist()
        except Exception:  # noqa: BLE001 - tensor/array adapters vary.
            raise EmbeddingProviderError from None
    if isinstance(dense, (str, bytes)) or not isinstance(dense, Sequence):
        raise EmbeddingProviderError
    if len(dense) != expected_count:
        raise EmbeddingProviderError

    vectors: list[tuple[float, ...]] = []
    for raw_vector in dense:
        if hasattr(raw_vector, "tolist"):
            try:
                raw_vector = raw_vector.tolist()
            except Exception:  # noqa: BLE001 - tensor/array adapters vary.
                raise EmbeddingProviderError from None
        if (
            isinstance(raw_vector, (str, bytes))
            or not isinstance(raw_vector, Sequence)
            or len(raw_vector) != EMBEDDING_DIMENSIONS
        ):
            raise EmbeddingProviderError
        if any(
            not isinstance(value, Real) or isinstance(value, bool)
            for value in raw_vector
        ):
            raise EmbeddingProviderError
        vector = tuple(float(cast(Real, value)) for value in raw_vector)
        if not all(math.isfinite(value) for value in vector):
            raise EmbeddingProviderError
        norm = math.sqrt(sum(value * value for value in vector))
        if not math.isclose(norm, 1.0, rel_tol=1e-3, abs_tol=1e-3):
            raise EmbeddingProviderError
        vectors.append(vector)
    return tuple(vectors)


def _is_memory_error(error: BaseException) -> bool:
    if isinstance(error, MemoryError):
        return True
    if error.__class__.__name__ in {
        "OutOfMemoryError",
        "CUDAOutOfMemoryError",
    }:
        return True
    message = str(error).casefold()
    return any(
        marker in message
        for marker in (
            "cuda out of memory",
            "mps backend out of memory",
            "defaultcpuallocator: can't allocate memory",
            "defaultcpuallocator: cannot allocate memory",
            "defaultcpuallocator: not enough memory",
        )
    )


def _clear_cuda_cache_if_available(actual_device: str) -> None:
    if actual_device != "cuda":
        return
    try:
        import torch

        torch.cuda.empty_cache()
    except (ImportError, RuntimeError):
        return


def _validate_texts(texts: Sequence[str]) -> tuple[str, ...]:
    if isinstance(texts, (str, bytes)):
        raise EmbeddingInputError
    try:
        validated = tuple(texts)
    except TypeError:
        raise EmbeddingInputError from None
    if not validated or len(validated) > EMBEDDING_MAX_TEXTS:
        raise EmbeddingInputError
    for text in validated:
        if (
            not isinstance(text, str)
            or not text.strip()
            or len(text) > EMBEDDING_MAX_INPUT_CHARACTERS
        ):
            raise EmbeddingInputError
    return validated
