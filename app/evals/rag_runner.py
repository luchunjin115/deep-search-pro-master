"""M2-22 bounded Parser/OCR and Chunk evaluation runners."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast
from uuid import UUID, uuid4

import psutil  # type: ignore[import-untyped]
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from pydantic import AwareDatetime, Field, model_validator
from sqlalchemy import delete, func, select

from app.core.config import Settings
from app.db.session import DatabaseRuntime, create_database_runtime
from app.evals.chunk_metrics import (
    ChunkConfigurationAggregate,
    ChunkDocumentQuality,
    aggregate_chunk_documents,
    evaluate_chunk_document,
    select_first_round_candidates,
)
from app.main import create_app
from app.models.catalog import ProductVariant
from app.models.identity import Role, Tenant, User, UserRole
from app.models.inventory import InventorySnapshot, Warehouse
from app.models.knowledge import (
    Document,
    DocumentAcl,
    DocumentChunkSet,
    DocumentVersion,
    StoredFile,
)
from app.schemas.auth import CurrentUser
from app.schemas.common import M1Schema, MarketCode, RoleName
from app.schemas.evaluation import (
    ChunkEvaluationConfig,
    ChunkHeadingGoldenDataset,
    EvaluationCase,
    EvaluationSourceManifest,
    SafeIdentifier,
    Sha256,
    TrustedHeadingContextCase,
    VersionLabel,
    default_chunk_evaluation_configs,
)
from app.services.documents.artifacts import (
    ArtifactTableBlock,
    ArtifactTextBlock,
    CanonicalParsedArtifact,
)
from app.services.documents.chunking import (
    CanonicalChunkArtifact,
    ChunkingConfig,
    DocumentChunkService,
    StructureAwareDocumentChunker,
    UnicodeMixedTokenCounter,
    build_chunk_artifact,
)
from app.services.documents.chunking.contracts import canonical_sha256
from app.services.documents.parser_service import DocumentParserService
from app.services.documents.parsers.docling import DoclingProvider, LocalDoclingProvider
from app.services.documents.quality import PostParseQualityDecision
from app.services.documents.routing import RoutedParseResult
from app.services.storage import LocalStorageBackend, StorageBackend
from scripts.seed_m2_complex_files import (
    generate_complex_sources,
    load_complex_seed_definition,
)
from scripts.seed_m2_files import generate_sources, load_seed_definition

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_MANIFEST_PATH = (
    PROJECT_ROOT / "data" / "evals" / "m2_cross_border_sources_v1.json"
)
DEFAULT_DATASET_PATH = (
    PROJECT_ROOT / "data" / "evals" / "m2_cross_border_rag_smoke_v1.jsonl"
)
DEFAULT_CHUNK_HEADING_DATASET_PATH = (
    PROJECT_ROOT / "data" / "evals" / "m2_cross_border_chunk_headings_v2.json"
)
DEFAULT_REPORT_PATH = (
    PROJECT_ROOT
    / "data"
    / "evals"
    / "runtime"
    / "reports"
    / "m2_cross_border_parser_report_v1.json"
)
DEFAULT_CHUNK_REPORT_PATH = (
    PROJECT_ROOT
    / "data"
    / "evals"
    / "runtime"
    / "reports"
    / "m2_cross_border_chunk_report_v1.json"
)
_EVALUATION_PASSWORD = "M2-eval-only-change-me"
_MIME_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
}


class EvaluationUserFixture(M1Schema):
    """Trusted test identity shape; runtime UUIDs never enter the Golden file."""

    fixture_id: SafeIdentifier
    roles: list[RoleName] = Field(min_length=1, max_length=3)
    market_scopes: list[MarketCode] = Field(min_length=1, max_length=2)


class EvaluationAclFixture(M1Schema):
    """Named authorization condition to be materialized by a later safety run."""

    fixture_id: SafeIdentifier
    access: Literal["public", "tenant", "role", "market", "denied"]
    role_name: RoleName | None = None
    market_code: MarketCode | None = None

    @model_validator(mode="after")
    def validate_acl_shape(self) -> EvaluationAclFixture:
        if self.access == "role" and self.role_name is None:
            raise ValueError("role ACL fixture requires a role")
        if self.access == "market" and self.market_code is None:
            raise ValueError("market ACL fixture requires a market")
        if self.access != "role" and self.role_name is not None:
            raise ValueError("only role ACL fixture may declare a role")
        if self.access != "market" and self.market_code is not None:
            raise ValueError("only market ACL fixture may declare a market")
        return self


class EvaluationVersionFixture(M1Schema):
    """Named document-version state used by frozen non-answer cases."""

    fixture_id: SafeIdentifier
    state: Literal["active", "deleted", "old_inactive"]


class EvaluationFixtureRegistry(M1Schema):
    """Complete trusted mapping for user, ACL, and version fixture references."""

    registry_version: Literal["m2-eval-fixtures-v1"] = "m2-eval-fixtures-v1"
    users: list[EvaluationUserFixture] = Field(min_length=1, max_length=16)
    acl: list[EvaluationAclFixture] = Field(min_length=1, max_length=16)
    versions: list[EvaluationVersionFixture] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def validate_unique_fixture_ids(self) -> EvaluationFixtureRegistry:
        for fixtures in (self.users, self.acl, self.versions):
            fixture_ids = [fixture.fixture_id for fixture in fixtures]
            if len(fixture_ids) != len(set(fixture_ids)):
                raise ValueError("evaluation fixture IDs must be unique by kind")
        return self


def build_default_fixture_registry() -> EvaluationFixtureRegistry:
    """Return the reviewed registry referenced by the M2 Smoke Golden."""

    return EvaluationFixtureRegistry(
        users=[
            EvaluationUserFixture(
                fixture_id="user-fixture-eval-reader",
                roles=["amazon_operator"],
                market_scopes=["DE", "FR"],
            ),
            EvaluationUserFixture(
                fixture_id="user-fixture-company-owner",
                roles=["company_owner"],
                market_scopes=["DE", "FR"],
            ),
            EvaluationUserFixture(
                fixture_id="user-fixture-product-scout",
                roles=["product_scout"],
                market_scopes=["DE", "FR"],
            ),
            EvaluationUserFixture(
                fixture_id="user-fixture-amazon-operator",
                roles=["amazon_operator"],
                market_scopes=["DE", "FR"],
            ),
            EvaluationUserFixture(
                fixture_id="user-fixture-de-operator",
                roles=["amazon_operator"],
                market_scopes=["DE"],
            ),
            EvaluationUserFixture(
                fixture_id="user-fixture-unauthorized",
                roles=["amazon_operator"],
                market_scopes=["FR"],
            ),
        ],
        acl=[
            EvaluationAclFixture(
                fixture_id="acl-fixture-public-eval",
                access="public",
            ),
            EvaluationAclFixture(
                fixture_id="acl-fixture-tenant",
                access="tenant",
            ),
            EvaluationAclFixture(
                fixture_id="acl-fixture-product-scout",
                access="role",
                role_name="product_scout",
            ),
            EvaluationAclFixture(
                fixture_id="acl-fixture-amazon-operator",
                access="role",
                role_name="amazon_operator",
            ),
            EvaluationAclFixture(
                fixture_id="acl-fixture-de-market",
                access="market",
                market_code="DE",
            ),
            EvaluationAclFixture(
                fixture_id="acl-fixture-denied",
                access="denied",
            ),
        ],
        versions=[
            EvaluationVersionFixture(
                fixture_id="version-fixture-active",
                state="active",
            ),
            EvaluationVersionFixture(
                fixture_id="version-fixture-deleted",
                state="deleted",
            ),
            EvaluationVersionFixture(
                fixture_id="version-fixture-old-inactive",
                state="old_inactive",
            ),
        ],
    )


class ArtifactRecoveryResult(M1Schema):
    """Exact Golden evidence recovery for one logical document."""

    expected_case_ids: list[SafeIdentifier] = Field(max_length=100)
    recovered_case_ids: list[SafeIdentifier] = Field(max_length=100)
    missing_case_ids: list[SafeIdentifier] = Field(max_length=100)
    recovery_rate: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_partition(self) -> ArtifactRecoveryResult:
        expected = set(self.expected_case_ids)
        recovered = set(self.recovered_case_ids)
        missing = set(self.missing_case_ids)
        if recovered & missing or recovered | missing != expected:
            raise ValueError(
                "recovered and missing cases must partition expected cases"
            )
        expected_rate = len(recovered) / len(expected) if expected else 1.0
        if self.recovery_rate != expected_rate:
            raise ValueError("recovery rate does not match case partition")
        return self


def evaluate_artifact_recovery(
    *,
    logical_document_id: str,
    artifact: CanonicalParsedArtifact,
    cases: list[EvaluationCase],
) -> ArtifactRecoveryResult:
    """Match only frozen exact Evidence, never answer variants or model output."""

    expected_cases = [
        case
        for case in cases
        if case.should_answer and logical_document_id in case.expected_document_ids
    ]
    searchable = _normalized_search_text(_artifact_search_text(artifact))
    recovered: list[str] = []
    missing: list[str] = []
    for case in expected_cases:
        spans = [
            span
            for span in case.expected_evidence_spans
            if span.document_id == logical_document_id
        ]
        target = (
            recovered
            if spans
            and all(
                _normalized_search_text(span.exact_text) in searchable for span in spans
            )
            else missing
        )
        target.append(case.case_id)
    return ArtifactRecoveryResult(
        expected_case_ids=[case.case_id for case in expected_cases],
        recovered_case_ids=recovered,
        missing_case_ids=missing,
        recovery_rate=(len(recovered) / len(expected_cases) if expected_cases else 1.0),
    )


def _artifact_search_text(artifact: CanonicalParsedArtifact) -> str:
    parts: list[str] = []
    for block in artifact.blocks:
        if isinstance(block, ArtifactTextBlock):
            parts.append(block.text)
            continue
        if isinstance(block, ArtifactTableBlock):
            for row in block.rows:
                row_parts: list[str] = []
                for cell in row.cells:
                    if cell.display_text:
                        row_parts.append(cell.display_text)
                    if cell.formula is not None:
                        row_parts.append(cell.formula)
                parts.append(" ".join(row_parts))
    return "\n".join(parts)


def _normalized_search_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


class ParserRouteCounts(M1Schema):
    native: int = Field(ge=0)
    docling: int = Field(ge=0)
    hybrid: int = Field(ge=0)


class ParserRecoveryGroup(M1Schema):
    group_id: SafeIdentifier
    cases_total: int = Field(ge=0)
    cases_recovered: int = Field(ge=0)
    recovery_rate: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_rate(self) -> ParserRecoveryGroup:
        expected = self.cases_recovered / self.cases_total if self.cases_total else None
        if self.cases_recovered > self.cases_total or self.recovery_rate != expected:
            raise ValueError("group recovery counts and rate do not match")
        return self


class ParserDocumentResult(M1Schema):
    source_id: SafeIdentifier
    logical_document_id: SafeIdentifier
    source_group: Literal[
        "synthetic_engineering_regression",
        "cross_border_core",
        "complex_document_diagnostics",
        "security_acl_version",
    ]
    source_type: Literal["pdf", "docx", "xlsx", "csv"]
    requires_ocr: bool
    upload_status: Literal["accepted", "rejected"]
    parse_status: Literal["completed", "failed", "skipped"]
    route: Literal["native", "docling", "hybrid"] | None = None
    parser_provider: Literal["native", "docling"] | None = None
    parser_name: str | None = Field(default=None, max_length=64)
    parser_version: str | None = Field(default=None, max_length=64)
    artifact_content_sha256: Sha256 | None = None
    published_sha256: Sha256 | None = None
    block_count: int | None = Field(default=None, ge=0)
    text_block_count: int | None = Field(default=None, ge=0)
    table_count: int | None = Field(default=None, ge=0)
    row_count: int | None = Field(default=None, ge=0)
    cell_count: int | None = Field(default=None, ge=0)
    formula_count: int | None = Field(default=None, ge=0)
    character_count: int | None = Field(default=None, ge=0)
    page_count: int | None = Field(default=None, ge=1)
    sheet_count: int | None = Field(default=None, ge=1)
    warning_count: int = Field(ge=0)
    upload_latency_ms: int = Field(ge=0)
    parse_latency_ms: int | None = Field(default=None, ge=0)
    peak_rss_bytes: int | None = Field(default=None, ge=0)
    post_parse_quality: PostParseQualityDecision | None = None
    recovery: ArtifactRecoveryResult
    failure_category: Literal["input_invalid", "calculation_error"] | None = None
    failure_summary: str | None = Field(default=None, min_length=1, max_length=300)

    @model_validator(mode="after")
    def validate_quality_decision(self) -> ParserDocumentResult:
        if (self.parse_status == "completed") != (self.post_parse_quality is not None):
            raise ValueError("completed parser results require post-parse quality")
        return self


class MalformedUploadProbeResult(M1Schema):
    status: Literal["planned", "rejected", "unexpectedly_accepted"]
    failure_category: Literal["input_invalid"] | None = None
    failure_summary: str | None = Field(default=None, min_length=1, max_length=300)


class ParserAggregate(M1Schema):
    documents_total: int = Field(ge=0)
    uploads_accepted: int = Field(ge=0)
    parses_completed: int = Field(ge=0)
    parses_failed: int = Field(ge=0)
    routes: ParserRouteCounts
    cases_total: int = Field(ge=0)
    cases_recovered: int = Field(ge=0)
    parser_fact_recovery_rate: float | None = Field(default=None, ge=0, le=1)
    ocr_cases_total: int = Field(ge=0)
    ocr_cases_recovered: int = Field(ge=0)
    ocr_field_accuracy: float | None = Field(default=None, ge=0, le=1)
    recovery_by_group: list[ParserRecoveryGroup] = Field(max_length=8)
    parse_latency_p50_ms: int | None = Field(default=None, ge=0)
    parse_latency_p95_ms: int | None = Field(default=None, ge=0)
    parse_latency_max_ms: int | None = Field(default=None, ge=0)
    peak_rss_max_bytes: int | None = Field(default=None, ge=0)


class ParserCleanupResult(M1Schema):
    cleanup_attempted: bool
    evaluation_database_rows_remaining: int = Field(ge=0)
    evaluation_storage_objects_remaining: int = Field(ge=0)
    formal_files: int = Field(ge=0)
    formal_documents: int = Field(ge=0)
    formal_versions: int = Field(ge=0)
    formal_acl: int = Field(ge=0)
    formal_pending_versions: int = Field(ge=0)
    formal_upload_objects: int = Field(ge=0)
    m1_guard_available: int | None = Field(default=None, ge=0)
    baseline_restored: bool


class ParserEvaluationReport(M1Schema):
    """Public-safe Parser/OCR report; source text and private keys are excluded."""

    schema_version: Literal["m2-parser-evaluation-report-v1"] = (
        "m2-parser-evaluation-report-v1"
    )
    run_id: SafeIdentifier
    run_status: Literal["planned", "completed", "failed"]
    started_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None
    source_manifest_version: VersionLabel
    source_manifest_sha256: Sha256
    dataset_version: VersionLabel
    dataset_sha256: Sha256
    fixture_registry_version: Literal["m2-eval-fixtures-v1"]
    documents: list[ParserDocumentResult] = Field(max_length=64)
    malformed_upload_probe: MalformedUploadProbeResult
    aggregate: ParserAggregate
    cleanup: ParserCleanupResult

    @model_validator(mode="after")
    def validate_run_claim(self) -> ParserEvaluationReport:
        if self.run_status == "planned":
            if (
                self.started_at is not None
                or self.completed_at is not None
                or self.documents
                or self.malformed_upload_probe.status != "planned"
                or self.cleanup.cleanup_attempted
            ):
                raise ValueError("planned parser report cannot contain run results")
            return self
        if self.started_at is None or self.completed_at is None or not self.documents:
            raise ValueError("executed parser report requires timestamps and documents")
        if self.completed_at < self.started_at:
            raise ValueError("parser report timestamps must be ordered")
        if len({document.source_id for document in self.documents}) != len(
            self.documents
        ):
            raise ValueError("parser report source IDs must be unique")
        completed = sum(
            document.parse_status == "completed" for document in self.documents
        )
        failed = sum(document.parse_status == "failed" for document in self.documents)
        if (
            self.aggregate.documents_total != len(self.documents)
            or self.aggregate.uploads_accepted
            != sum(document.upload_status == "accepted" for document in self.documents)
            or self.aggregate.parses_completed != completed
            or self.aggregate.parses_failed != failed
            or sum(self.aggregate.routes.model_dump().values()) != completed
        ):
            raise ValueError("parser report aggregate does not match its documents")
        if self.run_status == "completed" and (
            completed != len(self.documents)
            or self.malformed_upload_probe.status != "rejected"
            or not self.cleanup.baseline_restored
        ):
            raise ValueError("completed parser report requires a successful clean run")
        return self


class ChunkMatrixDocumentResult(M1Schema):
    """One source/config result with no source body or private runtime identity."""

    source_id: SafeIdentifier
    source_group: Literal[
        "synthetic_engineering_regression",
        "cross_border_core",
        "complex_document_diagnostics",
        "security_acl_version",
    ]
    source_type: Literal["pdf", "docx", "xlsx", "csv"]
    requires_ocr: bool
    route: Literal["native", "docling", "hybrid"]
    quality: ChunkDocumentQuality


class ChunkCohortAggregate(M1Schema):
    """Answer containment and locator results for one non-mixing cohort."""

    cohort_id: SafeIdentifier
    documents_total: int = Field(ge=0)
    golden_cases_total: int = Field(ge=0)
    golden_cases_contained: int = Field(ge=0)
    golden_cases_located: int = Field(ge=0)
    answer_containment_rate: float | None = Field(default=None, ge=0, le=1)
    locator_pass_rate: float | None = Field(default=None, ge=0, le=1)


class ChunkMatrixEntry(M1Schema):
    """One full configuration evaluated against every selected document."""

    phase: Literal["first_round", "overlap_sweep"]
    base_config_id: SafeIdentifier | None = None
    config: ChunkEvaluationConfig
    actual_config_sha256: Sha256
    documents: list[ChunkMatrixDocumentResult] = Field(min_length=1, max_length=64)
    aggregate: ChunkConfigurationAggregate
    cohorts: list[ChunkCohortAggregate] = Field(max_length=16)
    quality_gate_passed: bool

    @model_validator(mode="after")
    def validate_entry(self) -> ChunkMatrixEntry:
        if self.aggregate.config_id != self.config.config_id:
            raise ValueError("Chunk matrix aggregate config does not match its entry")
        if self.aggregate.documents_total != len(self.documents):
            raise ValueError("Chunk matrix document aggregate is inconsistent")
        if (self.phase == "overlap_sweep") != (self.base_config_id is not None):
            raise ValueError("overlap matrix entries require their base config")
        return self


class ChunkCandidateSelection(M1Schema):
    """Frozen rule and bounded overlap values used after the first round."""

    policy_version: Literal["m2-chunk-candidate-selection-v1"] = (
        "m2-chunk-candidate-selection-v1"
    )
    candidate_config_ids: list[SafeIdentifier] = Field(min_length=1, max_length=4)
    overlap_tokens: list[Literal[80, 100, 120]]

    @model_validator(mode="after")
    def validate_selection(self) -> ChunkCandidateSelection:
        if self.candidate_config_ids != sorted(set(self.candidate_config_ids)):
            raise ValueError("candidate config IDs must be unique and ordered")
        if self.overlap_tokens != [80, 100, 120]:
            raise ValueError("overlap sweep must stay frozen at 80/100/120")
        return self


class ChunkCleanupResult(M1Schema):
    cleanup_attempted: bool
    evaluation_database_rows_remaining: int = Field(ge=0)
    evaluation_chunk_sets_remaining: int = Field(ge=0)
    evaluation_storage_objects_remaining: int = Field(ge=0)
    formal_files: int = Field(ge=0)
    formal_documents: int = Field(ge=0)
    formal_versions: int = Field(ge=0)
    formal_acl: int = Field(ge=0)
    formal_pending_versions: int = Field(ge=0)
    formal_upload_objects: int = Field(ge=0)
    formal_chunk_sets: int = Field(ge=0)
    m1_guard_available: int | None = Field(default=None, ge=0)
    baseline_restored: bool


class ChunkEvaluationReport(M1Schema):
    """Public-safe M2-22.5 report; no Chunk text or internal keys are retained."""

    schema_version: Literal["m2-chunk-quality-report-v2"] = "m2-chunk-quality-report-v2"
    run_id: SafeIdentifier
    run_status: Literal["completed", "failed"]
    started_at: AwareDatetime
    completed_at: AwareDatetime
    source_manifest_version: VersionLabel
    source_manifest_sha256: Sha256
    dataset_version: VersionLabel
    dataset_sha256: Sha256
    heading_dataset_version: VersionLabel
    heading_dataset_sha256: Sha256
    heading_context_cases_total: int = Field(ge=0)
    documents_parsed: int = Field(ge=0)
    golden_cases_total: int = Field(ge=0)
    first_round: list[ChunkMatrixEntry] = Field(max_length=4)
    candidate_selection: ChunkCandidateSelection
    overlap_sweep: list[ChunkMatrixEntry] = Field(max_length=12)
    quality_gate_passed: bool
    failure_category: Literal["calculation_error"] | None = None
    failure_summary: str | None = Field(default=None, min_length=1, max_length=300)
    cleanup: ChunkCleanupResult

    @model_validator(mode="after")
    def validate_run(self) -> ChunkEvaluationReport:
        if self.completed_at < self.started_at:
            raise ValueError("Chunk evaluation timestamps must be ordered")
        first_ids = [entry.config.config_id for entry in self.first_round]
        if first_ids != [
            "chunk-compact",
            "chunk-medium",
            "chunk-current",
            "chunk-large",
        ]:
            raise ValueError("Chunk first-round matrix must use the frozen order")
        expected_sweep = len(self.candidate_selection.candidate_config_ids) * 3
        if len(self.overlap_sweep) != expected_sweep:
            raise ValueError("Chunk overlap matrix is incomplete")
        expected_quality_gate = _selected_candidate_quality_gate_passed(
            self.candidate_selection.candidate_config_ids,
            self.overlap_sweep,
        )
        if self.quality_gate_passed != expected_quality_gate:
            raise ValueError("Chunk report candidate quality gate is inconsistent")
        if self.run_status == "completed":
            if (
                self.failure_category is not None
                or self.failure_summary is not None
                or not self.cleanup.baseline_restored
            ):
                raise ValueError("completed Chunk evaluation must be clean")
        elif self.failure_category is None or self.failure_summary is None:
            raise ValueError("failed Chunk evaluation requires a safe reason")
        return self


@dataclass(frozen=True, slots=True)
class _EvaluationSourceInput:
    source_id: str
    logical_document_id: str
    source_group: Literal[
        "synthetic_engineering_regression",
        "cross_border_core",
        "complex_document_diagnostics",
        "security_acl_version",
    ]
    source_type: Literal["pdf", "docx", "xlsx", "csv"]
    requires_ocr: bool
    original_name: str
    title: str
    document_type: str
    language: str | None
    market: str | None
    access_level: str
    content: bytes


@dataclass(frozen=True, slots=True)
class _FormalBaseline:
    files: int
    documents: int
    versions: int
    acl: int
    pending_versions: int
    upload_objects: int
    m1_guard_available: int | None
    clean: bool


@dataclass(frozen=True, slots=True)
class _ChunkFormalBaseline:
    parser: _FormalBaseline
    chunk_sets: int
    clean: bool


@dataclass(frozen=True, slots=True)
class _ParsedEvaluationSource:
    source: _EvaluationSourceInput
    document_id: UUID
    version_id: UUID
    route: Literal["native", "docling", "hybrid"]
    routed: RoutedParseResult


def run_m2_parser_evaluation(
    settings: Settings,
    *,
    project_root: Path = PROJECT_ROOT,
    source_ids: set[str] | None = None,
    storage: StorageBackend | None = None,
    docling_provider: DoclingProvider | None = None,
) -> ParserEvaluationReport:
    """Run only the M2-22.4 upload and Parser/OCR evaluation boundary."""

    started_at = datetime.now(UTC)
    run_id = f"m2-22.4-{started_at:%Y%m%dt%H%M%S}-{uuid4().hex[:8]}"
    resolved_storage = storage or LocalStorageBackend(
        settings.local_storage_root,
        chunk_size_bytes=settings.upload_stream_chunk_size_bytes,
    )
    runtime = create_database_runtime(settings)
    cases = _load_cases(project_root / DEFAULT_DATASET_PATH.relative_to(PROJECT_ROOT))
    manifest = _load_source_manifest(
        project_root / DEFAULT_SOURCE_MANIFEST_PATH.relative_to(PROJECT_ROOT)
    )
    sources = _load_evaluation_sources(
        project_root=project_root,
        manifest=manifest,
        source_ids=source_ids,
    )
    baseline_before = _formal_baseline(runtime, resolved_storage)
    tenant_id: UUID | None = None
    documents: list[ParserDocumentResult] = []
    malformed = MalformedUploadProbeResult(status="planned")
    cleanup: ParserCleanupResult
    try:
        tenant_id, email = _create_evaluation_identity(runtime, run_id)
        application = create_app(settings, runtime, resolved_storage)
        selected_provider = docling_provider
        if selected_provider is None and settings.docling_backend == "docling":
            selected_provider = LocalDoclingProvider(settings)
        parser = DocumentParserService(
            runtime.session_factory,
            resolved_storage,
            settings,
            docling_provider=selected_provider,
        )
        with TestClient(application) as client:
            token, user = _login_evaluation_owner(client, email)
            headers = {"Authorization": f"Bearer {token}"}
            for source in sources:
                documents.append(
                    _evaluate_source(
                        client=client,
                        headers=headers,
                        user=user,
                        parser=parser,
                        runtime=runtime,
                        storage=resolved_storage,
                        source=source,
                        cases=cases,
                    )
                )
            malformed = _run_malformed_upload_probe(client, headers)
    finally:
        cleanup = _cleanup_evaluation(
            runtime=runtime,
            storage=resolved_storage,
            tenant_id=tenant_id,
            baseline_before=baseline_before,
        )
        runtime.engine.dispose()

    aggregate = _aggregate_parser_results(documents)
    completed = (
        bool(documents)
        and aggregate.uploads_accepted == aggregate.documents_total
        and aggregate.parses_completed == aggregate.documents_total
        and malformed.status == "rejected"
        and cleanup.baseline_restored
    )
    return ParserEvaluationReport(
        run_id=run_id,
        run_status="completed" if completed else "failed",
        started_at=started_at,
        completed_at=datetime.now(UTC),
        source_manifest_version=manifest.manifest_version,
        source_manifest_sha256=manifest.canonical_sha256(),
        dataset_version=cases[0].dataset_version,
        dataset_sha256=hashlib.sha256(
            (project_root / DEFAULT_DATASET_PATH.relative_to(PROJECT_ROOT)).read_bytes()
        ).hexdigest(),
        fixture_registry_version=build_default_fixture_registry().registry_version,
        documents=documents,
        malformed_upload_probe=malformed,
        aggregate=aggregate,
        cleanup=cleanup,
    )


def run_m2_chunk_evaluation(
    settings: Settings,
    *,
    project_root: Path = PROJECT_ROOT,
    source_ids: set[str] | None = None,
    storage: StorageBackend | None = None,
    docling_provider: DoclingProvider | None = None,
) -> ChunkEvaluationReport:
    """Run only the bounded M2-22.5 Parser-to-Chunk quality matrix."""

    started_at = datetime.now(UTC)
    run_id = f"m2-22.5-{started_at:%Y%m%dt%H%M%S}-{uuid4().hex[:8]}"
    resolved_storage = storage or LocalStorageBackend(
        settings.local_storage_root,
        chunk_size_bytes=settings.upload_stream_chunk_size_bytes,
    )
    runtime = create_database_runtime(settings)
    dataset_path = project_root / DEFAULT_DATASET_PATH.relative_to(PROJECT_ROOT)
    heading_dataset_path = (
        project_root / DEFAULT_CHUNK_HEADING_DATASET_PATH.relative_to(PROJECT_ROOT)
    )
    manifest_path = project_root / DEFAULT_SOURCE_MANIFEST_PATH.relative_to(
        PROJECT_ROOT
    )
    cases = _load_cases(dataset_path)
    heading_dataset = _load_heading_dataset(heading_dataset_path)
    manifest = _load_source_manifest(manifest_path)
    sources = _load_evaluation_sources(
        project_root=project_root,
        manifest=manifest,
        source_ids=source_ids,
    )
    baseline_before = _chunk_formal_baseline(runtime, resolved_storage)
    if not baseline_before.clean:
        runtime.engine.dispose()
        raise RuntimeError("formal database and Storage baseline is not clean")

    tenant_id: UUID | None = None
    parsed_sources: list[_ParsedEvaluationSource] = []
    first_round: list[ChunkMatrixEntry] = []
    overlap_sweep: list[ChunkMatrixEntry] = []
    try:
        tenant_id, email = _create_evaluation_identity(
            runtime,
            run_id,
            tenant_label="M2-22.5 Chunk Evaluation",
        )
        application = create_app(settings, runtime, resolved_storage)
        selected_provider = docling_provider
        if selected_provider is None and settings.docling_backend == "docling":
            selected_provider = LocalDoclingProvider(settings)
        parser = DocumentParserService(
            runtime.session_factory,
            resolved_storage,
            settings,
            docling_provider=selected_provider,
        )
        with TestClient(application) as client:
            token, user = _login_evaluation_owner(client, email)
            headers = {"Authorization": f"Bearer {token}"}
            parsed_sources = [
                _ingest_chunk_source(
                    client=client,
                    headers=headers,
                    user=user,
                    parser=parser,
                    runtime=runtime,
                    storage=resolved_storage,
                    source=source,
                )
                for source in sources
            ]

            first_configs = default_chunk_evaluation_configs()
            first_round = [
                _run_chunk_matrix_entry(
                    phase="first_round",
                    base_config_id=None,
                    evaluation_config=config,
                    base_settings=settings,
                    user=user,
                    parsed_sources=parsed_sources,
                    cases=cases,
                    heading_cases=heading_dataset.trusted_context_cases,
                    runtime=runtime,
                    storage=resolved_storage,
                )
                for config in first_configs
            ]
            candidate_ids = select_first_round_candidates(
                [entry.aggregate for entry in first_round]
            )
            overlap_configs = _overlap_sweep_configs(
                first_configs,
                candidate_ids=candidate_ids,
            )
            overlap_sweep = [
                _run_chunk_matrix_entry(
                    phase="overlap_sweep",
                    base_config_id=base_id,
                    evaluation_config=config,
                    base_settings=settings,
                    user=user,
                    parsed_sources=parsed_sources,
                    cases=cases,
                    heading_cases=heading_dataset.trusted_context_cases,
                    runtime=runtime,
                    storage=resolved_storage,
                )
                for base_id, config in overlap_configs
            ]
    finally:
        cleanup = _cleanup_chunk_evaluation(
            runtime=runtime,
            storage=resolved_storage,
            tenant_id=tenant_id,
            baseline_before=baseline_before,
        )
        runtime.engine.dispose()

    candidate_ids = select_first_round_candidates(
        [entry.aggregate for entry in first_round]
    )
    selected_document_ids = {
        source.source.logical_document_id for source in parsed_sources
    }
    golden_total = sum(
        case.should_answer
        and bool(selected_document_ids.intersection(case.expected_document_ids))
        for case in cases
    )
    heading_total = sum(
        case.source_id in {source.source.source_id for source in parsed_sources}
        for case in heading_dataset.trusted_context_cases
    )
    return ChunkEvaluationReport(
        run_id=run_id,
        run_status="completed" if cleanup.baseline_restored else "failed",
        started_at=started_at,
        completed_at=datetime.now(UTC),
        source_manifest_version=manifest.manifest_version,
        source_manifest_sha256=manifest.canonical_sha256(),
        dataset_version=cases[0].dataset_version,
        dataset_sha256=hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        heading_dataset_version=heading_dataset.dataset_version,
        heading_dataset_sha256=hashlib.sha256(
            heading_dataset_path.read_bytes()
        ).hexdigest(),
        heading_context_cases_total=heading_total,
        documents_parsed=len(parsed_sources),
        golden_cases_total=golden_total,
        first_round=first_round,
        candidate_selection=ChunkCandidateSelection(
            candidate_config_ids=candidate_ids,
            overlap_tokens=[80, 100, 120],
        ),
        overlap_sweep=overlap_sweep,
        quality_gate_passed=_selected_candidate_quality_gate_passed(
            candidate_ids,
            overlap_sweep,
        ),
        failure_category=None if cleanup.baseline_restored else "calculation_error",
        failure_summary=(
            None
            if cleanup.baseline_restored
            else "Chunk evaluation cleanup did not restore the formal baseline"
        ),
        cleanup=cleanup,
    )


def _load_cases(path: Path) -> list[EvaluationCase]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    cases = [EvaluationCase.model_validate_json(line) for line in lines]
    if not cases or len({case.dataset_version for case in cases}) != 1:
        raise ValueError("evaluation dataset is invalid")
    return cases


def _load_source_manifest(path: Path) -> EvaluationSourceManifest:
    return EvaluationSourceManifest.model_validate_json(path.read_bytes())


def _load_heading_dataset(path: Path) -> ChunkHeadingGoldenDataset:
    return ChunkHeadingGoldenDataset.model_validate_json(path.read_bytes())


def _load_evaluation_sources(
    *,
    project_root: Path,
    manifest: EvaluationSourceManifest,
    source_ids: set[str] | None,
) -> list[_EvaluationSourceInput]:
    loaded: list[_EvaluationSourceInput] = []
    for data, generated in (
        (load_seed_definition(), generate_sources(load_seed_definition())),
        (
            load_complex_seed_definition(),
            generate_complex_sources(load_complex_seed_definition()),
        ),
    ):
        for generated_source in generated:
            definition = generated_source.definition
            source_id = f"{data['version']}-{definition['key'].replace('_', '-')}"
            loaded.append(
                _EvaluationSourceInput(
                    source_id=source_id,
                    logical_document_id=str(generated_source.document_id),
                    source_group="synthetic_engineering_regression",
                    source_type=definition["format"],
                    requires_ocr=bool(definition.get("requires_ocr", False)),
                    original_name=definition["original_name"],
                    title=definition["title"],
                    document_type=definition["document_type"],
                    language=definition["language"],
                    market=definition["market"],
                    access_level=definition["access_level"],
                    content=generated_source.content,
                )
            )

    data_root = project_root / "data" / "evals" / "runtime"
    for manifest_source in manifest.sources:
        if manifest_source.lifecycle_status != "verified":
            continue
        if source_ids is not None and manifest_source.source_id not in source_ids:
            continue
        if manifest_source.source_format not in _MIME_TYPES:
            raise ValueError("verified evaluation source format is unsupported")
        relative_path = manifest_source.processed_relative_path
        if relative_path is None or manifest_source.processed_sha256 is None:
            raise ValueError("verified evaluation source is incomplete")
        path = data_root / Path(relative_path)
        content = path.read_bytes()
        if (
            len(content) != manifest_source.actual_size_bytes
            or hashlib.sha256(content).hexdigest() != manifest_source.processed_sha256
        ):
            raise ValueError("verified evaluation source does not match its manifest")
        loaded.append(
            _EvaluationSourceInput(
                source_id=manifest_source.source_id,
                logical_document_id=f"eval-doc-{manifest_source.source_id}",
                source_group=manifest_source.source_group,
                source_type=cast(
                    Literal["pdf", "docx", "xlsx", "csv"],
                    manifest_source.source_format,
                ),
                requires_ocr=False,
                original_name=path.name,
                title=manifest_source.source_name,
                document_type="evaluation_reference",
                language=manifest_source.languages[0],
                market=None,
                access_level="tenant",
                content=content,
            )
        )

    available_ids = {source.source_id for source in loaded}
    requested_ids = source_ids if source_ids is not None else available_ids
    if not requested_ids or not requested_ids <= available_ids:
        raise ValueError("evaluation source selection is invalid")
    return [source for source in loaded if source.source_id in requested_ids]


def _ingest_chunk_source(
    *,
    client: TestClient,
    headers: dict[str, str],
    user: CurrentUser,
    parser: DocumentParserService,
    runtime: DatabaseRuntime,
    storage: StorageBackend,
    source: _EvaluationSourceInput,
) -> _ParsedEvaluationSource:
    upload = client.post(
        "/api/v1/files",
        headers=headers,
        files=[
            (
                "files",
                (
                    source.original_name,
                    source.content,
                    _MIME_TYPES[source.source_type],
                ),
            )
        ],
    )
    if upload.status_code != 201:
        raise RuntimeError("evaluation source upload failed")
    file_id = UUID(upload.json()["items"][0]["file_id"])
    created = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "file_id": str(file_id),
            "title": source.title,
            "document_type": source.document_type,
            "language": source.language,
            "market": source.market,
            "access_level": source.access_level,
        },
    )
    if created.status_code != 201:
        raise RuntimeError("evaluation document registration failed")
    payload = created.json()
    document_id = UUID(payload["document_id"])
    version_id = UUID(payload["versions"][0]["version_id"])
    publication = parser.parse_version(
        user,
        document_id=document_id,
        version_id=version_id,
    )
    routed = _read_routed_artifact(
        runtime=runtime,
        storage=storage,
        tenant_id=user.tenant_id,
        document_id=document_id,
        version_id=version_id,
    )
    if (
        routed.post_parse_quality is None
        or routed.post_parse_quality.status != "accepted"
    ):
        raise RuntimeError("evaluation source did not pass post-parse quality")
    return _ParsedEvaluationSource(
        source=source,
        document_id=document_id,
        version_id=version_id,
        route=publication.route,
        routed=routed,
    )


def _run_chunk_matrix_entry(
    *,
    phase: Literal["first_round", "overlap_sweep"],
    base_config_id: str | None,
    evaluation_config: ChunkEvaluationConfig,
    base_settings: Settings,
    user: CurrentUser,
    parsed_sources: Sequence[_ParsedEvaluationSource],
    cases: Sequence[EvaluationCase],
    heading_cases: Sequence[TrustedHeadingContextCase],
    runtime: DatabaseRuntime,
    storage: StorageBackend,
) -> ChunkMatrixEntry:
    settings = base_settings.model_copy(
        update={
            "chunk_target_tokens": evaluation_config.target_tokens,
            "chunk_max_tokens": evaluation_config.max_tokens,
            "chunk_overlap_tokens": evaluation_config.text_overlap_tokens,
            "chunk_heading_context_max_tokens": (
                evaluation_config.heading_context_max_tokens
            ),
            "chunk_table_row_overlap": evaluation_config.table_row_overlap,
            "chunk_repeated_edge_min_pages": (
                evaluation_config.repeated_edge_min_pages
            ),
        }
    )
    expected_config = ChunkingConfig(
        target_tokens=evaluation_config.target_tokens,
        max_tokens=evaluation_config.max_tokens,
        overlap_tokens=evaluation_config.text_overlap_tokens,
        heading_context_max_tokens=evaluation_config.heading_context_max_tokens,
        table_row_overlap=evaluation_config.table_row_overlap,
        repeated_edge_min_pages=evaluation_config.repeated_edge_min_pages,
        include_hidden_sheets=evaluation_config.include_hidden_sheets,
        repeat_table_headers=evaluation_config.repeat_table_headers,
    )
    service = DocumentChunkService(runtime.session_factory, storage, settings)
    documents: list[ChunkMatrixDocumentResult] = []
    for parsed in parsed_sources:
        published = service.ensure_chunk_version(
            user,
            document_id=parsed.document_id,
            version_id=parsed.version_id,
        )
        if published.config != expected_config:
            raise RuntimeError("published Chunk config differs from evaluation config")
        payload = _read_chunk_payload(
            runtime=runtime,
            storage=storage,
            tenant_id=user.tenant_id,
            chunk_set_id=published.chunk_set_id,
        )
        rebuilt = _rebuild_chunk_artifact(published, parsed.routed)
        deterministic = rebuilt.model_dump_json().encode("utf-8") == payload
        quality = evaluate_chunk_document(
            source_id=parsed.source.source_id,
            logical_document_id=parsed.source.logical_document_id,
            artifact=parsed.routed.selected_artifact,
            chunk_artifact=published,
            cases=cases,
            heading_cases=heading_cases,
            deterministic_rebuild_passed=deterministic,
        )
        documents.append(
            ChunkMatrixDocumentResult(
                source_id=parsed.source.source_id,
                source_group=parsed.source.source_group,
                source_type=parsed.source.source_type,
                requires_ocr=parsed.source.requires_ocr,
                route=parsed.route,
                quality=quality,
            )
        )
    quality_documents = [document.quality for document in documents]
    aggregate = aggregate_chunk_documents(
        evaluation_config.config_id,
        quality_documents,
    )
    cohorts = _chunk_cohorts(documents)
    return ChunkMatrixEntry(
        phase=phase,
        base_config_id=base_config_id,
        config=evaluation_config,
        actual_config_sha256=canonical_sha256(expected_config.model_dump(mode="json")),
        documents=documents,
        aggregate=aggregate,
        cohorts=cohorts,
        quality_gate_passed=_chunk_quality_gate(
            aggregate,
            cohorts,
            max_tokens=evaluation_config.max_tokens,
        ),
    )


def _overlap_sweep_configs(
    first_round: Sequence[ChunkEvaluationConfig],
    *,
    candidate_ids: Sequence[str],
) -> list[tuple[str, ChunkEvaluationConfig]]:
    by_id = {config.config_id: config for config in first_round}
    configs: list[tuple[str, ChunkEvaluationConfig]] = []
    for candidate_id in candidate_ids:
        base = by_id[candidate_id]
        for overlap in (80, 100, 120):
            payload = base.model_dump(mode="json") | {
                "config_id": f"{candidate_id}-overlap-{overlap:03d}",
                "text_overlap_tokens": overlap,
            }
            configs.append(
                (candidate_id, ChunkEvaluationConfig.model_validate(payload))
            )
    return configs


def _selected_candidate_quality_gate_passed(
    candidate_ids: Sequence[str],
    overlap_sweep: Sequence[ChunkMatrixEntry],
) -> bool:
    selected_entries = [
        entry for entry in overlap_sweep if entry.base_config_id in candidate_ids
    ]
    return bool(selected_entries) and any(
        entry.quality_gate_passed for entry in selected_entries
    )


def _read_chunk_payload(
    *,
    runtime: DatabaseRuntime,
    storage: StorageBackend,
    tenant_id: UUID,
    chunk_set_id: UUID,
) -> bytes:
    with runtime.session_factory() as session:
        row = session.scalar(
            select(DocumentChunkSet).where(
                DocumentChunkSet.tenant_id == tenant_id,
                DocumentChunkSet.id == chunk_set_id,
                DocumentChunkSet.status == "ready",
            )
        )
        if row is None or row.chunk_storage_key is None:
            raise RuntimeError("published Chunk metadata is unavailable")
        key = row.chunk_storage_key
        expected_hash = row.output_sha256
    with storage.open(key) as stream:
        payload = stream.read()
    artifact = CanonicalChunkArtifact.model_validate_json(payload)
    if artifact.output_sha256 != expected_hash:
        raise RuntimeError("published Chunk metadata does not match its Artifact")
    return payload


def _rebuild_chunk_artifact(
    chunk_artifact: CanonicalChunkArtifact,
    routed: RoutedParseResult,
) -> CanonicalChunkArtifact:
    counter = UnicodeMixedTokenCounter()
    result = StructureAwareDocumentChunker(
        config=chunk_artifact.config,
        token_counter=counter,
    ).chunk(routed.selected_artifact)
    return build_chunk_artifact(
        input_provenance=chunk_artifact.input,
        chunker=chunk_artifact.chunker,
        config=chunk_artifact.config,
        chunks=result.chunks,
        excluded_spans=result.excluded_spans,
        skipped_tables=result.skipped_tables,
    )


def _chunk_cohorts(
    documents: Sequence[ChunkMatrixDocumentResult],
) -> list[ChunkCohortAggregate]:
    cohorts: list[tuple[str, list[ChunkMatrixDocumentResult]]] = []
    for group in sorted({document.source_group for document in documents}):
        cohorts.append(
            (
                group,
                [document for document in documents if document.source_group == group],
            )
        )
    cohorts.extend(
        [
            (
                "digital",
                [document for document in documents if not document.requires_ocr],
            ),
            ("ocr", [document for document in documents if document.requires_ocr]),
        ]
    )
    return [
        _chunk_cohort_aggregate(cohort_id, grouped)
        for cohort_id, grouped in cohorts
        if grouped
    ]


def _chunk_cohort_aggregate(
    cohort_id: str,
    documents: Sequence[ChunkMatrixDocumentResult],
) -> ChunkCohortAggregate:
    cases = [case for document in documents for case in document.quality.golden_cases]
    total = len(cases)
    contained = sum(case.answer_contained for case in cases)
    located = sum(case.locator_passed for case in cases)
    return ChunkCohortAggregate(
        cohort_id=cohort_id,
        documents_total=len(documents),
        golden_cases_total=total,
        golden_cases_contained=contained,
        golden_cases_located=located,
        answer_containment_rate=contained / total if total else None,
        locator_pass_rate=located / total if total else None,
    )


def _chunk_quality_gate(
    aggregate: ChunkConfigurationAggregate,
    cohorts: Sequence[ChunkCohortAggregate],
    *,
    max_tokens: int,
) -> bool:
    by_id = {cohort.cohort_id: cohort for cohort in cohorts}
    digital = by_id.get("digital")
    ocr = by_id.get("ocr")
    return bool(
        aggregate.documents_total
        and aggregate.parser_artifact_failures == 0
        and aggregate.boundary_breaks == 0
        and aggregate.heading_units == aggregate.heading_units_preserved
        and aggregate.table_rows == aggregate.table_rows_preserved
        and aggregate.deterministic_documents == aggregate.documents_total
        and aggregate.ordered_documents == aggregate.documents_total
        and aggregate.locator_integrity_documents == aggregate.documents_total
        and aggregate.empty_chunk_count == 0
        and aggregate.token_max is not None
        and aggregate.token_max <= max_tokens
        and (
            digital is None
            or digital.golden_cases_total == 0
            or (
                digital.answer_containment_rate is not None
                and digital.answer_containment_rate >= 0.95
                and digital.locator_pass_rate is not None
                and digital.locator_pass_rate >= 0.95
            )
        )
        and (
            ocr is None
            or ocr.golden_cases_total == 0
            or (
                ocr.answer_containment_rate is not None
                and ocr.answer_containment_rate >= 0.80
                and ocr.locator_pass_rate is not None
                and ocr.locator_pass_rate >= 0.80
            )
        )
    )


def _create_evaluation_identity(
    runtime: DatabaseRuntime,
    run_id: str,
    *,
    tenant_label: str = "M2-22.4 Parser Evaluation",
) -> tuple[UUID, str]:
    tenant_id = uuid4()
    registry = build_default_fixture_registry()
    owner_email: str | None = None
    password_hash = PasswordHash.recommended().hash(_EVALUATION_PASSWORD)
    with runtime.session_factory.begin() as session:
        role_names = {role for fixture in registry.users for role in fixture.roles}
        roles = {
            role.name: role
            for role in session.scalars(select(Role).where(Role.name.in_(role_names)))
        }
        if set(roles) != role_names:
            raise RuntimeError("evaluation role prerequisite is unavailable")
        session.add(
            Tenant(
                id=tenant_id,
                name=f"{tenant_label} {run_id[-8:]}",
                is_demo=True,
            )
        )
        for fixture in registry.users:
            user_id = uuid4()
            short_id = fixture.fixture_id.removeprefix("user-fixture-")
            email = f"m2.eval.{run_id[-8:]}.{short_id}@example.invalid"
            session.add(
                User(
                    id=user_id,
                    tenant_id=tenant_id,
                    email=email,
                    display_name=f"M2 Evaluation {short_id}",
                    password_hash=password_hash,
                    status="active",
                )
            )
            for role_name in fixture.roles:
                session.add(
                    UserRole(
                        user_id=user_id,
                        role_id=roles[role_name].id,
                        market_scopes=list(fixture.market_scopes),
                    )
                )
            if fixture.fixture_id == "user-fixture-company-owner":
                owner_email = email
    if owner_email is None:
        raise RuntimeError("evaluation owner fixture is unavailable")
    return tenant_id, owner_email


def _login_evaluation_owner(
    client: TestClient,
    email: str,
) -> tuple[str, CurrentUser]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": _EVALUATION_PASSWORD},
    )
    if response.status_code != 200:
        raise RuntimeError("evaluation login failed")
    payload = response.json()
    return cast(str, payload["access_token"]), CurrentUser.model_validate(
        payload["user"]
    )


def _evaluate_source(
    *,
    client: TestClient,
    headers: dict[str, str],
    user: CurrentUser,
    parser: DocumentParserService,
    runtime: DatabaseRuntime,
    storage: StorageBackend,
    source: _EvaluationSourceInput,
    cases: list[EvaluationCase],
) -> ParserDocumentResult:
    upload_started = time.perf_counter()
    upload = client.post(
        "/api/v1/files",
        headers=headers,
        files=[
            (
                "files",
                (
                    source.original_name,
                    source.content,
                    _MIME_TYPES[source.source_type],
                ),
            )
        ],
    )
    upload_latency_ms = _elapsed_ms(upload_started)
    if upload.status_code != 201:
        return _failed_document_result(
            source=source,
            cases=cases,
            upload_status="rejected",
            upload_latency_ms=upload_latency_ms,
            summary="Upload validation rejected an evaluation source",
            category="input_invalid",
        )

    file_id = UUID(upload.json()["items"][0]["file_id"])
    created = client.post(
        "/api/v1/documents",
        headers=headers,
        json={
            "file_id": str(file_id),
            "title": source.title,
            "document_type": source.document_type,
            "language": source.language,
            "market": source.market,
            "access_level": source.access_level,
        },
    )
    if created.status_code != 201:
        return _failed_document_result(
            source=source,
            cases=cases,
            upload_status="accepted",
            upload_latency_ms=upload_latency_ms,
            summary="Document registration rejected an evaluation source",
            category="input_invalid",
        )
    payload = created.json()
    document_id = UUID(payload["document_id"])
    version_id = UUID(payload["versions"][0]["version_id"])
    parse_started = time.perf_counter()
    sampler = _PeakRssSampler()
    try:
        sampler.start()
        publication = parser.parse_version(
            user,
            document_id=document_id,
            version_id=version_id,
        )
        parse_latency_ms = _elapsed_ms(parse_started)
        peak_rss = sampler.stop()
        routed = _read_routed_artifact(
            runtime=runtime,
            storage=storage,
            tenant_id=user.tenant_id,
            document_id=document_id,
            version_id=version_id,
        )
        artifact = routed.selected_artifact
        if routed.post_parse_quality is None:
            raise RuntimeError("post-parse quality decision is unavailable")
        recovery = evaluate_artifact_recovery(
            logical_document_id=source.logical_document_id,
            artifact=artifact,
            cases=cases,
        )
        statistics = artifact.statistics
        return ParserDocumentResult(
            source_id=source.source_id,
            logical_document_id=source.logical_document_id,
            source_group=source.source_group,
            source_type=source.source_type,
            requires_ocr=source.requires_ocr,
            upload_status="accepted",
            parse_status="completed",
            route=publication.route,
            parser_provider=publication.parser_provider,
            parser_name=publication.parser_name,
            parser_version=publication.parser_version,
            artifact_content_sha256=publication.artifact_content_sha256,
            published_sha256=publication.published_sha256,
            block_count=statistics.block_count,
            text_block_count=statistics.text_block_count,
            table_count=statistics.table_count,
            row_count=statistics.row_count,
            cell_count=statistics.cell_count,
            formula_count=statistics.formula_count,
            character_count=statistics.character_count,
            page_count=statistics.page_count,
            sheet_count=statistics.sheet_count,
            warning_count=publication.warning_count,
            upload_latency_ms=upload_latency_ms,
            parse_latency_ms=parse_latency_ms,
            peak_rss_bytes=peak_rss,
            post_parse_quality=routed.post_parse_quality,
            recovery=recovery,
        )
    except Exception:  # noqa: BLE001 - report must retain only a safe category.
        peak_rss = sampler.stop()
        return _failed_document_result(
            source=source,
            cases=cases,
            upload_status="accepted",
            upload_latency_ms=upload_latency_ms,
            parse_latency_ms=_elapsed_ms(parse_started),
            peak_rss_bytes=peak_rss,
            summary="Parser execution failed",
            category="calculation_error",
        )


def _failed_document_result(
    *,
    source: _EvaluationSourceInput,
    cases: list[EvaluationCase],
    upload_status: Literal["accepted", "rejected"],
    upload_latency_ms: int,
    summary: str,
    category: Literal["input_invalid", "calculation_error"],
    parse_latency_ms: int | None = None,
    peak_rss_bytes: int | None = None,
) -> ParserDocumentResult:
    expected = _expected_case_ids(source.logical_document_id, cases)
    return ParserDocumentResult(
        source_id=source.source_id,
        logical_document_id=source.logical_document_id,
        source_group=source.source_group,
        source_type=source.source_type,
        requires_ocr=source.requires_ocr,
        upload_status=upload_status,
        parse_status="failed" if upload_status == "accepted" else "skipped",
        upload_latency_ms=upload_latency_ms,
        parse_latency_ms=parse_latency_ms,
        peak_rss_bytes=peak_rss_bytes,
        warning_count=0,
        recovery=ArtifactRecoveryResult(
            expected_case_ids=expected,
            recovered_case_ids=[],
            missing_case_ids=expected,
            recovery_rate=0.0 if expected else 1.0,
        ),
        failure_category=category,
        failure_summary=summary,
    )


def _expected_case_ids(
    logical_document_id: str,
    cases: list[EvaluationCase],
) -> list[str]:
    return [
        case.case_id
        for case in cases
        if case.should_answer and logical_document_id in case.expected_document_ids
    ]


def _read_routed_artifact(
    *,
    runtime: DatabaseRuntime,
    storage: StorageBackend,
    tenant_id: UUID,
    document_id: UUID,
    version_id: UUID,
) -> RoutedParseResult:
    with runtime.session_factory() as session:
        key = session.scalar(
            select(DocumentVersion.parsed_storage_key).where(
                DocumentVersion.tenant_id == tenant_id,
                DocumentVersion.document_id == document_id,
                DocumentVersion.id == version_id,
                DocumentVersion.parse_status == "ready",
            )
        )
    if key is None:
        raise RuntimeError("parsed artifact publication is unavailable")
    with storage.open(key) as stream:
        return RoutedParseResult.model_validate_json(stream.read())


def _run_malformed_upload_probe(
    client: TestClient,
    headers: dict[str, str],
) -> MalformedUploadProbeResult:
    response = client.post(
        "/api/v1/files",
        headers=headers,
        files=[("files", ("malformed.pdf", b"not-a-pdf", "application/pdf"))],
    )
    if response.status_code == 422:
        return MalformedUploadProbeResult(
            status="rejected",
            failure_category="input_invalid",
            failure_summary="Malformed PDF was rejected at the upload boundary",
        )
    return MalformedUploadProbeResult(
        status="unexpectedly_accepted",
        failure_category="input_invalid",
        failure_summary="Malformed PDF bypassed the upload boundary",
    )


class _PeakRssSampler:
    def __init__(self) -> None:
        self._process = psutil.Process()
        self._peak = self._process.memory_info().rss
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._sample, daemon=True)
        self._thread.start()

    def stop(self) -> int:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
            self._thread = None
        self._peak = max(self._peak, self._process.memory_info().rss)
        return self._peak

    def _sample(self) -> None:
        while not self._stop.wait(0.01):
            self._peak = max(self._peak, self._process.memory_info().rss)


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


def _aggregate_parser_results(
    documents: list[ParserDocumentResult],
) -> ParserAggregate:
    completed = [item for item in documents if item.parse_status == "completed"]
    cases_total = sum(len(item.recovery.expected_case_ids) for item in documents)
    cases_recovered = sum(len(item.recovery.recovered_case_ids) for item in documents)
    ocr_documents = [item for item in documents if item.requires_ocr]
    ocr_total = sum(len(item.recovery.expected_case_ids) for item in ocr_documents)
    ocr_recovered = sum(len(item.recovery.recovered_case_ids) for item in ocr_documents)
    groups: list[ParserRecoveryGroup] = []
    for group_id in sorted({item.source_group for item in documents}):
        grouped = [item for item in documents if item.source_group == group_id]
        total = sum(len(item.recovery.expected_case_ids) for item in grouped)
        recovered = sum(len(item.recovery.recovered_case_ids) for item in grouped)
        groups.append(
            ParserRecoveryGroup(
                group_id=group_id,
                cases_total=total,
                cases_recovered=recovered,
                recovery_rate=recovered / total if total else None,
            )
        )
    latencies = sorted(
        item.parse_latency_ms for item in completed if item.parse_latency_ms is not None
    )
    peaks = [
        item.peak_rss_bytes for item in completed if item.peak_rss_bytes is not None
    ]
    return ParserAggregate(
        documents_total=len(documents),
        uploads_accepted=sum(item.upload_status == "accepted" for item in documents),
        parses_completed=len(completed),
        parses_failed=sum(item.parse_status == "failed" for item in documents),
        routes=ParserRouteCounts(
            native=sum(item.route == "native" for item in completed),
            docling=sum(item.route == "docling" for item in completed),
            hybrid=sum(item.route == "hybrid" for item in completed),
        ),
        cases_total=cases_total,
        cases_recovered=cases_recovered,
        parser_fact_recovery_rate=(
            cases_recovered / cases_total if cases_total else None
        ),
        ocr_cases_total=ocr_total,
        ocr_cases_recovered=ocr_recovered,
        ocr_field_accuracy=ocr_recovered / ocr_total if ocr_total else None,
        recovery_by_group=groups,
        parse_latency_p50_ms=_percentile(latencies, 0.50),
        parse_latency_p95_ms=_percentile(latencies, 0.95),
        parse_latency_max_ms=max(latencies) if latencies else None,
        peak_rss_max_bytes=max(peaks) if peaks else None,
    )


def _percentile(values: list[int], quantile: float) -> int | None:
    if not values:
        return None
    return values[max(0, math.ceil(len(values) * quantile) - 1)]


def _formal_baseline(
    runtime: DatabaseRuntime,
    storage: StorageBackend,
) -> _FormalBaseline:
    ordinary = generate_sources(load_seed_definition())
    complex_sources = generate_complex_sources(load_complex_seed_definition())
    sources = [*ordinary, *complex_sources]
    file_ids = [source.file_id for source in sources]
    document_ids = [source.document_id for source in sources]
    version_ids = [source.version_id for source in sources]
    with runtime.session_factory() as session:
        files = list(
            session.scalars(select(StoredFile).where(StoredFile.id.in_(file_ids)))
        )
        documents = list(
            session.scalars(select(Document).where(Document.id.in_(document_ids)))
        )
        versions = list(
            session.scalars(
                select(DocumentVersion).where(DocumentVersion.id.in_(version_ids))
            )
        )
        acl = (
            session.scalar(
                select(func.count())
                .select_from(DocumentAcl)
                .where(DocumentAcl.document_id.in_(document_ids))
            )
            or 0
        )
        available = session.scalar(
            select(
                InventorySnapshot.on_hand
                - InventorySnapshot.reserved
                - InventorySnapshot.unsellable
            )
            .join(ProductVariant, ProductVariant.id == InventorySnapshot.variant_id)
            .join(Warehouse, Warehouse.id == InventorySnapshot.warehouse_id)
            .where(
                ProductVariant.sku == "LR-TL-MUSH-OR01",
                Warehouse.code == "DE-FRA",
            )
            .order_by(InventorySnapshot.snapshot_at.desc())
            .limit(1)
        )
    upload_objects = sum(storage.exists(source.storage_key) for source in sources)
    pending = sum(
        version.parse_status == "pending"
        and version.index_status == "pending"
        and version.parsed_storage_key is None
        and version.parser_name is None
        and version.parser_version is None
        and version.active_index_set_id is None
        for version in versions
    )
    clean = (
        len(files) == 10
        and len(documents) == 10
        and len(versions) == 10
        and acl == 9
        and pending == 10
        and upload_objects == 10
        and available == 125
        and all(file.status == "uploaded" and file.deleted_at is None for file in files)
        and all(
            document.active_version_id is None and document.deleted_at is None
            for document in documents
        )
    )
    return _FormalBaseline(
        files=len(files),
        documents=len(documents),
        versions=len(versions),
        acl=acl,
        pending_versions=pending,
        upload_objects=upload_objects,
        m1_guard_available=available,
        clean=clean,
    )


def _chunk_formal_baseline(
    runtime: DatabaseRuntime,
    storage: StorageBackend,
) -> _ChunkFormalBaseline:
    parser = _formal_baseline(runtime, storage)
    version_ids = [
        source.version_id
        for source in [
            *generate_sources(load_seed_definition()),
            *generate_complex_sources(load_complex_seed_definition()),
        ]
    ]
    with runtime.session_factory() as session:
        chunk_sets = (
            session.scalar(
                select(func.count())
                .select_from(DocumentChunkSet)
                .where(DocumentChunkSet.document_version_id.in_(version_ids))
            )
            or 0
        )
    return _ChunkFormalBaseline(
        parser=parser,
        chunk_sets=chunk_sets,
        clean=parser.clean and chunk_sets == 0,
    )


def _cleanup_chunk_evaluation(
    *,
    runtime: DatabaseRuntime,
    storage: StorageBackend,
    tenant_id: UUID | None,
    baseline_before: _ChunkFormalBaseline,
) -> ChunkCleanupResult:
    storage_keys: set[str] = set()
    cleanup_ok = True
    if tenant_id is not None:
        try:
            with runtime.session_factory() as session:
                storage_keys.update(
                    session.scalars(
                        select(StoredFile.storage_key).where(
                            StoredFile.tenant_id == tenant_id
                        )
                    )
                )
                storage_keys.update(
                    key
                    for key in session.scalars(
                        select(DocumentVersion.parsed_storage_key).where(
                            DocumentVersion.tenant_id == tenant_id,
                            DocumentVersion.parsed_storage_key.is_not(None),
                        )
                    )
                    if key is not None
                )
                storage_keys.update(
                    key
                    for key in session.scalars(
                        select(DocumentChunkSet.chunk_storage_key).where(
                            DocumentChunkSet.tenant_id == tenant_id,
                            DocumentChunkSet.chunk_storage_key.is_not(None),
                        )
                    )
                    if key is not None
                )
            for key in sorted(storage_keys):
                storage.delete(key)
            with runtime.session_factory.begin() as session:
                session.execute(
                    delete(DocumentChunkSet).where(
                        DocumentChunkSet.tenant_id == tenant_id
                    )
                )
                session.execute(
                    delete(DocumentAcl).where(DocumentAcl.tenant_id == tenant_id)
                )
                session.execute(
                    delete(DocumentVersion).where(
                        DocumentVersion.tenant_id == tenant_id
                    )
                )
                session.execute(delete(Document).where(Document.tenant_id == tenant_id))
                session.execute(
                    delete(StoredFile).where(StoredFile.tenant_id == tenant_id)
                )
                user_ids = list(
                    session.scalars(select(User.id).where(User.tenant_id == tenant_id))
                )
                if user_ids:
                    session.execute(
                        delete(UserRole).where(UserRole.user_id.in_(user_ids))
                    )
                session.execute(delete(User).where(User.tenant_id == tenant_id))
                session.execute(delete(Tenant).where(Tenant.id == tenant_id))
        except Exception:  # noqa: BLE001 - cleanup remains safe and measurable.
            cleanup_ok = False

    database_remaining = 0
    chunk_sets_remaining = 0
    if tenant_id is not None:
        try:
            with runtime.session_factory() as session:
                chunk_sets_remaining = (
                    session.scalar(
                        select(func.count())
                        .select_from(DocumentChunkSet)
                        .where(DocumentChunkSet.tenant_id == tenant_id)
                    )
                    or 0
                )
                database_remaining = (
                    chunk_sets_remaining
                    + sum(
                        session.scalar(
                            select(func.count())
                            .select_from(model)
                            .where(model.tenant_id == tenant_id)
                        )
                        or 0
                        for model in (
                            StoredFile,
                            Document,
                            DocumentVersion,
                            DocumentAcl,
                            User,
                        )
                    )
                    + (
                        session.scalar(
                            select(func.count())
                            .select_from(Tenant)
                            .where(Tenant.id == tenant_id)
                        )
                        or 0
                    )
                )
        except Exception:  # noqa: BLE001
            database_remaining = 1
            chunk_sets_remaining = 1
            cleanup_ok = False
    try:
        storage_remaining = sum(storage.exists(key) for key in storage_keys)
    except Exception:  # noqa: BLE001
        storage_remaining = 1
        cleanup_ok = False
    try:
        baseline_after = _chunk_formal_baseline(runtime, storage)
    except Exception:  # noqa: BLE001
        baseline_after = baseline_before
        cleanup_ok = False
    baseline_restored = (
        cleanup_ok
        and database_remaining == 0
        and chunk_sets_remaining == 0
        and storage_remaining == 0
        and baseline_before.clean
        and baseline_after.clean
        and baseline_after == baseline_before
    )
    parser = baseline_after.parser
    return ChunkCleanupResult(
        cleanup_attempted=True,
        evaluation_database_rows_remaining=database_remaining,
        evaluation_chunk_sets_remaining=chunk_sets_remaining,
        evaluation_storage_objects_remaining=storage_remaining,
        formal_files=parser.files,
        formal_documents=parser.documents,
        formal_versions=parser.versions,
        formal_acl=parser.acl,
        formal_pending_versions=parser.pending_versions,
        formal_upload_objects=parser.upload_objects,
        formal_chunk_sets=baseline_after.chunk_sets,
        m1_guard_available=parser.m1_guard_available,
        baseline_restored=baseline_restored,
    )


def _cleanup_evaluation(
    *,
    runtime: DatabaseRuntime,
    storage: StorageBackend,
    tenant_id: UUID | None,
    baseline_before: _FormalBaseline,
) -> ParserCleanupResult:
    storage_keys: list[str] = []
    cleanup_ok = True
    if tenant_id is not None:
        try:
            with runtime.session_factory() as session:
                storage_keys.extend(
                    session.scalars(
                        select(StoredFile.storage_key).where(
                            StoredFile.tenant_id == tenant_id
                        )
                    ).all()
                )
                storage_keys.extend(
                    key
                    for key in session.scalars(
                        select(DocumentVersion.parsed_storage_key).where(
                            DocumentVersion.tenant_id == tenant_id,
                            DocumentVersion.parsed_storage_key.is_not(None),
                        )
                    ).all()
                    if key is not None
                )
            for key in storage_keys:
                storage.delete(key)
            with runtime.session_factory.begin() as session:
                session.execute(
                    delete(DocumentAcl).where(DocumentAcl.tenant_id == tenant_id)
                )
                session.execute(
                    delete(DocumentVersion).where(
                        DocumentVersion.tenant_id == tenant_id
                    )
                )
                session.execute(delete(Document).where(Document.tenant_id == tenant_id))
                session.execute(
                    delete(StoredFile).where(StoredFile.tenant_id == tenant_id)
                )
                user_ids = list(
                    session.scalars(select(User.id).where(User.tenant_id == tenant_id))
                )
                if user_ids:
                    session.execute(
                        delete(UserRole).where(UserRole.user_id.in_(user_ids))
                    )
                session.execute(delete(User).where(User.tenant_id == tenant_id))
                session.execute(delete(Tenant).where(Tenant.id == tenant_id))
        except Exception:  # noqa: BLE001 - cleanup status remains public-safe.
            cleanup_ok = False

    database_remaining = 0
    if tenant_id is not None:
        try:
            with runtime.session_factory() as session:
                database_remaining = sum(
                    session.scalar(
                        select(func.count())
                        .select_from(model)
                        .where(model.tenant_id == tenant_id)
                    )
                    or 0
                    for model in (
                        StoredFile,
                        Document,
                        DocumentVersion,
                        DocumentAcl,
                        User,
                    )
                ) + (
                    session.scalar(
                        select(func.count())
                        .select_from(Tenant)
                        .where(Tenant.id == tenant_id)
                    )
                    or 0
                )
        except Exception:  # noqa: BLE001
            database_remaining = 1
            cleanup_ok = False
    try:
        storage_remaining = sum(storage.exists(key) for key in storage_keys)
    except Exception:  # noqa: BLE001
        storage_remaining = 1
        cleanup_ok = False
    try:
        baseline_after = _formal_baseline(runtime, storage)
    except Exception:  # noqa: BLE001
        baseline_after = baseline_before
        cleanup_ok = False
    baseline_restored = (
        cleanup_ok
        and database_remaining == 0
        and storage_remaining == 0
        and baseline_before.clean
        and baseline_after.clean
        and baseline_after == baseline_before
    )
    return ParserCleanupResult(
        cleanup_attempted=True,
        evaluation_database_rows_remaining=database_remaining,
        evaluation_storage_objects_remaining=storage_remaining,
        formal_files=baseline_after.files,
        formal_documents=baseline_after.documents,
        formal_versions=baseline_after.versions,
        formal_acl=baseline_after.acl,
        formal_pending_versions=baseline_after.pending_versions,
        formal_upload_objects=baseline_after.upload_objects,
        m1_guard_available=baseline_after.m1_guard_available,
        baseline_restored=baseline_restored,
    )


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a bounded M2-22 Parser or Chunk evaluation"
    )
    parser.add_argument(
        "--stage",
        choices=("parser", "chunk"),
        default="parser",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--enable-docling",
        action="store_true",
        help="explicitly enable the local offline Docling/OCR path",
    )
    args = parser.parse_args()
    if not args.enable_docling:
        parser.error("--enable-docling is required for the full evaluation")
    settings = Settings(docling_backend="docling")  # type: ignore[call-arg]
    if args.stage == "chunk":
        report: ParserEvaluationReport | ChunkEvaluationReport = (
            run_m2_chunk_evaluation(settings)
        )
        output = args.output or DEFAULT_CHUNK_REPORT_PATH
    else:
        report = run_m2_parser_evaluation(settings)
        output = args.output or DEFAULT_REPORT_PATH
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if isinstance(report, ChunkEvaluationReport):
        print(
            f"run_status={report.run_status} "
            f"documents={report.documents_parsed} "
            f"golden={report.golden_cases_total} "
            f"quality_gate_passed={report.quality_gate_passed}"
        )
    else:
        print(
            f"run_status={report.run_status} "
            f"documents={report.aggregate.documents_total} "
            f"parsed={report.aggregate.parses_completed}"
        )
    return 0 if report.run_status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(_main())
