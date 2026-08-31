"""Transactional Chunk Set claiming, immutable publication, and compensation."""

from __future__ import annotations

import hashlib
import io
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import (
    DocumentChunkPublicationError,
    DocumentNotFoundError,
    DocumentStateConflictError,
    KnowledgePersistenceError,
)
from app.repositories.documents import DocumentRepository
from app.schemas.auth import CurrentUser
from app.schemas.knowledge import DocumentChunkSetPublication
from app.services.documents.chunking.contracts import (
    CHUNK_ARTIFACT_SCHEMA_VERSION,
    CHUNK_CONTENT_HASH_VERSION,
    CanonicalChunkArtifact,
    ChunkerIdentity,
    ChunkingConfig,
    ChunkInputProvenance,
    build_chunk_artifact,
    canonical_sha256,
    derive_chunk_set_id,
)
from app.services.documents.chunking.tables import StructureAwareDocumentChunker
from app.services.documents.chunking.token_counting import UnicodeMixedTokenCounter
from app.services.documents.routing import RoutedParseResult
from app.services.storage import (
    StorageBackend,
    StorageError,
    StorageObjectAlreadyExistsError,
)

if TYPE_CHECKING:
    from app.core.config import Settings

_JSON_CONTENT_TYPE = "application/json"
_FAILURE_MESSAGE = "文档切块失败"
_PARSED_ARTIFACT_EXPANSION_FACTOR = 4


@dataclass(frozen=True, slots=True)
class _ParsedInput:
    tenant_id: UUID
    document_id: UUID
    version_id: UUID
    parsed_storage_key: str
    source_sha256: str
    parsed_publication_sha256: str
    routed: RoutedParseResult


@dataclass(frozen=True, slots=True)
class _ChunkClaim:
    tenant_id: UUID
    document_id: UUID
    version_id: UUID
    chunk_set_id: UUID


@dataclass(frozen=True, slots=True)
class _ChunkPlan:
    provenance: ChunkInputProvenance
    config_json: dict[str, object]
    config_sha256: str
    chunk_set_id: UUID


class DocumentChunkService:
    """Publish deterministic Chunk Artifacts around short DB transactions."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        storage: StorageBackend,
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage
        self._settings = settings
        self._config = ChunkingConfig.from_settings(settings)
        self._counter = UnicodeMixedTokenCounter()
        self._identity = ChunkerIdentity(
            token_counter_name=self._counter.name,
            token_counter_version=self._counter.version,
        )
        self._chunker = StructureAwareDocumentChunker(
            config=self._config,
            token_counter=self._counter,
        )
        self._clock = clock or (lambda: datetime.now(UTC))

    def chunk_version(
        self,
        user: CurrentUser,
        *,
        document_id: UUID,
        version_id: UUID,
    ) -> DocumentChunkSetPublication:
        """Load, claim, chunk, publish, and close one parsed document version."""

        parsed = self._load_parsed_input(
            user,
            document_id=document_id,
            version_id=version_id,
        )
        selected = parsed.routed.selected_artifact
        plan = self._build_plan(parsed)
        claim = self._claim(
            user,
            parsed=parsed,
            chunk_set_id=plan.chunk_set_id,
            config_json=plan.config_json,
            config_sha256=plan.config_sha256,
        )

        published_key: str | None = None
        try:
            result = self._chunker.chunk(selected)
            artifact = build_chunk_artifact(
                input_provenance=plan.provenance,
                chunker=self._identity,
                config=self._config,
                chunks=result.chunks,
                excluded_spans=result.excluded_spans,
                skipped_tables=result.skipped_tables,
            )
            if artifact.chunk_set_id != claim.chunk_set_id:
                raise DocumentChunkPublicationError
            payload = artifact.model_dump_json().encode("utf-8")
            published_key = self._publish(claim, payload)
            self._complete(
                claim,
                output_sha256=artifact.output_sha256,
                chunk_storage_key=published_key,
                chunk_count=artifact.statistics.chunk_count,
                text_chunk_count=artifact.statistics.text_chunk_count,
                table_chunk_count=artifact.statistics.table_chunk_count,
                total_token_count=artifact.statistics.total_token_count,
                excluded_span_count=artifact.statistics.excluded_span_count,
            )
            return DocumentChunkSetPublication(
                chunk_set_id=artifact.chunk_set_id,
                document_id=document_id,
                version_id=version_id,
                config_sha256=artifact.config_sha256,
                output_sha256=artifact.output_sha256,
                chunk_count=artifact.statistics.chunk_count,
                text_chunk_count=artifact.statistics.text_chunk_count,
                table_chunk_count=artifact.statistics.table_chunk_count,
                total_token_count=artifact.statistics.total_token_count,
                excluded_span_count=artifact.statistics.excluded_span_count,
            )
        except Exception:  # noqa: BLE001 - all post-claim failures close safely.
            if published_key is not None:
                try:
                    self._storage.delete(published_key)
                except StorageError:
                    pass
            self._record_failure(claim)
            raise DocumentChunkPublicationError from None

    def ensure_chunk_version(
        self,
        user: CurrentUser,
        *,
        document_id: UUID,
        version_id: UUID,
    ) -> CanonicalChunkArtifact:
        """Reuse one verified ready artifact or publish the current identity."""

        parsed = self._load_parsed_input(
            user,
            document_id=document_id,
            version_id=version_id,
        )
        plan = self._build_plan(parsed)
        ready = self._load_ready_artifact(parsed, plan)
        if ready is not None:
            return ready
        self.chunk_version(
            user,
            document_id=document_id,
            version_id=version_id,
        )
        ready = self._load_ready_artifact(parsed, plan)
        if ready is None:
            raise DocumentChunkPublicationError
        return ready

    def _build_plan(self, parsed: _ParsedInput) -> _ChunkPlan:
        selected = parsed.routed.selected_artifact
        provenance = ChunkInputProvenance(
            document_id=parsed.document_id,
            document_version_id=parsed.version_id,
            source_sha256=parsed.source_sha256,
            parsed_publication_sha256=parsed.parsed_publication_sha256,
            selected_artifact_content_sha256=selected.content_sha256,
        )
        config_json = self._config.model_dump(mode="json")
        config_sha256 = canonical_sha256(config_json)
        return _ChunkPlan(
            provenance=provenance,
            config_json=config_json,
            config_sha256=config_sha256,
            chunk_set_id=derive_chunk_set_id(
                input_provenance=provenance,
                chunker=self._identity,
                config_sha256=config_sha256,
            ),
        )

    def _load_ready_artifact(
        self,
        parsed: _ParsedInput,
        plan: _ChunkPlan,
    ) -> CanonicalChunkArtifact | None:
        session = self._session_factory()
        try:
            row = DocumentRepository(
                session,
                self._settings.database_statement_timeout_ms,
            ).find_chunk_set(
                chunk_set_id=plan.chunk_set_id,
                tenant_id=parsed.tenant_id,
                document_id=parsed.document_id,
                version_id=parsed.version_id,
            )
            if row is None or row.status != "ready":
                return None
            if row.chunk_storage_key is None:
                raise DocumentChunkPublicationError
            storage_key = row.chunk_storage_key
        except SQLAlchemyError:
            raise KnowledgePersistenceError from None
        finally:
            session.close()

        maximum_bytes = self._settings.upload_max_file_size_bytes * 8
        try:
            with self._storage.open(storage_key) as stream:
                payload = stream.read(maximum_bytes + 1)
            if not isinstance(payload, bytes) or len(payload) > maximum_bytes:
                raise DocumentChunkPublicationError
            artifact = CanonicalChunkArtifact.model_validate_json(payload)
        except (StorageError, ValidationError, DocumentChunkPublicationError):
            raise DocumentChunkPublicationError from None
        except Exception:  # noqa: BLE001 - streams may raise private exceptions.
            raise DocumentChunkPublicationError from None

        statistics = artifact.statistics
        if (
            artifact.chunk_set_id != plan.chunk_set_id
            or artifact.input != plan.provenance
            or artifact.chunker != self._identity
            or artifact.config.model_dump(mode="json") != plan.config_json
            or artifact.config_sha256 != plan.config_sha256
            or row.output_sha256 != artifact.output_sha256
            or row.chunk_count != statistics.chunk_count
            or row.text_chunk_count != statistics.text_chunk_count
            or row.table_chunk_count != statistics.table_chunk_count
            or row.total_token_count != statistics.total_token_count
            or row.excluded_span_count != statistics.excluded_span_count
        ):
            raise DocumentChunkPublicationError
        return artifact

    def _load_parsed_input(
        self,
        user: CurrentUser,
        *,
        document_id: UUID,
        version_id: UUID,
    ) -> _ParsedInput:
        session = self._session_factory()
        try:
            documents = DocumentRepository(
                session,
                self._settings.database_statement_timeout_ms,
            )
            document = documents.find_manageable_by_id(
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                company_owner="company_owner" in user.roles,
                document_id=document_id,
            )
            if document is None:
                raise DocumentNotFoundError
            version = documents.find_version(
                tenant_id=user.tenant_id,
                document_id=document_id,
                version_id=version_id,
            )
            if version is None:
                raise DocumentNotFoundError
            if version.parse_status != "ready" or version.parsed_storage_key is None:
                raise DocumentStateConflictError
            parsed_storage_key = version.parsed_storage_key
            source_sha256 = version.content_hash
        except (DocumentNotFoundError, DocumentStateConflictError):
            session.rollback()
            raise
        except SQLAlchemyError:
            session.rollback()
            raise KnowledgePersistenceError from None
        finally:
            session.close()

        maximum_bytes = (
            self._settings.upload_max_file_size_bytes
            * _PARSED_ARTIFACT_EXPANSION_FACTOR
        )
        try:
            with self._storage.open(parsed_storage_key) as stream:
                payload = stream.read(maximum_bytes + 1)
            if not isinstance(payload, bytes) or len(payload) > maximum_bytes:
                raise DocumentChunkPublicationError
            routed = RoutedParseResult.model_validate_json(payload)
        except (StorageError, ValidationError, DocumentChunkPublicationError):
            raise DocumentChunkPublicationError from None
        except Exception:  # noqa: BLE001 - streams may raise private exceptions.
            raise DocumentChunkPublicationError from None

        if routed.selected_artifact.source_sha256 != source_sha256:
            raise DocumentChunkPublicationError
        return _ParsedInput(
            tenant_id=user.tenant_id,
            document_id=document_id,
            version_id=version_id,
            parsed_storage_key=parsed_storage_key,
            source_sha256=source_sha256,
            parsed_publication_sha256=hashlib.sha256(payload).hexdigest(),
            routed=routed,
        )

    def _claim(
        self,
        user: CurrentUser,
        *,
        parsed: _ParsedInput,
        chunk_set_id: UUID,
        config_json: dict[str, object],
        config_sha256: str,
    ) -> _ChunkClaim:
        claimed_at = self._now()
        selected = parsed.routed.selected_artifact
        session = self._session_factory()
        try:
            documents = DocumentRepository(
                session,
                self._settings.database_statement_timeout_ms,
            )
            document = documents.find_manageable_by_id(
                tenant_id=user.tenant_id,
                user_id=user.user_id,
                company_owner="company_owner" in user.roles,
                document_id=parsed.document_id,
            )
            if document is None:
                raise DocumentNotFoundError
            version = documents.find_version(
                tenant_id=parsed.tenant_id,
                document_id=parsed.document_id,
                version_id=parsed.version_id,
            )
            if version is None:
                raise DocumentNotFoundError
            if (
                version.parse_status != "ready"
                or version.parsed_storage_key != parsed.parsed_storage_key
                or version.content_hash != parsed.source_sha256
            ):
                raise DocumentStateConflictError
            row = documents.claim_chunk_set(
                chunk_set_id=chunk_set_id,
                tenant_id=parsed.tenant_id,
                document_id=parsed.document_id,
                version_id=parsed.version_id,
                artifact_schema_version=CHUNK_ARTIFACT_SCHEMA_VERSION,
                content_hash_version=CHUNK_CONTENT_HASH_VERSION,
                routed_schema_version=parsed.routed.schema_version,
                canonical_schema_version=selected.schema_version,
                source_sha256=parsed.source_sha256,
                parsed_publication_sha256=parsed.parsed_publication_sha256,
                selected_artifact_content_sha256=selected.content_sha256,
                chunker_name=self._identity.name,
                chunker_version=self._identity.version,
                token_counter_name=self._identity.token_counter_name,
                token_counter_version=self._identity.token_counter_version,
                normalization_version=self._config.normalization_version,
                config_json=config_json,
                config_sha256=config_sha256,
                claimed_at=claimed_at,
            )
            if row is None:
                raise DocumentStateConflictError
            session.commit()
            return _ChunkClaim(
                tenant_id=parsed.tenant_id,
                document_id=parsed.document_id,
                version_id=parsed.version_id,
                chunk_set_id=chunk_set_id,
            )
        except (DocumentNotFoundError, DocumentStateConflictError):
            session.rollback()
            raise
        except SQLAlchemyError:
            session.rollback()
            raise KnowledgePersistenceError from None
        finally:
            session.close()

    def _publish(self, claim: _ChunkClaim, payload: bytes) -> str:
        key = self._chunk_key(claim)
        expected_sha256 = hashlib.sha256(payload).hexdigest()
        try:
            stored = self._storage.put(key, io.BytesIO(payload), _JSON_CONTENT_TYPE)
        except StorageObjectAlreadyExistsError:
            try:
                with self._storage.open(key) as stream:
                    existing = stream.read(len(payload) + 1)
            except StorageError:
                raise DocumentChunkPublicationError from None
            if existing != payload:
                raise DocumentChunkPublicationError
            return key
        except StorageError:
            raise DocumentChunkPublicationError from None

        if (
            stored.key != key
            or stored.size_bytes != len(payload)
            or stored.sha256 != expected_sha256
            or stored.content_type != _JSON_CONTENT_TYPE
        ):
            try:
                self._storage.delete(key)
            except StorageError:
                pass
            raise DocumentChunkPublicationError
        return key

    def _complete(
        self,
        claim: _ChunkClaim,
        *,
        output_sha256: str,
        chunk_storage_key: str,
        chunk_count: int,
        text_chunk_count: int,
        table_chunk_count: int,
        total_token_count: int,
        excluded_span_count: int,
    ) -> None:
        session = self._session_factory()
        try:
            row = DocumentRepository(
                session,
                self._settings.database_statement_timeout_ms,
            ).complete_chunk_set(
                chunk_set_id=claim.chunk_set_id,
                tenant_id=claim.tenant_id,
                document_id=claim.document_id,
                version_id=claim.version_id,
                output_sha256=output_sha256,
                chunk_storage_key=chunk_storage_key,
                chunk_count=chunk_count,
                text_chunk_count=text_chunk_count,
                table_chunk_count=table_chunk_count,
                total_token_count=total_token_count,
                excluded_span_count=excluded_span_count,
                completed_at=self._now(),
            )
            if row is None:
                raise DocumentStateConflictError
            session.commit()
        except DocumentStateConflictError:
            session.rollback()
            raise
        except SQLAlchemyError:
            session.rollback()
            raise KnowledgePersistenceError from None
        finally:
            session.close()

    def _record_failure(self, claim: _ChunkClaim) -> None:
        session = self._session_factory()
        try:
            DocumentRepository(
                session,
                self._settings.database_statement_timeout_ms,
            ).fail_chunk_set(
                chunk_set_id=claim.chunk_set_id,
                tenant_id=claim.tenant_id,
                document_id=claim.document_id,
                version_id=claim.version_id,
                error_message=_FAILURE_MESSAGE,
                completed_at=self._now(),
            )
            session.commit()
        except Exception:  # noqa: BLE001 - preserve the original safe failure.
            session.rollback()
        finally:
            session.close()

    def _chunk_key(self, claim: _ChunkClaim) -> str:
        now = self._now()
        return f"{claim.tenant_id}/chunks/{now:%Y}/{now:%m}/{claim.chunk_set_id}.json"

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise DocumentChunkPublicationError
        return now
