from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import select

from app.models.identity import User
from app.models.knowledge import (
    Document,
    DocumentAcl,
    DocumentChunk,
    DocumentChunkSet,
    DocumentIndexSet,
    DocumentVersion,
    StoredFile,
)
from app.models.runtime import ContextArtifact, Evidence, ToolCall
from app.repositories.evidence import EvidenceRepository
from app.repositories.files import FileRepository
from app.runtime.budget import BudgetLimits, ExecutionBudget
from app.runtime.context import RunContext, build_run_context
from app.runtime.executor import HarnessExecutor
from app.runtime.permissions import PermissionGuard
from app.schemas.auth import CurrentUser
from app.schemas.common import ToolEnvelope
from app.schemas.evidence import GetEvidenceDetailInput, GetEvidenceDetailResult
from app.schemas.file_reading import ReadUploadedFileResult
from app.schemas.files import ReadUploadedFileInput
from app.services.documents.parsers import PdfParser
from app.services.documents.parsers.native import adapt_native_parse_result
from app.services.documents.quality import decide_parse_route
from app.services.documents.routing import RoutedParseResult
from app.services.evidence import EvidenceQueryService, EvidenceService
from app.services.file_reading import FileReadingService
from app.services.storage import LocalStorageBackend
from app.tools.get_evidence_detail import GetEvidenceDetailTool
from app.tools.read_uploaded_file import ReadUploadedFileTool
from app.tools.registry import create_m2_tool_registry
from tests.fixtures.pdf_factory import make_text_pdf
from tests.integration import test_retrieval_repository_scope as scope_support
from tests.integration.test_agent_tools import AgentToolFixture, load_calls
from tests.integration.test_knowledge_evidence_service import _build_one
from tests.integration.test_retrieval_repository_scope import RetrievalScopeFixture

AccessMode = Literal["owner", "company_owner", "user", "role", "market"]
InvalidState = Literal[
    "acl_revoked",
    "document_deleted",
    "file_deleted",
    "version_inactive",
    "index_inactive",
    "context_requester_changed",
]


@dataclass(slots=True)
class MatrixRunResult:
    run_id: UUID
    file_envelope: ToolEnvelope[ReadUploadedFileResult] | None = None
    evidence_envelope: ToolEnvelope[GetEvidenceDetailResult] | None = None


@dataclass(slots=True)
class M2FileEvidenceToolMatrix:
    """Committed Harness identity plus rollback-only M2 business rows and Storage."""

    fixture: AgentToolFixture
    user: CurrentUser
    context: RunContext
    storage: LocalStorageBackend
    file_service: FileReadingService
    evidence_service: EvidenceQueryService
    file_row: StoredFile
    document: Document
    version: DocumentVersion
    index_set: DocumentIndexSet
    chunk: DocumentChunk
    evidence_id: UUID
    parsed_storage_key: str
    other_owner_id: UUID

    @classmethod
    def create(
        cls,
        fixture: AgentToolFixture,
        storage_root: Path,
        *,
        role: Literal["company_owner", "product_scout", "amazon_operator"],
        access_mode: AccessMode,
    ) -> M2FileEvidenceToolMatrix:
        session = fixture.business_session
        user = CurrentUser(
            user_id=fixture.context.user_id,
            tenant_id=fixture.context.tenant_id,
            email="matrix.reader@demo.deepsearch.local",
            display_name="M2-20 Matrix Reader",
            roles=[role],
            market_scopes=["DE"],
            synthetic_data=True,
        )
        context = build_run_context(user, fixture.thread_id, trace_id=uuid4())
        other_owner_id = session.scalar(
            select(User.id).where(
                User.tenant_id == user.tenant_id,
                User.email == "scout@demo.deepsearch.local",
            )
        )
        assert other_owner_id is not None
        owner_id = user.user_id if access_mode == "owner" else other_owner_id
        label = f"m2_20_6_{role}_{access_mode}_{uuid4().hex[:8]}"
        document = scope_support._add_document(
            session,
            tenant_id=user.tenant_id,
            owner_id=owner_id,
            label=label,
        )
        version, index_set, chunk = scope_support._add_indexed_version(
            session,
            document=document,
            owner_id=owner_id,
            label=label,
        )
        if access_mode == "user":
            scope_support._grant_acl(
                session,
                document=document,
                subject_type="user",
                user_id=user.user_id,
            )
        elif access_mode == "role":
            scope_support._grant_acl(
                session,
                document=document,
                subject_type="role",
                role_name=role,
            )
        elif access_mode == "market":
            scope_support._grant_acl(
                session,
                document=document,
                subject_type="market",
                market_code="DE",
            )

        file_row = session.get(StoredFile, version.file_id)
        chunk_set = session.get(DocumentChunkSet, chunk.document_chunk_set_id)
        assert file_row is not None
        assert chunk_set is not None
        source = make_text_pdf(include_empty_page=False)
        source_sha256 = hashlib.sha256(source).hexdigest()
        parsed = PdfParser().parse(io.BytesIO(source))
        artifact = adapt_native_parse_result(parsed, source_sha256=source_sha256)
        quality = decide_parse_route(artifact)
        routed = RoutedParseResult(
            route=quality.route,
            reasons=quality.reasons,
            quality=quality,
            selected_artifact=artifact,
            native_artifact=artifact,
        )
        file_row.sha256 = source_sha256
        file_row.size_bytes = len(source)
        version.content_hash = source_sha256
        chunk_set.source_sha256 = source_sha256
        chunk.body_text = "M2-20.6合成整链证据：清洁前必须断开电源。"
        chunk.retrieval_text = chunk.body_text
        chunk.token_count = 20
        chunk.page_numbers = [1]
        chunk.source_spans = [
            {
                "block_id": "b000001",
                "start_locator": {"page_number": 1, "block_number": 1},
                "end_locator": {"page_number": 1, "block_number": 1},
                "character_start": 0,
                "character_end": len(chunk.body_text),
                "bounding_boxes": [],
            }
        ]
        session.flush()

        storage = LocalStorageBackend(storage_root)
        assert version.parsed_storage_key is not None
        storage.put(
            version.parsed_storage_key,
            io.BytesIO(routed.model_dump_json().encode("utf-8")),
            "application/json",
        )
        scope_fixture = RetrievalScopeFixture(
            fixture.runtime,
            session,
            {"reader": user},
            {"owner": chunk.id},
        )
        built = _build_one(scope_fixture, query="整链证据是什么？")
        persisted = EvidenceService(session).persist_document_context(user, built)
        evidence_id = persisted.evidences[0].id

        return cls(
            fixture=fixture,
            user=user,
            context=context,
            storage=storage,
            file_service=FileReadingService(
                FileRepository(
                    session,
                    fixture.settings.database_statement_timeout_ms,
                ),
                storage,
                maximum_artifact_bytes=fixture.settings.file_read_max_artifact_bytes,
            ),
            evidence_service=EvidenceQueryService(
                EvidenceRepository(
                    session,
                    fixture.settings.database_statement_timeout_ms,
                )
            ),
            file_row=file_row,
            document=document,
            version=version,
            index_set=index_set,
            chunk=chunk,
            evidence_id=evidence_id,
            parsed_storage_key=version.parsed_storage_key,
            other_owner_id=other_owner_id,
        )

    def run_both(self) -> MatrixRunResult:
        with self.fixture.recorder.run_scope(self.context, "knowledge_query") as run:
            harness = self._harness(run)
            file_envelope = ReadUploadedFileTool(
                harness,
                self.file_service,
                self.user,
            ).invoke(
                ReadUploadedFileInput(
                    file_id=self.file_row.id,
                    locator={"source_type": "pdf", "page_start": 1},
                )
            )
            evidence_envelope = GetEvidenceDetailTool(
                harness,
                self.evidence_service,
                self.user,
            ).invoke(GetEvidenceDetailInput(evidence_id=self.evidence_id))
        return MatrixRunResult(
            run_id=run.id,
            file_envelope=file_envelope,
            evidence_envelope=evidence_envelope,
        )

    def run_file(
        self,
        request: ReadUploadedFileInput | None = None,
        *,
        service: FileReadingService | None = None,
    ) -> MatrixRunResult:
        with self.fixture.recorder.run_scope(self.context, "knowledge_query") as run:
            envelope = ReadUploadedFileTool(
                self._harness(run),
                service or self.file_service,
                self.user,
            ).invoke(request or ReadUploadedFileInput(file_id=self.file_row.id))
        return MatrixRunResult(run_id=run.id, file_envelope=envelope)

    def run_evidence(
        self,
        *,
        service: EvidenceQueryService | None = None,
    ) -> MatrixRunResult:
        with self.fixture.recorder.run_scope(self.context, "knowledge_query") as run:
            envelope = GetEvidenceDetailTool(
                self._harness(run),
                service or self.evidence_service,
                self.user,
            ).invoke(GetEvidenceDetailInput(evidence_id=self.evidence_id))
        return MatrixRunResult(run_id=run.id, evidence_envelope=envelope)

    def mutate(self, state: InvalidState) -> None:
        session = self.fixture.business_session
        if state == "acl_revoked":
            for row in session.scalars(
                select(DocumentAcl).where(DocumentAcl.document_id == self.document.id)
            ):
                session.delete(row)
        elif state == "document_deleted":
            self.document.deleted_at = self.document.created_at
        elif state == "file_deleted":
            self.file_row.status = "soft_deleted"
            self.file_row.deleted_at = self.file_row.created_at
        elif state == "version_inactive":
            self.document.active_version_id = None
        elif state == "index_inactive":
            self.version.active_index_set_id = None
        else:
            evidence = session.get(ContextArtifact, self.chunk_context_id)
            assert evidence is not None
            evidence.requested_by_user_id = self.other_owner_id
        session.flush()

    @property
    def chunk_context_id(self) -> UUID:
        evidence = self.fixture.business_session.get(Evidence, self.evidence_id)
        assert evidence is not None
        assert evidence.context_artifact_id is not None
        return evidence.context_artifact_id

    def set_parse_status(self, status: Literal["pending", "failed"]) -> None:
        self.version.active_index_set_id = None
        self.version.index_status = status
        self.version.parse_status = status
        self.fixture.business_session.flush()

    def remove_parsed_artifact(self) -> None:
        self.storage.delete(self.parsed_storage_key)

    def corrupt_parsed_artifact(self) -> None:
        self.storage.delete(self.parsed_storage_key)
        self.storage.put(
            self.parsed_storage_key,
            io.BytesIO(b'{"private_path":"D:/secret","sql":"DROP TABLE"'),
            "application/json",
        )

    def calls(self, run_id: UUID) -> list[ToolCall]:
        return load_calls(self.fixture, run_id)

    def _harness(self, run: object) -> HarnessExecutor:
        from app.runtime.trace import RunTrace

        assert isinstance(run, RunTrace)
        registry = create_m2_tool_registry()
        return HarnessExecutor(
            context=self.context,
            run=run,
            budget=ExecutionBudget(
                BudgetLimits(
                    max_model_calls=2,
                    max_tool_calls=2,
                    max_repeat_tool_calls=1,
                    total_timeout_ms=20_000,
                )
            ),
            registry=registry,
            permission_guard=PermissionGuard(registry),
            trace_recorder=self.fixture.recorder,
        )
