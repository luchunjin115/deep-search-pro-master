"""Run the explicit, offline-only M2-22.7.4 local BGE resource probe."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path

from app.core.config import BGE_RERANKER_MODEL_ID, BGE_RERANKER_REVISION, Settings
from app.evals.reranker_context_report import write_reranker_resource_probe_report
from app.evals.reranker_resource_probe import run_m2_reranker_resource_probe
from app.services.retrieval import BgeRerankerProvider, create_reranker_provider
from scripts.download_m2_reranker import ensure_reranker_snapshot

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "output" / "m2_reranker_resource_probe.json"


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-real",
        action="store_true",
        required=True,
        help="explicitly authorize loading the already-downloaded local model",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_args(argv)
    del arguments.run_real
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    try:
        settings = Settings(  # type: ignore[call-arg]
            reranker_backend="bge",
            reranker_model=BGE_RERANKER_MODEL_ID,
            reranker_revision=BGE_RERANKER_REVISION,
            reranker_batch_size=2,
            reranker_max_length=8192,
            reranker_precision="float32",
            model_device="cpu",
            model_local_files_only=True,
        )
        snapshot = ensure_reranker_snapshot(
            settings.model_cache_root,
            allow_download=False,
        )
        provider = create_reranker_provider(settings)
        if not isinstance(provider, BgeRerankerProvider):
            raise TypeError
        report = run_m2_reranker_resource_probe(
            provider=provider,
            snapshot_verified=True,
            configured_batch_size=settings.reranker_batch_size,
        )
        output = write_reranker_resource_probe_report(arguments.output, report)
        del snapshot
    except Exception:  # noqa: BLE001 - CLI must not print paths or raw causes.
        print("M2-22.7.4资源探针失败；请检查固定快照、CPU内存与本地配置")
        return 1
    summary = {
        "run_status": report.run_status,
        "execution_mode": report.execution_mode,
        "quality_gate_passed": report.quality_gate_passed,
        "model": f"{report.scorer.model_id}@{report.scorer.revision}",
        "case_count": len(report.cases),
        "candidate_count_per_case": report.max_candidate_pool,
        "provider_score_calls": report.cache.provider_score_calls,
        "output_name": output.name,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
