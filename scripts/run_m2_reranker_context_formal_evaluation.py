"""Run the complete offline M2-22.7.5 Reranker and Context matrix."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Sequence
from pathlib import Path

from app.core.config import (
    BGE_M3_MODEL_ID,
    BGE_M3_REVISION,
    BGE_RERANKER_MODEL_ID,
    BGE_RERANKER_REVISION,
    Settings,
)
from app.db.session import create_database_runtime
from app.evals.rag_runner import PROJECT_ROOT
from app.evals.reranker_context_corpus import (
    build_m2_reranker_context_evidence_map,
    ensure_m2_reranker_context_corpus,
    inspect_m2_reranker_context_chunks,
)
from app.evals.reranker_context_formal import (
    run_m2_reranker_context_formal_evaluation,
)
from app.evals.reranker_context_report import write_public_report
from app.services.retrieval import (
    BgeM3EmbeddingProvider,
    BgeRerankerProvider,
    create_embedding_provider,
    create_reranker_provider,
)
from app.services.storage import LocalStorageBackend
from scripts.download_m2_reranker import ensure_reranker_snapshot

DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "evals"
    / "runtime"
    / "reports"
    / "m2-reranker-context-formal-report.json"
)
_REPORT_ROOT = DEFAULT_OUTPUT.parent.resolve()


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-real",
        action="store_true",
        required=True,
        help="explicitly authorize the complete local CPU model matrix",
    )
    parser.add_argument(
        "--keep-report",
        action="store_true",
        help="retain the public-safe report inside the managed report directory",
    )
    parser.add_argument(
        "--reranker-device",
        choices=("cpu", "cuda"),
        default="cpu",
        help="run only the Reranker on the selected local device",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def _validated_output(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(_REPORT_ROOT)
    except ValueError:
        raise ValueError(
            "formal report must stay in the managed report directory"
        ) from None
    return resolved


def _formal_settings() -> Settings:
    return Settings().model_copy(
        update={
            "embedding_backend": "bge",
            "embedding_model": BGE_M3_MODEL_ID,
            "embedding_revision": BGE_M3_REVISION,
            "embedding_batch_size": 16,
            "reranker_backend": "bge",
            "reranker_model": BGE_RERANKER_MODEL_ID,
            "reranker_revision": BGE_RERANKER_REVISION,
            "reranker_batch_size": 2,
            "reranker_max_length": 8192,
            "reranker_precision": "float32",
            "database_statement_timeout_ms": 30_000,
            "model_device": "cpu",
            "model_local_files_only": True,
        }
    )


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parse_args(argv)
    del arguments.run_real
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    output: Path | None = None
    runtime = None
    stage = "arguments"
    try:
        output = _validated_output(arguments.output)
        settings = _formal_settings()
        storage = LocalStorageBackend(
            settings.local_storage_root,
            chunk_size_bytes=settings.upload_stream_chunk_size_bytes,
        )
        stage = "retained_chunk_identity"
        before = inspect_m2_reranker_context_chunks(
            settings,
            project_root=PROJECT_ROOT,
        )
        embedding_provider = create_embedding_provider(settings)
        if not isinstance(embedding_provider, BgeM3EmbeddingProvider):
            raise TypeError
        stage = "retained_real_index"
        snapshot = ensure_m2_reranker_context_corpus(
            settings,
            project_root=PROJECT_ROOT,
            storage=storage,
            embedding_provider=embedding_provider,
        )
        if (
            before.corpus_sha256 != snapshot.corpus_sha256
            or before.document_ids != snapshot.document_ids
            or before.chunk_set_ids != snapshot.chunk_set_ids
            or before.chunk_count != snapshot.chunk_count
        ):
            raise RuntimeError("formal indexing changed the retained Chunk corpus")

        stage = "reranker_snapshot"
        ensure_reranker_snapshot(settings.model_cache_root, allow_download=False)
        reranker_settings = settings.model_copy(
            update={"model_device": arguments.reranker_device}
        )
        reranker_provider = create_reranker_provider(reranker_settings)
        if not isinstance(reranker_provider, BgeRerankerProvider):
            raise TypeError
        load_started = time.perf_counter()
        stage = "reranker_load"
        reranker_provider.load()
        load_seconds = max(0.0, time.perf_counter() - load_started)

        runtime = create_database_runtime(settings)
        stage = "evidence_map"
        evidence_map = build_m2_reranker_context_evidence_map(
            runtime=runtime,
            storage=storage,
            project_root=PROJECT_ROOT,
            snapshot=snapshot,
        )
        stage = "formal_matrix"
        report = run_m2_reranker_context_formal_evaluation(
            settings=settings,
            runtime=runtime,
            snapshot=snapshot,
            embedding_provider=embedding_provider,
            reranker_provider=reranker_provider,
            evidence_ids_by_chunk=evidence_map,
            reranker_load_seconds=load_seconds,
        )
        stage = "temporary_report"
        artifact_sha256 = write_public_report(output, report)
        artifact_size_bytes = output.stat().st_size
        if not arguments.keep_report:
            output.unlink()
            if output.exists():
                raise RuntimeError("temporary formal report was not deleted")
    except Exception:  # noqa: BLE001 - the CLI never prints raw paths or causes.
        print(
            "M2-22.7.5正式矩阵失败；"
            f"安全阶段={stage}；请检查对应的固定语料、本地模型、数据库或内存"
        )
        return 1
    finally:
        if runtime is not None:
            runtime.engine.dispose()

    reranker_rows = {
        f"{item.group_id}@{item.top_k}": {
            "rrf_hits": item.rrf_hit_count,
            "reranker_hits": item.reranker_hit_count,
            "cases": item.expected_case_count,
            "candidate_missing": item.candidate_missing_count,
            "promoted": item.promoted_count,
            "demoted": item.demoted_count,
            "unchanged": item.unchanged_count,
            "rrf_hit_rate": item.rrf_hit_rate_at_k,
            "reranker_hit_rate": item.reranker_hit_rate_at_k,
        }
        for item in report.reranker_aggregates
    }
    context_rows = {
        (
            f"{item.group_id}@n{item.context_neighbor_window}"
            f"-t{item.context_max_tokens}"
        ): {
            "cases": item.expected_case_count,
            "coverage": item.golden_evidence_coverage_rate,
            "anchor_coverage": item.anchor_golden_evidence_coverage_rate,
            "redundancy": item.context_redundancy_rate,
            "token_utilization": item.token_utilization_rate,
        }
        for item in report.context_aggregates
    }
    print(
        json.dumps(
            {
                "run_id": report.run_id,
                "run_status": report.run_status,
                "evaluation_completed": report.evaluation_completed,
                "quality_gate_passed": report.quality_gate_passed,
                "selected_top_k": report.selected_top_k,
                "answerable_cases": len(report.answerable_results),
                "safety_cases": len(report.safety_results),
                "safety_gate_passed": report.safety_gate_passed,
                "safety_leaks": report.safety_leak_count,
                "provider_score_calls": report.cache.provider_score_calls,
                "cache": report.cache.model_dump(mode="json"),
                "measurements": report.measurements.model_dump(mode="json"),
                "corpus": report.corpus.model_dump(mode="json"),
                "trace_set_sha256": report.trace_set_sha256,
                "report_size_bytes": artifact_size_bytes,
                "report_sha256": artifact_sha256,
                "report_deleted": not arguments.keep_report,
                "reranker": reranker_rows,
                "context": context_rows,
                "bad_cases": [
                    item.model_dump(mode="json") for item in report.bad_cases
                ],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
