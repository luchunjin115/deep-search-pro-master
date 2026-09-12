"""Idempotent preparation of the frozen M2-22.7 retrieval corpus."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import and_, delete, func, select, update

from app.core.config import Settings
from app.db.session import DatabaseRuntime, create_database_runtime
from app.evals.rag_runner import (
    DEFAULT_DATASET_PATH,
    DEFAULT_SOURCE_MANIFEST_PATH,
    PROJECT_ROOT,
    _chunk_formal_baseline,
    _ChunkFormalBaseline,
    _cleanup_chunk_evaluation,
    _create_evaluation_identity,
    _EvaluationSourceInput,
    _ingest_chunk_source,
    _load_cases,
    _load_evaluation_sources,
    _load_source_manifest,
    _login_evaluation_owner,
    _ParsedEvaluationSource,
    _read_routed_artifact,
)
from app.evals.retrieval_runner import (
    FrozenChunkCandidate,
    _build_evidence_map,
    _evaluation_users,
    _materialize_source_acls,
    _settings_for_chunk,
    build_frozen_chunk_candidates,
)
from app.main import create_app
from app.models.identity import Tenant
from app.models.knowledge import (
    Document,
    DocumentChunk,
    DocumentChunkSet,
    DocumentIndexSet,
    DocumentVersion,
    StoredFile,
)
from app.schemas.auth import CurrentUser
from app.schemas.evaluation import EvaluationCase
from app.services.documents.chunking.contracts import ChunkingConfig
from app.services.documents.indexing.service import DocumentIndexService
from app.services.documents.parser_service import DocumentParserService
from app.services.documents.parsers.docling import DoclingProvider, LocalDoclingProvider
from app.services.retrieval import EmbeddingProvider, create_embedding_provider
from app.services.retrieval.lexical_text import FTS_BUILDER_VERSION
from app.services.storage import LocalStorageBackend, StorageBackend

FROZEN_CORPUS_CONTRACT_VERSION = "m2-reranker-context-corpus-v1"
FROZEN_CHUNK_CONFIG_ID = "chunk-compact-overlap-100"
_TENANT_LABEL = "M2-22.7 Frozen RAG Corpus"


@dataclass(frozen=True, slots=True)
class FrozenRagCorpusSnapshot:
    """Private identity of one reusable corpus; no source text is serialized."""

    corpus_sha256: str
    index_sha256: str
    snapshot_sha256: str
    tenant_id: UUID
    owner: CurrentUser
    created: bool
    source_count: int
    document_count: int
    chunk_set_count: int
    index_set_count: int
    chunk_count: int
    document_ids: tuple[UUID, ...]
    chunk_set_ids: tuple[UUID, ...]
    index_set_ids: tuple[UUID, ...]
    chunk_ids: tuple[UUID, ...]
    logical_document_ids: Mapping[UUID, str]


@dataclass(frozen=True, slots=True)
class FrozenChunkCorpusIdentity:
    """Read-only identity of retained Documents and ChunkSets before indexing."""

    corpus_sha256: str
    document_ids: tuple[UUID, ...]
    chunk_set_ids: tuple[UUID, ...]
    chunk_count: int


@dataclass(frozen=True, slots=True)
class _CorpusIdentity:
    sha256: str
    run_id: str
    tenant_name: str


def ensure_m2_reranker_context_corpus(
    settings: Settings,
    *,
    project_root: Path,
    source_ids: set[str] | None = None,
    storage: StorageBackend | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    docling_provider: DoclingProvider | None = None,
) -> FrozenRagCorpusSnapshot:
    """Create the selected corpus once, then validate and reuse it unchanged."""

    resolved_storage = storage or LocalStorageBackend(
        settings.local_storage_root,
        chunk_size_bytes=settings.upload_stream_chunk_size_bytes,
    )
    runtime = create_database_runtime(settings)
    provider = embedding_provider or create_embedding_provider(settings)
    dataset_path = project_root / DEFAULT_DATASET_PATH.relative_to(PROJECT_ROOT)
    manifest_path = project_root / DEFAULT_SOURCE_MANIFEST_PATH.relative_to(
        PROJECT_ROOT
    )
    cases = _load_cases(dataset_path)
    manifest = _load_source_manifest(manifest_path)
    sources = _load_evaluation_sources(
        project_root=project_root,
        manifest=manifest,
        source_ids=source_ids,
    )
    candidate = _selected_chunk_candidate()
    corpus_identity = _corpus_identity(
        cases=cases,
        manifest_sha256=manifest.canonical_sha256(),
        sources=sources,
        candidate=candidate,
    )
    baseline_before = _chunk_formal_baseline(runtime, resolved_storage)
    tenant_id: UUID | None = None
    try:
        with runtime.session_factory() as session:
            existing_tenant_ids = tuple(
                session.scalars(
                    select(Tenant.id).where(Tenant.name == corpus_identity.tenant_name)
                )
            )
        if len(existing_tenant_ids) > 1:
            raise RuntimeError("frozen corpus identity matched multiple tenants")
        if existing_tenant_ids:
            owner = _evaluation_users(
                runtime,
                tenant_id=existing_tenant_ids[0],
                run_id=corpus_identity.run_id,
            )["user-fixture-company-owner"]
            _ensure_index_generation(
                runtime=runtime,
                storage=resolved_storage,
                settings=settings,
                provider=provider,
                owner=owner,
                tenant_id=existing_tenant_ids[0],
                sources=sources,
                candidate=candidate,
            )
            return _snapshot(
                runtime=runtime,
                settings=settings,
                tenant_id=existing_tenant_ids[0],
                corpus_identity=corpus_identity,
                sources=sources,
                candidate=candidate,
                provider=provider,
                created=False,
            )

        tenant_id, email = _create_evaluation_identity(
            runtime,
            corpus_identity.run_id,
            tenant_label=f"{_TENANT_LABEL} {corpus_identity.sha256[:24]}",
        )
        application = create_app(settings, runtime, resolved_storage)
        selected_docling = docling_provider
        if selected_docling is None and settings.docling_backend == "docling":
            selected_docling = LocalDoclingProvider(settings)
        parser = DocumentParserService(
            runtime.session_factory,
            resolved_storage,
            settings,
            docling_provider=selected_docling,
        )
        with TestClient(application) as client:
            token, owner = _login_evaluation_owner(client, email)
            headers = {"Authorization": f"Bearer {token}"}
            parsed_sources = tuple(
                _ingest_chunk_source(
                    client=client,
                    headers=headers,
                    user=owner,
                    parser=parser,
                    runtime=runtime,
                    storage=resolved_storage,
                    source=source,
                )
                for source in sources
            )
        _materialize_source_acls(
            runtime,
            tenant_id=tenant_id,
            parsed_sources=parsed_sources,
        )
        _ensure_index_generation(
            runtime=runtime,
            storage=resolved_storage,
            settings=settings,
            provider=provider,
            owner=owner,
            tenant_id=tenant_id,
            sources=sources,
            candidate=candidate,
        )
        return _snapshot(
            runtime=runtime,
            settings=settings,
            tenant_id=tenant_id,
            corpus_identity=corpus_identity,
            sources=sources,
            candidate=candidate,
            provider=provider,
            created=True,
        )
    except Exception:
        if tenant_id is not None:
            _cleanup_incomplete_corpus(
                runtime=runtime,
                storage=resolved_storage,
                tenant_id=tenant_id,
                baseline_before=baseline_before,
            )
        raise
    finally:
        runtime.engine.dispose()


def load_existing_m2_reranker_context_corpus(
    *,
    settings: Settings,
    runtime: DatabaseRuntime,
    project_root: Path,
    embedding_provider: EmbeddingProvider,
) -> FrozenRagCorpusSnapshot:
    """Validate and return the retained corpus without creating or rebuilding it."""

    dataset_path = project_root / DEFAULT_DATASET_PATH.relative_to(PROJECT_ROOT)
    manifest_path = project_root / DEFAULT_SOURCE_MANIFEST_PATH.relative_to(
        PROJECT_ROOT
    )
    cases = _load_cases(dataset_path)
    manifest = _load_source_manifest(manifest_path)
    sources = _load_evaluation_sources(
        project_root=project_root,
        manifest=manifest,
        source_ids=None,
    )
    candidate = _selected_chunk_candidate()
    corpus_identity = _corpus_identity(
        cases=cases,
        manifest_sha256=manifest.canonical_sha256(),
        sources=sources,
        candidate=candidate,
    )
    with runtime.session_factory() as session:
        tenant_ids = tuple(
            session.scalars(
                select(Tenant.id).where(Tenant.name == corpus_identity.tenant_name)
            )
        )
    if len(tenant_ids) != 1:
        raise RuntimeError("existing frozen corpus tenant is unavailable")
    return _snapshot(
        runtime=runtime,
        settings=settings,
        tenant_id=tenant_ids[0],
        corpus_identity=corpus_identity,
        sources=sources,
        candidate=candidate,
        provider=embedding_provider,
        created=False,
    )


def inspect_m2_reranker_context_chunks(
    settings: Settings,
    *,
    project_root: Path,
) -> FrozenChunkCorpusIdentity:
    """Read the fixed ChunkSet identity without activating any IndexSet."""

    runtime = create_database_runtime(settings)
    try:
        dataset_path = project_root / DEFAULT_DATASET_PATH.relative_to(PROJECT_ROOT)
        manifest_path = project_root / DEFAULT_SOURCE_MANIFEST_PATH.relative_to(
            PROJECT_ROOT
        )
        cases = _load_cases(dataset_path)
        manifest = _load_source_manifest(manifest_path)
        sources = _load_evaluation_sources(
            project_root=project_root,
            manifest=manifest,
            source_ids=None,
        )
        candidate = _selected_chunk_candidate()
        corpus_identity = _corpus_identity(
            cases=cases,
            manifest_sha256=manifest.canonical_sha256(),
            sources=sources,
            candidate=candidate,
        )
        expected_config = ChunkingConfig.from_settings(
            _settings_for_chunk(settings, candidate.config)
        ).model_dump(mode="json")
        with runtime.session_factory() as session:
            tenant_ids = tuple(
                session.scalars(
                    select(Tenant.id).where(Tenant.name == corpus_identity.tenant_name)
                )
            )
            if len(tenant_ids) != 1:
                raise RuntimeError("frozen corpus tenant identity is unavailable")
            rows = _source_rows(runtime, tenant_id=tenant_ids[0])
            expected_sources = _expected_sources(sources)
            if set(rows) != set(expected_sources):
                raise RuntimeError("frozen corpus sources do not match their identity")
            document_ids: list[UUID] = []
            chunk_set_ids: list[UUID] = []
            chunk_count = 0
            for key in expected_sources:
                document, version, _file_row = rows[key]
                chunk_sets = tuple(
                    session.scalars(
                        select(DocumentChunkSet).where(
                            DocumentChunkSet.tenant_id == tenant_ids[0],
                            DocumentChunkSet.document_id == document.id,
                            DocumentChunkSet.document_version_id == version.id,
                            DocumentChunkSet.status == "ready",
                            DocumentChunkSet.config_json == expected_config,
                        )
                    )
                )
                if len(chunk_sets) != 1 or chunk_sets[0].chunk_count is None:
                    raise RuntimeError("frozen corpus ChunkSet identity is incomplete")
                document_ids.append(document.id)
                chunk_set_ids.append(chunk_sets[0].id)
                chunk_count += chunk_sets[0].chunk_count
        return FrozenChunkCorpusIdentity(
            corpus_sha256=corpus_identity.sha256,
            document_ids=tuple(document_ids),
            chunk_set_ids=tuple(chunk_set_ids),
            chunk_count=chunk_count,
        )
    finally:
        runtime.engine.dispose()


def build_m2_reranker_context_evidence_map(
    *,
    runtime: DatabaseRuntime,
    storage: StorageBackend,
    project_root: Path,
    snapshot: FrozenRagCorpusSnapshot,
) -> dict[UUID, frozenset[str]]:
    """Map Golden Evidence onto the active index over the retained ChunkSets."""

    cases = _load_cases(project_root / DEFAULT_DATASET_PATH.relative_to(PROJECT_ROOT))
    manifest = _load_source_manifest(
        project_root / DEFAULT_SOURCE_MANIFEST_PATH.relative_to(PROJECT_ROOT)
    )
    sources = _load_evaluation_sources(
        project_root=project_root,
        manifest=manifest,
        source_ids=None,
    )
    rows = _source_rows(runtime, tenant_id=snapshot.tenant_id)
    parsed_sources: list[_ParsedEvaluationSource] = []
    index_set_ids: dict[UUID, UUID] = {}
    for key, source in _expected_sources(sources).items():
        document, version, _file_row = rows[key]
        routed = _read_routed_artifact(
            runtime=runtime,
            storage=storage,
            tenant_id=snapshot.tenant_id,
            document_id=document.id,
            version_id=version.id,
        )
        parsed_sources.append(
            _ParsedEvaluationSource(
                source=source,
                document_id=document.id,
                version_id=version.id,
                route=routed.route,
                routed=routed,
            )
        )
        active_index_set_id = version.active_index_set_id
        if active_index_set_id is None:
            raise RuntimeError("frozen corpus active Index Set is unavailable")
        index_set_ids[document.id] = active_index_set_id
    evidence_map = _build_evidence_map(
        runtime=runtime,
        storage=storage,
        tenant_id=snapshot.tenant_id,
        parsed_sources=parsed_sources,
        cases=cases,
        index_set_ids=index_set_ids,
    )
    if not set(evidence_map) <= set(snapshot.chunk_ids):
        raise RuntimeError("Golden Evidence mapped outside the active frozen index")
    return evidence_map


def _selected_chunk_candidate() -> FrozenChunkCandidate:
    return next(
        candidate
        for candidate in build_frozen_chunk_candidates()
        if candidate.config.config_id == FROZEN_CHUNK_CONFIG_ID
    )


def _corpus_identity(
    *,
    cases: Sequence[EvaluationCase],
    manifest_sha256: str,
    sources: Sequence[_EvaluationSourceInput],
    candidate: FrozenChunkCandidate,
) -> _CorpusIdentity:
    payload = {
        "contract_version": FROZEN_CORPUS_CONTRACT_VERSION,
        "dataset_version": cases[0].dataset_version,
        "manifest_sha256": manifest_sha256,
        "sources": [
            {
                "source_id": source.source_id,
                "logical_document_id": source.logical_document_id,
                "sha256": hashlib.sha256(source.content).hexdigest(),
            }
            for source in sources
        ],
        "chunk_config": candidate.config.model_dump(mode="json"),
    }
    digest = hashlib.sha256(_canonical_json(payload)).hexdigest()
    run_id = f"m2-2273-{digest[:16]}"
    tenant_name = f"{_TENANT_LABEL} {digest[:24]} {run_id[-8:]}"
    return _CorpusIdentity(sha256=digest, run_id=run_id, tenant_name=tenant_name)


def _ensure_index_generation(
    *,
    runtime: DatabaseRuntime,
    storage: StorageBackend,
    settings: Settings,
    provider: EmbeddingProvider,
    owner: CurrentUser,
    tenant_id: UUID,
    sources: Sequence[_EvaluationSourceInput],
    candidate: FrozenChunkCandidate,
) -> None:
    """Index the frozen ChunkSets, reusing parse and chunk artifacts if present."""

    rows = _source_rows(runtime, tenant_id=tenant_id)
    expected_sources = _expected_sources(sources)
    if len(rows) != len(expected_sources) or set(rows) != set(expected_sources):
        raise RuntimeError("frozen corpus sources do not match their identity")
    service = DocumentIndexService(
        runtime.session_factory,
        storage,
        _settings_for_chunk(settings, candidate.config),
        provider,
    )
    for key in expected_sources:
        document, version, _file_row = rows[key]
        service.index_version(
            owner,
            document_id=document.id,
            version_id=version.id,
        )


def _source_rows(
    runtime: DatabaseRuntime,
    *,
    tenant_id: UUID,
) -> dict[tuple[str, str, str], tuple[Document, DocumentVersion, StoredFile]]:
    with runtime.session_factory() as session:
        rows = session.execute(
            select(Document, DocumentVersion, StoredFile)
            .join(
                DocumentVersion,
                and_(
                    DocumentVersion.tenant_id == Document.tenant_id,
                    DocumentVersion.document_id == Document.id,
                ),
            )
            .join(
                StoredFile,
                and_(
                    StoredFile.tenant_id == DocumentVersion.tenant_id,
                    StoredFile.id == DocumentVersion.file_id,
                ),
            )
            .where(Document.tenant_id == tenant_id)
        ).all()
    return {
        (file_row.sha256, file_row.original_name, document.title): (
            document,
            version,
            file_row,
        )
        for document, version, file_row in rows
    }


def _expected_sources(
    sources: Sequence[_EvaluationSourceInput],
) -> dict[tuple[str, str, str], _EvaluationSourceInput]:
    return {
        (
            hashlib.sha256(source.content).hexdigest(),
            source.original_name,
            source.title,
        ): source
        for source in sources
    }


def _snapshot(
    *,
    runtime: DatabaseRuntime,
    settings: Settings,
    tenant_id: UUID,
    corpus_identity: _CorpusIdentity,
    sources: Sequence[_EvaluationSourceInput],
    candidate: FrozenChunkCandidate,
    provider: EmbeddingProvider,
    created: bool,
) -> FrozenRagCorpusSnapshot:
    expected_config = ChunkingConfig.from_settings(
        _settings_for_chunk(settings, candidate.config)
    ).model_dump(mode="json")
    expected_embedding = asdict(provider.identity)
    with runtime.session_factory() as session:
        tenant = session.get(Tenant, tenant_id)
        if tenant is None or tenant.name != corpus_identity.tenant_name:
            raise RuntimeError("frozen corpus tenant identity is unavailable")
        rows = session.execute(
            select(
                Document,
                DocumentVersion,
                StoredFile,
                DocumentIndexSet,
                DocumentChunkSet,
            )
            .join(
                DocumentVersion,
                and_(
                    DocumentVersion.tenant_id == Document.tenant_id,
                    DocumentVersion.id == Document.active_version_id,
                    DocumentVersion.document_id == Document.id,
                ),
            )
            .join(
                StoredFile,
                and_(
                    StoredFile.tenant_id == DocumentVersion.tenant_id,
                    StoredFile.id == DocumentVersion.file_id,
                ),
            )
            .join(
                DocumentIndexSet,
                and_(
                    DocumentIndexSet.tenant_id == DocumentVersion.tenant_id,
                    DocumentIndexSet.id == DocumentVersion.active_index_set_id,
                ),
            )
            .join(
                DocumentChunkSet,
                and_(
                    DocumentChunkSet.tenant_id == DocumentIndexSet.tenant_id,
                    DocumentChunkSet.id == DocumentIndexSet.document_chunk_set_id,
                ),
            )
            .where(Document.tenant_id == tenant_id)
        ).all()
        expected_sources = _expected_sources(sources)
        observed = {
            (file_row.sha256, file_row.original_name, document.title): (
                document,
                version,
                file_row,
                index_set,
                chunk_set,
            )
            for document, version, file_row, index_set, chunk_set in rows
        }
        if len(observed) != len(rows) or set(observed) != set(expected_sources):
            raise RuntimeError("frozen corpus sources do not match their identity")
        chunk_set_total = (
            session.scalar(
                select(func.count())
                .select_from(DocumentChunkSet)
                .where(DocumentChunkSet.tenant_id == tenant_id)
            )
            or 0
        )
        index_set_total = (
            session.scalar(
                select(func.count())
                .select_from(DocumentIndexSet)
                .where(DocumentIndexSet.tenant_id == tenant_id)
            )
            or 0
        )
        if chunk_set_total != len(sources) or index_set_total < len(sources):
            raise RuntimeError("frozen corpus generations are incomplete")

        document_ids: list[UUID] = []
        chunk_set_ids: list[UUID] = []
        index_set_ids: list[UUID] = []
        logical_document_ids: dict[UUID, str] = {}
        for key, source in expected_sources.items():
            document, version, file_row, index_set, chunk_set = observed[key]
            if (
                document.deleted_at is not None
                or file_row.status != "ready"
                or file_row.deleted_at is not None
                or version.parse_status != "ready"
                or version.index_status != "ready"
                or index_set.status != "ready"
                or chunk_set.status != "ready"
                or chunk_set.config_json != expected_config
                or index_set.embedding_identity_json != expected_embedding
                or index_set.embedding_model != provider.identity.model_id
                or index_set.embedding_version != provider.identity.revision
                or index_set.fts_builder_version != FTS_BUILDER_VERSION
            ):
                raise RuntimeError("frozen corpus active generation is incompatible")
            document_ids.append(document.id)
            chunk_set_ids.append(chunk_set.id)
            index_set_ids.append(index_set.id)
            logical_document_ids[document.id] = source.logical_document_id

        chunk_rows = session.execute(
            select(DocumentChunk.id, DocumentChunk.content_sha256)
            .where(DocumentChunk.document_index_set_id.in_(index_set_ids))
            .order_by(DocumentChunk.id)
        ).all()
        expected_chunk_count = sum(
            observed[key][3].chunk_count or 0 for key in expected_sources
        )
        if not chunk_rows or len(chunk_rows) != expected_chunk_count:
            raise RuntimeError("frozen corpus Chunk rows are incomplete")
        snapshot_sha256 = hashlib.sha256(
            _canonical_json(
                {
                    "corpus_sha256": corpus_identity.sha256,
                    "documents": [str(item) for item in document_ids],
                    "chunk_sets": [str(item) for item in chunk_set_ids],
                    "index_sets": [str(item) for item in index_set_ids],
                    "chunks": [
                        {"id": str(chunk_id), "content_sha256": content_sha256}
                        for chunk_id, content_sha256 in chunk_rows
                    ],
                }
            )
        ).hexdigest()
        owner = _evaluation_users(
            runtime,
            tenant_id=tenant_id,
            run_id=corpus_identity.run_id,
        )["user-fixture-company-owner"]
        return FrozenRagCorpusSnapshot(
            corpus_sha256=corpus_identity.sha256,
            index_sha256=hashlib.sha256(
                _canonical_json(
                    {
                        "embedding_identity": expected_embedding,
                        "fts_builder_version": FTS_BUILDER_VERSION,
                    }
                )
            ).hexdigest(),
            snapshot_sha256=snapshot_sha256,
            tenant_id=tenant_id,
            owner=owner,
            created=created,
            source_count=len(sources),
            document_count=len(document_ids),
            chunk_set_count=len(chunk_set_ids),
            index_set_count=index_set_total,
            chunk_count=len(chunk_rows),
            document_ids=tuple(document_ids),
            chunk_set_ids=tuple(chunk_set_ids),
            index_set_ids=tuple(index_set_ids),
            chunk_ids=tuple(chunk_id for chunk_id, _content_hash in chunk_rows),
            logical_document_ids=logical_document_ids,
        )


def _cleanup_incomplete_corpus(
    *,
    runtime: DatabaseRuntime,
    storage: StorageBackend,
    tenant_id: UUID,
    baseline_before: _ChunkFormalBaseline,
) -> None:
    with runtime.session_factory.begin() as session:
        session.execute(
            update(DocumentVersion)
            .where(DocumentVersion.tenant_id == tenant_id)
            .values(active_index_set_id=None)
        )
        session.execute(
            update(Document)
            .where(Document.tenant_id == tenant_id)
            .values(active_version_id=None)
        )
        session.execute(
            delete(DocumentChunk).where(DocumentChunk.tenant_id == tenant_id)
        )
        session.execute(
            delete(DocumentIndexSet).where(DocumentIndexSet.tenant_id == tenant_id)
        )
    cleanup = _cleanup_chunk_evaluation(
        runtime=runtime,
        storage=storage,
        tenant_id=tenant_id,
        baseline_before=baseline_before,
    )
    if (
        cleanup.evaluation_database_rows_remaining
        or cleanup.evaluation_storage_objects_remaining
    ):
        raise RuntimeError("incomplete frozen corpus cleanup failed")


def _canonical_json(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
