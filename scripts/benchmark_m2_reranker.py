"""Benchmark pinned local BGE-Reranker quality, latency, and memory."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import platform
import re
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Protocol, TypeVar

import psutil  # type: ignore[import-untyped]

from app.core.config import BGE_RERANKER_MODEL_ID, BGE_RERANKER_REVISION, Settings
from app.services.retrieval.reranker_provider import (
    BgeRerankerProvider,
    RerankerBatch,
    RerankerIdentity,
    create_reranker_provider,
)
from scripts.download_m2_reranker import ensure_reranker_snapshot

RERANKER_BENCHMARK_SCHEMA_VERSION = "m2-reranker-benchmark-v1"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "output" / "m2_reranker_benchmarks"
_MACHINE_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$")
_CASES = (
    (
        "chinese",
        "蘑菇灯在德国仓还有多少可售库存？",
        "LR-TL-MUSH-OR01 在 DE-FRA 的可售库存为 125。",
        "USB-C扩展坞支持HDMI和千兆网口。",
    ),
    (
        "english",
        "Which ports are available on the USB-C hub?",
        "The USB-C hub provides HDMI, USB 3.0 and Gigabit Ethernet.",
        "The orange mushroom lamp emits warm bedroom light.",
    ),
    (
        "sku",
        "LR-TL-MUSH-OR01 DE-FRA sellable inventory",
        "SKU LR-TL-MUSH-OR01 | warehouse DE-FRA | sellable 125",
        "SKU DK-HUB-8IN1 | market US | inbound 40",
    ),
)

T = TypeVar("T")


class RerankerBenchmarkError(RuntimeError):
    """Stable benchmark failure without machine-private details."""


class BenchmarkProvider(Protocol):
    @property
    def identity(self) -> RerankerIdentity: ...

    @property
    def actual_device(self) -> str: ...

    def load(self) -> None: ...

    def score(self, query: str, passages: Sequence[str]) -> RerankerBatch: ...


def validate_machine_label(label: str) -> str:
    if not _MACHINE_LABEL.fullmatch(label):
        raise RerankerBenchmarkError(
            "--machine-label必须是1至32位小写字母、数字或中划线"
        )
    sensitive = {
        value.casefold() for value in (platform.node(), getpass.getuser()) if value
    }
    if any(value in label.casefold() for value in sensitive):
        raise RerankerBenchmarkError("--machine-label不能使用用户名或主机名")
    return label


def run_benchmark(
    settings: Settings,
    *,
    machine_label: str,
    provider: BenchmarkProvider | None = None,
    iterations: int = 5,
) -> dict[str, Any]:
    """Run fixed synthetic positive/negative pairs without persistence."""

    label = validate_machine_label(machine_label)
    if not 1 <= iterations <= 20:
        raise RerankerBenchmarkError("iterations必须在1至20之间")
    resolved = provider or _create_real_provider(settings)
    _, load_metrics = _measure(resolved.load)
    _reset_gpu_peak(resolved.actual_device)

    latencies: list[float] = []
    first_results: dict[str, RerankerBatch] = {}
    peak_rss = load_metrics["rss_peak_mib"]
    for iteration in range(iterations):
        started = time.perf_counter()
        iteration_results: dict[str, RerankerBatch] = {}
        rss_before = psutil.Process().memory_info().rss
        for case_id, query, related, unrelated in _CASES:
            iteration_results[case_id] = resolved.score(
                query,
                [related, unrelated],
            )
        elapsed = time.perf_counter() - started
        latencies.append(elapsed)
        peak_rss = max(
            peak_rss,
            round(max(rss_before, psutil.Process().memory_info().rss) / 1024 / 1024, 1),
        )
        if iteration == 0:
            first_results = iteration_results

    scores = {
        case_id: {
            "related_raw": round(result.scores[0].raw_score, 6),
            "unrelated_raw": round(result.scores[1].raw_score, 6),
        }
        for case_id, result in first_results.items()
    }
    return {
        "schema_version": RERANKER_BENCHMARK_SCHEMA_VERSION,
        "machine_label": label,
        "synthetic_data": True,
        "offline_inference": True,
        "model": asdict(resolved.identity),
        "environment": _environment_profile(),
        "runtime": {
            "requested_device": settings.model_device,
            "actual_device": resolved.actual_device,
            "precision": resolved.identity.precision,
            "configured_batch_size": settings.reranker_batch_size,
            "effective_batch_sizes": {
                case_id: result.effective_batch_size
                for case_id, result in first_results.items()
            },
            "iterations": iterations,
        },
        "measurements": {
            "load_seconds": load_metrics["elapsed_seconds"],
            "latency_p50_seconds": round(_percentile(latencies, 0.50), 6),
            "latency_p95_seconds": round(_percentile(latencies, 0.95), 6),
            "rss_start_mib": load_metrics["rss_start_mib"],
            "rss_peak_mib": peak_rss,
            "rss_peak_delta_mib": round(
                max(0.0, peak_rss - load_metrics["rss_start_mib"]), 1
            ),
            "gpu_peak_allocated_mib": _gpu_peak_mib(resolved.actual_device),
        },
        "corpus": {
            "version": "m2-reranker-benchmark-corpus-v1",
            "case_ids": [case[0] for case in _CASES],
            "pair_count": len(_CASES) * 2,
        },
        "quality": {
            "chinese_order_passed": (
                scores["chinese"]["related_raw"] > scores["chinese"]["unrelated_raw"]
            ),
            "english_order_passed": (
                scores["english"]["related_raw"] > scores["english"]["unrelated_raw"]
            ),
            "sku_order_passed": (
                scores["sku"]["related_raw"] > scores["sku"]["unrelated_raw"]
            ),
            "scores": scores,
        },
    }


def write_report(
    report: dict[str, Any],
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> Path:
    if report.get("schema_version") != RERANKER_BENCHMARK_SCHEMA_VERSION:
        raise RerankerBenchmarkError("Reranker基准报告Schema版本无效")
    raw_label = report.get("machine_label")
    if not isinstance(raw_label, str):
        raise RerankerBenchmarkError("Reranker基准报告缺少machine_label")
    label = validate_machine_label(raw_label)
    output = Path(output_root) / f"{label}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output


def _create_real_provider(settings: Settings) -> BenchmarkProvider:
    provider = create_reranker_provider(settings)
    if not isinstance(provider, BgeRerankerProvider):
        raise RerankerBenchmarkError("真实基准必须显式配置BGE Reranker backend")
    return provider


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
    return result, {
        "elapsed_seconds": round(elapsed, 6),
        "rss_start_mib": round(start_rss / 1024 / 1024, 1),
        "rss_peak_mib": round(peak_rss / 1024 / 1024, 1),
    }


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _environment_profile() -> dict[str, Any]:
    try:
        import torch

        cuda_available = bool(torch.cuda.is_available())
        torch_profile: dict[str, Any] = {
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
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--iterations", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    try:
        settings = Settings(  # type: ignore[call-arg]
            reranker_backend="bge",
            reranker_model=BGE_RERANKER_MODEL_ID,
            reranker_revision=BGE_RERANKER_REVISION,
            reranker_batch_size=arguments.batch_size,
            reranker_precision="float32",
            model_device=arguments.device,
            model_local_files_only=True,
        )
        ensure_reranker_snapshot(
            settings.model_cache_root,
            allow_download=arguments.allow_download,
        )
        report = run_benchmark(
            settings,
            machine_label=arguments.machine_label,
            iterations=arguments.iterations,
        )
        output = write_report(report)
    except Exception:  # noqa: BLE001 - CLI never prints raw causes.
        print("M2 Reranker基准失败；请检查匿名标签、本地快照和设备配置")
        return 1
    print(json.dumps(report["quality"], ensure_ascii=False, indent=2))
    print(f"report=output/m2_reranker_benchmarks/{output.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
