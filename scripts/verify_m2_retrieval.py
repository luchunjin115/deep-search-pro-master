"""Verify formal M2 retrieval with Fake/BGE and restore the clean Seed."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import BGE_M3_MODEL_ID, BGE_M3_REVISION, Settings
from app.db.session import DatabaseRuntime, create_database_runtime
from app.models.identity import Tenant, User
from app.models.knowledge import (
    Document,
    DocumentVersion,
    StoredFile,
)
from app.repositories.retrieval import RetrievalRepository
from app.schemas.auth import CurrentUser
from app.schemas.retrieval import RetrievalRequest, RetrievalResponse, RetrievalResult
from app.services.documents.indexing.service import (
    DocumentIndexResult,
    DocumentIndexService,
)
from app.services.retrieval import (
    BgeM3EmbeddingProvider,
    EmbeddingProvider,
    FakeEmbeddingProvider,
    create_embedding_provider,
)
from app.services.retrieval.dense import DenseRetrievalService
from app.services.retrieval.hybrid import HybridRetrievalService
from app.services.retrieval.lexical import LexicalRetrievalService
from scripts.benchmark_m2_docling import verify_model_cache
from scripts.benchmark_m2_embedding import ensure_bge_snapshot
from scripts.seed_m1 import load_seed_definition as load_m1_seed_definition
from scripts.seed_m2_files import GeneratedSource
from scripts.verify_m2_chunk_pipeline import GOLDEN_CHUNK_PROBES, normalize_text
from scripts.verify_m2_index_pipeline import (
    EXPECTED_FORMAL_CHUNK_COUNTS,
    _audit_ready_document,
    _force_offline_mode,
    _prepare_formal_seed,
    _require_clean_formal_baseline,
    _restore_formal_baseline,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "output" / "m2_retrieval_report.json"

REPORT_SCHEMA_VERSION = "m2-retrieval-report-v1"
BGE_SMOKE_SCHEMA_VERSION = "m2-retrieval-bge-smoke-v1"
ROUTING_CONCLUSION = "insufficient_scale_keep_default_hybrid"


def fake_retrieval_verification_complete(report: dict[str, Any]) -> bool:
    """Return whether every reviewed Fake retrieval and cleanup gate passed."""

    provider = report.get("provider", {})
    index = report.get("index", {})
    retrieval = report.get("retrieval", {})
    security = report.get("security", {})
    indexes = report.get("indexes", {})
    latency = report.get("latency", {})
    cleanup = report.get("cleanup", {})
    counts = cleanup.get("database_counts", {})
    security_fields = (
        "owner_can_access_all",
        "de_market_acl_allowed",
        "fr_market_mismatch_denied",
        "role_acl_allowed",
        "role_acl_mismatch_denied",
        "inactive_version_denied",
        "inactive_index_set_denied",
        "soft_deleted_document_denied",
        "soft_deleted_file_denied",
    )
    return bool(
        report.get("schema_version") == REPORT_SCHEMA_VERSION
        and provider.get("model_id") == "fake/m2-deterministic"
        and provider.get("revision") == "m2-fake-v1"
        and index.get("documents_ready") == 10
        and index.get("chunks") == 35
        and index.get("embeddings") == 35
        and retrieval.get("questions_total") == 20
        and isinstance(retrieval.get("dense_document_hits"), int)
        and retrieval.get("dense_document_hits", 0) > 0
        and retrieval.get("lexical_document_hits", 0) >= 18
        and retrieval.get("hybrid_document_hits", 0) >= 18
        and retrieval.get("hybrid_evidence_hits") == 18
        and retrieval.get("hybrid_locator_hits") == 18
        and retrieval.get("deterministic_queries") == 20
        and retrieval.get("known_unretrievable_facts") == 2
        and all(security.get(field) is True for field in security_fields)
        and indexes.get("gin_available") is True
        and indexes.get("hnsw_available") is True
        and latency.get("sample_count") == 20
        and _finite_nonnegative(latency.get("dense_p95_ms"))
        and _finite_nonnegative(latency.get("lexical_p95_ms"))
        and _finite_nonnegative(latency.get("hybrid_p95_ms"))
        and latency.get("routing_conclusion") == ROUTING_CONCLUSION
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


def bge_retrieval_smoke_complete(report: dict[str, Any]) -> bool:
    """Return whether the pinned offline BGE retrieval and cleanup gates passed."""

    model = report.get("model", {})
    retrieval = report.get("retrieval", {})
    cleanup = report.get("cleanup", {})
    return bool(
        report.get("schema_version") == BGE_SMOKE_SCHEMA_VERSION
        and report.get("offline_inference") is True
        and model.get("model_id") == BGE_M3_MODEL_ID
        and model.get("revision") == BGE_M3_REVISION
        and model.get("dimensions") == 1024
        and isinstance(retrieval.get("query"), str)
        and retrieval.get("dense_hit") is True
        and retrieval.get("hybrid_hit") is True
        and retrieval.get("evidence_hit") is True
        and retrieval.get("has_dense_score") is True
        and retrieval.get("has_lexical_score") is True
        and cleanup.get("baseline_restored") is True
    )


def run_fake_retrieval_verification(settings: Settings) -> dict[str, Any]:
    """Index ten formal documents, retrieve twenty facts, audit, and restore."""

    if settings.embedding_backend != "fake":
        raise RuntimeError("M2-16.7 daily verification requires Fake Embedding")
    if settings.docling_backend != "docling" or settings.docling_device != "cpu":
        raise RuntimeError("M2-16.7 formal verification requires local CPU Docling")
    _force_offline_mode()
    model_manifest = verify_model_cache(settings.docling_model_cache_root.resolve())
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
        owner = _load_named_user(runtime.session_factory, "owner@demo.deepsearch.local")
        provider = FakeEmbeddingProvider()
        index_service = DocumentIndexService(
            runtime.session_factory,
            storage,
            settings,
            provider,
        )
        results: dict[str, DocumentIndexResult] = {}
        audits: list[dict[str, Any]] = []
        for corpus, source in sources:
            key = str(source.definition["key"])
            result = index_service.index_version(
                owner,
                document_id=source.document_id,
                version_id=source.version_id,
            )
            results[key] = result
            audits.append(
                _audit_ready_document(
                    runtime,
                    storage,
                    corpus=corpus,
                    source=source,
                    result=result,
                )
            )

        query_report, latency = _run_golden_queries(
            runtime,
            settings,
            provider,
            owner,
            sources,
        )
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "synthetic_data": True,
            "offline_inference": True,
            "docling_model_manifest": model_manifest,
            "provider": {
                "model_id": provider.identity.model_id,
                "revision": provider.identity.revision,
                "dimensions": provider.identity.dimensions,
            },
            "index": {
                "documents_ready": sum(
                    audit["database_ready"] is True for audit in audits
                ),
                "chunks": sum(audit["chunk_count"] for audit in audits),
                "embeddings": sum(audit["embedding_count"] for audit in audits),
                "expected_chunk_counts": EXPECTED_FORMAL_CHUNK_COUNTS,
            },
            "queries": query_report,
            "retrieval": _aggregate_queries(query_report),
            "security": _run_security_matrix(
                runtime.session_factory,
                owner=owner,
                sources=sources,
                results=results,
            ),
            "indexes": _explain_retrieval_indexes(runtime),
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
        "m2_16_complete": fake_retrieval_verification_complete(report)
    }
    return report


def run_bge_retrieval_smoke(settings: Settings) -> dict[str, Any]:
    """Index and retrieve one native PDF with the pinned local BGE snapshot."""

    if settings.embedding_backend != "bge":
        raise RuntimeError("M2-16.7 BGE Smoke requires EMBEDDING_BACKEND=bge")
    if (
        settings.embedding_model != BGE_M3_MODEL_ID
        or settings.embedding_revision != BGE_M3_REVISION
        or not settings.model_local_files_only
    ):
        raise RuntimeError("M2-16.7 BGE Smoke requires the pinned offline identity")
    _force_offline_mode()
    snapshot = ensure_bge_snapshot(settings.model_cache_root, allow_download=False)
    provider = create_embedding_provider(settings)
    if not isinstance(provider, BgeM3EmbeddingProvider):
        raise TypeError("Configured BGE provider was not created")

    storage, sources, _ordinary_data = _prepare_formal_seed(settings)
    target = next(
        source
        for _corpus, source in sources
        if source.definition["key"] == "mushroom_lamp_manual"
    )
    runtime = create_database_runtime(settings)
    cleanup: dict[str, Any] = {}
    report: dict[str, Any] = {}
    preflight_complete = False
    try:
        _require_clean_formal_baseline(
            runtime.session_factory,
            version_ids=[source.version_id for _corpus, source in sources],
            file_ids=[source.file_id for _corpus, source in sources],
            expected_document_count=10,
        )
        preflight_complete = True
        owner = _load_named_user(runtime.session_factory, "owner@demo.deepsearch.local")
        index_result = DocumentIndexService(
            runtime.session_factory,
            storage,
            settings,
            provider,
        ).index_version(
            owner,
            document_id=target.document_id,
            version_id=target.version_id,
        )
        query = "这款台灯需要多少伏特供电？"
        with runtime.session_factory() as session:
            _dense, _lexical, hybrid = _retrieval_services(
                session,
                settings,
                provider,
            )
            response = hybrid.retrieve(owner, RetrievalRequest(query=query))
        target_results = [
            result
            for result in response.results
            if result.identity.document_id == target.document_id
        ]
        evidence_results = [
            result
            for result in target_results
            if "220v" in normalize_text(result.body_text)
        ]
        report = {
            "schema_version": BGE_SMOKE_SCHEMA_VERSION,
            "synthetic_data": True,
            "offline_inference": True,
            "snapshot_path_name": snapshot.name,
            "model": {
                "model_id": provider.identity.model_id,
                "revision": provider.identity.revision,
                "dimensions": provider.identity.dimensions,
            },
            "index": {
                "index_set_id": str(index_result.index_set_id),
                "status": index_result.status,
                "chunk_count": index_result.chunk_count,
            },
            "retrieval": {
                "query": query,
                "dense_hit": any(
                    result.scores.dense is not None for result in target_results
                ),
                "hybrid_hit": bool(target_results),
                "evidence_hit": bool(evidence_results),
                "has_dense_score": any(
                    result.scores.dense is not None for result in response.results
                ),
                "has_lexical_score": any(
                    result.scores.lexical is not None for result in response.results
                ),
                "evidence_ranks": [result.final_rank for result in evidence_results],
            },
        }
    finally:
        if preflight_complete:
            cleanup = _restore_formal_baseline(
                runtime.session_factory,
                storage,
                version_ids=[target.version_id],
                file_ids=[target.file_id],
                document_ids=[target.document_id],
            )
        runtime.engine.dispose()

    report["cleanup"] = cleanup
    report["decision"] = {
        "bge_retrieval_smoke_passed": bge_retrieval_smoke_complete(report)
    }
    return report


def _run_golden_queries(
    runtime: DatabaseRuntime,
    settings: Settings,
    provider: EmbeddingProvider,
    owner: CurrentUser,
    sources: Sequence[tuple[str, GeneratedSource]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    query_rows: list[dict[str, Any]] = []
    dense_times: list[float] = []
    lexical_times: list[float] = []
    hybrid_times: list[float] = []
    for _corpus, source in sources:
        key = str(source.definition["key"])
        golden_facts = source.definition["golden_facts"]
        probes_by_fact = GOLDEN_CHUNK_PROBES[key]
        for fact_number, (fact, probes) in enumerate(
            zip(golden_facts, probes_by_fact, strict=True),
            start=1,
        ):
            request = RetrievalRequest(query=str(fact["question"]))
            with runtime.session_factory() as session:
                dense, lexical, hybrid = _retrieval_services(
                    session,
                    settings,
                    provider,
                )
                started = perf_counter()
                dense_response = dense.retrieve(owner, request)
                dense_ms = (perf_counter() - started) * 1000
                started = perf_counter()
                lexical_response = lexical.retrieve(owner, request)
                lexical_ms = (perf_counter() - started) * 1000
                started = perf_counter()
                hybrid_response = hybrid.retrieve(owner, request)
                hybrid_ms = (perf_counter() - started) * 1000
                repeated = hybrid.retrieve(owner, request)
            dense_times.append(dense_ms)
            lexical_times.append(lexical_ms)
            hybrid_times.append(hybrid_ms)
            expected_document_id = source.document_id
            evidence = _matching_evidence(
                hybrid_response,
                document_id=expected_document_id,
                probes=probes,
            )
            exact_locator_hit = any(
                _public_locator_covers(result, fact["locator"]) for result in evidence
            )
            safe_locator_hit = bool(evidence) and all(
                _safe_public_locator_present(result) for result in evidence
            )
            query_rows.append(
                {
                    "document_key": key,
                    "fact_number": fact_number,
                    "question": fact["question"],
                    "expected_answer": fact["answer"],
                    "dense_document_rank": _document_rank(
                        dense_response,
                        expected_document_id,
                    ),
                    "lexical_document_rank": _document_rank(
                        lexical_response,
                        expected_document_id,
                    ),
                    "hybrid_document_rank": _document_rank(
                        hybrid_response,
                        expected_document_id,
                    ),
                    "hybrid_evidence_ranks": [result.final_rank for result in evidence],
                    "hybrid_evidence_hit": bool(evidence),
                    "hybrid_locator_hit": safe_locator_hit,
                    "hybrid_exact_locator_hit": exact_locator_hit,
                    "hybrid_source_locators": [
                        result.source_locator.model_dump(mode="json")
                        for result in evidence
                    ],
                    "deterministic": _response_fingerprint(hybrid_response)
                    == _response_fingerprint(repeated),
                }
            )
    latency = {
        "sample_count": len(query_rows),
        "dense_p50_ms": _percentile(dense_times, 0.50),
        "dense_p95_ms": _percentile(dense_times, 0.95),
        "dense_max_ms": max(dense_times),
        "lexical_p50_ms": _percentile(lexical_times, 0.50),
        "lexical_p95_ms": _percentile(lexical_times, 0.95),
        "lexical_max_ms": max(lexical_times),
        "hybrid_p50_ms": _percentile(hybrid_times, 0.50),
        "hybrid_p95_ms": _percentile(hybrid_times, 0.95),
        "hybrid_max_ms": max(hybrid_times),
        "routing_conclusion": ROUTING_CONCLUSION,
    }
    return query_rows, latency


def _retrieval_services(
    session: Session,
    settings: Settings,
    provider: EmbeddingProvider,
) -> tuple[DenseRetrievalService, LexicalRetrievalService, HybridRetrievalService]:
    repository = RetrievalRepository(
        session,
        statement_timeout_ms=settings.database_statement_timeout_ms,
    )
    dense = DenseRetrievalService(
        repository,
        provider,
        query_max_characters=settings.retrieval_query_max_characters,
        candidate_count=settings.dense_candidate_count,
    )
    lexical = LexicalRetrievalService(
        repository,
        query_max_characters=settings.retrieval_query_max_characters,
        candidate_count=settings.lexical_candidate_count,
    )
    hybrid = HybridRetrievalService(
        dense,
        lexical,
        rrf_k=settings.rrf_k,
        candidate_count=settings.hybrid_candidate_count,
    )
    return dense, lexical, hybrid


def _matching_evidence(
    response: RetrievalResponse,
    *,
    document_id: UUID,
    probes: Sequence[str],
) -> list[RetrievalResult]:
    normalized_probes = [normalize_text(probe) for probe in probes]
    return [
        result
        for result in response.results
        if result.identity.document_id == document_id
        and all(
            probe in normalize_text(result.body_text) for probe in normalized_probes
        )
    ]


def _document_rank(response: RetrievalResponse, document_id: UUID) -> int | None:
    return next(
        (
            result.final_rank
            for result in response.results
            if result.identity.document_id == document_id
        ),
        None,
    )


def _response_fingerprint(response: RetrievalResponse) -> list[dict[str, Any]]:
    return [result.model_dump(mode="json") for result in response.results]


def _public_locator_covers(
    result: RetrievalResult,
    expected: dict[str, Any],
) -> bool:
    actual = result.source_locator.model_dump(mode="json", exclude_none=True)
    page_number = expected.get("page_number")
    if page_number is not None and page_number not in {
        actual.get("page_number"),
        *actual.get("page_numbers", []),
    }:
        return False
    for field in ("heading_path", "paragraph_number", "table_number", "sheet_name"):
        if field in expected and field in actual and actual[field] != expected[field]:
            return False
    expected_range = expected.get("cell_range")
    actual_range = actual.get("cell_range")
    if expected_range is not None and (
        not isinstance(actual_range, str)
        or not _cell_range_contains(actual_range, str(expected_range))
    ):
        return False
    expected_start = expected.get("row_start", expected.get("row_number"))
    expected_end = expected.get("row_end", expected.get("row_number"))
    actual_start = actual.get("row_start")
    actual_end = actual.get("row_end")
    if not (
        isinstance(expected_start, int)
        and isinstance(expected_end, int)
        and isinstance(actual_start, int)
        and isinstance(actual_end, int)
    ):
        return True
    return actual_start <= expected_start and actual_end >= expected_end


def _safe_public_locator_present(result: RetrievalResult) -> bool:
    actual = result.source_locator.model_dump(mode="json")
    forbidden_fields = {
        "storage_key",
        "file_path",
        "tenant_id",
        "source_spans",
        "table_json",
    }
    coordinates = {
        key: value
        for key, value in actual.items()
        if key != "source_type" and value not in (None, [], "")
    }
    return not forbidden_fields.intersection(actual) and bool(coordinates)


def _cell_range_contains(actual: str, expected: str) -> bool:
    actual_box = _cell_range_box(actual)
    expected_box = _cell_range_box(expected)
    if actual_box is None or expected_box is None:
        return False
    return (
        actual_box[0] <= expected_box[0]
        and actual_box[1] <= expected_box[1]
        and actual_box[2] >= expected_box[2]
        and actual_box[3] >= expected_box[3]
    )


def _cell_range_box(value: str) -> tuple[int, int, int, int] | None:
    match = re.fullmatch(
        r"([A-Z]{1,3})([1-9][0-9]*)(?::([A-Z]{1,3})([1-9][0-9]*))?",
        value,
    )
    if match is None:
        return None
    start_column = _column_number(match.group(1))
    start_row = int(match.group(2))
    end_column = _column_number(match.group(3) or match.group(1))
    end_row = int(match.group(4) or match.group(2))
    return start_column, start_row, end_column, end_row


def _column_number(label: str) -> int:
    value = 0
    for character in label:
        value = value * 26 + ord(character) - ord("A") + 1
    return value


def _aggregate_queries(rows: Sequence[dict[str, Any]]) -> dict[str, int]:
    return {
        "questions_total": len(rows),
        "dense_document_hits": sum(
            row["dense_document_rank"] is not None for row in rows
        ),
        "lexical_document_hits": sum(
            row["lexical_document_rank"] is not None for row in rows
        ),
        "hybrid_document_hits": sum(
            row["hybrid_document_rank"] is not None for row in rows
        ),
        "hybrid_evidence_hits": sum(row["hybrid_evidence_hit"] is True for row in rows),
        "hybrid_locator_hits": sum(row["hybrid_locator_hit"] is True for row in rows),
        "hybrid_exact_locator_hits": sum(
            row["hybrid_exact_locator_hit"] is True for row in rows
        ),
        "deterministic_queries": sum(row["deterministic"] is True for row in rows),
        "known_unretrievable_facts": sum(
            row["hybrid_evidence_hit"] is False for row in rows
        ),
    }


def _run_security_matrix(
    session_factory: sessionmaker[Session],
    *,
    owner: CurrentUser,
    sources: Sequence[tuple[str, GeneratedSource]],
    results: dict[str, DocumentIndexResult],
) -> dict[str, bool]:
    source_by_key = {
        str(source.definition["key"]): source for _corpus, source in sources
    }
    de_user = _load_named_user(session_factory, "de.operator@demo.deepsearch.local")
    fr_user = _load_named_user(session_factory, "fr.operator@demo.deepsearch.local")
    scout = _load_named_user(session_factory, "scout@demo.deepsearch.local")
    owner_ids = _authorized_document_ids(session_factory, owner)
    de_ids = _authorized_document_ids(session_factory, de_user)
    fr_ids = _authorized_document_ids(session_factory, fr_user)
    scout_ids = _authorized_document_ids(session_factory, scout)
    compliance_id = source_by_key["de_compliance_checklist"].document_id
    supplier_id = source_by_key["supplier_quotes"].document_id
    target = source_by_key["mushroom_lamp_manual"]
    target_result = results["mushroom_lamp_manual"]
    return {
        "owner_can_access_all": len(owner_ids) == 10,
        "de_market_acl_allowed": compliance_id in de_ids,
        "fr_market_mismatch_denied": compliance_id not in fr_ids,
        "role_acl_allowed": supplier_id in scout_ids,
        "role_acl_mismatch_denied": supplier_id not in de_ids,
        "inactive_version_denied": _mutation_hides_document(
            session_factory,
            owner,
            target.document_id,
            Document,
            "active_version_id",
            None,
            target.version_id,
        ),
        "inactive_index_set_denied": _mutation_hides_document(
            session_factory,
            owner,
            target.document_id,
            DocumentVersion,
            "active_index_set_id",
            None,
            target_result.index_set_id,
            row_id=target.version_id,
        ),
        "soft_deleted_document_denied": _mutation_hides_document(
            session_factory,
            owner,
            target.document_id,
            Document,
            "deleted_at",
            datetime.now(UTC),
            None,
        ),
        "soft_deleted_file_denied": _soft_deleted_file_hides_document(
            session_factory,
            owner,
            target,
        ),
    }


def _authorized_document_ids(
    session_factory: sessionmaker[Session],
    user: CurrentUser,
) -> set[UUID]:
    with session_factory() as session:
        statement = (
            RetrievalRepository(session)
            .authorized_active_chunks_statement(user)
            .with_only_columns(Document.id)
            .distinct()
        )
        return set(session.scalars(statement))


def _mutation_hides_document(
    session_factory: sessionmaker[Session],
    user: CurrentUser,
    document_id: UUID,
    model: type[Document | DocumentVersion],
    field: str,
    hidden_value: object,
    restored_value: object,
    *,
    row_id: UUID | None = None,
) -> bool:
    target_id = row_id or document_id
    try:
        with session_factory.begin() as session:
            session.execute(
                update(model).where(model.id == target_id).values({field: hidden_value})
            )
        return document_id not in _authorized_document_ids(session_factory, user)
    finally:
        with session_factory.begin() as session:
            session.execute(
                update(model)
                .where(model.id == target_id)
                .values({field: restored_value})
            )


def _soft_deleted_file_hides_document(
    session_factory: sessionmaker[Session],
    user: CurrentUser,
    source: GeneratedSource,
) -> bool:
    try:
        with session_factory.begin() as session:
            session.execute(
                update(StoredFile)
                .where(StoredFile.id == source.file_id)
                .values(status="soft_deleted", deleted_at=datetime.now(UTC))
            )
        return source.document_id not in _authorized_document_ids(
            session_factory,
            user,
        )
    finally:
        with session_factory.begin() as session:
            session.execute(
                update(StoredFile)
                .where(StoredFile.id == source.file_id)
                .values(status="ready", deleted_at=None)
            )


def _load_named_user(
    session_factory: sessionmaker[Session],
    email: str,
) -> CurrentUser:
    definitions = load_m1_seed_definition()
    definition = next(user for user in definitions["users"] if user["email"] == email)
    with session_factory() as session:
        tenant = session.scalar(
            select(Tenant).where(Tenant.name == definitions["tenant"]["name"])
        )
        if tenant is None:
            raise RuntimeError("Formal tenant is missing")
        user = session.scalar(
            select(User).where(User.tenant_id == tenant.id, User.email == email)
        )
        if user is None:
            raise RuntimeError("Formal user is missing")
        return CurrentUser(
            user_id=user.id,
            tenant_id=tenant.id,
            email=user.email,
            display_name=user.display_name,
            roles=[definition["role"]],
            market_scopes=definition["market_scopes"],
            synthetic_data=True,
        )


def _explain_retrieval_indexes(runtime: DatabaseRuntime) -> dict[str, Any]:
    vector_text = "[" + ",".join(["1"] + ["0"] * 1023) + "]"
    with runtime.session_factory() as session:
        session.execute(text("SET LOCAL enable_seqscan = off"))
        gin_plan = list(
            session.scalars(
                text(
                    "EXPLAIN SELECT id FROM document_chunks "
                    "WHERE search_vector @@ to_tsquery('simple', :query)"
                ),
                {"query": "亮度"},
            )
        )
        hnsw_plan = list(
            session.scalars(
                text(
                    "EXPLAIN SELECT id FROM document_chunks "
                    "WHERE embedding IS NOT NULL "
                    "ORDER BY embedding <=> CAST(:query_vector AS vector) LIMIT 5"
                ),
                {"query_vector": vector_text},
            )
        )
    return {
        "gin_available": any(
            "ix_document_chunks_search_vector_gin" in line for line in gin_plan
        ),
        "hnsw_available": any(
            "ix_document_chunks_embedding_hnsw_cosine" in line for line in hnsw_plan
        ),
        "gin_plan": gin_plan,
        "hnsw_plan": hnsw_plan,
    }


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--bge-smoke", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.bge_smoke:
            settings = Settings(  # type: ignore[call-arg]
                embedding_backend="bge",
                embedding_model=BGE_M3_MODEL_ID,
                embedding_revision=BGE_M3_REVISION,
                model_local_files_only=True,
                docling_backend="disabled",
            )
            report = run_bge_retrieval_smoke(settings)
            passed = report["decision"]["bge_retrieval_smoke_passed"]
        else:
            report = run_fake_retrieval_verification(Settings())
            passed = report["decision"]["m2_16_complete"]
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001 - CLI must not expose paths or raw internals.
        print("M2检索验收失败；请检查正式Seed、本地模型缓存和安全状态")
        return 1
    print(json.dumps(report.get("retrieval", {}), ensure_ascii=False, indent=2))
    print(json.dumps(report["cleanup"], ensure_ascii=False, indent=2))
    print(f"report={output}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
