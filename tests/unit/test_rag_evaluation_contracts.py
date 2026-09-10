from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.evaluation import (
    EXTERNAL_RAW_DOWNLOAD_HARD_MAX_BYTES,
    MINIMUM_FREE_SPACE_BYTES,
    ChunkEvaluationConfig,
    ComponentIdentity,
    DeterministicEvaluationResults,
    DiskBudgetPolicy,
    DiskPreflightInput,
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationConfigurationCatalog,
    EvaluationDataset,
    EvaluationLayerResult,
    EvaluationRunIdentity,
    EvaluationSource,
    EvaluationSourceManifest,
    EvaluatorIdentity,
    ExpectedEvidenceSpan,
    JudgeParameters,
    ProjectMetricResult,
    RagasEvaluationResults,
    RagasMetricResult,
    RetrievalContextEvaluationConfig,
    RetryPolicySummary,
    canonical_evaluation_sha256,
    default_chunk_evaluation_configs,
    evaluate_disk_preflight,
)

MIB = 1024 * 1024


def planned_source(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_id": "eu-vat-oss-guides",
        "dataset_version": "m2-cross-border-sources-v1",
        "source_group": "cross_border_core",
        "source_kind": "public_source",
        "source_name": "EU VAT one-stop-shop guides",
        "source_organization": "European Commission",
        "official_source_url": "https://vat-one-stop-shop.ec.europa.eu/guides_en",
        "source_format": "webpage",
        "languages": ["en"],
        "business_purpose": "Cross-border VAT and OSS/IOSS retrieval evaluation",
        "counts_toward_core_score": True,
        "license_status": "pending_review",
        "license_name": None,
        "license_url": None,
        "download_allowed": False,
        "redistribution_allowed": False,
        "accessed_on": "2026-09-07",
        "published_on": None,
        "source_version": None,
        "lifecycle_status": "planned",
        "max_download_bytes": 20 * MIB,
        "expected_size_bytes": None,
        "actual_size_bytes": None,
        "raw_sha256": None,
        "processed_sha256": None,
        "raw_relative_path": None,
        "processed_relative_path": None,
        "transformation_method": None,
        "transformation_version": None,
        "rejection_reason": None,
    }
    payload.update(overrides)
    return payload


def verified_source(**overrides: object) -> dict[str, object]:
    payload = planned_source(
        source_id="eu-low-value-returns",
        official_source_url=(
            "https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/"
            "?uri=CELEX%3A52025XC06233"
        ),
        source_format="pdf",
        license_status="allowed_no_redistribution",
        license_name="Official EU reuse terms reviewed",
        license_url="https://commission.europa.eu/legal-notice_en",
        download_allowed=True,
        source_version="2025-06-23",
        lifecycle_status="verified",
        expected_size_bytes=2 * MIB,
        actual_size_bytes=2 * MIB,
        raw_sha256="0123456789abcdef" * 4,
        processed_sha256="fedcba9876543210" * 4,
        raw_relative_path="raw/eu-low-value-returns/source.pdf",
        processed_relative_path="processed/eu-low-value-returns/source.pdf",
        transformation_method="identity_copy",
        transformation_version="m2-eval-transform-v1",
    )
    payload.update(overrides)
    return payload


def manifest(*sources: dict[str, object]) -> EvaluationSourceManifest:
    return EvaluationSourceManifest(
        manifest_version="m2-cross-border-sources-v1",
        dataset_version="m2-cross-border-sources-v1",
        sources=list(sources) or [planned_source()],
    )


def expected_span() -> ExpectedEvidenceSpan:
    return ExpectedEvidenceSpan(
        source_id="eu-vat-oss-guides",
        document_id="eu-vat-oss-guides-en",
        source_type="pdf",
        page_start=3,
        page_end=3,
        exact_text="The Union scheme covers cross-border supplies of services.",
    )


def evaluation_case(**overrides: object) -> EvaluationCase:
    payload: dict[str, object] = {
        "case_id": "rag-debug-001",
        "dataset_version": "m2-rag-eval-v1",
        "split": "debug",
        "question": "Which transactions are covered by the Union scheme?",
        "language": "en",
        "category": "vat_oss",
        "difficulty": "direct",
        "source_group": "cross_border_core",
        "expected_document_ids": ["eu-vat-oss-guides-en"],
        "expected_evidence_spans": [expected_span().model_dump(mode="json")],
        "answer_key_points": ["It covers eligible cross-border supplies."],
        "acceptable_answer_variants": ["Eligible cross-border supplies are covered."],
        "forbidden_claims": ["All domestic transactions are always covered."],
        "should_answer": True,
        "expected_non_answer_reason": None,
        "trusted_user_fixture_id": "user-fixture-de-operator",
        "acl_fixture_id": "acl-fixture-core-reader",
        "version_fixture_id": "version-fixture-active-v1",
    }
    payload.update(overrides)
    return EvaluationCase.model_validate(payload)


def retrieval_config(**overrides: object) -> RetrievalContextEvaluationConfig:
    payload: dict[str, object] = {
        "config_id": "retrieval-current",
        "config_version": "m2-rag-retrieval-config-v1",
        "dense_candidate_count": 30,
        "lexical_candidate_count": 30,
        "hybrid_candidate_count": 30,
        "rrf_k": 60,
        "reranker_top_k": 8,
        "context_neighbor_window": 1,
        "context_max_tokens": 4000,
        "embedding_model": "BAAI/bge-m3",
        "embedding_version": "5617a9f61b028005a4858fdac845db406aefb181",
        "reranker_model": "BAAI/bge-reranker-v2-m3",
        "reranker_version": "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e",
        "query_languages": ["zh-CN", "en", "de"],
        "dataset_version": "m2-rag-eval-v1",
    }
    payload.update(overrides)
    return RetrievalContextEvaluationConfig.model_validate(payload)


def project_evaluator(**overrides: object) -> EvaluatorIdentity:
    payload: dict[str, object] = {
        "evaluator_id": "project-recall-at-k-v1",
        "evaluator_backend": "project",
        "evaluator_framework": "deep-search-pro",
        "evaluator_framework_version": "1.0.0",
        "metric_name": "recall",
        "metric_source": "project_deterministic",
        "judge_provider": None,
        "judge_model": None,
        "judge_model_version": None,
        "judge_parameters": None,
        "review_prompt_version": None,
        "review_prompt_sha256": None,
        "retry_policy": {"max_attempts": 1, "timeout_ms": 1000},
        "run_status": "planned",
        "failure_category": None,
        "failure_summary": None,
    }
    payload.update(overrides)
    return EvaluatorIdentity.model_validate(payload)


def ragas_evaluator(**overrides: object) -> EvaluatorIdentity:
    payload: dict[str, object] = {
        "evaluator_id": "ragas-faithfulness-v1",
        "evaluator_backend": "ragas",
        "evaluator_framework": "ragas",
        "evaluator_framework_version": "0.0.0-not-installed",
        "metric_name": "faithfulness",
        "metric_source": "ragas_semantic",
        "judge_provider": "qwen-openai-compatible",
        "judge_model": "qwen3.8-max",
        "judge_model_version": "planned",
        "judge_parameters": {
            "temperature": 0.0,
            "top_p": 1.0,
            "max_output_tokens": 2048,
            "seed": 20260907,
        },
        "review_prompt_version": "m2-ragas-faithfulness-prompt-v1",
        "review_prompt_sha256": "1234567890abcdef" * 4,
        "retry_policy": {"max_attempts": 2, "timeout_ms": 30000},
        "run_status": "planned",
        "failure_category": None,
        "failure_summary": None,
    }
    payload.update(overrides)
    return EvaluatorIdentity.model_validate(payload)


def test_source_contract_accepts_planned_and_verified_without_fake_observations() -> (
    None
):
    planned = EvaluationSource.model_validate(planned_source())
    verified = EvaluationSource.model_validate(verified_source())

    assert planned.lifecycle_status == "planned"
    assert planned.actual_size_bytes is None
    assert planned.raw_sha256 is None
    assert verified.lifecycle_status == "verified"
    assert verified.actual_size_bytes == 2 * MIB


@pytest.mark.parametrize(
    "changes",
    [
        {"unknown": True},
        {"source_group": "invoice_core"},
        {"source_format": "exe"},
        {"lifecycle_status": "ready"},
        {"official_source_url": "http://example.com/file.pdf"},
        {"official_source_url": "https://user:pass@example.com/file.pdf"},
        {"official_source_url": "https://localhost/file.pdf"},
        {"accessed_on": "2026-99-99"},
        {"source_version": "../latest"},
        {"max_download_bytes": 0},
    ],
)
def test_source_contract_rejects_unknown_or_unsafe_values(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        EvaluationSource.model_validate(planned_source(**changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"actual_size_bytes": 12},
        {"raw_sha256": "0123456789abcdef" * 4},
        {"raw_relative_path": "raw/source.pdf"},
        {"rejection_reason": "not usable"},
    ],
)
def test_planned_source_rejects_download_or_rejection_observations(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="planned"):
        EvaluationSource.model_validate(planned_source(**changes))


def test_downloaded_verified_and_rejected_lifecycle_rules_are_strict() -> None:
    allowed = planned_source(
        license_status="allowed_no_redistribution",
        license_name="Terms reviewed",
        license_url="https://example.org/terms",
        download_allowed=True,
    )
    downloaded = allowed | {
        "lifecycle_status": "downloaded",
        "actual_size_bytes": 123,
        "raw_sha256": "0123456789abcdef" * 4,
        "raw_relative_path": "raw/example/source.pdf",
    }
    assert EvaluationSource.model_validate(downloaded).actual_size_bytes == 123

    with pytest.raises(ValidationError, match="downloaded"):
        EvaluationSource.model_validate(downloaded | {"raw_sha256": None})
    with pytest.raises(ValidationError, match="verified"):
        EvaluationSource.model_validate(verified_source(processed_sha256=None))
    with pytest.raises(ValidationError, match="rejected"):
        EvaluationSource.model_validate(
            planned_source(lifecycle_status="rejected", rejection_reason=None)
        )
    rejected = EvaluationSource.model_validate(
        planned_source(
            lifecycle_status="rejected",
            rejection_reason="License could not be verified.",
        )
    )
    assert rejected.lifecycle_status == "rejected"


@pytest.mark.parametrize(
    "bad_hash",
    ["0" * 64, "a" * 63, "g" * 64, "sha256:" + "1" * 64],
)
def test_source_contract_rejects_fake_or_malformed_hashes(bad_hash: str) -> None:
    with pytest.raises(ValidationError):
        EvaluationSource.model_validate(verified_source(raw_sha256=bad_hash))


@pytest.mark.parametrize(
    "bad_path",
    [
        "/raw/source.pdf",
        "../raw/source.pdf",
        "raw/../source.pdf",
        "C:/private/source.pdf",
        "C:\\private\\source.pdf",
        "\\\\server\\share\\source.pdf",
    ],
)
def test_source_contract_rejects_unsafe_paths(bad_path: str) -> None:
    with pytest.raises(ValidationError):
        EvaluationSource.model_validate(verified_source(raw_relative_path=bad_path))


def test_license_state_cannot_claim_download_or_redistribution_without_review() -> None:
    with pytest.raises(ValidationError, match="license"):
        EvaluationSource.model_validate(planned_source(download_allowed=True))
    with pytest.raises(ValidationError, match="redistribution"):
        EvaluationSource.model_validate(planned_source(redistribution_allowed=True))
    with pytest.raises(ValidationError, match="license"):
        EvaluationSource.model_validate(
            planned_source(
                license_status="allowed_redistribution",
                download_allowed=True,
                redistribution_allowed=True,
            )
        )


def test_manifest_rejects_duplicate_sources_and_external_budget_overflow() -> None:
    duplicate = planned_source()
    with pytest.raises(ValidationError, match="source IDs"):
        manifest(duplicate, deepcopy(duplicate))

    with pytest.raises(ValidationError, match="200 MiB"):
        manifest(
            planned_source(source_id="source-one", max_download_bytes=120 * MIB),
            planned_source(source_id="source-two", max_download_bytes=81 * MIB),
        )


def test_manifest_rejects_more_than_sixty_four_sources() -> None:
    sources = [
        planned_source(
            source_id=f"source-{index:03d}",
            max_download_bytes=1,
        )
        for index in range(65)
    ]
    with pytest.raises(ValidationError):
        manifest(*sources)


@pytest.mark.parametrize(
    "injected",
    [
        {"question": "leaked question"},
        {"answer": "leaked answer"},
        {"answer_key_points": ["leaked"]},
        {"tenant_id": "tenant-controlled"},
        {"roles": ["company_owner"]},
        {"storage_key": "private/object"},
        {"database_url": "postgresql://secret"},
    ],
)
def test_manifest_rejects_golden_identity_acl_secret_and_budget_injection(
    injected: dict[str, object],
) -> None:
    payload = {
        "manifest_version": "m2-cross-border-sources-v1",
        "dataset_version": "m2-cross-border-sources-v1",
        "sources": [planned_source()],
    }
    payload.update(injected)
    with pytest.raises(ValidationError, match="extra_forbidden"):
        EvaluationSourceManifest.model_validate(payload)


def test_manifest_serialization_and_hash_are_canonical_and_stable() -> None:
    first = manifest(planned_source())
    second = EvaluationSourceManifest.model_validate_json(first.model_dump_json())

    assert first == second
    assert first.canonical_json() == second.canonical_json()
    assert first.canonical_sha256() == second.canonical_sha256()
    assert canonical_evaluation_sha256(first) == first.canonical_sha256()
    assert json.loads(first.canonical_json())["sources"][0]["source_id"] == (
        "eu-vat-oss-guides"
    )


def test_canonical_serialization_rejects_depth_keys_size_nan_and_non_json() -> None:
    too_deep: dict[str, object] = {}
    cursor = too_deep
    for index in range(13):
        child: dict[str, object] = {}
        cursor[f"level_{index}"] = child
        cursor = child

    unsafe_values: list[object] = [
        too_deep,
        {f"key_{index}": index for index in range(129)},
        {"text": "x" * (1024 * 1024)},
        {"score": float("nan")},
        {"unsupported": {"set-value"}},
    ]
    for value in unsafe_values:
        with pytest.raises((TypeError, ValueError)):
            canonical_evaluation_sha256(value)  # type: ignore[arg-type]


def test_checked_in_manifest_has_verified_core_and_planned_non_core_diagnostics() -> (
    None
):
    path = Path("data/evals/m2_cross_border_sources_v1.json")
    loaded = EvaluationSourceManifest.model_validate_json(
        path.read_text(encoding="utf-8")
    )

    assert loaded.manifest_version == "m2-cross-border-sources-v1"
    assert loaded.total_external_download_budget_bytes <= 200 * MIB
    core = [
        source
        for source in loaded.sources
        if source.source_group == "cross_border_core"
    ]
    assert len(core) == 8
    assert all(source.lifecycle_status == "verified" for source in core)
    assert all(source.download_allowed for source in core)
    assert all(source.license_status == "allowed_no_redistribution" for source in core)
    assert all(
        source.actual_size_bytes == source.expected_size_bytes for source in core
    )
    assert all(source.raw_sha256 == source.processed_sha256 for source in core)
    assert all(source.transformation_method == "identity_copy" for source in core)
    diagnostics = [
        source
        for source in loaded.sources
        if source.source_group == "complex_document_diagnostics"
    ]
    assert len(diagnostics) == 3
    assert all(not source.counts_toward_core_score for source in diagnostics)
    assert all(source.lifecycle_status == "planned" for source in diagnostics)
    assert all(source.license_status == "pending_review" for source in diagnostics)
    assert all(not source.download_allowed for source in diagnostics)


def test_evaluation_case_keeps_golden_and_trusted_fixture_references_separate() -> None:
    case = evaluation_case()

    assert case.split == "debug"
    assert case.expected_evidence_spans[0].page_start == 3
    assert case.trusted_user_fixture_id == "user-fixture-de-operator"
    rendered = case.model_dump_json()
    for forbidden in ("tenant_id", "user_id", "roles", "market_code", "storage_key"):
        assert forbidden not in rendered


@pytest.mark.parametrize(
    "changes",
    [
        {"split": "training"},
        {"source_group": "invoice_core"},
        {"question": ""},
        {"trusted_user_fixture_id": "../user"},
        {"tenant_id": "injected"},
        {"acl": {"allow": True}},
        {"real_budget": 999999},
    ],
)
def test_evaluation_case_rejects_unknown_unbounded_or_trusted_data_injection(
    changes: dict[str, object],
) -> None:
    payload = evaluation_case().model_dump(mode="json") | changes
    with pytest.raises(ValidationError):
        EvaluationCase.model_validate(payload)


def test_answerability_state_cannot_contradict_golden_fields() -> None:
    with pytest.raises(ValidationError, match="answerable"):
        evaluation_case(should_answer=True, expected_non_answer_reason="no_evidence")
    with pytest.raises(ValidationError, match="non-answer"):
        evaluation_case(
            should_answer=False,
            expected_non_answer_reason=None,
            answer_key_points=[],
            acceptable_answer_variants=[],
        )
    denied = evaluation_case(
        should_answer=False,
        expected_non_answer_reason="acl_denied",
        answer_key_points=[],
        acceptable_answer_variants=[],
    )
    assert denied.expected_document_ids


def test_dataset_rejects_duplicate_case_ids_and_version_drift() -> None:
    case = evaluation_case()
    with pytest.raises(ValidationError, match="case IDs"):
        EvaluationDataset(
            dataset_version="m2-rag-eval-v1",
            cases=[case, case],
        )
    with pytest.raises(ValidationError, match="dataset version"):
        EvaluationDataset(
            dataset_version="m2-rag-eval-v2",
            cases=[case],
        )


def test_chunk_config_freezes_full_current_baseline_and_supported_variants() -> None:
    configs = default_chunk_evaluation_configs()
    by_id = {config.config_id: config for config in configs}

    current = by_id["chunk-current"]
    assert (
        current.target_tokens,
        current.max_tokens,
        current.text_overlap_tokens,
        current.heading_context_max_tokens,
        current.table_row_overlap,
        current.repeated_edge_min_pages,
    ) == (600, 700, 100, 120, 1, 2)
    assert current.repeat_table_headers is True
    assert current.include_hidden_sheets is True
    assert set(by_id) == {
        "chunk-compact",
        "chunk-medium",
        "chunk-current",
        "chunk-large",
    }
    assert by_id["chunk-compact"].target_tokens == 400
    assert by_id["chunk-large"].max_tokens == 850


@pytest.mark.parametrize(
    "changes",
    [
        {"target_tokens": 701},
        {"target_tokens": 600, "max_tokens": 500},
        {"target_tokens": 400, "text_overlap_tokens": 400},
        {"normalization_version": "latest"},
        {"sql": "SELECT 1"},
    ],
)
def test_chunk_config_rejects_illegal_relationships_and_extra_fields(
    changes: dict[str, object],
) -> None:
    payload = default_chunk_evaluation_configs()[2].model_dump(mode="json") | changes
    with pytest.raises(ValidationError):
        ChunkEvaluationConfig.model_validate(payload)


@pytest.mark.parametrize(
    "changes",
    [
        {"reranker_top_k": 31},
        {"dense_candidate_count": 5, "reranker_top_k": 8},
        {"hybrid_candidate_count": 61},
        {"context_neighbor_window": 2},
        {"query_languages": ["en", "en"]},
        {"tenant_id": "injected"},
    ],
)
def test_retrieval_context_config_is_bounded_and_relational(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        retrieval_config(**changes)


def test_configuration_catalog_rejects_duplicate_config_ids() -> None:
    chunk = default_chunk_evaluation_configs()[0]
    retrieval = retrieval_config(config_id=chunk.config_id)
    with pytest.raises(ValidationError, match="config IDs"):
        EvaluationConfigurationCatalog(
            catalog_version="m2-rag-config-catalog-v1",
            chunk_configs=[chunk],
            retrieval_context_configs=[retrieval],
        )


def test_evaluator_identity_separates_project_and_ragas_and_bounds_judge_parameters() -> (
    None
):
    project = project_evaluator()
    ragas = ragas_evaluator()

    assert project.metric_source == "project_deterministic"
    assert project.judge_model is None
    assert ragas.metric_source == "ragas_semantic"
    assert ragas.judge_parameters == JudgeParameters(
        temperature=0.0,
        top_p=1.0,
        max_output_tokens=2048,
        seed=20260907,
    )
    assert ragas.retry_policy == RetryPolicySummary(max_attempts=2, timeout_ms=30000)

    with pytest.raises(ValidationError, match="project"):
        project_evaluator(metric_source="ragas_semantic")
    with pytest.raises(ValidationError, match="Ragas"):
        ragas_evaluator(judge_model=None)
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ragas_evaluator(judge_parameters={"temperature": 0.0, "api_key": "secret"})


def test_framework_and_judge_failures_cannot_be_recorded_as_zero_scores() -> None:
    completed_zero = RagasMetricResult(
        metric_name="faithfulness",
        status="completed",
        value=0.0,
        direction="higher_is_better",
    )
    assert completed_zero.value == 0.0

    for status in ("framework_failed", "judge_failed", "skipped"):
        with pytest.raises(ValidationError):
            RagasMetricResult(
                metric_name="faithfulness",
                status=status,
                value=0.0,
                direction="higher_is_better",
                failure_category=(
                    "judge_provider_error"
                    if status == "judge_failed"
                    else "framework_error"
                ),
                failure_summary="Safe bounded failure",
            )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "metric_name": "recall",
            "status": "completed",
            "value": 1.1,
            "direction": "higher_is_better",
            "k": 8,
        },
        {
            "metric_name": "precision",
            "status": "completed",
            "value": 0.8,
            "direction": "lower_is_better",
            "k": 2,
        },
        {
            "metric_name": "latency_ms",
            "status": "completed",
            "value": -1,
            "direction": "lower_is_better",
        },
    ],
)
def test_project_metrics_reject_illegal_values_directions_and_k(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ProjectMetricResult.model_validate(payload)


def test_deterministic_and_ragas_results_have_separate_serialized_sections() -> None:
    layer = EvaluationLayerResult(
        layer="retrieval",
        status="completed",
        case_id="rag-debug-001",
        config_id="retrieval-current",
        project_metrics=[
            ProjectMetricResult(
                metric_name="recall",
                status="completed",
                value=1.0,
                direction="higher_is_better",
                k=8,
            )
        ],
        latency_ms=12,
        peak_memory_bytes=1024,
    )
    result = EvaluationCaseResult(
        run_id="eval-run-001",
        case_id="rag-debug-001",
        deterministic=DeterministicEvaluationResults(layers=[layer]),
        ragas=RagasEvaluationResults(
            evaluator_ids=["ragas-faithfulness-v1"],
            metrics=[
                RagasMetricResult(
                    metric_name="faithfulness",
                    status="completed",
                    value=0.9,
                    direction="higher_is_better",
                )
            ],
        ),
    )

    dumped = result.model_dump(mode="json")
    assert dumped["deterministic"]["layers"][0]["project_metrics"]
    assert dumped["ragas"]["metrics"][0]["metric_source"] == "ragas_semantic"
    assert "judge_reasoning" not in result.model_dump_json()

    with pytest.raises(ValidationError):
        EvaluationLayerResult.model_validate(
            layer.model_dump(mode="json")
            | {"ragas_metrics": [{"metric_name": "faithfulness", "value": 1.0}]}
        )


def test_failure_summaries_reject_raw_exceptions_paths_sql_and_secrets() -> None:
    for unsafe in (
        "Traceback: provider failed",
        "C:\\private\\source.pdf",
        "SQL=SELECT * FROM documents",
        "api_key=secret",
    ):
        with pytest.raises(ValidationError):
            ragas_evaluator(
                run_status="judge_failed",
                failure_category="judge_provider_error",
                failure_summary=unsafe,
            )


def test_run_identity_binds_data_code_models_and_full_configs_without_trusted_context() -> (
    None
):
    current = next(
        config
        for config in default_chunk_evaluation_configs()
        if config.config_id == "chunk-current"
    )
    run = EvaluationRunIdentity(
        run_id="eval-run-001",
        source_manifest_version="m2-cross-border-sources-v1",
        source_manifest_sha256="0123456789abcdef" * 4,
        dataset_version="m2-rag-eval-v1",
        dataset_sha256="fedcba9876543210" * 4,
        code_revision="0123456789abcdef0123456789abcdef01234567",
        code_dirty=False,
        parser=ComponentIdentity(name="parser-router", version="m2-parser-router-v1"),
        ocr=ComponentIdentity(name="rapidocr", version="1.4.4"),
        chunk_config=current,
        retrieval_context_config=retrieval_config(),
        answer_model=ComponentIdentity(
            name="qwen-openai-compatible",
            version="planned",
            model_id="qwen3.8-max",
            model_revision="planned",
        ),
        evaluators=[project_evaluator(), ragas_evaluator()],
        run_status="planned",
    )

    rendered = run.model_dump_json()
    assert "m2-structure-aware-chunker-v3" in rendered
    assert "BAAI/bge-m3" in rendered
    for forbidden in ("tenant_id", "roles", "market_code", "storage_key"):
        assert forbidden not in rendered

    with pytest.raises(ValidationError, match="extra_forbidden"):
        EvaluationRunIdentity(**run.model_dump(), tenant_id="injected")  # type: ignore[call-arg]


def test_disk_gate_freezes_byte_limits_and_excludes_existing_model_cache() -> None:
    policy = DiskBudgetPolicy()
    assert policy.external_raw_hard_limit_bytes == 200 * MIB
    assert policy.processed_artifact_target_limit_bytes == 300 * MIB
    assert policy.postgres_index_target_limit_bytes == 600 * MIB
    assert policy.minimum_free_space_bytes == 3 * 1024 * MIB

    result = evaluate_disk_preflight(
        DiskPreflightInput(
            unit="bytes",
            external_raw_bytes=200 * MIB,
            processed_artifact_bytes=300 * MIB,
            postgres_index_bytes=600 * MIB,
            existing_model_cache_bytes=50 * 1024 * MIB,
            available_free_bytes=MINIMUM_FREE_SPACE_BYTES,
        ),
        policy=policy,
    )
    assert result.allowed is True
    assert result.existing_model_cache_excluded is True


@pytest.mark.parametrize(
    "changes",
    [
        {"external_raw_bytes": EXTERNAL_RAW_DOWNLOAD_HARD_MAX_BYTES + 1},
        {"available_free_bytes": MINIMUM_FREE_SPACE_BYTES - 1},
        {"available_free_bytes": None},
        {"external_raw_bytes": -1},
        {"unit": "MiB"},
        {"postgres_index_bytes": 2**63},
    ],
)
def test_disk_gate_safely_rejects_limits_missing_info_units_and_overflow(
    changes: dict[str, object],
) -> None:
    payload: dict[str, object] = {
        "unit": "bytes",
        "external_raw_bytes": 1,
        "processed_artifact_bytes": 1,
        "postgres_index_bytes": 1,
        "existing_model_cache_bytes": 0,
        "available_free_bytes": MINIMUM_FREE_SPACE_BYTES,
    }
    payload.update(changes)
    try:
        request = DiskPreflightInput.model_validate(payload)
    except ValidationError:
        return
    assert evaluate_disk_preflight(request).allowed is False


def test_contract_text_lists_and_serialized_output_are_bounded() -> None:
    with pytest.raises(ValidationError):
        evaluation_case(question="x" * 2001)
    with pytest.raises(ValidationError):
        evaluation_case(answer_key_points=["point"] * 21)
    with pytest.raises(ValidationError):
        EvaluationDataset(
            dataset_version="m2-rag-eval-v1",
            cases=[
                evaluation_case(case_id=f"rag-debug-{index:04d}")
                for index in range(1001)
            ],
        )


def test_date_values_are_real_dates_after_validation() -> None:
    source = EvaluationSource.model_validate(planned_source())
    assert source.accessed_on == date(2026, 9, 7)
