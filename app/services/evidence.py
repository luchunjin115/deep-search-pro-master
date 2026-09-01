"""Persist validated M1 database and M2 document Evidence safely."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol, cast
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import (
    EvidenceNotFoundError,
    EvidencePersistenceError,
    EvidenceReadError,
    KnowledgeEvidencePersistenceError,
)
from app.models.runtime import ContextArtifact, Evidence
from app.repositories.evidence import KnowledgeEvidenceRepository
from app.repositories.retrieval import ContextChunkRehydrationError
from app.schemas.auth import CurrentUser
from app.schemas.context import (
    CONTEXT_BUNDLE_CONTRACT_VERSION,
    CONTEXT_TOKEN_COUNTER_VERSION,
    ContextBundle,
)
from app.schemas.evidence import (
    DocumentEvidenceDetail,
    EvidenceAccessScope,
    EvidenceDetail,
    EvidenceSummary,
    InventoryEvidenceQuery,
)
from app.schemas.inventory import InventoryResult, SearchInventoryInput
from app.services.retrieval.context import BuiltContext, validate_built_context


@dataclass(frozen=True, slots=True)
class EvidenceWriteContext:
    """Trusted runtime IDs required by the Evidence foreign-key chain."""

    tenant_id: UUID
    agent_run_id: UUID
    tool_call_id: UUID


@dataclass(frozen=True, slots=True)
class PersistedDocumentContext:
    """One verified Bundle and its aligned persistent document Evidence."""

    bundle: ContextBundle
    evidences: tuple[DocumentEvidenceDetail, ...]
    reused: bool


class EvidenceService:
    """Persist typed database or document Evidence without committing requests."""

    def __init__(
        self,
        session: Session,
        *,
        knowledge_repository: KnowledgeEvidenceRepository | None = None,
    ) -> None:
        self._session = session
        self._knowledge_repository = (
            knowledge_repository or KnowledgeEvidenceRepository(session)
        )

    def persist_inventory_evidence(
        self,
        context: EvidenceWriteContext,
        request: SearchInventoryInput,
        inventory: InventoryResult,
        snapshot_id: UUID,
    ) -> EvidenceDetail:
        """Persist and return the exact database fact supporting an inventory result."""

        evidence_id = uuid4()
        created_at = datetime.now(UTC)
        query_summary = InventoryEvidenceQuery(
            sku=request.sku,
            market_code=request.market_code,
            warehouse_code=inventory.warehouse_code,
        )
        access_scope = EvidenceAccessScope(
            tenant_id=context.tenant_id,
            market_codes=[inventory.market_code],
        )
        source_locator = f"inventory_snapshots/{snapshot_id}"
        title = f"{inventory.warehouse_code} {inventory.product_name}库存"
        excerpt = (
            f"SKU {inventory.sku}可售库存{inventory.available}件，"
            f"数据时间{inventory.snapshot_at.isoformat()}"
        )
        confidence = Decimal("1.000")

        evidence_row = Evidence(
            id=evidence_id,
            tenant_id=context.tenant_id,
            agent_run_id=context.agent_run_id,
            tool_call_id=context.tool_call_id,
            source_type="database",
            source_name="synthetic_inventory",
            source_locator=source_locator,
            title=title,
            excerpt=excerpt,
            query_summary=query_summary.model_dump(mode="json"),
            structured_data=inventory.model_dump(mode="json"),
            observed_at=inventory.snapshot_at,
            confidence=confidence,
            trust_level="internal_demo",
            access_scope=access_scope.model_dump(mode="json"),
            synthetic_data=True,
            created_at=created_at,
        )

        try:
            self._session.add(evidence_row)
            self._session.flush()
            return EvidenceDetail(
                id=evidence_id,
                source_type="database",
                source_name="synthetic_inventory",
                source_locator=source_locator,
                title=title,
                excerpt=excerpt,
                query_summary=query_summary,
                structured_data=inventory,
                observed_at=inventory.snapshot_at,
                confidence=confidence,
                trust_level="internal_demo",
                access_scope=access_scope,
                synthetic_data=True,
                created_at=created_at,
            )
        except (SQLAlchemyError, ValidationError):
            raise EvidencePersistenceError from None

    def persist_document_context(
        self,
        current_user: CurrentUser,
        built: BuiltContext,
        *,
        runtime_context: EvidenceWriteContext | None = None,
    ) -> PersistedDocumentContext:
        """Atomically persist one deterministic Context and all of its Evidence."""

        try:
            with self._session.begin_nested():
                validate_built_context(current_user, built)
                if runtime_context is not None and (
                    not isinstance(runtime_context, EvidenceWriteContext)
                    or runtime_context.tenant_id != current_user.tenant_id
                ):
                    raise ValueError(
                        "runtime Context does not match the current tenant"
                    )
                trusted_sources = self._knowledge_repository.reauthorize_sources(
                    current_user,
                    built.sources,
                )
                if trusted_sources != built.sources:
                    raise ValueError("Context sources changed before persistence")

                context_values = _context_artifact_values(current_user, built)
                inserted = self._knowledge_repository.insert_context_artifact(
                    context_values
                )
                context_row = self._knowledge_repository.find_context_artifact(
                    tenant_id=current_user.tenant_id,
                    user_id=current_user.user_id,
                    identity_sha256=built.identity_sha256,
                )
                if context_row is None or not _context_row_matches(
                    context_row,
                    context_values,
                ):
                    raise ValueError("persistent Context identity conflicts")

                observed_at = datetime.now(UTC)
                evidence_values = _document_evidence_values(
                    current_user,
                    built,
                    observed_at=observed_at,
                    runtime_context=runtime_context,
                )
                self._knowledge_repository.insert_document_evidences(evidence_values)
                evidence_rows = self._knowledge_repository.list_document_evidences(
                    tenant_id=current_user.tenant_id,
                    context_id=built.bundle.context_id,
                )
                if not _evidence_rows_match(evidence_rows, evidence_values):
                    raise ValueError("persistent document Evidence conflicts")
                details = _document_evidence_details(built, evidence_rows)
        except (
            ContextChunkRehydrationError,
            SQLAlchemyError,
            ValidationError,
            TypeError,
            ValueError,
        ):
            raise KnowledgeEvidencePersistenceError from None

        return PersistedDocumentContext(
            bundle=built.bundle,
            evidences=details,
            reused=not inserted,
        )


def _context_artifact_values(
    current_user: CurrentUser,
    built: BuiltContext,
) -> dict[str, object]:
    bundle = built.bundle
    return {
        "id": bundle.context_id,
        "tenant_id": current_user.tenant_id,
        "requested_by_user_id": current_user.user_id,
        "contract_version": CONTEXT_BUNDLE_CONTRACT_VERSION,
        "token_counter_version": CONTEXT_TOKEN_COUNTER_VERSION,
        "query_sha256": bundle.query_sha256,
        "retrieval_snapshot_json": built.retrieval_snapshot,
        "retrieval_snapshot_sha256": built.retrieval_snapshot_sha256,
        "config_json": built.config,
        "config_sha256": built.config_sha256,
        "context_sha256": bundle.context_sha256,
        "identity_sha256": built.identity_sha256,
        "max_tokens": bundle.max_tokens,
        "total_tokens": bundle.total_tokens,
        "segment_count": len(bundle.segments),
    }


def _context_row_matches(
    row: ContextArtifact,
    expected: dict[str, object],
) -> bool:
    return all(getattr(row, field) == value for field, value in expected.items())


def _document_evidence_values(
    current_user: CurrentUser,
    built: BuiltContext,
    *,
    observed_at: datetime,
    runtime_context: EvidenceWriteContext | None,
) -> list[dict[str, object]]:
    values: list[dict[str, object]] = []
    for ordinal, (segment, source) in enumerate(
        zip(built.bundle.segments, built.sources, strict=True),
        start=1,
    ):
        values.append(
            {
                "id": segment.evidence_id,
                "tenant_id": current_user.tenant_id,
                "agent_run_id": (
                    runtime_context.agent_run_id
                    if runtime_context is not None
                    else None
                ),
                "tool_call_id": (
                    runtime_context.tool_call_id
                    if runtime_context is not None
                    else None
                ),
                "evidence_schema_version": "m2-document-evidence-v1",
                "source_type": segment.source_type,
                "source_name": "document_chunk",
                "source_locator": None,
                "source_locator_json": segment.source_locator.model_dump(mode="json"),
                "title": segment.document.title,
                "excerpt": segment.text[:1000],
                "query_summary": None,
                "structured_data": None,
                "observed_at": observed_at,
                "confidence": None,
                "trust_level": "document_snapshot",
                "access_scope": None,
                "context_artifact_id": built.bundle.context_id,
                "citation_ordinal": ordinal,
                "file_id": source.file_id,
                "document_id": source.document_id,
                "document_version_id": source.version_id,
                "document_chunk_set_id": source.chunk_set_id,
                "document_index_set_id": source.index_set_id,
                "document_chunk_id": source.chunk_id,
                "source_content_sha256": source.content_sha256,
                "context_text_sha256": segment.text_sha256,
                "synthetic_data": True,
            }
        )
    return values


def _evidence_rows_match(
    rows: list[Evidence],
    expected_values: list[dict[str, object]],
) -> bool:
    if len(rows) != len(expected_values):
        return False
    stable_fields = (
        "id",
        "tenant_id",
        "agent_run_id",
        "tool_call_id",
        "evidence_schema_version",
        "source_type",
        "source_name",
        "source_locator",
        "source_locator_json",
        "title",
        "excerpt",
        "query_summary",
        "structured_data",
        "confidence",
        "trust_level",
        "access_scope",
        "context_artifact_id",
        "citation_ordinal",
        "file_id",
        "document_id",
        "document_version_id",
        "document_chunk_set_id",
        "document_index_set_id",
        "document_chunk_id",
        "source_content_sha256",
        "context_text_sha256",
        "synthetic_data",
    )
    return all(
        all(getattr(row, field) == expected[field] for field in stable_fields)
        for row, expected in zip(rows, expected_values, strict=True)
    )


def _document_evidence_details(
    built: BuiltContext,
    rows: list[Evidence],
) -> tuple[DocumentEvidenceDetail, ...]:
    return tuple(
        DocumentEvidenceDetail(
            id=row.id,
            source_type=segment.source_type,
            title=row.title,
            excerpt=row.excerpt,
            observed_at=row.observed_at,
            context_id=built.bundle.context_id,
            citation_label=segment.citation_label,
            identity=segment.identity,
            document=segment.document,
            source_locator=segment.source_locator,
            source_content_sha256=cast(str, row.source_content_sha256),
            context_text_sha256=cast(str, row.context_text_sha256),
            trust_level="document_snapshot",
            synthetic_data=True,
            created_at=row.created_at,
        )
        for segment, row in zip(built.bundle.segments, rows, strict=True)
    )


class EvidenceReader(Protocol):
    """The only tenant-scoped Evidence read needed by M1 HTTP routes."""

    def find_by_id(self, *, tenant_id: UUID, evidence_id: UUID) -> Evidence | None: ...


class EvidenceQueryService:
    """Hide absent, cross-tenant, and out-of-market Evidence identically."""

    def __init__(self, repository: EvidenceReader) -> None:
        self._repository = repository

    def get_detail(self, user: CurrentUser, evidence_id: UUID) -> EvidenceDetail:
        try:
            row = self._repository.find_by_id(
                tenant_id=user.tenant_id,
                evidence_id=evidence_id,
            )
        except SQLAlchemyError:
            raise EvidenceReadError from None
        if row is None:
            raise EvidenceNotFoundError

        try:
            detail = EvidenceDetail.model_validate(
                {
                    "id": row.id,
                    "source_type": row.source_type,
                    "source_name": row.source_name,
                    "source_locator": row.source_locator,
                    "title": row.title,
                    "excerpt": row.excerpt,
                    "query_summary": row.query_summary,
                    "structured_data": row.structured_data,
                    "observed_at": row.observed_at,
                    "confidence": row.confidence,
                    "trust_level": row.trust_level,
                    "access_scope": row.access_scope,
                    "synthetic_data": row.synthetic_data,
                    "created_at": row.created_at,
                }
            )
        except ValidationError:
            raise EvidenceReadError from None

        if detail.access_scope.tenant_id != user.tenant_id or not set(
            detail.access_scope.market_codes
        ).issubset(user.market_scopes):
            raise EvidenceNotFoundError
        return detail

    def get_summaries(
        self,
        user: CurrentUser,
        evidence_ids: list[UUID],
    ) -> list[EvidenceSummary]:
        return [
            EvidenceSummary(
                id=detail.id,
                source_type=detail.source_type,
                source_name=detail.source_name,
                title=detail.title,
                excerpt=detail.excerpt,
                observed_at=detail.observed_at,
                synthetic_data=True,
            )
            for detail in (
                self.get_detail(user, evidence_id) for evidence_id in evidence_ids
            )
        ]
