"""Hardware-independent Reranker protocol and deterministic offline fake."""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from numbers import Real
from pathlib import Path, PurePosixPath
from typing import Final, Literal, Protocol, cast

from app.core.config import (
    BGE_RERANKER_MODEL_ID,
    BGE_RERANKER_REVISION,
    RETRIEVAL_CANDIDATE_HARD_MAX,
    RETRIEVAL_QUERY_HARD_MAX_CHARACTERS,
    Settings,
)
from app.core.errors import RerankerInputError, RerankerProviderError

RERANKER_CONTRACT_VERSION: Final = "m2-reranker-provider-v1"
RERANKER_MAX_QUERY_CHARACTERS: Final = RETRIEVAL_QUERY_HARD_MAX_CHARACTERS
RERANKER_MAX_CANDIDATES: Final = RETRIEVAL_CANDIDATE_HARD_MAX
RERANKER_MAX_PASSAGE_CHARACTERS: Final = 100_000
_FAKE_MODEL_ID: Final = "fake/m2-reranker-deterministic"
_FAKE_REVISION: Final = "m2-fake-reranker-v1"
RERANKER_SNAPSHOT_SCHEMA_VERSION: Final = "m2-reranker-snapshot-v1"
RERANKER_SNAPSHOT_MANIFEST_NAME: Final = "m2_reranker_snapshot.json"
BGE_RERANKER_REQUIRED_FILES: Final = (
    "config.json",
    "model.safetensors",
    "sentencepiece.bpe.model",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
)

RerankerPrecision = Literal["float32", "float16", "bfloat16"]


@dataclass(frozen=True, slots=True)
class RerankerIdentity:
    """Every inference setting that can change logical Reranker scores."""

    contract_version: str
    provider: str
    model_id: str
    revision: str
    max_length: int
    precision: RerankerPrecision
    score_transform: Literal["sigmoid"]


@dataclass(frozen=True, slots=True)
class RerankerPairScore:
    """One score bound to an exact query, passage, and original position."""

    pair_key: str
    raw_score: float
    normalized_score: float


@dataclass(frozen=True, slots=True)
class RerankerBatch:
    """Validated pair scores in the exact original candidate order."""

    scores: tuple[RerankerPairScore, ...]
    identity: RerankerIdentity
    effective_batch_size: int


@dataclass(frozen=True, slots=True)
class BgeRerankerLoadRequest:
    """Local-only settings passed to the slow FlagEmbedding constructor."""

    snapshot_path: Path
    model_id: str
    revision: str
    device: str
    precision: RerankerPrecision
    batch_size: int
    max_length: int
    trust_remote_code: bool = False
    normalize: bool = False


class RerankerProvider(Protocol):
    """Replaceable scoring boundary for the Fake and future local BGE adapter."""

    @property
    def identity(self) -> RerankerIdentity:
        """Return the logical identity that determines score meaning."""

    def score(self, query: str, passages: Sequence[str]) -> RerankerBatch:
        """Score bounded query/passage pairs without changing count or order."""


def build_reranker_pair_key(
    identity: RerankerIdentity,
    query: str,
    passage: str,
    position: int,
) -> str:
    """Hash exact pair identity and ordinal without exposing source text."""

    payload = {
        "identity": asdict(identity),
        "passage_sha256": hashlib.sha256(passage.encode("utf-8")).hexdigest(),
        "position": position,
        "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


class FakeRerankerProvider:
    """Return stable synthetic scores without models, hardware, or network."""

    def __init__(self) -> None:
        self._identity = RerankerIdentity(
            contract_version=RERANKER_CONTRACT_VERSION,
            provider="fake",
            model_id=_FAKE_MODEL_ID,
            revision=_FAKE_REVISION,
            max_length=8192,
            precision="float32",
            score_transform="sigmoid",
        )

    @property
    def identity(self) -> RerankerIdentity:
        return self._identity

    def score(self, query: str, passages: Sequence[str]) -> RerankerBatch:
        validated_query, validated_passages = _validate_inputs(query, passages)
        scores = tuple(
            RerankerPairScore(
                pair_key=build_reranker_pair_key(
                    self.identity,
                    validated_query,
                    passage,
                    position,
                ),
                raw_score=(raw_score := self._raw_score(validated_query, passage)),
                normalized_score=_sigmoid(raw_score),
            )
            for position, passage in enumerate(validated_passages)
        )
        batch = RerankerBatch(
            scores=scores,
            identity=self.identity,
            effective_batch_size=len(validated_passages),
        )
        return validate_reranker_batch(
            batch,
            query=validated_query,
            passages=validated_passages,
            expected_identity=self.identity,
        )

    def _raw_score(self, query: str, passage: str) -> float:
        payload = {
            "contract_version": RERANKER_CONTRACT_VERSION,
            "passage_sha256": hashlib.sha256(passage.encode("utf-8")).hexdigest(),
            "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        integer = int.from_bytes(hashlib.sha256(canonical).digest()[:8], "big")
        return (integer / ((1 << 64) - 1)) * 16.0 - 8.0


class BgeRerankerProvider:
    """Lazy local-only BGE-Reranker adapter with strict output validation."""

    def __init__(
        self,
        *,
        snapshot_path: Path,
        requested_device: str = "cpu",
        precision: RerankerPrecision = "float32",
        batch_size: int = 2,
        max_length: int = 8192,
        backend_loader: Callable[[BgeRerankerLoadRequest], object] | None = None,
        cuda_is_available: Callable[[], bool] | None = None,
    ) -> None:
        self._snapshot_path = Path(snapshot_path)
        _validate_snapshot(self._snapshot_path)
        self._actual_device = _select_device(
            requested_device,
            cuda_is_available,
        )
        if precision not in {"float32", "float16", "bfloat16"}:
            raise RerankerProviderError
        if self._actual_device == "cpu" and precision != "float32":
            raise RerankerProviderError
        if (
            not isinstance(batch_size, int)
            or isinstance(batch_size, bool)
            or not 1 <= batch_size <= 16
            or max_length != 8192
        ):
            raise RerankerProviderError
        if backend_loader is not None and not callable(backend_loader):
            raise RerankerProviderError
        self._precision = precision
        self._batch_size = batch_size
        self._max_length = max_length
        self._backend_loader = backend_loader or _default_backend_loader
        self._backend: object | None = None
        self._load_lock = threading.Lock()
        self._identity = RerankerIdentity(
            contract_version=RERANKER_CONTRACT_VERSION,
            provider="bge-reranker-local",
            model_id=BGE_RERANKER_MODEL_ID,
            revision=BGE_RERANKER_REVISION,
            max_length=max_length,
            precision=precision,
            score_transform="sigmoid",
        )

    @property
    def identity(self) -> RerankerIdentity:
        return self._identity

    @property
    def snapshot_path(self) -> Path:
        """Expose the managed path only to explicit operational tooling."""

        return self._snapshot_path

    @property
    def actual_device(self) -> str:
        return self._actual_device

    @property
    def is_loaded(self) -> bool:
        return self._backend is not None

    def load(self) -> None:
        """Explicitly warm the lazy backend for Smoke tests and benchmarks."""

        self._load_backend()

    def score(self, query: str, passages: Sequence[str]) -> RerankerBatch:
        validated_query, validated_passages = _validate_inputs(query, passages)
        backend = self._load_backend()
        pairs = [(validated_query, passage) for passage in validated_passages]
        effective_batch_size = self._batch_size
        while True:
            try:
                raw_output = _compute_backend_scores(
                    backend,
                    pairs,
                    batch_size=effective_batch_size,
                    max_length=self._max_length,
                )
                break
            except Exception as error:  # noqa: BLE001 - runtimes vary.
                memory_error = _is_memory_error(error)
                if memory_error and effective_batch_size > 1:
                    effective_batch_size = max(1, effective_batch_size // 2)
                    _clear_cuda_cache_if_available(self._actual_device)
                    continue
                raise RerankerProviderError(retryable=memory_error) from None

        raw_scores = _validate_backend_scores(raw_output, len(validated_passages))
        scores = tuple(
            RerankerPairScore(
                pair_key=build_reranker_pair_key(
                    self.identity,
                    validated_query,
                    passage,
                    position,
                ),
                raw_score=raw_score,
                normalized_score=_sigmoid(raw_score),
            )
            for position, (passage, raw_score) in enumerate(
                zip(validated_passages, raw_scores, strict=True)
            )
        )
        batch = RerankerBatch(
            scores=scores,
            identity=self.identity,
            effective_batch_size=min(effective_batch_size, len(validated_passages)),
        )
        return validate_reranker_batch(
            batch,
            query=validated_query,
            passages=validated_passages,
            expected_identity=self.identity,
        )

    def _load_backend(self) -> object:
        if self._backend is None:
            with self._load_lock:
                if self._backend is None:
                    os.environ["HF_HUB_OFFLINE"] = "1"
                    os.environ["TRANSFORMERS_OFFLINE"] = "1"
                    request = BgeRerankerLoadRequest(
                        snapshot_path=self._snapshot_path,
                        model_id=BGE_RERANKER_MODEL_ID,
                        revision=BGE_RERANKER_REVISION,
                        device=self._actual_device,
                        precision=self._precision,
                        batch_size=self._batch_size,
                        max_length=self._max_length,
                    )
                    try:
                        self._backend = self._backend_loader(request)
                    except Exception as error:  # noqa: BLE001
                        raise RerankerProviderError(
                            retryable=_is_memory_error(error)
                        ) from None
        if self._backend is None:
            raise RerankerProviderError
        return self._backend


def create_reranker_provider(settings: Settings) -> RerankerProvider:
    """Create the configured Provider without loading model weights."""

    if settings.reranker_backend == "fake":
        return FakeRerankerProvider()
    return BgeRerankerProvider(
        snapshot_path=(
            settings.model_cache_root
            / "bge-reranker-v2-m3"
            / settings.reranker_revision
        ),
        requested_device=settings.model_device,
        precision=settings.reranker_precision,
        batch_size=settings.reranker_batch_size,
        max_length=settings.reranker_max_length,
    )


def verify_reranker_snapshot(snapshot_path: Path) -> bool:
    """Recompute the managed manifest without leaking the rejected path."""

    try:
        _validate_snapshot(Path(snapshot_path))
    except RerankerProviderError:
        return False
    return True


def _select_device(
    requested_device: str,
    cuda_is_available: Callable[[], bool] | None,
) -> str:
    if requested_device not in {"cpu", "cuda", "auto"}:
        raise RerankerProviderError
    probe = cuda_is_available or _torch_cuda_is_available
    try:
        cuda_available = bool(probe())
    except Exception:  # noqa: BLE001 - capability probes are untrusted.
        cuda_available = False
    if requested_device == "cuda":
        if not cuda_available:
            raise RerankerProviderError
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


def _default_backend_loader(request: BgeRerankerLoadRequest) -> object:
    from FlagEmbedding import FlagReranker  # type: ignore[import-untyped]

    backend = FlagReranker(
        str(request.snapshot_path),
        use_fp16=request.precision == "float16",
        trust_remote_code=request.trust_remote_code,
        devices=request.device,
        batch_size=request.batch_size,
        query_max_length=request.max_length * 3 // 4,
        max_length=request.max_length,
        normalize=request.normalize,
    )
    if request.precision == "bfloat16":
        model = getattr(backend, "model", None)
        convert = getattr(model, "bfloat16", None)
        if not callable(convert):
            raise RerankerProviderError
        convert()
    return backend


def _compute_backend_scores(
    backend: object,
    pairs: list[tuple[str, str]],
    *,
    batch_size: int,
    max_length: int,
) -> object:
    compute_score = getattr(backend, "compute_score", None)
    if not callable(compute_score):
        raise RerankerProviderError
    return compute_score(
        pairs,
        batch_size=batch_size,
        max_length=max_length,
        normalize=False,
    )


def _validate_backend_scores(
    raw_output: object,
    expected_count: int,
) -> tuple[float, ...]:
    if hasattr(raw_output, "tolist"):
        try:
            raw_output = raw_output.tolist()
        except Exception:  # noqa: BLE001 - tensor/array adapters vary.
            raise RerankerProviderError from None
    if isinstance(raw_output, (str, bytes)) or not isinstance(raw_output, Sequence):
        raise RerankerProviderError
    if len(raw_output) != expected_count:
        raise RerankerProviderError
    if any(not _is_finite_real(value) for value in raw_output):
        raise RerankerProviderError
    return tuple(float(cast(Real, value)) for value in raw_output)


def _validate_snapshot(snapshot_path: Path) -> None:
    try:
        payload = json.loads(
            (snapshot_path / RERANKER_SNAPSHOT_MANIFEST_NAME).read_text(
                encoding="utf-8"
            )
        )
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise RerankerProviderError from None
    if not isinstance(payload, Mapping) or set(payload) != {
        "schema_version",
        "model_id",
        "revision",
        "files",
    }:
        raise RerankerProviderError
    if (
        payload["schema_version"] != RERANKER_SNAPSHOT_SCHEMA_VERSION
        or payload["model_id"] != BGE_RERANKER_MODEL_ID
        or payload["revision"] != BGE_RERANKER_REVISION
        or not isinstance(payload["files"], Mapping)
    ):
        raise RerankerProviderError
    files = cast(Mapping[object, object], payload["files"])
    if not set(BGE_RERANKER_REQUIRED_FILES).issubset(files):
        raise RerankerProviderError
    for relative_path, raw_metadata in files.items():
        if not isinstance(relative_path, str) or not _safe_relative_path(relative_path):
            raise RerankerProviderError
        if not isinstance(raw_metadata, Mapping) or set(raw_metadata) != {
            "sha256",
            "size_bytes",
        }:
            raise RerankerProviderError
        expected_hash = raw_metadata["sha256"]
        expected_size = raw_metadata["size_bytes"]
        if (
            not isinstance(expected_hash, str)
            or len(expected_hash) != 64
            or any(character not in "0123456789abcdef" for character in expected_hash)
            or not isinstance(expected_size, int)
            or isinstance(expected_size, bool)
            or expected_size <= 0
        ):
            raise RerankerProviderError
        target = snapshot_path.joinpath(*PurePosixPath(relative_path).parts)
        try:
            if (
                not target.is_file()
                or target.stat().st_size != expected_size
                or _sha256_file(target) != expected_hash
            ):
                raise RerankerProviderError
        except OSError:
            raise RerankerProviderError from None


def _safe_relative_path(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        bool(value)
        and "\\" not in value
        and not path.is_absolute()
        and ".." not in path.parts
        and "." not in path.parts
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _is_memory_error(error: BaseException) -> bool:
    if isinstance(error, MemoryError):
        return True
    if error.__class__.__name__ in {"OutOfMemoryError", "CUDAOutOfMemoryError"}:
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


def validate_reranker_batch(
    batch: RerankerBatch,
    *,
    query: str,
    passages: Sequence[str],
    expected_identity: RerankerIdentity,
) -> RerankerBatch:
    """Reject provider output that cannot map exactly back to input pairs."""

    validated_query, validated_passages = _validate_inputs(query, passages)
    if not isinstance(batch, RerankerBatch):
        raise RerankerProviderError
    if batch.identity != expected_identity or len(batch.scores) != len(
        validated_passages
    ):
        raise RerankerProviderError
    if (
        not isinstance(batch.effective_batch_size, int)
        or isinstance(batch.effective_batch_size, bool)
        or not 1 <= batch.effective_batch_size <= len(validated_passages)
    ):
        raise RerankerProviderError

    for position, (passage, score) in enumerate(
        zip(validated_passages, batch.scores, strict=True)
    ):
        expected_key = build_reranker_pair_key(
            expected_identity,
            validated_query,
            passage,
            position,
        )
        if not isinstance(score, RerankerPairScore) or score.pair_key != expected_key:
            raise RerankerProviderError
        if not _is_finite_real(score.raw_score) or not _is_finite_real(
            score.normalized_score
        ):
            raise RerankerProviderError
        raw_score = float(cast(Real, score.raw_score))
        normalized_score = float(cast(Real, score.normalized_score))
        if not 0 <= normalized_score <= 1 or not math.isclose(
            normalized_score,
            _sigmoid(raw_score),
            rel_tol=0,
            abs_tol=1e-12,
        ):
            raise RerankerProviderError
    return batch


def _validate_inputs(
    query: str,
    passages: Sequence[str],
) -> tuple[str, tuple[str, ...]]:
    if (
        not isinstance(query, str)
        or not query.strip()
        or len(query) > RERANKER_MAX_QUERY_CHARACTERS
    ):
        raise RerankerInputError(field="query")
    if isinstance(passages, (str, bytes)):
        raise RerankerInputError(field="passages")
    try:
        validated_passages = tuple(passages)
    except TypeError:
        raise RerankerInputError(field="passages") from None
    if not validated_passages or len(validated_passages) > RERANKER_MAX_CANDIDATES:
        raise RerankerInputError(field="passages")
    if any(
        not isinstance(passage, str)
        or not passage.strip()
        or len(passage) > RERANKER_MAX_PASSAGE_CHARACTERS
        for passage in validated_passages
    ):
        raise RerankerInputError(field="passages")
    return query, validated_passages


def _is_finite_real(value: object) -> bool:
    return (
        isinstance(value, Real)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1 / (1 + math.exp(-value))
    exponential = math.exp(value)
    return exponential / (1 + exponential)
