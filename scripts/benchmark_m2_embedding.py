"""Download pinned BGE-M3 explicitly and benchmark local-only dense embeddings."""

from __future__ import annotations

import argparse
import getpass
import json
import math
import os
import platform
import re
import threading
import time
from collections.abc import Callable
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Protocol, TypeVar, cast

import psutil  # type: ignore[import-untyped]

from app.core.config import BGE_M3_MODEL_ID, BGE_M3_REVISION, Settings
from app.services.documents.chunking.token_counting import UnicodeMixedTokenCounter
from app.services.retrieval.embedding import (
    BGE_M3_REQUIRED_FILES,
    SNAPSHOT_MANIFEST_NAME,
    BgeM3EmbeddingProvider,
    EmbeddingBatch,
    EmbeddingIdentity,
    EmbeddingPurpose,
    create_embedding_provider,
)

BENCHMARK_SCHEMA_VERSION = "m2-embedding-benchmark-v1"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "output" / "m2_embedding_benchmarks"
_MACHINE_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$")
_CORPUS_VERSION = "m2-embedding-benchmark-corpus-v1"
_QUERY_ZH = "这款USB-C扩展坞支持哪些接口？"
_RELATED_ZH = "这款八合一USB-C扩展坞支持HDMI、USB 3.0和千兆网口。"
_UNRELATED_ZH = "橙色蘑菇台灯采用暖光灯泡，适合卧室床头照明。"
_QUERY_EN = "Which ports are available on the USB-C hub?"
_RELATED_DE = "Der USB-C-Hub bietet HDMI, USB 3.0 und einen Gigabit-Ethernet-Anschluss."
_UNRELATED_FR = "La lampe champignon orange diffuse une lumière chaude dans la chambre."

T = TypeVar("T")


class EmbeddingBenchmarkError(RuntimeError):
    """A stable operational error that never contains machine-private details."""


class BenchmarkProvider(Protocol):
    @property
    def identity(self) -> EmbeddingIdentity: ...

    @property
    def actual_device(self) -> str: ...

    def load(self) -> None: ...

    def embed(
        self,
        texts: list[str],
        *,
        purpose: EmbeddingPurpose,
    ) -> EmbeddingBatch: ...


def validate_machine_label(label: str) -> str:
    """Accept only a short anonymous slug, never a path or known local identity."""

    if not _MACHINE_LABEL.fullmatch(label):
        raise EmbeddingBenchmarkError(
            "--machine-label必须是1至32位小写字母、数字或中划线"
        )
    sensitive = {
        value.casefold() for value in (platform.node(), getpass.getuser()) if value
    }
    if any(value in label.casefold() for value in sensitive):
        raise EmbeddingBenchmarkError("--machine-label不能使用用户名或主机名")
    return label


def snapshot_path(model_cache_root: Path) -> Path:
    """Return the deterministic managed location without touching the network."""

    return Path(model_cache_root) / "bge-m3" / BGE_M3_REVISION


def ensure_bge_snapshot(
    model_cache_root: Path,
    *,
    allow_download: bool,
    downloader: Callable[..., str] | None = None,
) -> Path:
    """Reuse a verified marker or explicitly download exactly one pinned commit."""

    target = snapshot_path(model_cache_root)
    if _snapshot_manifest_matches(target):
        return target
    if not allow_download:
        raise EmbeddingBenchmarkError(
            "本地BGE-M3固定快照不存在；只有显式传入--allow-download才允许下载"
        )

    saved_offline = {
        name: os.environ.pop(name, None)
        for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
    }
    try:
        if downloader is None:
            from huggingface_hub import snapshot_download

            downloader = cast(Callable[..., str], snapshot_download)
        downloaded = downloader(
            repo_id=BGE_M3_MODEL_ID,
            revision=BGE_M3_REVISION,
            local_dir=target,
            token=False,
            ignore_patterns=[
                "onnx/**",
                "imgs/**",
                "*.jpg",
                "*.webp",
                "**/.DS_Store",
            ],
            max_workers=1,
        )
    except Exception:  # noqa: BLE001 - network and Hub failures vary.
        raise EmbeddingBenchmarkError("BGE-M3固定快照下载失败") from None
    finally:
        for name, value in saved_offline.items():
            if value is not None:
                os.environ[name] = value

    try:
        if (
            Path(downloaded).resolve() != target.resolve()
            or not target.is_dir()
            or not _required_snapshot_files_exist(target)
        ):
            raise EmbeddingBenchmarkError("BGE-M3固定快照下载结果无效")
        (target / SNAPSHOT_MANIFEST_NAME).write_text(
            json.dumps(
                {"model_id": BGE_M3_MODEL_ID, "revision": BGE_M3_REVISION},
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError:
        raise EmbeddingBenchmarkError("BGE-M3固定快照无法写入受管缓存") from None
    return target


def run_benchmark(
    settings: Settings,
    *,
    machine_label: str,
    provider: BenchmarkProvider | None = None,
) -> dict[str, Any]:
    """Run one fixed multilingual quality/resource benchmark without persistence."""

    label = validate_machine_label(machine_label)
    resolved_provider = provider or _create_real_provider(settings)
    long_text = _long_m2_document()
    query_texts = [_QUERY_ZH, _QUERY_EN]
    document_texts = [
        _RELATED_ZH,
        _UNRELATED_ZH,
        _RELATED_DE,
        _UNRELATED_FR,
        long_text,
    ]

    _, load_metrics = _measure(resolved_provider.load)
    _reset_gpu_peak(resolved_provider.actual_device)

    def encode_all() -> tuple[EmbeddingBatch, EmbeddingBatch]:
        return (
            resolved_provider.embed(query_texts, purpose=EmbeddingPurpose.QUERY),
            resolved_provider.embed(
                document_texts,
                purpose=EmbeddingPurpose.DOCUMENT,
            ),
        )

    (queries, documents), encode_metrics = _measure(encode_all)
    all_vectors = [*queries.vectors, *documents.vectors]
    norms = [_norm(vector) for vector in all_vectors]
    sample_ids = (
        "query_zh",
        "query_en",
        "related_zh",
        "unrelated_zh",
        "related_de",
        "unrelated_fr",
        "long_document",
    )
    cache_keys = [*queries.cache_keys, *documents.cache_keys]
    zh_related = _cosine(queries.vectors[0], documents.vectors[0])
    zh_unrelated = _cosine(queries.vectors[0], documents.vectors[1])
    cross_related = _cosine(queries.vectors[1], documents.vectors[2])
    cross_unrelated = _cosine(queries.vectors[1], documents.vectors[3])
    gpu_peak_mib = _gpu_peak_mib(resolved_provider.actual_device)
    encode_seconds = max(encode_metrics["elapsed_seconds"], 1e-9)

    return {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "machine_label": label,
        "synthetic_data": True,
        "offline_inference": True,
        "model": asdict(resolved_provider.identity),
        "environment": _environment_profile(),
        "runtime": {
            "requested_device": settings.model_device,
            "actual_device": resolved_provider.actual_device,
            "precision": resolved_provider.identity.precision,
            "initial_batch_size": settings.embedding_batch_size,
            "query_effective_batch_size": queries.effective_batch_size,
            "document_effective_batch_size": documents.effective_batch_size,
        },
        "measurements": {
            "load_seconds": load_metrics["elapsed_seconds"],
            "encode_seconds": encode_metrics["elapsed_seconds"],
            "throughput_texts_per_second": round(
                len(all_vectors) / encode_seconds,
                3,
            ),
            "rss_start_mib": load_metrics["rss_start_mib"],
            "rss_peak_mib": max(
                load_metrics["rss_peak_mib"],
                encode_metrics["rss_peak_mib"],
            ),
            "rss_peak_delta_mib": max(
                load_metrics["rss_peak_delta_mib"],
                encode_metrics["rss_peak_delta_mib"],
            ),
            "gpu_peak_allocated_mib": gpu_peak_mib,
        },
        "corpus": {
            "version": _CORPUS_VERSION,
            "sample_ids": list(sample_ids),
            "long_m2_token_count": UnicodeMixedTokenCounter().count(long_text),
        },
        "vectors": {
            "sample_count": len(all_vectors),
            "dimension": len(all_vectors[0]),
            "norm_min": round(min(norms), 6),
            "norm_max": round(max(norms), 6),
            "cache_keys": dict(zip(sample_ids, cache_keys, strict=True)),
        },
        "quality": {
            "chinese_related_similarity": round(zh_related, 6),
            "chinese_unrelated_similarity": round(zh_unrelated, 6),
            "chinese_order_passed": zh_related > zh_unrelated,
            "cross_language_related_similarity": round(cross_related, 6),
            "cross_language_unrelated_similarity": round(cross_unrelated, 6),
            "cross_language_order_passed": cross_related > cross_unrelated,
        },
    }


def write_report(
    report: dict[str, Any],
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> Path:
    """Write one schema-versioned report beneath its anonymous machine label."""

    if report.get("schema_version") != BENCHMARK_SCHEMA_VERSION:
        raise EmbeddingBenchmarkError("Embedding基准报告Schema版本无效")
    label_value = report.get("machine_label")
    if not isinstance(label_value, str):
        raise EmbeddingBenchmarkError("Embedding基准报告缺少machine_label")
    label = validate_machine_label(label_value)
    output = Path(output_root) / f"{label}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output


def _snapshot_manifest_matches(target: Path) -> bool:
    try:
        payload = json.loads(
            (target / SNAPSHOT_MANIFEST_NAME).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return payload == {
        "model_id": BGE_M3_MODEL_ID,
        "revision": BGE_M3_REVISION,
    } and _required_snapshot_files_exist(target)


def _required_snapshot_files_exist(target: Path) -> bool:
    try:
        return all(
            (target / relative_path).is_file()
            and (target / relative_path).stat().st_size > 0
            for relative_path in BGE_M3_REQUIRED_FILES
        )
    except OSError:
        return False


def _create_real_provider(settings: Settings) -> BenchmarkProvider:
    provider = create_embedding_provider(settings)
    if not isinstance(provider, BgeM3EmbeddingProvider):
        raise EmbeddingBenchmarkError("真实基准必须显式配置BGE Embedding backend")
    return provider


def _long_m2_document() -> str:
    counter = UnicodeMixedTokenCounter()
    source = "USB-C扩展坞支持HDMI、USB 3.0和千兆网口，本文为合成测试内容。 " * 80
    spans = counter.spans(source)
    target_tokens = 680
    if len(spans) < target_tokens:
        raise EmbeddingBenchmarkError("固定长文本未达到M2基准长度")
    return source[: spans[target_tokens - 1].end]


def _measure(call: Callable[[], T]) -> tuple[T, dict[str, float]]:
    process = psutil.Process()
    start_rss = process.memory_info().rss
    peak_rss = start_rss
    stopped = threading.Event()

    def sample() -> None:
        nonlocal peak_rss
        while not stopped.wait(0.05):
            peak_rss = max(peak_rss, process.memory_info().rss)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    started = time.perf_counter()
    try:
        result = call()
    finally:
        elapsed = time.perf_counter() - started
        stopped.set()
        sampler.join(timeout=1)
        peak_rss = max(peak_rss, process.memory_info().rss)
    mebibyte = 1024 * 1024
    return result, {
        "elapsed_seconds": round(elapsed, 6),
        "rss_start_mib": round(start_rss / mebibyte, 1),
        "rss_peak_mib": round(peak_rss / mebibyte, 1),
        "rss_peak_delta_mib": round((peak_rss - start_rss) / mebibyte, 1),
    }


def _environment_profile() -> dict[str, Any]:
    torch_profile: dict[str, Any]
    try:
        import torch

        cuda_available = bool(torch.cuda.is_available())
        torch_profile = {
            "version": torch.__version__,
            "cuda_build": torch.version.cuda,
            "cuda_available": cuda_available,
            "cuda_device_count": torch.cuda.device_count(),
            "gpu_name": torch.cuda.get_device_name(0) if cuda_available else None,
            "gpu_total_memory_mib": (
                round(torch.cuda.get_device_properties(0).total_memory / 1024 / 1024, 1)
                if cuda_available
                else None
            ),
        }
    except (ImportError, RuntimeError):
        torch_profile = {
            "version": _package_version("torch"),
            "cuda_build": None,
            "cuda_available": False,
            "cuda_device_count": 0,
            "gpu_name": None,
            "gpu_total_memory_mib": None,
        }
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "cpu_model": platform.processor()
        or os.getenv("PROCESSOR_IDENTIFIER", "unknown"),
        "cpu_physical_cores": psutil.cpu_count(logical=False),
        "cpu_logical_cores": psutil.cpu_count(logical=True),
        "ram_total_mib": round(psutil.virtual_memory().total / 1024 / 1024, 1),
        "packages": {
            package: _package_version(package)
            for package in (
                "FlagEmbedding",
                "torch",
                "transformers",
                "sentence-transformers",
                "huggingface-hub",
                "psutil",
            )
        },
        "torch": torch_profile,
    }


def _package_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "not-installed"


def _norm(vector: tuple[float, ...]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True)) / (
        _norm(left) * _norm(right)
    )


def _reset_gpu_peak(actual_device: str) -> None:
    if actual_device != "cuda":
        return
    try:
        import torch

        torch.cuda.reset_peak_memory_stats()
    except (ImportError, RuntimeError):
        return


def _gpu_peak_mib(actual_device: str) -> float | None:
    if actual_device != "cuda":
        return None
    try:
        import torch

        return round(torch.cuda.max_memory_allocated() / 1024 / 1024, 1)
    except (ImportError, RuntimeError):
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--machine-label", required=True)
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--device", choices=("cpu", "cuda", "auto"), default="auto")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument(
        "--precision",
        choices=("float32", "float16", "bfloat16"),
        default="float32",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    try:
        settings = Settings(  # type: ignore[call-arg]
            embedding_backend="bge",
            embedding_model=BGE_M3_MODEL_ID,
            embedding_revision=BGE_M3_REVISION,
            embedding_batch_size=arguments.batch_size,
            embedding_precision=arguments.precision,
            model_device=arguments.device,
            model_local_files_only=True,
        )
        ensure_bge_snapshot(
            settings.model_cache_root,
            allow_download=arguments.allow_download,
        )
        report = run_benchmark(
            settings,
            machine_label=arguments.machine_label,
        )
        output = write_report(report)
    except Exception:  # noqa: BLE001 - CLI must never expose private tracebacks.
        print("M2 Embedding基准失败；请检查匿名机器标签、本地快照和设备配置")
        return 1
    print(json.dumps(report["quality"], ensure_ascii=False, indent=2))
    print(f"report=output/m2_embedding_benchmarks/{output.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
