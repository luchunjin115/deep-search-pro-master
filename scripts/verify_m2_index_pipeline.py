"""Verify M2 indexing with Fake/BGE providers and restore the formal Seed."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import BGE_M3_MODEL_ID, BGE_M3_REVISION, Settings
from app.core.errors import DocumentIndexingError, EmbeddingProviderError
from app.db.session import DatabaseRuntime, create_database_runtime
from app.models.identity import Tenant, User
from app.models.knowledge import (
    Document,
    DocumentAcl,
    DocumentChunk,
    DocumentChunkSet,
    DocumentIndexSet,
    DocumentVersion,
    StoredFile,
)
from app.schemas.auth import CurrentUser
from app.services.documents.chunking import CanonicalChunkArtifact
from app.services.documents.indexing.service import (
    DocumentIndexResult,
    DocumentIndexService,
)
from app.services.retrieval import (
    BgeM3EmbeddingProvider,
    FakeEmbeddingProvider,
    create_embedding_provider,
)
from app.services.storage import LocalStorageBackend
from scripts.benchmark_m2_docling import verify_model_cache
from scripts.benchmark_m2_embedding import ensure_bge_snapshot
from scripts.seed_m1 import load_seed_definition as load_m1_seed_definition
from scripts.seed_m2_complex_files import (
    generate_complex_sources,
    load_complex_seed_definition,
    seed_m2_complex_files,
)
from scripts.seed_m2_files import (
    GeneratedSource,
    generate_sources,
    load_seed_definition,
    seed_m2_files,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "output" / "m2_index_pipeline_report.json"

REPORT_SCHEMA_VERSION = "m2-index-pipeline-report-v1"
BGE_SMOKE_SCHEMA_VERSION = "m2-index-bge-smoke-v1"

EXPECTED_FORMAL_CHUNK_COUNTS: dict[str, int] = {
    "mushroom_lamp_manual": 7,
    "quality_inspection_sop": 6,
    "de_compliance_checklist": 5,
    "supplier_quotes": 2,
    "monthly_operations": 1,
    "scanned_receiving_ticket": 2,
    "two_column_market_brief": 4,
    "merged_header_cost_table": 2,
    "visual_quality_notice": 4,
    "multi_region_replenishment": 2,
}


class FailOnceCountingFakeEmbeddingProvider(FakeEmbeddingProvider):
    """Fail the first real batch, then behave like the deterministic Fake."""

    def __init__(self) -> None:
        super().__init__()
        self.call_count = 0

    def embed(self, texts, *, purpose):  # type: ignore[no-untyped-def]
        self.call_count += 1
        if self.call_count == 1:
            raise EmbeddingProviderError(retryable=True)
        return super().embed(texts, purpose=purpose)


def fake_index_pipeline_complete(report: dict[str, Any]) -> bool:
    """Return whether every reviewed Fake pipeline and cleanup gate passed."""

    aggregate = report.get("aggregate", {})
    cleanup = report.get("cleanup", {})
    provider = report.get("provider", {})
    counts = cleanup.get("database_counts", {})
    return bool(
        report.get("schema_version") == REPORT_SCHEMA_VERSION
        and provider.get("model_id") == "fake/m2-deterministic"
        and provider.get("revision") == "m2-fake-v1"
        and aggregate.get("documents_total") == 10
        and aggregate.get("documents_ready") == 10
        and aggregate.get("chunk_count") == 35
        and aggregate.get("text_chunk_count") == 27
        and aggregate.get("table_chunk_count") == 8
        and aggregate.get("embedding_count") == 35
        and aggregate.get("fts_count") == 35
        and aggregate.get("row_audits_passed") == 10
        and aggregate.get("repeat_reused") == 10
        and aggregate.get("index_set_count_after_repeat") == 10
        and aggregate.get("chunk_count_after_repeat") == 35
        and aggregate.get("failure_recorded") is True
        and aggregate.get("failure_retry_succeeded") is True
        and aggregate.get("retried_attempt_count") == 2
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


def bge_index_smoke_complete(report: dict[str, Any]) -> bool:
    """Return whether the pinned real BGE index and cleanup gates passed."""

    model = report.get("model", {})
    index = report.get("index", {})
    cleanup = report.get("cleanup", {})
    chunk_count = index.get("chunk_count")
    return bool(
        report.get("schema_version") == BGE_SMOKE_SCHEMA_VERSION
        and model.get("model_id") == BGE_M3_MODEL_ID
        and model.get("revision") == BGE_M3_REVISION
        and model.get("dimensions") == 1024
        and index.get("status") == "ready"
        and isinstance(chunk_count, int)
        and chunk_count > 0
        and index.get("embedding_count") == chunk_count
        and index.get("reused") is True
        and index.get("same_index_set") is True
        and cleanup.get("baseline_restored") is True
    )


def run_fake_index_pipeline_verification(settings: Settings) -> dict[str, Any]:
    """Index all ten formal documents with Fake, audit, repeat, and restore."""

    if settings.embedding_backend != "fake":
        raise RuntimeError("M2-15.6 Fake verification requires EMBEDDING_BACKEND=fake")
    if settings.docling_backend != "docling" or settings.docling_device != "cpu":
        raise RuntimeError("M2-15.6 formal verification requires local CPU Docling")
    _force_offline_mode()
    model_manifest = verify_model_cache(settings.docling_model_cache_root.resolve())
    storage, sources, ordinary_data = _prepare_formal_seed(settings)
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
        user = _load_owner(runtime.session_factory, ordinary_data)
        provider = FailOnceCountingFakeEmbeddingProvider()
        service = DocumentIndexService(
            runtime.session_factory,
            storage,
            settings,
            provider,
        )
        first_source = sources[0][1]
        failure_recorded = _run_expected_first_failure(
            runtime,
            service,
            user,
            first_source,
        )

        results: dict[str, DocumentIndexResult] = {}
        documents: list[dict[str, Any]] = []
        for corpus, source in sources:
            result = service.index_version(
                user,
                document_id=source.document_id,
                version_id=source.version_id,
            )
            key = str(source.definition["key"])
            results[key] = result
            documents.append(
                _audit_ready_document(
                    runtime,
                    storage,
                    corpus=corpus,
                    source=source,
                    result=result,
                )
            )

        calls_before_repeat = provider.call_count
        repeats = [
            service.index_version(
                user,
                document_id=source.document_id,
                version_id=source.version_id,
            )
            for _corpus, source in sources
        ]
        counts_after_repeat = _index_counts(runtime, version_ids)
        first_ready = _load_index_set(
            runtime,
            results[str(first_source.definition["key"])].index_set_id,
        )
        aggregate = {
            "documents_total": len(documents),
            "documents_ready": sum(
                document["database_ready"] is True for document in documents
            ),
            "chunk_count": sum(document["chunk_count"] for document in documents),
            "text_chunk_count": sum(
                document["text_chunk_count"] for document in documents
            ),
            "table_chunk_count": sum(
                document["table_chunk_count"] for document in documents
            ),
            "embedding_count": sum(
                document["embedding_count"] for document in documents
            ),
            "fts_count": sum(document["fts_count"] for document in documents),
            "row_audits_passed": sum(
                document["row_audit_passed"] is True for document in documents
            ),
            "repeat_reused": sum(result.reused is True for result in repeats),
            "index_set_count_after_repeat": counts_after_repeat["index_sets"],
            "chunk_count_after_repeat": counts_after_repeat["chunks"],
            "failure_recorded": failure_recorded,
            "failure_retry_succeeded": bool(
                first_ready is not None and first_ready.status == "ready"
            ),
            "retried_attempt_count": (
                first_ready.attempt_count if first_ready is not None else None
            ),
            "provider_calls_before_repeat": calls_before_repeat,
            "provider_calls_after_repeat": provider.call_count,
        }
        report = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "corpora": [
                load_seed_definition()["version"],
                load_complex_seed_definition()["version"],
            ],
            "synthetic_data": True,
            "offline_inference": True,
            "docling_model_manifest": model_manifest,
            "provider": {
                "model_id": provider.identity.model_id,
                "revision": provider.identity.revision,
                "dimensions": provider.identity.dimensions,
            },
            "documents": documents,
            "aggregate": aggregate,
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
    report["decision"] = {"m2_15_complete": fake_index_pipeline_complete(report)}
    return report


def run_bge_index_smoke(settings: Settings) -> dict[str, Any]:
    """Index one native formal PDF with the pinned local BGE snapshot and restore."""

    if settings.embedding_backend != "bge":
        raise RuntimeError("M2-15.6 BGE Smoke requires EMBEDDING_BACKEND=bge")
    if (
        settings.embedding_model != BGE_M3_MODEL_ID
        or settings.embedding_revision != BGE_M3_REVISION
        or not settings.model_local_files_only
    ):
        raise RuntimeError("M2-15.6 BGE Smoke requires the pinned offline identity")
    _force_offline_mode()
    snapshot = ensure_bge_snapshot(settings.model_cache_root, allow_download=False)
    provider = create_embedding_provider(settings)
    if not isinstance(provider, BgeM3EmbeddingProvider):
        raise TypeError("Configured BGE provider was not created")

    storage, sources, ordinary_data = _prepare_formal_seed(settings)
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
        user = _load_owner(runtime.session_factory, ordinary_data)
        service = DocumentIndexService(
            runtime.session_factory,
            storage,
            settings,
            provider,
        )
        first = service.index_version(
            user,
            document_id=target.document_id,
            version_id=target.version_id,
        )
        repeated = service.index_version(
            user,
            document_id=target.document_id,
            version_id=target.version_id,
        )
        with runtime.session_factory() as session:
            embedding_count = session.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .where(
                    DocumentChunk.document_index_set_id == first.index_set_id,
                    DocumentChunk.embedding.is_not(None),
                )
            )
            models = set(
                session.execute(
                    select(
                        DocumentChunk.embedding_model,
                        DocumentChunk.embedding_version,
                    ).where(DocumentChunk.document_index_set_id == first.index_set_id)
                ).all()
            )
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
                "status": first.status,
                "chunk_count": first.chunk_count,
                "embedding_count": embedding_count,
                "reused": repeated.reused,
                "same_index_set": first.index_set_id == repeated.index_set_id,
                "database_identities": [list(item) for item in sorted(models)],
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
    report["decision"] = {"bge_index_smoke_passed": bge_index_smoke_complete(report)}
    return report


def _force_offline_mode() -> None:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"


def _prepare_formal_seed(
    settings: Settings,
) -> tuple[
    LocalStorageBackend,
    list[tuple[str, GeneratedSource]],
    dict[str, Any],
]:
    storage = LocalStorageBackend(
        settings.local_storage_root,
        chunk_size_bytes=settings.upload_stream_chunk_size_bytes,
    )
    ordinary_data = load_seed_definition()
    complex_data = load_complex_seed_definition()
    seed_m2_files(settings, storage=storage)
    seed_m2_complex_files(settings, storage=storage)
    sources = [
        (str(ordinary_data["version"]), source)
        for source in generate_sources(ordinary_data)
    ] + [
        (str(complex_data["version"]), source)
        for source in generate_complex_sources(complex_data)
    ]
    return storage, sources, ordinary_data


def _load_owner(
    session_factory: sessionmaker[Session],
    data: dict[str, Any],
) -> CurrentUser:
    m1_data = load_m1_seed_definition()
    owner_definition = next(
        user for user in m1_data["users"] if user["email"] == data["owner_email"]
    )
    with session_factory() as session:
        tenant = session.scalar(
            select(Tenant).where(Tenant.name == data["tenant_name"])
        )
        if tenant is None:
            raise RuntimeError("Formal M2 tenant is missing")
        owner = session.scalar(
            select(User).where(
                User.tenant_id == tenant.id,
                User.email == data["owner_email"],
            )
        )
        if owner is None:
            raise RuntimeError("Formal M2 owner is missing")
        return CurrentUser(
            user_id=owner.id,
            tenant_id=tenant.id,
            email=owner.email,
            display_name=owner.display_name,
            roles=[owner_definition["role"]],
            market_scopes=owner_definition["market_scopes"],
            synthetic_data=True,
        )


def _require_clean_formal_baseline(
    session_factory: sessionmaker[Session],
    *,
    version_ids: Sequence[UUID],
    file_ids: Sequence[UUID],
    expected_document_count: int,
) -> None:
    with session_factory() as session:
        versions = list(
            session.scalars(
                select(DocumentVersion).where(DocumentVersion.id.in_(version_ids))
            )
        )
        files = list(
            session.scalars(select(StoredFile).where(StoredFile.id.in_(file_ids)))
        )
        counts = _index_counts_from_session(session, version_ids)
        active_documents = session.scalar(
            select(func.count())
            .select_from(Document)
            .where(
                Document.id.in_(
                    select(DocumentVersion.document_id).where(
                        DocumentVersion.id.in_(version_ids)
                    )
                ),
                Document.active_version_id.is_not(None),
            )
        )
    clean = bool(
        len(versions) == expected_document_count
        and len(files) == expected_document_count
        and all(
            version.parse_status == "pending"
            and version.index_status == "pending"
            and version.parser_name is None
            and version.parser_version is None
            and version.parsed_storage_key is None
            and version.active_index_set_id is None
            for version in versions
        )
        and all(
            file.status == "uploaded"
            and file.deleted_at is None
            and file.error_message is None
            for file in files
        )
        and counts == {"chunk_sets": 0, "index_sets": 0, "chunks": 0}
        and active_documents == 0
    )
    if not clean:
        raise RuntimeError("Formal M2 Seed is not at the clean pending index baseline")


def _run_expected_first_failure(
    runtime: DatabaseRuntime,
    service: DocumentIndexService,
    user: CurrentUser,
    source: GeneratedSource,
) -> bool:
    try:
        service.index_version(
            user,
            document_id=source.document_id,
            version_id=source.version_id,
        )
    except DocumentIndexingError:
        pass
    else:
        return False
    with runtime.session_factory() as session:
        failed = session.scalar(
            select(DocumentIndexSet).where(
                DocumentIndexSet.document_version_id == source.version_id
            )
        )
        chunk_count = session.scalar(
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.document_version_id == source.version_id)
        )
        return bool(
            failed is not None
            and failed.status == "failed"
            and failed.attempt_count == 1
            and chunk_count == 0
        )


def _audit_ready_document(
    runtime: DatabaseRuntime,
    storage: LocalStorageBackend,
    *,
    corpus: str,
    source: GeneratedSource,
    result: DocumentIndexResult,
) -> dict[str, Any]:
    key = str(source.definition["key"])
    expected_count = EXPECTED_FORMAL_CHUNK_COUNTS[key]
    with runtime.session_factory() as session:
        document = session.get(Document, source.document_id)
        version = session.get(DocumentVersion, source.version_id)
        file_row = session.get(StoredFile, source.file_id)
        chunk_set = session.get(DocumentChunkSet, result.chunk_set_id)
        index_set = session.get(DocumentIndexSet, result.index_set_id)
        rows = list(
            session.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_index_set_id == result.index_set_id)
                .order_by(DocumentChunk.chunk_index)
            )
        )
        fts_count = session.scalar(
            select(func.count())
            .select_from(DocumentChunk)
            .where(
                DocumentChunk.document_index_set_id == result.index_set_id,
                DocumentChunk.search_vector.is_not(None),
            )
        )
        if chunk_set is None or chunk_set.chunk_storage_key is None:
            raise RuntimeError(f"Chunk publication is missing for {key}")
        chunk_key = chunk_set.chunk_storage_key
        session.expunge(chunk_set)
        if index_set is not None:
            session.expunge(index_set)

    with storage.open(chunk_key) as stream:
        artifact = CanonicalChunkArtifact.model_validate_json(stream.read())
    row_checks = [
        _row_matches_artifact(row, artifact.chunks[position], result)
        for position, row in enumerate(rows)
    ]
    database_ready = bool(
        document is not None
        and document.active_version_id == source.version_id
        and version is not None
        and version.parse_status == "ready"
        and version.index_status == "ready"
        and version.active_index_set_id == result.index_set_id
        and file_row is not None
        and file_row.status == "ready"
        and index_set is not None
        and index_set.status == "ready"
    )
    row_audit_passed = bool(
        len(rows) == expected_count
        and len(artifact.chunks) == expected_count
        and all(row_checks)
        and fts_count == expected_count
        and index_set is not None
        and index_set.chunk_count == expected_count
        and index_set.text_chunk_count == artifact.statistics.text_chunk_count
        and index_set.table_chunk_count == artifact.statistics.table_chunk_count
        and index_set.total_token_count == artifact.statistics.total_token_count
    )
    return {
        "corpus_version": corpus,
        "key": key,
        "document_id": str(source.document_id),
        "version_id": str(source.version_id),
        "chunk_set_id": str(result.chunk_set_id),
        "index_set_id": str(result.index_set_id),
        "chunk_count": len(rows),
        "text_chunk_count": sum(row.kind == "text" for row in rows),
        "table_chunk_count": sum(row.kind == "table" for row in rows),
        "embedding_count": sum(row.embedding is not None for row in rows),
        "fts_count": fts_count,
        "database_ready": database_ready,
        "row_audit_passed": row_audit_passed,
    }


def _row_matches_artifact(
    row: DocumentChunk,
    chunk: Any,
    result: DocumentIndexResult,
) -> bool:
    payload = chunk.model_dump(mode="json")
    embedding = row.embedding
    return bool(
        row.document_id == result.document_id
        and row.document_version_id == result.version_id
        and row.document_chunk_set_id == result.chunk_set_id
        and row.document_index_set_id == result.index_set_id
        and row.chunk_id == chunk.chunk_id
        and row.chunk_index == chunk.chunk_index
        and row.kind == chunk.kind
        and row.body_text == chunk.body_text
        and row.retrieval_text == chunk.retrieval_text
        and row.fts_text == chunk.retrieval_text
        and row.token_count == chunk.token_count
        and row.content_sha256 == chunk.content_sha256
        and row.heading_path == chunk.heading_path
        and row.page_numbers == chunk.page_numbers
        and row.source_block_ids == chunk.source_block_ids
        and row.source_spans == payload["source_spans"]
        and row.bounding_boxes == payload["bounding_boxes"]
        and row.overlap_json == payload["overlap"]
        and row.table_json == payload["table"]
        and row.warnings == chunk.warnings
        and embedding is not None
        and len(embedding) == 1024
        and row.embedding_model == result.embedding_model
        and row.embedding_version == result.embedding_version
        and row.embedding_cache_key.startswith("sha256:")
    )


def _load_index_set(
    runtime: DatabaseRuntime,
    index_set_id: UUID,
) -> DocumentIndexSet | None:
    with runtime.session_factory() as session:
        row = session.get(DocumentIndexSet, index_set_id)
        if row is not None:
            session.expunge(row)
        return row


def _index_counts(
    runtime: DatabaseRuntime,
    version_ids: Sequence[UUID],
) -> dict[str, int]:
    with runtime.session_factory() as session:
        return _index_counts_from_session(session, version_ids)


def _index_counts_from_session(
    session: Session,
    version_ids: Sequence[UUID],
) -> dict[str, int]:
    return {
        "chunk_sets": session.scalar(
            select(func.count())
            .select_from(DocumentChunkSet)
            .where(DocumentChunkSet.document_version_id.in_(version_ids))
        )
        or 0,
        "index_sets": session.scalar(
            select(func.count())
            .select_from(DocumentIndexSet)
            .where(DocumentIndexSet.document_version_id.in_(version_ids))
        )
        or 0,
        "chunks": session.scalar(
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.document_version_id.in_(version_ids))
        )
        or 0,
    }


def _restore_formal_baseline(
    session_factory: sessionmaker[Session],
    storage: LocalStorageBackend,
    *,
    version_ids: Sequence[UUID],
    file_ids: Sequence[UUID],
    document_ids: Sequence[UUID],
) -> dict[str, Any]:
    keys: set[str] = set()
    with session_factory() as session:
        keys.update(
            key
            for key in session.scalars(
                select(DocumentVersion.parsed_storage_key).where(
                    DocumentVersion.id.in_(version_ids),
                    DocumentVersion.parsed_storage_key.is_not(None),
                )
            )
            if key is not None
        )
        keys.update(
            key
            for key in session.scalars(
                select(DocumentChunkSet.chunk_storage_key).where(
                    DocumentChunkSet.document_version_id.in_(version_ids),
                    DocumentChunkSet.chunk_storage_key.is_not(None),
                )
            )
            if key is not None
        )

    deleted_keys: list[str] = []
    for key in sorted(keys):
        storage.delete(key)
        deleted_keys.append(key)

    with session_factory.begin() as session:
        session.execute(
            update(Document)
            .where(Document.id.in_(document_ids))
            .values(active_version_id=None)
        )
        session.execute(
            update(DocumentVersion)
            .where(DocumentVersion.id.in_(version_ids))
            .values(active_index_set_id=None)
        )
        session.execute(
            delete(DocumentIndexSet).where(
                DocumentIndexSet.document_version_id.in_(version_ids)
            )
        )
        session.execute(
            delete(DocumentChunkSet).where(
                DocumentChunkSet.document_version_id.in_(version_ids)
            )
        )
        session.execute(
            update(DocumentVersion)
            .where(DocumentVersion.id.in_(version_ids))
            .values(
                parser_name=None,
                parser_version=None,
                parsed_storage_key=None,
                parse_status="pending",
                index_status="pending",
                active_index_set_id=None,
            )
        )
        session.execute(
            update(StoredFile)
            .where(StoredFile.id.in_(file_ids))
            .values(status="uploaded", error_message=None, deleted_at=None)
        )

    with session_factory() as session:
        counts = {
            "files": session.scalar(select(func.count()).select_from(StoredFile)),
            "documents": session.scalar(select(func.count()).select_from(Document)),
            "versions": session.scalar(
                select(func.count()).select_from(DocumentVersion)
            ),
            "acl": session.scalar(select(func.count()).select_from(DocumentAcl)),
            "chunk_sets": session.scalar(
                select(func.count()).select_from(DocumentChunkSet)
            ),
            "index_sets": session.scalar(
                select(func.count()).select_from(DocumentIndexSet)
            ),
            "chunks": session.scalar(select(func.count()).select_from(DocumentChunk)),
            "embeddings": session.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .where(DocumentChunk.embedding.is_not(None))
            ),
        }
        versions = list(
            session.scalars(
                select(DocumentVersion).where(DocumentVersion.id.in_(version_ids))
            )
        )
        files = list(
            session.scalars(select(StoredFile).where(StoredFile.id.in_(file_ids)))
        )
        active_documents = session.scalar(
            select(func.count())
            .select_from(Document)
            .where(Document.active_version_id.is_not(None))
        )
    remaining_keys = [key for key in deleted_keys if storage.exists(key)]
    baseline_restored = bool(
        counts
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
        and len(versions) == len(version_ids)
        and all(
            version.parse_status == "pending"
            and version.index_status == "pending"
            and version.parsed_storage_key is None
            and version.active_index_set_id is None
            for version in versions
        )
        and len(files) == len(file_ids)
        and all(file.status == "uploaded" for file in files)
        and active_documents == 0
        and not remaining_keys
    )
    return {
        "deleted_publication_count": len(deleted_keys),
        "remaining_publication_keys": remaining_keys,
        "database_counts": counts,
        "baseline_restored": baseline_restored,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = run_fake_index_pipeline_verification(Settings())
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001 - CLI must not expose internal paths/details.
        print("M2索引验收失败；请检查正式Seed、本地模型缓存和安全状态")
        return 1
    print(json.dumps(report["aggregate"], ensure_ascii=False, indent=2))
    print(json.dumps(report["cleanup"], ensure_ascii=False, indent=2))
    print(f"report={output}")
    return 0 if report["decision"]["m2_15_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
