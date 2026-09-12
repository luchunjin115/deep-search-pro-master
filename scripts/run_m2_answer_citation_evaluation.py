"""Run Fake, real-Gateway, or explicitly paid formal Answer/Citation evaluation."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path

import httpx
from openai import AsyncOpenAI

from app.core.config import (
    BGE_M3_MODEL_ID,
    BGE_M3_REVISION,
    BGE_RERANKER_MODEL_ID,
    BGE_RERANKER_REVISION,
    Settings,
)
from app.db.session import create_database_runtime
from app.evals.answer_citation_formal import (
    ExternalUsageRecorder,
    FormalEvaluationRuntime,
    run_m2_answer_citation_gateway_evaluation,
)
from app.evals.answer_citation_report import (
    AnswerCitationFormalEvaluationReport,
    ReviewEvidenceWriteError,
    write_answer_citation_public_report,
)
from app.evals.answer_citation_runner import (
    DeterministicFakeAnswerProvider,
    build_fake_answer_case_inputs_from_dataset,
    run_m2_answer_citation_fake_evaluation,
)
from app.evals.rag_runner import PROJECT_ROOT
from app.evals.ragas_generation import (
    Ragas043GenerationBackend,
    RagasGenerationAdapter,
)
from app.evals.ragas_retrieval import RagasJudgeRuntime
from app.evals.reranker_context_corpus import (
    build_m2_reranker_context_evidence_map,
    load_existing_m2_reranker_context_corpus,
)
from app.llm.agent_deepseek import DeepSeekAgentProvider
from app.services.retrieval import create_embedding_provider, create_reranker_provider
from app.services.storage import LocalStorageBackend
from scripts.download_m2_reranker import ensure_reranker_snapshot

DATASET_PATH = PROJECT_ROOT / "data" / "evals" / "m2_cross_border_rag_smoke_v1.jsonl"
DEFAULT_OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "evals"
    / "runtime"
    / "reports"
    / "m2-answer-citation-fake-report.json"
)
DEFAULT_GATEWAY_OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "evals"
    / "runtime"
    / "reports"
    / "m2-answer-citation-gateway-report.json"
)
DEFAULT_FORMAL_OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "evals"
    / "runtime"
    / "reports"
    / "m2-answer-citation-formal-report.json"
)
FORMAL_PREFLIGHT_CASE_IDS = (
    "smoke-syn-001-voltage",
    "smoke-safe-035-sop-acl",
    "smoke-safe-040-unknown-fee",
)
ANSWER_API_CALLS_PER_COMPOSE_LIMIT = 2
RAGAS_JUDGE_CALLS_PER_ELIGIBLE_CASE = 9
PREFLIGHT_ANSWER_API_CALL_LIMIT = (
    len(FORMAL_PREFLIGHT_CASE_IDS) * ANSWER_API_CALLS_PER_COMPOSE_LIMIT
)
PREFLIGHT_JUDGE_API_CALL_LIMIT = (
    len(FORMAL_PREFLIGHT_CASE_IDS) * RAGAS_JUDGE_CALLS_PER_ELIGIBLE_CASE
)
FORMAL_ANSWER_API_CALL_LIMIT = 40 * ANSWER_API_CALLS_PER_COMPOSE_LIMIT
FORMAL_JUDGE_API_CALL_LIMIT = 40 * RAGAS_JUDGE_CALLS_PER_ELIGIBLE_CASE
_REPORT_ROOT = DEFAULT_OUTPUT_PATH.parent.resolve()


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--run-real-gateway",
        action="store_true",
        help="explicitly run PostgreSQL/pgvector and local BGE through the public API",
    )
    modes.add_argument(
        "--run-formal",
        action="store_true",
        help="explicitly run paid DeepSeek Answer and Judge after a three-case preflight",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args(argv)


def _gateway_settings() -> Settings:
    """Freeze the exact M2-22.7.5 winner without changing production defaults."""

    return Settings().model_copy(
        update={
            "embedding_backend": "bge",
            "embedding_model": BGE_M3_MODEL_ID,
            "embedding_revision": BGE_M3_REVISION,
            "embedding_batch_size": 16,
            "embedding_precision": "float32",
            "reranker_backend": "bge",
            "reranker_model": BGE_RERANKER_MODEL_ID,
            "reranker_revision": BGE_RERANKER_REVISION,
            "reranker_batch_size": 2,
            "reranker_max_length": 8192,
            "reranker_precision": "float32",
            "dense_candidate_count": 10,
            "lexical_candidate_count": 10,
            "hybrid_candidate_count": 20,
            "rrf_k": 60,
            "reranker_top_k": 5,
            "context_neighbor_window": 1,
            "context_max_tokens": 3000,
            "database_statement_timeout_ms": 30_000,
            "model_device": "cpu",
            "model_local_files_only": True,
        }
    )


def _gateway_model_settings() -> tuple[Settings, Settings]:
    """Keep BGE-M3 on CPU and create only the Reranker on CUDA."""

    embedding_settings = _gateway_settings()
    reranker_settings = embedding_settings.model_copy(update={"model_device": "cuda"})
    return embedding_settings, reranker_settings


def _validated_gateway_output(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(_REPORT_ROOT)
    except ValueError:
        raise ValueError(
            "Gateway report must stay in the managed report directory"
        ) from None
    return resolved


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.run_formal:
        return _run_formal(args.output)
    if args.run_real_gateway:
        return _run_real_gateway(args.output)
    cases, dataset_version, dataset_sha256 = build_fake_answer_case_inputs_from_dataset(
        DATASET_PATH
    )
    provider = DeterministicFakeAnswerProvider()
    report = run_m2_answer_citation_fake_evaluation(
        cases=cases,
        dataset_version=dataset_version,
        dataset_sha256=dataset_sha256,
        provider=provider,
    )
    write_answer_citation_public_report(args.output, report)
    print(
        json.dumps(
            {
                "run_id": report.run_id,
                "run_status": report.run_status,
                "answerable_cases": len(report.cohort.answerable_cases),
                "safety_cases": len(report.cohort.safety_cases),
                "provider_answer_calls": report.cache.provider_answer_calls,
                "quality_gate_passed": report.quality_gate_passed,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _run_real_gateway(requested_output: Path) -> int:
    """Run and delete one bounded formal artifact; print only public-safe facts."""

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    output = (
        DEFAULT_GATEWAY_OUTPUT_PATH
        if requested_output == DEFAULT_OUTPUT_PATH
        else requested_output
    )
    runtime = None
    stage = "arguments"
    try:
        output = _validated_gateway_output(output)
        settings, reranker_settings = _gateway_model_settings()
        storage = LocalStorageBackend(settings.local_storage_root)
        runtime = create_database_runtime(settings)
        stage = "retained_real_index"
        embedding = create_embedding_provider(settings)
        snapshot = load_existing_m2_reranker_context_corpus(
            settings=settings,
            runtime=runtime,
            project_root=PROJECT_ROOT,
            embedding_provider=embedding,
        )
        stage = "golden_evidence_map"
        evidence_map = build_m2_reranker_context_evidence_map(
            runtime=runtime,
            storage=storage,
            project_root=PROJECT_ROOT,
            snapshot=snapshot,
        )
        stage = "reranker_snapshot"
        ensure_reranker_snapshot(settings.model_cache_root, allow_download=False)
        reranker = create_reranker_provider(reranker_settings)
        stage = "public_gateway_matrix"
        report = run_m2_answer_citation_gateway_evaluation(
            settings=settings,
            runtime=runtime,
            storage=storage,
            snapshot=snapshot,
            embedding_provider=embedding,
            reranker_provider=reranker,
            evidence_ids_by_chunk=evidence_map,
            project_root=PROJECT_ROOT,
        )
        stage = "temporary_report"
        artifact_sha256 = write_answer_citation_public_report(output, report)
        artifact_size_bytes = output.stat().st_size
        output.unlink()
        if output.exists():
            raise RuntimeError("temporary Gateway report was not deleted")
    except Exception:  # noqa: BLE001 - never print private paths or raw exceptions
        print(
            "M2-22.8.3公开Gateway评估失败；"
            f"安全阶段={stage}；请检查固定语料、本地模型、数据库或清理状态"
        )
        return 1
    finally:
        if runtime is not None:
            runtime.engine.dispose()

    print(
        json.dumps(
            {
                "run_id": report.run_id,
                "run_status": report.run_status,
                "answerable_cases": len(report.cohort.answerable_cases),
                "safety_cases": len(report.cohort.safety_cases),
                "chain_passed_cases": sum(
                    item.chain_passed is True for item in report.chain_audits
                ),
                "answer_compose_calls": report.answer_compose_calls,
                "quality_gate_passed": report.quality_gate_passed,
                "runtime_identity": report.runtime_identity.model_dump(mode="json"),
                "baseline_restored": report.lifecycle.baseline_restored,
                "corpus": report.corpus_after.model_dump(mode="json"),
                "report_size_bytes": artifact_size_bytes,
                "report_sha256": artifact_sha256,
                "report_deleted": True,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _formal_runtime(
    settings: Settings,
    embedding: object,
    *,
    judge_api_call_limit: int,
) -> FormalEvaluationRuntime:
    api_key = settings.deepseek_api_key
    if api_key is None:
        raise ValueError("formal evaluation requires DEEPSEEK_API_KEY")
    answer_provider = DeepSeekAgentProvider(
        api_key=api_key,
        model=settings.deepseek_model,
        base_url=settings.deepseek_base_url,
        timeout_seconds=settings.deepseek_timeout_seconds,
        max_output_tokens=settings.deepseek_agent_max_output_tokens,
    )
    usage = ExternalUsageRecorder(max_api_calls=judge_api_call_limit)
    judge = RagasJudgeRuntime(
        provider="deepseek-openai-compatible",
        model=settings.deepseek_model,
        model_version="api-alias-20260911",
        temperature=0.0,
        top_p=1.0,
        max_output_tokens=2048,
        seed=None,
        max_attempts=1,
        timeout_ms=30_000,
    )
    judge_http = httpx.AsyncClient(
        event_hooks={
            "request": [usage.capture_request],
            "response": [usage.capture_response],
        }
    )

    def client_factory(**kwargs: object) -> AsyncOpenAI:
        return AsyncOpenAI(http_client=judge_http, **kwargs)

    backend = Ragas043GenerationBackend(
        judge=judge,
        api_key=api_key,
        base_url=settings.deepseek_base_url,
        embedding_provider=embedding,  # type: ignore[arg-type]
        client_factory=client_factory,
    )
    return FormalEvaluationRuntime(
        answer_provider=answer_provider,
        semantic_adapter=RagasGenerationAdapter(
            backend=backend,
            judge=judge,
            answer_provider="deepseek",
            answer_model=settings.deepseek_model,
        ),
        judge_usage=usage,
    )


def _formal_preflight_passed(
    report: AnswerCitationFormalEvaluationReport,
    selected_case_ids: frozenset[str],
) -> bool:
    evaluations = {item.case_id: item for item in report.formal_evaluations}
    audits = {item.case_id: item for item in report.chain_audits}
    if set(evaluations) < selected_case_ids or set(audits) < selected_case_ids:
        return False
    return bool(
        report.answer_compose_calls
        == sum(
            audits[case_id].provider_evidence_count > 0 for case_id in selected_case_ids
        )
        and report.lifecycle.baseline_restored
        and all(
            audits[case_id].chain_passed is True
            and evaluations[case_id].answer_usage.api_calls
            in (
                {1, ANSWER_API_CALLS_PER_COMPOSE_LIMIT}
                if audits[case_id].provider_evidence_count > 0
                else {0}
            )
            and (
                evaluations[case_id].answer_usage.total_tokens > 0
                if audits[case_id].provider_evidence_count > 0
                else evaluations[case_id].answer_usage.total_tokens == 0
            )
            for case_id in selected_case_ids
        )
    )


def _run_formal(requested_output: Path) -> int:
    """Run a paid three-case Answer preflight, then the fixed 40-row matrix."""

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    output = (
        DEFAULT_FORMAL_OUTPUT_PATH
        if requested_output == DEFAULT_OUTPUT_PATH
        else requested_output
    )
    runtime = None
    stage = "arguments"
    try:
        output = _validated_gateway_output(output)
        settings, reranker_settings = _gateway_model_settings()
        if settings.llm_provider != "deepseek":
            raise ValueError("formal evaluation requires LLM_PROVIDER=deepseek")
        storage = LocalStorageBackend(settings.local_storage_root)
        runtime = create_database_runtime(settings)
        stage = "retained_real_index"
        embedding = create_embedding_provider(settings)
        snapshot = load_existing_m2_reranker_context_corpus(
            settings=settings,
            runtime=runtime,
            project_root=PROJECT_ROOT,
            embedding_provider=embedding,
        )
        stage = "golden_evidence_map"
        evidence_map = build_m2_reranker_context_evidence_map(
            runtime=runtime,
            storage=storage,
            project_root=PROJECT_ROOT,
            snapshot=snapshot,
        )
        stage = "reranker_snapshot"
        ensure_reranker_snapshot(settings.model_cache_root, allow_download=False)
        reranker = create_reranker_provider(reranker_settings)
        preflight_ids = frozenset(FORMAL_PREFLIGHT_CASE_IDS)

        stage = "paid_three_case_answer_preflight"
        preflight = run_m2_answer_citation_gateway_evaluation(
            settings=settings,
            runtime=runtime,
            storage=storage,
            snapshot=snapshot,
            embedding_provider=embedding,
            reranker_provider=reranker,
            evidence_ids_by_chunk=evidence_map,
            project_root=PROJECT_ROOT,
            formal_runtime=_formal_runtime(
                settings,
                embedding,
                judge_api_call_limit=PREFLIGHT_JUDGE_API_CALL_LIMIT,
            ),
            selected_case_ids=preflight_ids,
        )
        if not isinstance(preflight, AnswerCitationFormalEvaluationReport):
            raise TypeError("formal preflight returned the wrong report contract")
        preflight_output = output.with_name(f"{output.stem}-preflight.json")
        preflight_sha256 = write_answer_citation_public_report(
            preflight_output, preflight
        )
        preflight_passed = _formal_preflight_passed(preflight, preflight_ids)
        if not preflight_passed:
            raise RuntimeError("formal preflight did not pass its safety checks")
        if (
            preflight.answer_usage.api_calls > PREFLIGHT_ANSWER_API_CALL_LIMIT
            or preflight.judge_usage.api_calls > PREFLIGHT_JUDGE_API_CALL_LIMIT
        ):
            raise RuntimeError("formal preflight exceeded its paid call budget")

        stage = "paid_fixed_40_matrix"
        report = run_m2_answer_citation_gateway_evaluation(
            settings=settings,
            runtime=runtime,
            storage=storage,
            snapshot=snapshot,
            embedding_provider=embedding,
            reranker_provider=reranker,
            evidence_ids_by_chunk=evidence_map,
            project_root=PROJECT_ROOT,
            formal_runtime=_formal_runtime(
                settings,
                embedding,
                judge_api_call_limit=FORMAL_JUDGE_API_CALL_LIMIT,
            ),
        )
        if not isinstance(report, AnswerCitationFormalEvaluationReport):
            raise TypeError("formal matrix returned the wrong report contract")
        stage = "public_formal_report"
        artifact_sha256 = write_answer_citation_public_report(output, report)
        if (
            report.run_status != "completed"
            or report.answer_usage.api_calls > FORMAL_ANSWER_API_CALL_LIMIT
            or report.judge_usage.api_calls > FORMAL_JUDGE_API_CALL_LIMIT
        ):
            raise RuntimeError("formal matrix stopped or exceeded its paid call budget")
    except ReviewEvidenceWriteError:
        print(
            "M2-22.8.7正式评估失败；安全阶段=private_review_persistence；现场证据未完整保存，已停止后续调用。"
        )
        return 1
    except Exception:  # noqa: BLE001 - never expose keys, paths, or raw Provider bodies
        print(
            "M2-22.8.7正式评估失败；"
            f"安全阶段={stage}；请检查固定语料、本地模型、数据库、DeepSeek额度或网络"
        )
        return 1
    finally:
        if runtime is not None:
            runtime.engine.dispose()

    print(
        json.dumps(
            {
                "run_id": report.run_id,
                "run_status": report.run_status,
                "business_quality_gate_passed": report.business_quality_gate_passed,
                "ragas_quality_gate_passed": report.ragas_quality_gate_passed,
                "chain_passed_cases": sum(
                    item.chain_passed is True for item in report.chain_audits
                ),
                "answer_compose_calls": report.answer_compose_calls,
                "answer_usage": report.answer_usage.model_dump(mode="json"),
                "answer_repair_calls": max(
                    report.answer_usage.api_calls - report.answer_compose_calls,
                    0,
                ),
                "judge_usage": report.judge_usage.model_dump(mode="json"),
                "preflight_answer_usage": preflight.answer_usage.model_dump(
                    mode="json"
                ),
                "preflight_judge_usage": preflight.judge_usage.model_dump(mode="json"),
                "paid_call_limits": {
                    "preflight_answer": PREFLIGHT_ANSWER_API_CALL_LIMIT,
                    "preflight_judge": PREFLIGHT_JUDGE_API_CALL_LIMIT,
                    "formal_answer": FORMAL_ANSWER_API_CALL_LIMIT,
                    "formal_judge": FORMAL_JUDGE_API_CALL_LIMIT,
                },
                "semantic_aggregates": [
                    item.model_dump(mode="json") for item in report.semantic_aggregates
                ],
                "same_model_bias": report.semantic_evaluator.same_model_bias,
                "baseline_restored": report.lifecycle.baseline_restored,
                "preflight_report_sha256": preflight_sha256,
                "report_sha256": artifact_sha256,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
