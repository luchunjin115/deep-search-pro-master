"""Compare formal RRF and pinned offline BGE-Reranker quality, then restore Seed."""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, TypeGuard, TypeVar
from uuid import UUID

import psutil  # type: ignore[import-untyped]

from app.core.config import (
    BGE_RERANKER_MODEL_ID,
    BGE_RERANKER_REVISION,
    Settings,
)
from app.db.session import DatabaseRuntime, create_database_runtime
from app.schemas.auth import CurrentUser
from app.schemas.retrieval import (
    RetrievalRequest,
    RetrievalResponse,
    RetrievalResult,
)
from app.services.documents.indexing.service import DocumentIndexService
from app.services.retrieval import (
    BgeRerankerProvider,
    FakeEmbeddingProvider,
    RerankerProvider,
    create_reranker_provider,
    verify_reranker_snapshot,
)
from app.services.retrieval.reranker import RerankerRetrievalService
from scripts.benchmark_m2_docling import verify_model_cache
from scripts.download_m2_reranker import reranker_snapshot_path
from scripts.seed_m2_files import GeneratedSource
from scripts.verify_m2_chunk_pipeline import GOLDEN_CHUNK_PROBES, normalize_text
from scripts.verify_m2_index_pipeline import (
    _audit_ready_document,
    _force_offline_mode,
    _prepare_formal_seed,
    _require_clean_formal_baseline,
    _restore_formal_baseline,
)
from scripts.verify_m2_retrieval import _load_named_user, _retrieval_services

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "output" / "m2_reranker_verification.json"

REPORT_SCHEMA_VERSION = "m2-reranker-verification-v1"
KNOWN_UPSTREAM_UNRETRIEVABLE_CASE_IDS = (
    "visual_quality_notice:1",
    "visual_quality_notice:2",
)
UPSTREAM_EXCLUSION_REASON = "upstream_image_text_not_extracted"
ResultT = TypeVar("ResultT", bound=RetrievalResult)


@dataclass(frozen=True)
class _FrozenHybridRoute:
    """Return the exact already-measured authorized Hybrid response once more."""

    current_user: CurrentUser
    request: RetrievalRequest
    response: RetrievalResponse

    def retrieve(
        self,
        current_user: CurrentUser,
        request: RetrievalRequest,
    ) -> RetrievalResponse:
        if current_user != self.current_user or request != self.request:
            raise RuntimeError("Frozen Hybrid route received different trusted input")
        return self.response


def build_quality_metrics(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Calculate Recall@8 and MRR@8 over the fixed non-excluded cases."""

    evaluated = [row for row in rows if row.get("excluded") is False]
    denominator = len(evaluated)
    if denominator == 0:
        raise ValueError("At least one evaluated Reranker case is required")

    rrf = _route_metrics(evaluated, "rrf_first_evidence_rank", denominator)
    reranker = _route_metrics(
        evaluated,
        "reranker_first_evidence_rank",
        denominator,
    )
    recall_delta = round(reranker["recall_at_8"] - rrf["recall_at_8"], 6)
    mrr_delta = round(reranker["mrr_at_8"] - rrf["mrr_at_8"], 6)
    if (reranker["recall_at_8"], reranker["mrr_at_8"]) > (
        rrf["recall_at_8"],
        rrf["mrr_at_8"],
    ):
        conclusion = "improved"
    elif (reranker["recall_at_8"], reranker["mrr_at_8"]) == (
        rrf["recall_at_8"],
        rrf["mrr_at_8"],
    ):
        conclusion = "unchanged"
    else:
        conclusion = "regressed"
    return {
        "denominator": denominator,
        "rrf": rrf,
        "reranker": reranker,
        "delta": {
            "recall_at_8": recall_delta,
            "mrr_at_8": mrr_delta,
        },
        "quality_conclusion": conclusion,
    }


def reranker_verification_complete(report: dict[str, Any]) -> bool:
    """Return whether the real comparison is complete, honest, and cleaned up."""

    model = report.get("model", {})
    index = report.get("index", {})
    corpus = report.get("corpus", {})
    queries = report.get("queries", [])
    latency = report.get("latency", {})
    cleanup = report.get("cleanup", {})
    counts = cleanup.get("database_counts", {})
    if not isinstance(queries, list):
        return False
    case_ids = [row.get("case_id") for row in queries if isinstance(row, dict)]
    excluded_ids = [
        row.get("case_id")
        for row in queries
        if isinstance(row, dict) and row.get("excluded") is True
    ]
    evaluated_rows = [
        row for row in queries if isinstance(row, dict) and row.get("excluded") is False
    ]
    query_contract_valid = bool(
        len(queries) == 20
        and len(case_ids) == len(set(case_ids)) == 20
        and excluded_ids == list(KNOWN_UPSTREAM_UNRETRIEVABLE_CASE_IDS)
        and len(evaluated_rows) == 18
        and all(
            _positive_rank(row.get("rrf_first_evidence_rank"))
            and row.get("exclusion_reason") is None
            for row in evaluated_rows
        )
        and all(
            row.get("exclusion_reason") == UPSTREAM_EXCLUSION_REASON
            for row in queries
            if isinstance(row, dict) and row.get("excluded") is True
        )
    )
    try:
        metrics_match = report.get("metrics") == build_quality_metrics(queries)
    except (TypeError, ValueError):
        metrics_match = False
    latency_fields = (
        "hybrid_p50_ms",
        "hybrid_p95_ms",
        "reranker_p50_ms",
        "reranker_p95_ms",
        "end_to_end_p50_ms",
        "end_to_end_p95_ms",
        "cold_reranker_ms",
        "rss_peak_mib",
        "rss_peak_delta_mib",
    )
    return bool(
        report.get("schema_version") == REPORT_SCHEMA_VERSION
        and report.get("synthetic_data") is True
        and report.get("offline_inference") is True
        and report.get("snapshot_verified") is True
        and model.get("model_id") == BGE_RERANKER_MODEL_ID
        and model.get("revision") == BGE_RERANKER_REVISION
        and index.get("documents_ready") == 10
        and index.get("chunks") == 35
        and index.get("embeddings") == 35
        and corpus.get("questions_total") == 20
        and corpus.get("evaluated_questions") == 18
        and corpus.get("excluded_questions") == 2
        and corpus.get("excluded_case_ids")
        == list(KNOWN_UPSTREAM_UNRETRIEVABLE_CASE_IDS)
        and query_contract_valid
        and metrics_match
        and latency.get("sample_count") == 20
        and all(_finite_nonnegative(latency.get(field)) for field in latency_fields)
        and cleanup.get("baseline_restored") is True
        and cleanup.get("remaining_publication_keys") == []
        and counts
        == {
            "files": 10,
            "documents": 10,
            "versions": 10,
            "acl": 9,
            "chunk_sets": 0,
            "index_sets": 0,
            "chunks": 0,
            "embeddings": 0,
        }
    )


def run_reranker_verification(settings: Settings) -> dict[str, Any]:
    """Build the formal Fake index, compare real reranking, and restore Seed."""

    if settings.embedding_backend != "fake":
        raise RuntimeError("M2-17.5 formal verification requires Fake Embedding")
    if settings.reranker_backend != "bge":
        raise RuntimeError("M2-17.5 formal verification requires BGE-Reranker")
    if settings.docling_backend != "docling" or settings.docling_device != "cpu":
        raise RuntimeError("M2-17.5 formal verification requires local CPU Docling")
    if not settings.model_local_files_only:
        raise RuntimeError("M2-17.5 formal verification must be local-only")

    _force_offline_mode()
    docling_manifest = verify_model_cache(settings.docling_model_cache_root.resolve())
    snapshot = reranker_snapshot_path(settings.model_cache_root)
    if not verify_reranker_snapshot(snapshot):
        raise RuntimeError("Pinned Reranker snapshot verification failed")
    reranker_provider = create_reranker_provider(settings)
    if not isinstance(reranker_provider, BgeRerankerProvider):
        raise TypeError("Configured BGE-Reranker provider was not created")

    storage, sources, _ordinary_data = _prepare_formal_seed(settings)
    runtime = create_database_runtime(settings)
    version_ids = [source.version_id for _corpus, source in sources]
    file_ids = [source.file_id for _corpus, source in sources]
    document_ids = [source.document_id for _corpus, source in sources]
    cleanup: dict[str, Any] = {}
    report: dict[str, Any] = {}
    preflight_complete = False
    try:
        _require_clean_formal_baseline(
            runtime.session_factory,
            version_ids=version_ids,
            file_ids=file_ids,
            expected_document_count=10,
        )
        preflight_complete = True
        owner = _load_named_user(
            runtime.session_factory,
            "owner@demo.deepsearch.local",
        )
        embedding_provider = FakeEmbeddingProvider()
        index_service = DocumentIndexService(
            runtime.session_factory,
            storage,
            settings,
            embedding_provider,
        )
        audits: list[dict[str, Any]] = []
        for corpus_name, source in sources:
            result = index_service.index_version(
                owner,
                document_id=source.document_id,
                version_id=source.version_id,
            )
            audits.append(
                _audit_ready_document(
                    runtime,
                    storage,
                    corpus=corpus_name,
                    source=source,
                    result=result,
                )
            )

        query_rows, latency = _run_formal_queries(
            runtime,
            settings,
            embedding_provider,
            reranker_provider,
            owner,
            sources,
        )
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "synthetic_data": True,
            "offline_inference": True,
            "snapshot_verified": True,
            "docling_model_manifest": docling_manifest,
            "model": {
                "contract_version": reranker_provider.identity.contract_version,
                "provider": reranker_provider.identity.provider,
                "model_id": reranker_provider.identity.model_id,
                "revision": reranker_provider.identity.revision,
                "max_length": reranker_provider.identity.max_length,
                "precision": reranker_provider.identity.precision,
                "score_transform": reranker_provider.identity.score_transform,
                "snapshot_path_name": snapshot.name,
            },
            "index": {
                "provider_model_id": embedding_provider.identity.model_id,
                "provider_revision": embedding_provider.identity.revision,
                "documents_ready": sum(
                    audit["database_ready"] is True for audit in audits
                ),
                "chunks": sum(audit["chunk_count"] for audit in audits),
                "embeddings": sum(audit["embedding_count"] for audit in audits),
            },
            "corpus": {
                "questions_total": 20,
                "evaluated_questions": 18,
                "excluded_questions": 2,
                "excluded_case_ids": list(KNOWN_UPSTREAM_UNRETRIEVABLE_CASE_IDS),
            },
            "queries": query_rows,
            "metrics": build_quality_metrics(query_rows),
            "latency": latency,
        }
    finally:
        if preflight_complete:
            cleanup = _restore_formal_baseline(
                runtime.session_factory,
                storage,
                version_ids=version_ids,
                file_ids=file_ids,
                document_ids=document_ids,
            )
        runtime.engine.dispose()

    report["cleanup"] = cleanup
    report["decision"] = {
        "m2_17_complete": reranker_verification_complete(report),
        "recommended_retrieval_order": _recommended_order(report),
    }
    return report


def _run_formal_queries(
    runtime: DatabaseRuntime,
    settings: Settings,
    embedding_provider: FakeEmbeddingProvider,
    reranker_provider: RerankerProvider,
    owner: CurrentUser,
    sources: Sequence[tuple[str, GeneratedSource]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    hybrid_times: list[float] = []
    reranker_times: list[float] = []
    end_to_end_times: list[float] = []
    process = psutil.Process()
    rss_start = process.memory_info().rss / (1024 * 1024)
    rss_peak = rss_start

    for _corpus, source in sources:
        document_key = str(source.definition["key"])
        golden_facts = source.definition["golden_facts"]
        probes_by_fact = GOLDEN_CHUNK_PROBES[document_key]
        for fact_number, (fact, probes) in enumerate(
            zip(golden_facts, probes_by_fact, strict=True),
            start=1,
        ):
            request = RetrievalRequest(query=str(fact["question"]))
            end_to_end_started = perf_counter()
            with runtime.session_factory() as session:
                _dense, _lexical, hybrid = _retrieval_services(
                    session,
                    settings,
                    embedding_provider,
                )
                started = perf_counter()
                hybrid_response = hybrid.retrieve(owner, request)
                hybrid_ms = (perf_counter() - started) * 1000
            reranker = RerankerRetrievalService(
                _FrozenHybridRoute(owner, request, hybrid_response),
                reranker_provider,
                top_k=settings.reranker_top_k,
            )
            started = perf_counter()
            reranked_response = reranker.retrieve(owner, request)
            reranker_ms = (perf_counter() - started) * 1000
            end_to_end_ms = (perf_counter() - end_to_end_started) * 1000
            hybrid_times.append(hybrid_ms)
            reranker_times.append(reranker_ms)
            end_to_end_times.append(end_to_end_ms)
            rss_peak = max(rss_peak, process.memory_info().rss / (1024 * 1024))

            case_id = f"{document_key}:{fact_number}"
            excluded = case_id in KNOWN_UPSTREAM_UNRETRIEVABLE_CASE_IDS
            rrf_evidence = _matching_results(
                hybrid_response.results,
                document_id=source.document_id,
                probes=probes,
            )
            reranker_evidence = _matching_results(
                reranked_response.results,
                document_id=source.document_id,
                probes=probes,
            )
            rows.append(
                {
                    "case_id": case_id,
                    "document_key": document_key,
                    "fact_number": fact_number,
                    "question": fact["question"],
                    "expected_answer": fact["answer"],
                    "excluded": excluded,
                    "exclusion_reason": (
                        UPSTREAM_EXCLUSION_REASON if excluded else None
                    ),
                    "hybrid_candidate_count": len(hybrid_response.results),
                    "reranked_candidate_count": len(reranked_response.results),
                    "rrf_first_evidence_rank": _first_rank(rrf_evidence),
                    "reranker_first_evidence_rank": _first_rank(reranker_evidence),
                    "rrf_evidence_ranks": [item.final_rank for item in rrf_evidence],
                    "reranker_evidence_ranks": [
                        item.final_rank for item in reranker_evidence
                    ],
                    "reranker_raw_scores": [
                        float(item.reranker.raw_score) for item in reranker_evidence
                    ],
                    "reranker_normalized_scores": [
                        float(item.reranker.normalized_score)
                        for item in reranker_evidence
                    ],
                }
            )

    return rows, {
        "sample_count": len(rows),
        "hybrid_p50_ms": _percentile(hybrid_times, 0.50),
        "hybrid_p95_ms": _percentile(hybrid_times, 0.95),
        "reranker_p50_ms": _percentile(reranker_times, 0.50),
        "reranker_p95_ms": _percentile(reranker_times, 0.95),
        "end_to_end_p50_ms": _percentile(end_to_end_times, 0.50),
        "end_to_end_p95_ms": _percentile(end_to_end_times, 0.95),
        "cold_reranker_ms": round(reranker_times[0], 3),
        "rss_start_mib": round(rss_start, 1),
        "rss_peak_mib": round(rss_peak, 1),
        "rss_peak_delta_mib": round(max(0.0, rss_peak - rss_start), 1),
    }


def _matching_results(
    results: Sequence[ResultT],
    *,
    document_id: UUID,
    probes: Sequence[str],
) -> list[ResultT]:
    normalized_probes = [normalize_text(probe) for probe in probes]
    return [
        result
        for result in results
        if result.identity.document_id == document_id
        and all(
            probe in normalize_text(result.body_text) for probe in normalized_probes
        )
    ]


def _first_rank(
    results: Sequence[RetrievalResult],
) -> int | None:
    return min((result.final_rank for result in results), default=None)


def _route_metrics(
    rows: Sequence[dict[str, Any]],
    rank_field: str,
    denominator: int,
) -> dict[str, int | float]:
    ranks = [row.get(rank_field) for row in rows]
    ranks_at_eight = [rank for rank in ranks if _rank_at_eight(rank)]
    hits = len(ranks_at_eight)
    reciprocal_sum = sum(1 / rank for rank in ranks_at_eight)
    return {
        "hits_at_8": hits,
        "recall_at_8": round(hits / denominator, 6),
        "mrr_at_8": round(reciprocal_sum / denominator, 6),
    }


def _rank_at_eight(value: object) -> TypeGuard[int]:
    return _positive_rank(value) and value <= 8


def _positive_rank(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return round(ordered[index], 3)


def _finite_nonnegative(value: object) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0
    )


def _recommended_order(report: dict[str, Any]) -> str:
    metrics = report.get("metrics", {})
    conclusion = metrics.get("quality_conclusion")
    return "reranker" if conclusion in {"improved", "unchanged"} else "rrf"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-real", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.run_real:
        print("真实Reranker验收未运行；请显式提供--run-real")
        return 2
    try:
        settings = Settings(  # type: ignore[call-arg]
            embedding_backend="fake",
            reranker_backend="bge",
            reranker_model=BGE_RERANKER_MODEL_ID,
            reranker_revision=BGE_RERANKER_REVISION,
            model_local_files_only=True,
            docling_backend="docling",
            docling_device="cpu",
        )
        report = run_reranker_verification(settings)
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001 - CLI must not expose paths or raw internals.
        print("M2 Reranker验收失败；请检查正式Seed、本地模型和离线状态")
        return 1
    print(json.dumps(report["metrics"], ensure_ascii=False, indent=2))
    print(json.dumps(report["latency"], ensure_ascii=False, indent=2))
    print(json.dumps(report["cleanup"], ensure_ascii=False, indent=2))
    print(f"report={output}")
    return 0 if report["decision"]["m2_17_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
