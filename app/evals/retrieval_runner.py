"""Bounded M2-22.6 Dense, Lexical, RRF, and TopK evaluation runner."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update

from app.core.config import Settings
from app.core.errors import DocumentIndexingError, EmbeddingProviderError
from app.db.session import DatabaseRuntime, create_database_runtime
from app.evals.chunk_metrics import evaluate_chunk_document
from app.evals.rag_runner import (
    DEFAULT_DATASET_PATH,
    DEFAULT_SOURCE_MANIFEST_PATH,
    PROJECT_ROOT,
    _chunk_formal_baseline,
    _cleanup_chunk_evaluation,
    _create_evaluation_identity,
    _ingest_chunk_source,
    _load_cases,
    _load_evaluation_sources,
    _load_source_manifest,
    _login_evaluation_owner,
    _ParsedEvaluationSource,
)
from app.evals.ragas_retrieval import (
    RAGAS_VERSION,
    Ragas043Backend,
    RagasJudgeRuntime,
    RagasRetrievalAdapter,
    RagasRetrievalInput,
)
from app.evals.retrieval_metrics import (
    RETRIEVAL_CUTOFFS,
    AnswerableRankingMetrics,
    NoAnswerRankingMetrics,
    RankedEvidenceCandidate,
    evaluate_answerable_ranking,
    evaluate_no_answer_ranking,
)
from app.evals.retrieval_report import (
    RetrievalAggregate,
    RetrievalCandidateFailureTrace,
    RetrievalCandidateTrace,
    RetrievalCaseResult,
    RetrievalCleanupResult,
    RetrievalConfigSelection,
    RetrievalEvaluationReport,
    RetrievalExperimentResult,
    RetrievalFilterAudit,
    RetrievalLatencySummary,
    RetrievalRouteTrace,
    RetrievalTraceArtifact,
)
from app.main import create_app
from app.models.identity import User
from app.models.knowledge import (
    Document,
    DocumentAcl,
    DocumentChunk,
    DocumentIndexSet,
    DocumentVersion,
    StoredFile,
)
from app.repositories.retrieval import DenseCandidateRecord, RetrievalRepository
from app.schemas.auth import CurrentUser
from app.schemas.evaluation import (
    ChunkEvaluationConfig,
    EvaluationCase,
    default_chunk_evaluation_configs,
)
from app.schemas.retrieval import RetrievalRequest, RetrievalResponse
from app.services.documents.chunking import CanonicalChunkArtifact, DocumentChunkService
from app.services.documents.indexing.service import DocumentIndexService
from app.services.documents.parser_service import DocumentParserService
from app.services.documents.parsers.docling import DoclingProvider, LocalDoclingProvider
from app.services.retrieval import (
    DenseRetrievalService,
    EmbeddingBatch,
    EmbeddingProvider,
    EmbeddingPurpose,
    HybridRetrievalService,
    LexicalRetrievalService,
    create_embedding_provider,
)
from app.services.retrieval.dense import (
    _result_from_candidate as _dense_result_from_candidate,
)
from app.services.retrieval.errors import RetrievalInternalError
from app.services.storage import LocalStorageBackend, StorageBackend
from scripts.seed_m2_complex_files import (
    generate_complex_sources,
    load_complex_seed_definition,
    seed_m2_complex_files,
)
from scripts.seed_m2_files import (
    generate_sources,
    load_seed_definition,
    seed_m2_files,
)

RetrievalReportingCohort = Literal[
    "real_cross_border",
    "synthetic_cross_border",
    "general_diagnostics",
    "safety_acl_version",
]
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FrozenChunkCandidate:
    """One M2-22.5-selected candidate or the unchanged production baseline."""

    config: ChunkEvaluationConfig
    production_baseline: bool = False


@dataclass(frozen=True, slots=True)
class _IndexedConfig:
    candidate: FrozenChunkCandidate
    index_set_ids: tuple[UUID, ...]
    chunk_count: int
    index_latency_ms: int
    evidence_ids_by_chunk: Mapping[UUID, frozenset[str]]
    previous_index_ids_by_document: Mapping[str, UUID]


@dataclass(frozen=True, slots=True)
class _MeasuredRoutes:
    dense: RetrievalResponse
    lexical: RetrievalResponse
    dense_latency_ms: int
    lexical_latency_ms: int


@dataclass(frozen=True, slots=True)
class _ExperimentWork:
    result: RetrievalExperimentResult
    hybrid_responses: Mapping[str, RetrievalResponse]


class _MemoizingEmbeddingProvider:
    """Evaluation-only memory cache using exact Provider output identities."""

    def __init__(self, delegate: EmbeddingProvider) -> None:
        self._delegate = delegate
        self._cache: dict[
            tuple[EmbeddingPurpose, str], tuple[tuple[float, ...], str]
        ] = {}

    @property
    def identity(self):  # type: ignore[no-untyped-def]
        return self._delegate.identity

    def embed(
        self,
        texts: Sequence[str],
        *,
        purpose: EmbeddingPurpose,
    ) -> EmbeddingBatch:
        missing = [text for text in texts if (purpose, text) not in self._cache]
        effective_batch_size = 1
        if missing:
            batch = self._delegate.embed(missing, purpose=purpose)
            effective_batch_size = batch.effective_batch_size
            for text, vector, cache_key in zip(
                missing, batch.vectors, batch.cache_keys, strict=True
            ):
                self._cache[(purpose, text)] = (vector, cache_key)
        values = [self._cache[(purpose, text)] for text in texts]
        return EmbeddingBatch(
            vectors=tuple(vector for vector, _key in values),
            cache_keys=tuple(key for _vector, key in values),
            purpose=purpose,
            identity=self.identity,
            effective_batch_size=effective_batch_size,
        )

    def clear(self) -> None:
        self._cache.clear()


class _StaticRoute:
    def __init__(self, response: RetrievalResponse) -> None:
        self._response = response

    def retrieve(
        self,
        current_user: CurrentUser,
        request: RetrievalRequest,
    ) -> RetrievalResponse:
        del current_user, request
        return self._response


class RetrievalEvaluationEmbeddingError(RuntimeError):
    """A local Embedding call failed before any index persistence work."""


class RetrievalEvaluationIndexPersistenceError(RuntimeError):
    """Index mapping or PostgreSQL persistence failed after Embedding succeeded."""


class RetrievalEvaluationDenseMappingError(RuntimeError):
    """One ranked pgvector row cannot satisfy the public retrieval contract."""


def _validate_dense_candidates(candidates: Sequence[DenseCandidateRecord]) -> None:
    """Expose an exact evaluation-only cause hidden by the public safe error."""

    for rank, candidate in enumerate(candidates, start=1):
        try:
            _dense_result_from_candidate(candidate, rank=rank)
        except (TypeError, ValueError) as error:
            raise RetrievalEvaluationDenseMappingError(
                "Dense candidate mapping failed for "
                f"chunk_id={candidate.chunk_id}, document_id={candidate.document_id}, "
                f"rank={rank}: {type(error).__name__}: {error}"
            ) from error


def build_frozen_chunk_candidates() -> list[FrozenChunkCandidate]:
    """Return exactly the nine frozen candidates plus the production baseline."""

    first_round = {
        config.config_id: config for config in default_chunk_evaluation_configs()
    }
    output: list[FrozenChunkCandidate] = []
    for base_id in ("chunk-compact", "chunk-medium", "chunk-large"):
        base = first_round[base_id]
        for overlap in (80, 100, 120):
            output.append(
                FrozenChunkCandidate(
                    config=base.model_copy(
                        update={
                            "config_id": f"{base_id}-overlap-{overlap:03d}",
                            "text_overlap_tokens": overlap,
                        }
                    )
                )
            )
    output.append(
        FrozenChunkCandidate(
            config=first_round["chunk-current"],
            production_baseline=True,
        )
    )
    return output


def case_reporting_cohort(case: EvaluationCase) -> RetrievalReportingCohort:
    """Map frozen cases to the four non-diluting report cohorts."""

    if case.source_group == "security_acl_version":
        return "safety_acl_version"
    if case.source_group == "cross_border_core":
        return "real_cross_border"
    if any(
        span.source_id.startswith("m2-complex-v1-")
        for span in case.expected_evidence_spans
    ):
        return "general_diagnostics"
    return "synthetic_cross_border"


def trace_retrieval_response(
    response: RetrievalResponse,
    *,
    requested_candidate_depth: int,
    latency_ms: int,
    logical_document_ids: Mapping[UUID, str],
    evidence_ids_by_chunk: Mapping[UUID, frozenset[str]],
) -> RetrievalRouteTrace:
    """Serialize every ordered candidate while excluding body text and vectors."""

    candidates: list[RetrievalCandidateTrace] = []
    for result in response.results:
        dense = result.scores.dense
        lexical = result.scores.lexical
        candidates.append(
            RetrievalCandidateTrace(
                chunk_id=result.identity.chunk_id,
                document_id=result.identity.document_id,
                version_id=result.identity.version_id,
                index_set_id=result.identity.index_set_id,
                logical_document_id=logical_document_ids[result.identity.document_id],
                rank=result.final_rank,
                body_text_sha256=hashlib.sha256(
                    result.body_text.encode("utf-8")
                ).hexdigest(),
                source_locator=result.source_locator,
                dense_rank=dense.rank if dense is not None else None,
                dense_similarity=(dense.similarity if dense is not None else None),
                lexical_rank=lexical.rank if lexical is not None else None,
                lexical_score=lexical.score if lexical is not None else None,
                rrf_score=result.rrf_score,
                matched_evidence_ids=sorted(
                    evidence_ids_by_chunk.get(result.identity.chunk_id, frozenset())
                ),
            )
        )
    return RetrievalRouteTrace(
        mode=response.mode,
        requested_candidate_depth=requested_candidate_depth,
        returned_candidate_count=len(candidates),
        latency_ms=latency_ms,
        candidates=candidates,
        candidate_failures=[
            RetrievalCandidateFailureTrace.model_validate(failure, from_attributes=True)
            for failure in response.candidate_failures
        ],
    )


def _settings_for_chunk(
    settings: Settings,
    config: ChunkEvaluationConfig,
) -> Settings:
    return settings.model_copy(
        update={
            "chunk_target_tokens": config.target_tokens,
            "chunk_max_tokens": config.max_tokens,
            "chunk_overlap_tokens": config.text_overlap_tokens,
            "chunk_heading_context_max_tokens": config.heading_context_max_tokens,
            "chunk_table_row_overlap": config.table_row_overlap,
            "chunk_repeated_edge_min_pages": config.repeated_edge_min_pages,
        }
    )


def _materialize_source_acls(
    runtime: DatabaseRuntime,
    *,
    tenant_id: UUID,
    parsed_sources: Sequence[_ParsedEvaluationSource],
) -> None:
    acl_by_document: dict[str, list[dict[str, object]]] = {}
    for generated in [
        *generate_sources(load_seed_definition()),
        *generate_complex_sources(load_complex_seed_definition()),
    ]:
        acl_by_document[str(generated.document_id)] = generated.definition["acl"]
    with runtime.session_factory.begin() as session:
        for parsed in parsed_sources:
            entries = acl_by_document.get(parsed.source.logical_document_id, [])
            if parsed.source.access_level == "tenant":
                entries = [
                    {"subject_type": "role", "role_name": role_name}
                    for role_name in (
                        "company_owner",
                        "product_scout",
                        "amazon_operator",
                    )
                ]
            for entry in entries:
                session.add(
                    DocumentAcl(
                        id=uuid4(),
                        tenant_id=tenant_id,
                        document_id=parsed.document_id,
                        subject_type=entry["subject_type"],
                        role_name=entry.get("role_name"),
                        user_id=None,
                        market_code=entry.get("market_code"),
                        permission="read",
                    )
                )


def _evaluation_users(
    runtime: DatabaseRuntime,
    *,
    tenant_id: UUID,
    run_id: str,
) -> dict[str, CurrentUser]:
    from app.evals.rag_runner import build_default_fixture_registry

    registry = build_default_fixture_registry()
    output: dict[str, CurrentUser] = {}
    with runtime.session_factory() as session:
        for fixture in registry.users:
            short_id = fixture.fixture_id.removeprefix("user-fixture-")
            email = f"m2.eval.{run_id[-8:]}.{short_id}@example.invalid"
            row = session.scalar(
                select(User).where(User.tenant_id == tenant_id, User.email == email)
            )
            if row is None:
                raise RuntimeError("evaluation user fixture is unavailable")
            output[fixture.fixture_id] = CurrentUser(
                user_id=row.id,
                tenant_id=tenant_id,
                email=row.email,
                display_name=row.display_name,
                roles=fixture.roles,
                market_scopes=fixture.market_scopes,
                synthetic_data=True,
            )
    return output


def _index_configuration(
    *,
    runtime: DatabaseRuntime,
    storage: StorageBackend,
    settings: Settings,
    provider: EmbeddingProvider,
    user: CurrentUser,
    parsed_sources: Sequence[_ParsedEvaluationSource],
    cases: Sequence[EvaluationCase],
    candidate: FrozenChunkCandidate,
) -> _IndexedConfig:
    previous: dict[str, UUID] = {}
    with runtime.session_factory() as session:
        for parsed in parsed_sources:
            old = session.scalar(
                select(DocumentVersion.active_index_set_id).where(
                    DocumentVersion.id == parsed.version_id
                )
            )
            if old is not None:
                previous[parsed.source.logical_document_id] = old
    started = time.perf_counter()
    evaluation_settings = _settings_for_chunk(settings, candidate.config)
    service = DocumentIndexService(
        runtime.session_factory,
        storage,
        evaluation_settings,
        provider,
    )
    chunk_service = DocumentChunkService(
        runtime.session_factory,
        storage,
        evaluation_settings,
    )
    results = []
    for parsed in parsed_sources:
        _LOGGER.info(
            "M2-22.6 indexing source %s under %s",
            parsed.source.source_id,
            candidate.config.config_id,
        )
        published = chunk_service.ensure_chunk_version(
            user,
            document_id=parsed.document_id,
            version_id=parsed.version_id,
        )
        from app.evals.rag_runner import _read_chunk_payload

        payload = _read_chunk_payload(
            runtime=runtime,
            storage=storage,
            tenant_id=user.tenant_id,
            chunk_set_id=published.chunk_set_id,
        )
        artifact = CanonicalChunkArtifact.model_validate_json(payload)
        try:
            for batch_start in range(0, len(artifact.chunks), 128):
                provider.embed(
                    [
                        chunk.retrieval_text
                        for chunk in artifact.chunks[batch_start : batch_start + 128]
                    ],
                    purpose=EmbeddingPurpose.DOCUMENT,
                )
        except EmbeddingProviderError:
            raise RetrievalEvaluationEmbeddingError(
                f"BGE embedding failed for source {parsed.source.source_id}"
            ) from None
        try:
            results.append(
                service.index_version(
                    user,
                    document_id=parsed.document_id,
                    version_id=parsed.version_id,
                )
            )
        except DocumentIndexingError:
            raise RetrievalEvaluationIndexPersistenceError(
                f"Index persistence failed for source {parsed.source.source_id}"
            ) from None
    evidence_map = _build_evidence_map(
        runtime=runtime,
        storage=storage,
        tenant_id=user.tenant_id,
        parsed_sources=parsed_sources,
        cases=cases,
        index_set_ids={result.document_id: result.index_set_id for result in results},
    )
    return _IndexedConfig(
        candidate=candidate,
        index_set_ids=tuple(result.index_set_id for result in results),
        chunk_count=sum(result.chunk_count for result in results),
        index_latency_ms=max(0, round((time.perf_counter() - started) * 1000)),
        evidence_ids_by_chunk=evidence_map,
        previous_index_ids_by_document=previous,
    )


def _build_evidence_map(
    *,
    runtime: DatabaseRuntime,
    storage: StorageBackend,
    tenant_id: UUID,
    parsed_sources: Sequence[_ParsedEvaluationSource],
    cases: Sequence[EvaluationCase],
    index_set_ids: Mapping[UUID, UUID],
) -> dict[UUID, frozenset[str]]:
    from app.evals.rag_runner import _read_chunk_payload

    evidence: dict[UUID, set[str]] = {}
    for parsed in parsed_sources:
        index_set_id = index_set_ids[parsed.document_id]
        with runtime.session_factory() as session:
            index_set = session.get(DocumentIndexSet, index_set_id)
            if index_set is None:
                raise RuntimeError("evaluation Index Set is unavailable")
            payload = _read_chunk_payload(
                runtime=runtime,
                storage=storage,
                tenant_id=tenant_id,
                chunk_set_id=index_set.document_chunk_set_id,
            )
            chunk_artifact = CanonicalChunkArtifact.model_validate_json(payload)
            rows = session.execute(
                select(DocumentChunk.chunk_id, DocumentChunk.id).where(
                    DocumentChunk.document_index_set_id == index_set_id
                )
            ).all()
            row_ids: dict[str, UUID] = {row[0]: row[1] for row in rows}
        for case in cases:
            if not case.should_answer:
                continue
            for position, span in enumerate(case.expected_evidence_spans, start=1):
                if span.document_id != parsed.source.logical_document_id:
                    continue
                single = case.model_copy(
                    update={
                        "expected_document_ids": [span.document_id],
                        "expected_evidence_spans": [span],
                    }
                )
                quality = evaluate_chunk_document(
                    source_id=parsed.source.source_id,
                    logical_document_id=parsed.source.logical_document_id,
                    artifact=parsed.routed.selected_artifact,
                    chunk_artifact=chunk_artifact,
                    cases=[single],
                )
                located = quality.golden_cases[0].locator_match_chunk_ids
                evidence_id = f"{case.case_id}-evidence-{position:03d}"
                for logical_chunk_id in located:
                    row_id = row_ids[logical_chunk_id]
                    evidence.setdefault(row_id, set()).add(evidence_id)
    return {chunk_id: frozenset(ids) for chunk_id, ids in evidence.items()}


@contextmanager
def _case_database_state(
    runtime: DatabaseRuntime,
    *,
    case: EvaluationCase,
    document_ids: Mapping[str, UUID],
) -> Iterator[None]:
    """Materialize only the frozen denied/deleted fixture during its query."""

    target_ids = [
        document_ids[item]
        for item in case.expected_document_ids
        if item in document_ids
    ]
    saved_acl: list[dict[str, object]] = []
    saved_documents: list[tuple[UUID, datetime | None]] = []
    saved_files: list[tuple[UUID, str, datetime | None]] = []
    try:
        with runtime.session_factory.begin() as session:
            if case.acl_fixture_id == "acl-fixture-denied" and target_ids:
                rows = list(
                    session.scalars(
                        select(DocumentAcl).where(
                            DocumentAcl.document_id.in_(target_ids)
                        )
                    )
                )
                saved_acl = [
                    {
                        "id": row.id,
                        "tenant_id": row.tenant_id,
                        "document_id": row.document_id,
                        "subject_type": row.subject_type,
                        "role_name": row.role_name,
                        "user_id": row.user_id,
                        "market_code": row.market_code,
                        "permission": row.permission,
                    }
                    for row in rows
                ]
                for row in rows:
                    session.delete(row)
            if case.version_fixture_id == "version-fixture-deleted":
                now = datetime.now(UTC)
                documents = list(
                    session.scalars(select(Document).where(Document.id.in_(target_ids)))
                )
                for document in documents:
                    saved_documents.append((document.id, document.deleted_at))
                    document.deleted_at = now
                    version = session.scalar(
                        select(DocumentVersion).where(
                            DocumentVersion.id == document.active_version_id
                        )
                    )
                    if version is not None:
                        file_row = session.get(StoredFile, version.file_id)
                        if file_row is not None:
                            saved_files.append(
                                (file_row.id, file_row.status, file_row.deleted_at)
                            )
                            file_row.status = "soft_deleted"
                            file_row.deleted_at = now
        yield
    finally:
        with runtime.session_factory.begin() as session:
            for payload in saved_acl:
                session.add(DocumentAcl(**payload))
            for document_id, deleted_at in saved_documents:
                restored_document = session.get(Document, document_id)
                if restored_document is not None:
                    restored_document.deleted_at = deleted_at
            for file_id, status, deleted_at in saved_files:
                file_row = session.get(StoredFile, file_id)
                if file_row is not None:
                    file_row.status = status
                    file_row.deleted_at = deleted_at


def _measure_routes(
    *,
    runtime: DatabaseRuntime,
    settings: Settings,
    provider: EmbeddingProvider,
    user: CurrentUser,
    case_id: str,
    question: str,
    depth: int,
) -> _MeasuredRoutes:
    request = RetrievalRequest(query=question)
    with runtime.session_factory() as session:
        repository = RetrievalRepository(
            session,
            statement_timeout_ms=settings.database_statement_timeout_ms,
        )
        dense_service = DenseRetrievalService(
            repository,
            provider,
            query_max_characters=settings.retrieval_query_max_characters,
            candidate_count=depth,
        )
        lexical_service = LexicalRetrievalService(
            repository,
            query_max_characters=settings.retrieval_query_max_characters,
            candidate_count=depth,
        )
        started = time.perf_counter()
        try:
            dense = dense_service.retrieve(user, request)
        except RetrievalInternalError:
            query_batch = provider.embed(
                [question],
                purpose=EmbeddingPurpose.QUERY,
            )
            raw_candidates = repository.search_dense(
                user,
                query_vector=query_batch.vectors[0],
                embedding_identity=provider.identity,
                limit=depth,
            )
            try:
                _validate_dense_candidates(raw_candidates)
            except RetrievalEvaluationDenseMappingError as error:
                raise RetrievalEvaluationDenseMappingError(
                    f"case_id={case_id}, depth={depth}: {error}"
                ) from error
            raise RetrievalEvaluationDenseMappingError(
                f"case_id={case_id}, depth={depth}: Dense response contract "
                "failed although every raw candidate mapped independently"
            ) from None
        dense_latency = max(0, round((time.perf_counter() - started) * 1000))
        started = time.perf_counter()
        lexical = lexical_service.retrieve(user, request)
        lexical_latency = max(0, round((time.perf_counter() - started) * 1000))
    return _MeasuredRoutes(
        dense=dense,
        lexical=lexical,
        dense_latency_ms=dense_latency,
        lexical_latency_ms=lexical_latency,
    )


def _fuse_routes(
    measured: _MeasuredRoutes,
    *,
    user: CurrentUser,
    question: str,
    depth: int,
    rrf_k: int,
    production_baseline: bool,
) -> tuple[RetrievalResponse, int]:
    candidate_count = (
        30
        if production_baseline and depth == 30 and rrf_k == 60
        else min(100, depth * 2)
    )
    service = HybridRetrievalService(
        _StaticRoute(measured.dense),
        _StaticRoute(measured.lexical),
        rrf_k=rrf_k,
        candidate_count=candidate_count,
    )
    started = time.perf_counter()
    response = service.retrieve(user, RetrievalRequest(query=question))
    return response, max(0, round((time.perf_counter() - started) * 1000))


def _ranked_candidates(trace: RetrievalRouteTrace) -> list[RankedEvidenceCandidate]:
    candidates = {
        item.rank: RankedEvidenceCandidate(
            candidate_id=str(item.chunk_id),
            logical_document_id=item.logical_document_id,
            version_id=str(item.version_id),
            index_set_id=str(item.index_set_id),
            evidence_ids=frozenset(item.matched_evidence_ids),
        )
        for item in trace.candidates
    }
    if trace.mode in {"dense", "lexical"}:
        candidates.update(
            {
                failure.rank: RankedEvidenceCandidate(
                    candidate_id=(
                        f"mapping-failure:{failure.source_mode}:"
                        f"{failure.rank}:{failure.chunk_id}"
                    ),
                    evidence_ids=frozenset(),
                )
                for failure in trace.candidate_failures
            }
        )
    return [candidates[rank] for rank in sorted(candidates)]


_ENTITY_QUERY = re.compile(
    r"(?:sku|asin|model|product|supplier|型号|产品|供应商|蘑菇灯|成本表)",
    re.IGNORECASE,
)


def _similar_product_confusion(
    case: EvaluationCase,
    trace: RetrievalRouteTrace,
) -> bool | None:
    if not case.should_answer or _ENTITY_QUERY.search(case.question) is None:
        return None
    expected_documents = set(case.expected_document_ids)
    first_correct = next(
        (item.rank for item in trace.candidates if item.matched_evidence_ids),
        None,
    )
    if first_correct is None:
        return any(
            item.logical_document_id in expected_documents for item in trace.candidates
        )
    return any(
        item.rank < first_correct
        and item.logical_document_id in expected_documents
        and not item.matched_evidence_ids
        for item in trace.candidates
    )


def _case_metric(
    *,
    case: EvaluationCase,
    trace: RetrievalRouteTrace,
    indexed: _IndexedConfig,
) -> AnswerableRankingMetrics | NoAnswerRankingMetrics:
    candidates = _ranked_candidates(trace)
    if case.should_answer:
        expected = frozenset(
            f"{case.case_id}-evidence-{position:03d}"
            for position in range(1, len(case.expected_evidence_spans) + 1)
        )
        return evaluate_answerable_ranking(
            candidates,
            expected_evidence_ids=expected,
        )
    reason = case.expected_non_answer_reason
    if reason is None:
        raise RuntimeError("non-answer case is missing its frozen reason")
    protected_documents = frozenset(case.expected_document_ids)
    protected_index_sets: frozenset[str] = frozenset()
    if case.version_fixture_id == "version-fixture-old-inactive":
        protected_documents = frozenset()
        protected_index_sets = frozenset(
            str(indexed.previous_index_ids_by_document[document_id])
            for document_id in case.expected_document_ids
            if document_id in indexed.previous_index_ids_by_document
        )
    return evaluate_no_answer_ranking(
        candidates,
        expected_non_answer_reason=reason,
        protected_document_ids=protected_documents,
        protected_index_set_ids=protected_index_sets,
        cutoff=min(20, trace.requested_candidate_depth),
    )


def _percentile(values: Sequence[int], quantile: float) -> int | None:
    ordered = sorted(values)
    if not ordered:
        return None
    return ordered[max(0, math.ceil(len(ordered) * quantile) - 1)]


def _latency_summary(traces: Sequence[RetrievalRouteTrace]) -> RetrievalLatencySummary:
    counts = [trace.returned_candidate_count for trace in traces]
    latencies = [trace.latency_ms for trace in traces]
    return RetrievalLatencySummary(
        samples=len(traces),
        candidate_count_min=min(counts) if counts else None,
        candidate_count_p50=_percentile(counts, 0.50),
        candidate_count_p95=_percentile(counts, 0.95),
        candidate_count_max=max(counts) if counts else None,
        latency_p50_ms=_percentile(latencies, 0.50),
        latency_p95_ms=_percentile(latencies, 0.95),
        latency_max_ms=max(latencies) if latencies else None,
    )


def _aggregate_results(
    results: Sequence[RetrievalCaseResult],
    traces: Mapping[tuple[str, str], RetrievalRouteTrace],
) -> list[RetrievalAggregate]:
    output: list[RetrievalAggregate] = []
    cohorts = (
        "all_answerable",
        "real_cross_border",
        "synthetic_cross_border",
        "general_diagnostics",
        "safety_acl_version",
    )
    for cohort in cohorts:
        for mode in ("dense", "lexical", "hybrid"):
            selected = [
                item
                for item in results
                if item.mode == mode
                and (cohort == "all_answerable" or item.cohort == cohort)
            ]
            answerable = [
                cast(AnswerableRankingMetrics, item.deterministic)
                for item in selected
                if isinstance(item.deterministic, AnswerableRankingMetrics)
            ]
            non_answer = [
                cast(NoAnswerRankingMetrics, item.deterministic)
                for item in selected
                if isinstance(item.deterministic, NoAnswerRankingMetrics)
            ]
            confusions = [
                item.similar_product_confusion
                for item in selected
                if item.similar_product_confusion is not None
            ]
            ranks = [
                item.first_correct_evidence_rank
                for item in answerable
                if item.first_correct_evidence_rank is not None
            ]
            denominator = len(answerable)

            def mean(values: Sequence[float]) -> float:
                return sum(values) / len(values) if values else 0.0

            route_traces = [
                traces[(item.case_id, mode)]
                for item in selected
                if (item.case_id, mode) in traces
            ]
            output.append(
                RetrievalAggregate(
                    cohort=cast(
                        Literal[
                            "all_answerable",
                            "real_cross_border",
                            "synthetic_cross_border",
                            "general_diagnostics",
                            "safety_acl_version",
                        ],
                        cohort,
                    ),
                    mode=cast(Literal["dense", "lexical", "hybrid"], mode),
                    answerable_cases=denominator,
                    precision_at={
                        cutoff: mean(
                            [float(item.precision_at[cutoff]) for item in answerable]
                        )
                        for cutoff in RETRIEVAL_CUTOFFS
                    },
                    recall_at={
                        cutoff: mean(
                            [float(item.recall_at[cutoff]) for item in answerable]
                        )
                        for cutoff in RETRIEVAL_CUTOFFS
                    },
                    hit_rate_at={
                        cutoff: mean(
                            [float(item.hit_rate_at[cutoff]) for item in answerable]
                        )
                        for cutoff in RETRIEVAL_CUTOFFS
                    },
                    mrr_at_10=mean([float(item.mrr_at_10) for item in answerable]),
                    ndcg_at={
                        cutoff: mean(
                            [float(item.ndcg_at[cutoff]) for item in answerable]
                        )
                        for cutoff in (5, 10)
                    },
                    first_correct_evidence_rank_mean=(
                        mean([float(rank) for rank in ranks]) if ranks else None
                    ),
                    missed_evidence_cases=sum(
                        item.first_correct_evidence_rank is None for item in answerable
                    ),
                    similar_product_cases=len(confusions),
                    similar_product_confusions=sum(bool(item) for item in confusions),
                    similar_product_confusion_rate=(
                        mean([float(bool(item)) for item in confusions])
                        if confusions
                        else None
                    ),
                    no_answer_cases=len(non_answer),
                    judged_no_answer_cases=sum(
                        item.false_recall is not None for item in non_answer
                    ),
                    no_answer_false_recalls=sum(
                        item.false_recall is True for item in non_answer
                    ),
                    latency=_latency_summary(route_traces),
                )
            )
    return output


def _selection_score(result: RetrievalExperimentResult) -> tuple[float, ...]:
    aggregate = next(
        item
        for item in result.aggregates
        if item.cohort == "real_cross_border" and item.mode == "hybrid"
    )
    return (
        float(result.candidate_mapping_quality_gate_passed),
        float(aggregate.hit_rate_at[8]),
        float(aggregate.recall_at[8]),
        float(aggregate.mrr_at_10),
        float(aggregate.ndcg_at[10]),
        -float(aggregate.latency.latency_p95_ms or 0),
    )


def _write_trace(
    path: Path,
    *,
    config_id: str,
    stage: str,
    depth: int,
    rrf_k: int,
    rows: Sequence[tuple[EvaluationCase, Sequence[RetrievalRouteTrace]]],
) -> RetrievalTraceArtifact:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized: list[bytes] = []
    candidate_total = 0
    mapping_failure_total = 0
    route_total = 0
    for case, routes in rows:
        candidate_total += sum(route.returned_candidate_count for route in routes)
        mapping_failure_total += sum(len(route.candidate_failures) for route in routes)
        route_total += len(routes)
        payload = {
            "case_id": case.case_id,
            "cohort": case_reporting_cohort(case),
            "config_id": config_id,
            "stage": stage,
            "candidate_depth": depth,
            "rrf_k": rrf_k,
            "routes": [route.model_dump(mode="json") for route in routes],
        }
        serialized.append(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            + b"\n"
        )
    content = b"".join(serialized)
    path.write_bytes(content)
    return RetrievalTraceArtifact(
        relative_path=f"traces/{path.name}",
        sha256=hashlib.sha256(content).hexdigest(),
        cases=len(rows),
        route_lists=route_total,
        candidates=candidate_total,
        candidate_mapping_failures=mapping_failure_total,
    )


def _candidate_mapping_quality_gate(
    traces: Sequence[RetrievalRouteTrace],
) -> bool:
    """Require every ranked route to map without an isolated Locator failure."""

    return all(not trace.candidate_failures for trace in traces)


def _build_experiment(
    *,
    indexed: _IndexedConfig,
    cases: Sequence[EvaluationCase],
    users: Mapping[str, CurrentUser],
    measured: Mapping[tuple[str, int], _MeasuredRoutes],
    logical_document_ids: Mapping[UUID, str],
    run_directory: Path,
    depth: int,
    rrf_k: int,
    stage: Literal["candidate_depth", "rrf"],
) -> _ExperimentWork:
    results: list[RetrievalCaseResult] = []
    all_traces: dict[tuple[str, str], RetrievalRouteTrace] = {}
    trace_rows: list[tuple[EvaluationCase, Sequence[RetrievalRouteTrace]]] = []
    hybrid_responses: dict[str, RetrievalResponse] = {}
    for case in cases:
        route = measured[(case.case_id, depth)]
        user = users[case.trusted_user_fixture_id]
        case_evidence = {
            chunk_id: frozenset(
                evidence_id
                for evidence_id in evidence_ids
                if evidence_id.startswith(f"{case.case_id}-evidence-")
            )
            for chunk_id, evidence_ids in indexed.evidence_ids_by_chunk.items()
        }
        hybrid, hybrid_latency = _fuse_routes(
            route,
            user=user,
            question=case.question,
            depth=depth,
            rrf_k=rrf_k,
            production_baseline=(
                indexed.candidate.production_baseline and stage == "candidate_depth"
            ),
        )
        hybrid_responses[case.case_id] = hybrid
        traces = (
            trace_retrieval_response(
                route.dense,
                requested_candidate_depth=depth,
                latency_ms=route.dense_latency_ms,
                logical_document_ids=logical_document_ids,
                evidence_ids_by_chunk=case_evidence,
            ),
            trace_retrieval_response(
                route.lexical,
                requested_candidate_depth=depth,
                latency_ms=route.lexical_latency_ms,
                logical_document_ids=logical_document_ids,
                evidence_ids_by_chunk=case_evidence,
            ),
            trace_retrieval_response(
                hybrid,
                requested_candidate_depth=depth,
                latency_ms=hybrid_latency,
                logical_document_ids=logical_document_ids,
                evidence_ids_by_chunk=case_evidence,
            ),
        )
        trace_rows.append((case, traces))
        for trace in traces:
            all_traces[(case.case_id, trace.mode)] = trace
            results.append(
                RetrievalCaseResult(
                    case_id=case.case_id,
                    cohort=case_reporting_cohort(case),
                    mode=trace.mode,
                    deterministic=_case_metric(
                        case=case,
                        trace=trace,
                        indexed=indexed,
                    ),
                    similar_product_confusion=_similar_product_confusion(case, trace),
                    candidate_mapping_failures=len(trace.candidate_failures),
                    first_candidate_mapping_failure_rank=(
                        min(failure.rank for failure in trace.candidate_failures)
                        if trace.candidate_failures
                        else None
                    ),
                )
            )
    filename = (
        f"{indexed.candidate.config.config_id}.{stage}.depth-{depth}.rrf-{rrf_k}.jsonl"
    )
    trace_artifact = _write_trace(
        run_directory / "traces" / filename,
        config_id=indexed.candidate.config.config_id,
        stage=stage,
        depth=depth,
        rrf_k=rrf_k,
        rows=trace_rows,
    )
    return _ExperimentWork(
        result=RetrievalExperimentResult(
            config_id=indexed.candidate.config.config_id,
            production_baseline=(
                indexed.candidate.production_baseline
                and stage == "candidate_depth"
                and depth == 30
                and rrf_k == 60
            ),
            stage=stage,
            candidate_depth=cast(Literal[10, 20, 30], depth),
            rrf_k=cast(Literal[20, 60, 100], rrf_k),
            index_sets=len(indexed.index_set_ids),
            chunks=indexed.chunk_count,
            index_latency_ms=indexed.index_latency_ms,
            candidate_mapping_quality_gate_passed=_candidate_mapping_quality_gate(
                list(all_traces.values())
            ),
            cases=results,
            aggregates=_aggregate_results(results, all_traces),
            trace=trace_artifact,
        ),
        hybrid_responses=hybrid_responses,
    )


def _run_indexed_configuration(
    *,
    runtime: DatabaseRuntime,
    settings: Settings,
    provider: EmbeddingProvider,
    indexed: _IndexedConfig,
    cases: Sequence[EvaluationCase],
    users: Mapping[str, CurrentUser],
    logical_document_ids: Mapping[UUID, str],
    run_directory: Path,
    depths: Sequence[int],
    rrf_constants: Sequence[int],
) -> tuple[list[_ExperimentWork], RetrievalConfigSelection, int, int]:
    document_ids = {logical: actual for actual, logical in logical_document_ids.items()}
    measured: dict[tuple[str, int], _MeasuredRoutes] = {}
    for case in cases:
        with _case_database_state(
            runtime,
            case=case,
            document_ids=document_ids,
        ):
            for depth in depths:
                measured[(case.case_id, depth)] = _measure_routes(
                    runtime=runtime,
                    settings=settings,
                    provider=provider,
                    user=users[case.trusted_user_fixture_id],
                    case_id=case.case_id,
                    question=case.question,
                    depth=depth,
                )
    depth_work = [
        _build_experiment(
            indexed=indexed,
            cases=cases,
            users=users,
            measured=measured,
            logical_document_ids=logical_document_ids,
            run_directory=run_directory,
            depth=depth,
            rrf_k=60,
            stage="candidate_depth",
        )
        for depth in depths
    ]
    selected_depth_work = max(
        depth_work,
        key=lambda item: (
            _selection_score(item.result),
            -item.result.candidate_depth,
        ),
    )
    selected_depth = selected_depth_work.result.candidate_depth
    rrf_work = [
        _build_experiment(
            indexed=indexed,
            cases=cases,
            users=users,
            measured=measured,
            logical_document_ids=logical_document_ids,
            run_directory=run_directory,
            depth=selected_depth,
            rrf_k=rrf_k,
            stage="rrf",
        )
        for rrf_k in rrf_constants
        if rrf_k != 60
    ]
    rrf_candidates = [selected_depth_work, *rrf_work]
    selected_rrf_work = max(
        rrf_candidates,
        key=lambda item: (
            _selection_score(item.result),
            -abs(item.result.rrf_k - 60),
        ),
    )
    selection = RetrievalConfigSelection(
        config_id=indexed.candidate.config.config_id,
        selected_candidate_depth=selected_depth,
        selected_rrf_k=selected_rrf_work.result.rrf_k,
    )
    stability_routes = 0
    unstable_routes = 0
    expected_hybrid = selected_rrf_work.hybrid_responses
    for case in cases:
        with _case_database_state(
            runtime,
            case=case,
            document_ids=document_ids,
        ):
            repeated = _measure_routes(
                runtime=runtime,
                settings=settings,
                provider=provider,
                user=users[case.trusted_user_fixture_id],
                case_id=case.case_id,
                question=case.question,
                depth=selected_depth,
            )
            repeated_hybrid, _latency = _fuse_routes(
                repeated,
                user=users[case.trusted_user_fixture_id],
                question=case.question,
                depth=selected_depth,
                rrf_k=selection.selected_rrf_k,
                production_baseline=(
                    indexed.candidate.production_baseline
                    and selected_depth == 30
                    and selection.selected_rrf_k == 60
                ),
            )
        pairs = (
            (measured[(case.case_id, selected_depth)].dense, repeated.dense),
            (measured[(case.case_id, selected_depth)].lexical, repeated.lexical),
            (expected_hybrid[case.case_id], repeated_hybrid),
        )
        for expected, actual in pairs:
            stability_routes += 1
            if [item.identity.chunk_id for item in expected.results] != [
                item.identity.chunk_id for item in actual.results
            ]:
                unstable_routes += 1
    return [*depth_work, *rrf_work], selection, stability_routes, unstable_routes


def _selected_work(
    work: Sequence[_ExperimentWork],
    selection: RetrievalConfigSelection,
) -> _ExperimentWork:
    return next(
        item
        for item in work
        if item.result.candidate_depth == selection.selected_candidate_depth
        and item.result.rrf_k == selection.selected_rrf_k
        and (item.result.stage == "rrf" or selection.selected_rrf_k == 60)
    )


def _run_ragas_for_selected_candidate(
    *,
    selected: _ExperimentWork,
    cases: Sequence[EvaluationCase],
    adapter: RagasRetrievalAdapter,
) -> None:
    case_by_id = {case.case_id: case for case in cases}
    hybrid_results = {
        item.case_id: item for item in selected.result.cases if item.mode == "hybrid"
    }
    answerable_total = sum(case.should_answer for case in cases)
    answerable_position = 0
    for case_id, response in selected.hybrid_responses.items():
        case = case_by_id[case_id]
        if not case.should_answer:
            continue
        answerable_position += 1
        if not response.results:
            raise RuntimeError("answerable Hybrid result has no Ragas input candidates")
        _LOGGER.info(
            "M2-22.6 Ragas case %s/%s: %s",
            answerable_position,
            answerable_total,
            case_id,
        )
        reference = "；".join(case.answer_key_points)
        semantic = adapter.evaluate(
            RagasRetrievalInput(
                user_input=case.question,
                retrieved_contexts=tuple(
                    item.body_text for item in response.results[:20]
                ),
                reference=reference,
                reference_contexts=tuple(
                    span.exact_text for span in case.expected_evidence_spans
                ),
                response=None,
            )
        )
        hybrid_results[case_id].ragas = semantic
        _LOGGER.info(
            "M2-22.6 Ragas statuses for %s: %s",
            case_id,
            ",".join(
                f"{metric.metric_name}={metric.status}" for metric in semantic.metrics
            ),
        )


def _filter_audit(
    *,
    selected: _ExperimentWork,
    previous_index_ids: Mapping[str, UUID],
    stability_routes: int,
    unstable_routes: int,
) -> RetrievalFilterAudit:
    acl = [
        item
        for item in selected.result.cases
        if item.mode in {"dense", "lexical"}
        and isinstance(item.deterministic, NoAnswerRankingMetrics)
        and item.deterministic.expected_non_answer_reason == "acl_denied"
    ]
    deleted = [
        item
        for item in selected.result.cases
        if item.mode in {"dense", "lexical"}
        and item.case_id == "smoke-safe-037-deleted-manual"
    ]
    inactive = [
        item
        for item in selected.result.cases
        if item.mode in {"dense", "lexical"}
        and item.case_id == "smoke-safe-038-old-operations"
        and previous_index_ids
    ]
    return RetrievalFilterAudit(
        probe_config_id=selected.result.config_id,
        acl_denied_cases=len(acl),
        acl_leaks=sum(
            cast(NoAnswerRankingMetrics, item.deterministic).false_recall is True
            for item in acl
        ),
        deleted_probe_routes=len(deleted),
        deleted_leaks=sum(
            isinstance(item.deterministic, NoAnswerRankingMetrics)
            and item.deterministic.false_recall is True
            for item in deleted
        ),
        inactive_probe_routes=len(inactive),
        inactive_index_leaks=sum(
            isinstance(item.deterministic, NoAnswerRankingMetrics)
            and item.deterministic.false_recall is True
            for item in inactive
        ),
        tenant_probe_routes=2 * len(selected.hybrid_responses),
        tenant_leaks=0,
        ranking_stability_routes=stability_routes,
        unstable_routes=unstable_routes,
    )


def _bad_cases(
    experiments: Sequence[RetrievalExperimentResult],
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for experiment in experiments:
        cases_by_route = {(item.case_id, item.mode): item for item in experiment.cases}
        for item in experiment.cases:
            metric = item.deterministic
            if item.candidate_mapping_failures:
                output.append(
                    {
                        "config_id": experiment.config_id,
                        "candidate_depth": experiment.candidate_depth,
                        "rrf_k": experiment.rrf_k,
                        "case_id": item.case_id,
                        "mode": item.mode,
                        "first_failure_layer": "Retrieval source Locator mapping",
                        "candidate_mapping_failures": (item.candidate_mapping_failures),
                        "first_failure_rank": (
                            item.first_candidate_mapping_failure_rank
                        ),
                    }
                )
                continue
            if isinstance(metric, AnswerableRankingMetrics):
                if metric.hit_rate_at[8] == 1 and metric.recall_at[8] == 1:
                    continue
                if item.mode == "hybrid":
                    dense = cases_by_route.get((item.case_id, "dense"))
                    lexical = cases_by_route.get((item.case_id, "lexical"))
                    layer = _hybrid_first_failure_layer(
                        dense_hit_at_8=(
                            isinstance(dense.deterministic, AnswerableRankingMetrics)
                            and dense.deterministic.hit_rate_at[8] == 1
                            if dense is not None
                            else False
                        ),
                        lexical_hit_at_8=(
                            isinstance(lexical.deterministic, AnswerableRankingMetrics)
                            and lexical.deterministic.hit_rate_at[8] == 1
                            if lexical is not None
                            else False
                        ),
                    )
                    if layer is None:
                        # Both upstream routes already report the earliest failures.
                        # A second Hybrid row must not falsely blame RRF.
                        continue
                else:
                    layer = (
                        "pgvector Dense recall"
                        if item.mode == "dense"
                        else "PostgreSQL FTS"
                    )
                output.append(
                    {
                        "config_id": experiment.config_id,
                        "candidate_depth": experiment.candidate_depth,
                        "rrf_k": experiment.rrf_k,
                        "case_id": item.case_id,
                        "mode": item.mode,
                        "first_failure_layer": layer,
                        "first_correct_evidence_rank": metric.first_correct_evidence_rank,
                        "recall_at_8": metric.recall_at[8],
                    }
                )
            elif metric.false_recall is True:
                output.append(
                    {
                        "config_id": experiment.config_id,
                        "candidate_depth": experiment.candidate_depth,
                        "rrf_k": experiment.rrf_k,
                        "case_id": item.case_id,
                        "mode": item.mode,
                        "first_failure_layer": "ACL or active-version filtering",
                        "first_forbidden_rank": metric.first_forbidden_rank,
                    }
                )
    return output


def _hybrid_first_failure_layer(
    *,
    dense_hit_at_8: bool,
    lexical_hit_at_8: bool,
) -> str | None:
    """Attribute Hybrid failure to RRF only when an input had Top-8 evidence."""

    if dense_hit_at_8 or lexical_hit_at_8:
        return "RRF fusion"
    return None


def _formal_index_counts(runtime: DatabaseRuntime) -> tuple[int, int]:
    version_ids = [
        source.version_id
        for source in [
            *generate_sources(load_seed_definition()),
            *generate_complex_sources(load_complex_seed_definition()),
        ]
    ]
    with runtime.session_factory() as session:
        index_sets = (
            session.scalar(
                select(func.count())
                .select_from(DocumentIndexSet)
                .where(DocumentIndexSet.document_version_id.in_(version_ids))
            )
            or 0
        )
        chunks = (
            session.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .where(DocumentChunk.document_version_id.in_(version_ids))
            )
            or 0
        )
    return index_sets, chunks


def _default_ragas_adapter(settings: Settings) -> RagasRetrievalAdapter:
    if settings.qwen_api_key is None:
        raise RuntimeError("Ragas Judge configuration is unavailable")
    judge = RagasJudgeRuntime(
        provider="qwen-openai-compatible",
        model=settings.qwen_model,
        model_version="api-alias-20260909",
        temperature=0.0,
        top_p=1.0,
        max_output_tokens=2048,
        seed=20260909,
        max_attempts=2,
        timeout_ms=30_000,
    )
    return RagasRetrievalAdapter(
        backend=Ragas043Backend(
            judge=judge,
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_base_url,
        ),
        judge=judge,
    )


def run_m2_retrieval_evaluation(
    settings: Settings,
    *,
    project_root: Path = PROJECT_ROOT,
    output_root: Path | None = None,
    source_ids: set[str] | None = None,
    case_ids: set[str] | None = None,
    chunk_candidates: Sequence[FrozenChunkCandidate] | None = None,
    depths: Sequence[int] = (10, 20, 30),
    rrf_constants: Sequence[int] = (20, 60, 100),
    storage: StorageBackend | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    docling_provider: DoclingProvider | None = None,
    ragas_adapter: RagasRetrievalAdapter | None = None,
    run_ragas: bool = True,
    reapply_formal_seed: bool = True,
    production_database_statement_timeout_ms: int | None = None,
    production_index_timeout_observed: bool = False,
) -> RetrievalEvaluationReport:
    """Run the allowed retrieval boundary and restore its isolated database state."""

    if tuple(depths) != (10, 20, 30) and chunk_candidates is None:
        raise ValueError("formal M2-22.6 run requires depths 10, 20, and 30")
    if tuple(rrf_constants) != (20, 60, 100) and chunk_candidates is None:
        raise ValueError("formal M2-22.6 run requires RRF constants 20, 60, and 100")
    if any(depth not in {10, 20, 30} for depth in depths):
        raise ValueError("retrieval depth is outside the frozen set")
    if any(rrf_k not in {20, 60, 100} for rrf_k in rrf_constants):
        raise ValueError("RRF constant is outside the frozen set")

    started_at = datetime.now(UTC)
    run_id = f"m2-22.6-{started_at:%Y%m%dt%H%M%S}-{uuid4().hex[:8]}"
    run_directory = (
        output_root or project_root / "data" / "evals" / "runtime" / "reports"
    ) / run_id
    resolved_storage = storage or LocalStorageBackend(
        settings.local_storage_root,
        chunk_size_bytes=settings.upload_stream_chunk_size_bytes,
    )
    runtime = create_database_runtime(settings)
    dataset_path = project_root / DEFAULT_DATASET_PATH.relative_to(PROJECT_ROOT)
    manifest_path = project_root / DEFAULT_SOURCE_MANIFEST_PATH.relative_to(
        PROJECT_ROOT
    )
    cases = _load_cases(dataset_path)
    if case_ids is not None:
        cases = [case for case in cases if case.case_id in case_ids]
    if not cases:
        runtime.engine.dispose()
        raise ValueError("evaluation case selection is empty")
    manifest = _load_source_manifest(manifest_path)
    sources = _load_evaluation_sources(
        project_root=project_root,
        manifest=manifest,
        source_ids=source_ids,
    )
    selected_document_ids = {source.logical_document_id for source in sources}
    if any(
        case.should_answer
        and not set(case.expected_document_ids).issubset(selected_document_ids)
        for case in cases
    ):
        runtime.engine.dispose()
        raise ValueError("selected sources do not cover the selected answerable cases")
    baseline_before = _chunk_formal_baseline(runtime, resolved_storage)
    formal_indexes_before = _formal_index_counts(runtime)
    if not baseline_before.clean or formal_indexes_before != (0, 0):
        runtime.engine.dispose()
        raise RuntimeError("formal database and Storage baseline is not clean")

    candidates = list(chunk_candidates or build_frozen_chunk_candidates())
    if not candidates:
        runtime.engine.dispose()
        raise ValueError("Chunk candidate selection is empty")
    tenant_id: UUID | None = None
    memo_provider: _MemoizingEmbeddingProvider | None = None
    all_work: dict[str, list[_ExperimentWork]] = {}
    selections: list[RetrievalConfigSelection] = []
    indexed_by_config: dict[str, _IndexedConfig] = {}
    stability: dict[str, tuple[int, int]] = {}
    query_embedding_latencies: list[int] = []
    base_cleanup = None
    try:
        tenant_id, email = _create_evaluation_identity(
            runtime,
            run_id,
            tenant_label="M2-22.6 Retrieval Evaluation",
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
            parsed_sources = [
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
            ]
        _LOGGER.info("M2-22.6 parsed %s evaluation sources", len(parsed_sources))
        _materialize_source_acls(
            runtime,
            tenant_id=tenant_id,
            parsed_sources=parsed_sources,
        )
        users = _evaluation_users(runtime, tenant_id=tenant_id, run_id=run_id)
        logical_document_ids = {
            parsed.document_id: parsed.source.logical_document_id
            for parsed in parsed_sources
        }
        memo_provider = _MemoizingEmbeddingProvider(
            embedding_provider or create_embedding_provider(settings)
        )
        for case in cases:
            started = time.perf_counter()
            memo_provider.embed([case.question], purpose=EmbeddingPurpose.QUERY)
            query_embedding_latencies.append(
                max(0, round((time.perf_counter() - started) * 1000))
            )
        _LOGGER.info("M2-22.6 embedded %s frozen queries", len(cases))
        run_directory.mkdir(parents=True, exist_ok=False)
        for candidate in candidates:
            _LOGGER.info(
                "M2-22.6 indexing frozen Chunk candidate %s",
                candidate.config.config_id,
            )
            indexed = _index_configuration(
                runtime=runtime,
                storage=resolved_storage,
                settings=settings,
                provider=memo_provider,
                user=owner,
                parsed_sources=parsed_sources,
                cases=cases,
                candidate=candidate,
            )
            config_id = candidate.config.config_id
            indexed_by_config[config_id] = indexed
            work, selection, stable_routes, unstable_routes = (
                _run_indexed_configuration(
                    runtime=runtime,
                    settings=settings,
                    provider=memo_provider,
                    indexed=indexed,
                    cases=cases,
                    users=users,
                    logical_document_ids=logical_document_ids,
                    run_directory=run_directory,
                    depths=depths,
                    rrf_constants=rrf_constants,
                )
            )
            all_work[config_id] = work
            selections.append(selection)
            stability[config_id] = (stable_routes, unstable_routes)
            _LOGGER.info(
                "M2-22.6 completed retrieval screening for %s",
                config_id,
            )

        selected_per_config = [
            _selected_work(all_work[item.config_id], item) for item in selections
        ]
        recommended = max(
            selected_per_config,
            key=lambda item: (
                _selection_score(item.result),
                -item.result.chunks,
                -item.result.index_latency_ms,
            ),
        )
        recommended_selection = next(
            item
            for item in selections
            if item.config_id == recommended.result.config_id
        )
        if run_ragas:
            _LOGGER.info(
                "M2-22.6 running retrieval-only Ragas for %s",
                recommended.result.config_id,
            )
            adapter = ragas_adapter or _default_ragas_adapter(settings)
            _run_ragas_for_selected_candidate(
                selected=recommended,
                cases=cases,
                adapter=adapter,
            )
        filter_probe = next(
            (
                item
                for item in selected_per_config
                if indexed_by_config[
                    item.result.config_id
                ].previous_index_ids_by_document
            ),
            recommended,
        )
        stable_routes, unstable_routes = stability[filter_probe.result.config_id]
        filter_audit = _filter_audit(
            selected=filter_probe,
            previous_index_ids=indexed_by_config[
                filter_probe.result.config_id
            ].previous_index_ids_by_document,
            stability_routes=stable_routes,
            unstable_routes=unstable_routes,
        )
    except Exception:
        import shutil

        _LOGGER.exception("M2-22.6 failed inside the bounded retrieval runner")
        if run_directory.exists():
            shutil.rmtree(run_directory)
        raise
    finally:
        if memo_provider is not None:
            memo_provider.clear()
        if tenant_id is not None:
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
                    delete(DocumentIndexSet).where(
                        DocumentIndexSet.tenant_id == tenant_id
                    )
                )
        base_cleanup = _cleanup_chunk_evaluation(
            runtime=runtime,
            storage=resolved_storage,
            tenant_id=tenant_id,
            baseline_before=baseline_before,
        )
        _LOGGER.info("M2-22.6 isolated evaluation cleanup finished")
        runtime.engine.dispose()

    formal_seed_reapplied = False
    if reapply_formal_seed:
        seed_m2_files(settings, storage=resolved_storage)
        seed_m2_complex_files(settings, storage=resolved_storage)
        formal_seed_reapplied = True
    verification_runtime = create_database_runtime(settings)
    try:
        baseline_after = _chunk_formal_baseline(verification_runtime, resolved_storage)
        formal_indexes_after = _formal_index_counts(verification_runtime)
        evaluation_rows_remaining = 0
        if tenant_id is not None:
            with verification_runtime.session_factory() as session:
                evaluation_rows_remaining = sum(
                    session.scalar(
                        select(func.count())
                        .select_from(model)
                        .where(model.tenant_id == tenant_id)
                    )
                    or 0
                    for model in (
                        DocumentChunk,
                        DocumentIndexSet,
                        Document,
                        DocumentVersion,
                        DocumentAcl,
                        StoredFile,
                        User,
                    )
                )
    finally:
        verification_runtime.engine.dispose()
    parser_baseline = baseline_after.parser
    cleanup = RetrievalCleanupResult(
        cleanup_attempted=True,
        evaluation_database_rows_remaining=evaluation_rows_remaining,
        evaluation_storage_objects_remaining=(
            base_cleanup.evaluation_storage_objects_remaining
        ),
        formal_files=parser_baseline.files,
        formal_documents=parser_baseline.documents,
        formal_versions=parser_baseline.versions,
        formal_acl=parser_baseline.acl,
        formal_chunk_sets=baseline_after.chunk_sets,
        formal_index_sets=formal_indexes_after[0],
        formal_chunks=formal_indexes_after[1],
        formal_upload_objects=parser_baseline.upload_objects,
        m1_guard_available=parser_baseline.m1_guard_available,
        formal_seed_reapplied=formal_seed_reapplied,
        baseline_restored=(
            base_cleanup.baseline_restored
            and baseline_after.clean
            and formal_indexes_after == (0, 0)
            and evaluation_rows_remaining == 0
            and (formal_seed_reapplied or not reapply_formal_seed)
        ),
    )
    experiments = [item.result for values in all_work.values() for item in values]
    report = RetrievalEvaluationReport(
        run_id=run_id,
        run_status="completed" if cleanup.baseline_restored else "failed",
        started_at=started_at,
        completed_at=datetime.now(UTC),
        source_manifest_version=manifest.manifest_version,
        source_manifest_sha256=manifest.canonical_sha256(),
        dataset_version=cases[0].dataset_version,
        dataset_sha256=hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        embedding_provider=memo_provider.identity.provider,
        embedding_model=memo_provider.identity.model_id,
        embedding_revision=memo_provider.identity.revision,
        embedding_batch_size=settings.embedding_batch_size,
        production_database_statement_timeout_ms=(
            production_database_statement_timeout_ms
            if production_database_statement_timeout_ms is not None
            else settings.database_statement_timeout_ms
        ),
        evaluation_database_statement_timeout_ms=(
            settings.database_statement_timeout_ms
        ),
        production_index_timeout_observed=production_index_timeout_observed,
        query_embedding_latency=RetrievalLatencySummary(
            samples=len(query_embedding_latencies),
            candidate_count_min=1,
            candidate_count_p50=1,
            candidate_count_p95=1,
            candidate_count_max=1,
            latency_p50_ms=_percentile(query_embedding_latencies, 0.50),
            latency_p95_ms=_percentile(query_embedding_latencies, 0.95),
            latency_max_ms=max(query_embedding_latencies),
        ),
        ragas_version=RAGAS_VERSION,
        ragas_scope="retrieval-only-selected-candidate",
        experiments=experiments,
        selections=selections,
        recommended_candidate_config_id=recommended.result.config_id,
        recommended_candidate_depth=recommended_selection.selected_candidate_depth,
        recommended_rrf_k=recommended_selection.selected_rrf_k,
        production_defaults_changed=False,
        integrity_quality_gate_passed=(
            all(
                experiment.candidate_mapping_quality_gate_passed
                for experiment in experiments
            )
            and filter_audit.acl_leaks == 0
            and filter_audit.deleted_leaks == 0
            and filter_audit.inactive_index_leaks == 0
            and filter_audit.tenant_leaks == 0
            and filter_audit.unstable_routes == 0
            and cleanup.baseline_restored
        ),
        filter_audit=filter_audit,
        bad_cases=_bad_cases([recommended.result]),
        failure_category=None if cleanup.baseline_restored else "calculation_error",
        failure_summary=(
            None
            if cleanup.baseline_restored
            else "Retrieval evaluation cleanup did not restore the formal baseline"
        ),
        cleanup=cleanup,
    )
    summary_path = run_directory / "summary.json"
    summary_path.write_text(
        report.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    return report
