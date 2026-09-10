"""Strict, framework-neutral contracts for the M2-22 RAG evaluation boundary."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from datetime import date
from pathlib import PurePosixPath
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import (
    Field,
    FiniteFloat,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.schemas.common import M1Schema

MIB = 1024 * 1024
GIB = 1024 * MIB
EXTERNAL_RAW_DOWNLOAD_HARD_MAX_BYTES = 200 * MIB
PROCESSED_ARTIFACT_TARGET_MAX_BYTES = 300 * MIB
POSTGRES_INDEX_TARGET_MAX_BYTES = 600 * MIB
MINIMUM_FREE_SPACE_BYTES = 3 * GIB
MAX_SIGNED_64_BIT_INTEGER = 2**63 - 1
MAX_EVALUATION_SERIALIZED_BYTES = 1024 * 1024
MAX_MANIFEST_SERIALIZED_BYTES = 256 * 1024
MAX_JSON_DEPTH = 12
MAX_JSON_KEYS = 128
MAX_JSON_LIST_ITEMS = 1000

EvaluationSourceGroup = Literal[
    "synthetic_engineering_regression",
    "cross_border_core",
    "complex_document_diagnostics",
    "security_acl_version",
]
EvaluationSourceKind = Literal[
    "public_source",
    "deterministic_transform",
    "synthetic_demo",
]
EvaluationSourceFormat = Literal[
    "pdf",
    "docx",
    "xlsx",
    "csv",
    "png",
    "jpeg",
    "webpage",
    "repository_archive",
    "dataset_archive",
]
LicenseStatus = Literal[
    "pending_review",
    "allowed_redistribution",
    "allowed_no_redistribution",
    "prohibited",
]
SourceLifecycleStatus = Literal["planned", "downloaded", "verified", "rejected"]
EvaluationSplit = Literal["debug", "validation", "test"]
EvaluationDifficulty = Literal["direct", "multi_step", "adversarial"]
ExpectedNonAnswerReason = Literal[
    "acl_denied",
    "version_unavailable",
    "source_rejected",
    "unknown",
    "no_evidence",
]
MetricDirection = Literal["higher_is_better", "lower_is_better", "zero_tolerance"]
ProjectMetricStatus = Literal["completed", "calculation_failed", "skipped"]
RagasMetricStatus = Literal[
    "completed",
    "framework_failed",
    "judge_failed",
    "skipped",
]
FailureCategory = Literal[
    "input_invalid",
    "calculation_error",
    "framework_error",
    "network_error",
    "judge_provider_error",
    "judge_timeout",
    "rate_limited",
    "dependency_unavailable",
    "safety_violation",
]
EvaluationLayer = Literal[
    "parser",
    "ocr",
    "chunk",
    "retrieval",
    "reranker",
    "context",
    "answer",
    "citation",
    "safety",
]
LayerResultStatus = Literal["completed", "failed", "skipped"]
EvaluatorRunStatus = Literal[
    "planned",
    "running",
    "completed",
    "framework_failed",
    "judge_failed",
    "skipped",
]
ProjectMetricName = Literal[
    "parser_fact_recovery_rate",
    "ocr_field_accuracy",
    "chunk_answer_containment_rate",
    "evidence_span_coverage_rate",
    "boundary_break_rate",
    "heading_retention_rate",
    "table_row_integrity_rate",
    "precision",
    "recall",
    "hit_rate",
    "mrr",
    "ndcg",
    "context_evidence_coverage_rate",
    "citation_precision",
    "citation_recall",
    "acl_security_pass_rate",
    "version_security_pass_rate",
    "latency_ms",
    "peak_memory_bytes",
]
RagasMetricName = Literal[
    "context_precision",
    "context_recall",
    "context_relevancy",
    "noise_sensitivity",
    "faithfulness",
    "response_relevancy",
    "factual_correctness",
    "semantic_similarity",
]

SafeIdentifier = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        min_length=3,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9._-]{2,99}$",
    ),
]
VersionLabel = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
    ),
]
ModelIdentifier = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$",
    ),
]
LanguageCode = Annotated[
    str,
    StringConstraints(
        strict=True,
        pattern=r"^[a-z]{2,3}(?:-[A-Z]{2})?$",
        max_length=6,
    ),
]
Sha256 = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$", max_length=64),
]

_DRIVE_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_SENSITIVE_FAILURE_MARKERS = (
    "traceback",
    "stack trace",
    "sql=",
    "select ",
    "insert ",
    "update ",
    "delete from",
    "api_key",
    "apikey",
    "password",
    "access_token",
    "storage_key",
    "postgresql://",
)


def _validate_sha256(value: str | None) -> str | None:
    if value is not None and len(set(value)) == 1:
        raise ValueError("SHA-256 cannot be a repeated placeholder value")
    return value


def _validate_https_url(value: str) -> str:
    parsed = urlsplit(value)
    hostname = parsed.hostname
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError("source URL must be a safe HTTPS URL")
    if hostname.casefold() == "localhost" or hostname.casefold().endswith(".local"):
        raise ValueError("source URL cannot target a local host")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        if "." not in hostname:
            raise ValueError("source URL requires a qualified public host") from None
    else:
        raise ValueError("source URL cannot use an IP literal")
    return value


def _validate_relative_path(value: str | None) -> str | None:
    if value is None:
        return None
    if (
        value != value.strip()
        or not value
        or "\\" in value
        or value.startswith(("/", "//"))
        or _DRIVE_PATH.match(value)
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError("path must be a safe relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("path must not escape its managed relative root")
    normalized = path.as_posix()
    if normalized != value:
        raise ValueError("path must use one normalized relative representation")
    return value


def _validate_safe_failure_summary(value: str | None) -> str | None:
    if value is None:
        return None
    folded = value.casefold()
    if (
        any(marker in folded for marker in _SENSITIVE_FAILURE_MARKERS)
        or _DRIVE_PATH.search(value) is not None
        or "\\\\" in value
        or "/home/" in folded
        or "/users/" in folded
    ):
        raise ValueError("failure summary must not expose raw or sensitive details")
    return value


class EvaluationSource(M1Schema):
    """One bounded source record whose lifecycle cannot claim unobserved facts."""

    source_id: SafeIdentifier
    dataset_version: VersionLabel
    source_group: EvaluationSourceGroup
    source_kind: EvaluationSourceKind
    source_name: str = Field(strict=True, min_length=1, max_length=300)
    source_organization: str = Field(strict=True, min_length=1, max_length=200)
    official_source_url: str = Field(strict=True, min_length=10, max_length=1000)
    source_format: EvaluationSourceFormat
    languages: list[LanguageCode] = Field(min_length=1, max_length=8)
    business_purpose: str = Field(strict=True, min_length=1, max_length=500)
    counts_toward_core_score: bool
    license_status: LicenseStatus
    license_name: str | None = Field(
        default=None, strict=True, min_length=1, max_length=200
    )
    license_url: str | None = Field(
        default=None, strict=True, min_length=10, max_length=1000
    )
    download_allowed: bool
    redistribution_allowed: bool
    accessed_on: date
    published_on: date | None = None
    source_version: VersionLabel | None = None
    lifecycle_status: SourceLifecycleStatus
    max_download_bytes: int = Field(strict=True, ge=1, le=MAX_SIGNED_64_BIT_INTEGER)
    expected_size_bytes: int | None = Field(
        default=None, strict=True, ge=1, le=MAX_SIGNED_64_BIT_INTEGER
    )
    actual_size_bytes: int | None = Field(
        default=None, strict=True, ge=1, le=MAX_SIGNED_64_BIT_INTEGER
    )
    raw_sha256: Sha256 | None = None
    processed_sha256: Sha256 | None = None
    raw_relative_path: str | None = Field(default=None, strict=True, max_length=500)
    processed_relative_path: str | None = Field(
        default=None, strict=True, max_length=500
    )
    transformation_method: SafeIdentifier | None = None
    transformation_version: VersionLabel | None = None
    rejection_reason: str | None = Field(
        default=None, strict=True, min_length=1, max_length=300
    )

    @field_validator("official_source_url")
    @classmethod
    def validate_official_source_url(cls, value: str) -> str:
        return _validate_https_url(value)

    @field_validator("license_url")
    @classmethod
    def validate_license_url(cls, value: str | None) -> str | None:
        return None if value is None else _validate_https_url(value)

    @field_validator("raw_relative_path", "processed_relative_path")
    @classmethod
    def validate_managed_path(cls, value: str | None) -> str | None:
        return _validate_relative_path(value)

    @field_validator("raw_sha256", "processed_sha256")
    @classmethod
    def reject_placeholder_hash(cls, value: str | None) -> str | None:
        return _validate_sha256(value)

    @field_validator("rejection_reason")
    @classmethod
    def validate_rejection_reason(cls, value: str | None) -> str | None:
        return _validate_safe_failure_summary(value)

    @model_validator(mode="after")
    def validate_source_rules(self) -> EvaluationSource:
        if len(self.languages) != len(set(self.languages)):
            raise ValueError("source languages must be unique")
        if self.published_on is not None and self.published_on > self.accessed_on:
            raise ValueError("source publication date cannot be after access date")
        if self.counts_toward_core_score and self.source_group != "cross_border_core":
            raise ValueError("only cross-border core sources may enter the core score")
        if (
            self.expected_size_bytes is not None
            and self.expected_size_bytes > self.max_download_bytes
        ):
            raise ValueError("expected source size exceeds its download budget")
        if (
            self.actual_size_bytes is not None
            and self.actual_size_bytes > self.max_download_bytes
        ):
            raise ValueError("actual source size exceeds its download budget")

        allowed_statuses = {"allowed_redistribution", "allowed_no_redistribution"}
        if self.license_status in allowed_statuses:
            if (
                self.license_name is None
                or self.license_url is None
                or not self.download_allowed
            ):
                raise ValueError(
                    "allowed license status requires reviewed license details"
                )
        elif self.download_allowed:
            raise ValueError("unreviewed or prohibited license cannot allow download")
        if self.license_status == "allowed_redistribution":
            if not self.redistribution_allowed:
                raise ValueError(
                    "redistribution license must declare redistribution allowed"
                )
        elif self.redistribution_allowed:
            raise ValueError("redistribution cannot be allowed by this license status")

        raw_fields = (self.actual_size_bytes, self.raw_sha256, self.raw_relative_path)
        processed_fields = (
            self.processed_sha256,
            self.processed_relative_path,
            self.transformation_method,
            self.transformation_version,
        )
        if (
            self.lifecycle_status != "verified"
            and any(value is not None for value in processed_fields)
            and not all(value is not None for value in processed_fields)
        ):
            raise ValueError(
                "processed observations must be recorded as one complete group"
            )

        if self.lifecycle_status == "planned":
            if any(value is not None for value in (*raw_fields, *processed_fields)):
                raise ValueError("planned source cannot contain download observations")
            if self.rejection_reason is not None:
                raise ValueError("planned source cannot contain a rejection reason")
            return self
        if self.lifecycle_status == "downloaded":
            if not all(value is not None for value in raw_fields):
                raise ValueError(
                    "downloaded source requires size, raw hash, and raw path"
                )
            if not self.download_allowed:
                raise ValueError("downloaded source requires an allowed license state")
            if self.rejection_reason is not None:
                raise ValueError("downloaded source cannot contain a rejection reason")
            return self
        if self.lifecycle_status == "verified":
            if (
                not all(value is not None for value in raw_fields)
                or not all(value is not None for value in processed_fields)
                or self.source_version is None
            ):
                raise ValueError(
                    "verified source requires version, sizes, paths, hashes, and transform identity"
                )
            if not self.download_allowed or self.rejection_reason is not None:
                raise ValueError(
                    "verified source requires an allowed, non-rejected state"
                )
            return self

        if self.rejection_reason is None:
            raise ValueError("rejected source requires a safe rejection reason")
        if any(value is not None for value in (*raw_fields, *processed_fields)):
            raise ValueError(
                "rejected source cannot retain accepted download observations"
            )
        return self


class EvaluationSourceManifest(M1Schema):
    """A small source allow-list, separate from all questions and Golden answers."""

    manifest_version: VersionLabel
    dataset_version: VersionLabel
    sources: list[EvaluationSource] = Field(min_length=1, max_length=64)

    @property
    def total_external_download_budget_bytes(self) -> int:
        return sum(
            source.max_download_bytes
            for source in self.sources
            if source.source_kind != "synthetic_demo"
        )

    def canonical_json(self) -> str:
        return canonical_evaluation_json(self)

    def canonical_sha256(self) -> str:
        return canonical_evaluation_sha256(self)

    @model_validator(mode="after")
    def validate_manifest(self) -> EvaluationSourceManifest:
        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source IDs must be unique")
        if any(
            source.dataset_version != self.dataset_version for source in self.sources
        ):
            raise ValueError("source dataset version must match its Manifest")
        total = self.total_external_download_budget_bytes
        if total > MAX_SIGNED_64_BIT_INTEGER:
            raise ValueError("external source budget exceeds signed integer capacity")
        if total > EXTERNAL_RAW_DOWNLOAD_HARD_MAX_BYTES:
            raise ValueError("external raw download budget cannot exceed 200 MiB")
        if len(canonical_evaluation_bytes(self)) > MAX_MANIFEST_SERIALIZED_BYTES:
            raise ValueError("source Manifest exceeds its serialized size limit")
        return self


class ExpectedEvidenceSpan(M1Schema):
    """Human-checked source text and coordinates, never a Storage path."""

    source_id: SafeIdentifier
    document_id: SafeIdentifier
    source_type: Literal["pdf", "docx", "xlsx", "csv"]
    page_start: int | None = Field(default=None, strict=True, ge=1, le=2000)
    page_end: int | None = Field(default=None, strict=True, ge=1, le=2000)
    sheet_name: str | None = Field(
        default=None, strict=True, min_length=1, max_length=31
    )
    cell_range: str | None = Field(
        default=None,
        strict=True,
        pattern=r"^[A-Z]{1,3}[1-9][0-9]{0,6}(?::[A-Z]{1,3}[1-9][0-9]{0,6})?$",
        max_length=64,
    )
    row_start: int | None = Field(default=None, strict=True, ge=1, le=1_048_576)
    row_end: int | None = Field(default=None, strict=True, ge=1, le=1_048_576)
    character_start: int | None = Field(default=None, strict=True, ge=0, le=10_000_000)
    character_end: int | None = Field(default=None, strict=True, ge=1, le=10_000_000)
    exact_text: str = Field(strict=True, min_length=1, max_length=10_000)

    @model_validator(mode="after")
    def validate_coordinates(self) -> ExpectedEvidenceSpan:
        if (self.page_start is None) != (self.page_end is None):
            raise ValueError("page range requires both boundaries")
        if (
            self.page_start is not None
            and self.page_end is not None
            and self.page_end < self.page_start
        ):
            raise ValueError("page range must be ordered")
        if (self.row_start is None) != (self.row_end is None):
            raise ValueError("row range requires both boundaries")
        if (
            self.row_start is not None
            and self.row_end is not None
            and self.row_end < self.row_start
        ):
            raise ValueError("row range must be ordered")
        if (self.character_start is None) != (self.character_end is None):
            raise ValueError("character range requires both boundaries")
        if (
            self.character_start is not None
            and self.character_end is not None
            and self.character_end <= self.character_start
        ):
            raise ValueError("character range must be non-empty and ordered")
        if (
            self.source_type in {"pdf", "docx"}
            and self.page_start is None
            and self.character_start is None
        ):
            raise ValueError("document Evidence requires a page or character range")
        if self.source_type == "xlsx" and self.sheet_name is None:
            raise ValueError("XLSX Evidence requires a sheet name")
        if (
            self.source_type in {"xlsx", "csv"}
            and self.cell_range is None
            and self.row_start is None
        ):
            raise ValueError("tabular Evidence requires a cell or row range")
        if self.source_type != "xlsx" and (
            self.sheet_name is not None or self.cell_range is not None
        ):
            raise ValueError("only XLSX Evidence can use worksheet coordinates")
        return self


class EvaluationCase(M1Schema):
    """One Golden case; trusted identity and ACL are fixture references only."""

    case_id: SafeIdentifier
    dataset_version: VersionLabel
    split: EvaluationSplit
    question: str = Field(strict=True, min_length=1, max_length=2000)
    language: LanguageCode
    category: SafeIdentifier
    difficulty: EvaluationDifficulty
    source_group: EvaluationSourceGroup
    expected_document_ids: list[SafeIdentifier] = Field(
        default_factory=list, max_length=20
    )
    expected_evidence_spans: list[ExpectedEvidenceSpan] = Field(
        default_factory=list, max_length=20
    )
    answer_key_points: list[str] = Field(default_factory=list, max_length=20)
    acceptable_answer_variants: list[str] = Field(default_factory=list, max_length=20)
    forbidden_claims: list[str] = Field(default_factory=list, max_length=20)
    should_answer: bool
    expected_non_answer_reason: ExpectedNonAnswerReason | None = None
    trusted_user_fixture_id: SafeIdentifier
    acl_fixture_id: SafeIdentifier
    version_fixture_id: SafeIdentifier

    @field_validator(
        "answer_key_points", "acceptable_answer_variants", "forbidden_claims"
    )
    @classmethod
    def validate_bounded_text_list(cls, value: list[str]) -> list[str]:
        if any(
            not isinstance(item, str) or not 1 <= len(item.strip()) <= 500
            for item in value
        ):
            raise ValueError("Golden text items must contain 1-500 characters")
        if len(value) != len(set(value)):
            raise ValueError("Golden text items must be unique")
        return [item.strip() for item in value]

    @model_validator(mode="after")
    def validate_case(self) -> EvaluationCase:
        if len(self.expected_document_ids) != len(set(self.expected_document_ids)):
            raise ValueError("expected document IDs must be unique")
        span_keys = [
            (
                span.source_id,
                span.document_id,
                span.source_type,
                span.page_start,
                span.sheet_name,
                span.cell_range,
                span.row_start,
                span.character_start,
            )
            for span in self.expected_evidence_spans
        ]
        if len(span_keys) != len(set(span_keys)):
            raise ValueError("expected Evidence spans must be unique")
        if self.should_answer:
            if self.expected_non_answer_reason is not None:
                raise ValueError("answerable case cannot declare a non-answer reason")
            if (
                not self.expected_document_ids
                or not self.expected_evidence_spans
                or not self.answer_key_points
            ):
                raise ValueError(
                    "answerable case requires documents, Evidence, and answer points"
                )
        else:
            if self.expected_non_answer_reason is None:
                raise ValueError(
                    "non-answer case requires an explicit non-answer reason"
                )
            if self.answer_key_points or self.acceptable_answer_variants:
                raise ValueError("non-answer case cannot contain answer material")
        return self


class EvaluationDataset(M1Schema):
    """A versioned, bounded collection that rejects duplicate Golden identities."""

    dataset_version: VersionLabel
    cases: list[EvaluationCase] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_dataset(self) -> EvaluationDataset:
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("case IDs must be unique")
        if any(case.dataset_version != self.dataset_version for case in self.cases):
            raise ValueError("case dataset version must match its dataset version")
        canonical_evaluation_bytes(self)
        return self


HeadingBindingScope = Literal["following_flow", "same_column"]
RejectedHeadingReason = Literal[
    "body_list_item",
    "numeric_callout",
    "field_label",
    "field_value",
    "masthead_label",
]


def _normalize_heading_review_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


class HeadingHintAuditSummary(M1Schema):
    """Reviewed partition of every Parser heading hint for one source."""

    source_id: SafeIdentifier
    hints_total: int = Field(strict=True, ge=1, le=1000)
    standalone_heading_hints: int = Field(strict=True, ge=0, le=1000)
    composite_component_hints: int = Field(strict=True, ge=0, le=1000)
    non_heading_hints: int = Field(strict=True, ge=0, le=1000)

    @model_validator(mode="after")
    def validate_partition(self) -> HeadingHintAuditSummary:
        classified = (
            self.standalone_heading_hints
            + self.composite_component_hints
            + self.non_heading_hints
        )
        if classified != self.hints_total:
            raise ValueError("heading hint audit partition must match its total")
        return self


class HeadingHintReference(M1Schema):
    """One stable occurrence of a Parser hint on a physical page."""

    page_number: int = Field(strict=True, ge=1, le=2000)
    text: str = Field(strict=True, min_length=1, max_length=200)
    parser_hint_level: int = Field(strict=True, ge=1, le=9)
    hint_occurrence: int = Field(default=1, strict=True, ge=1, le=100)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("heading hint text cannot have outer whitespace")
        return value


class TrustedHeadingCandidate(HeadingHintReference):
    """A visually reviewed Parser hint that is a standalone heading."""

    heading_id: SafeIdentifier
    source_id: SafeIdentifier
    document_id: SafeIdentifier
    semantic_level: int = Field(strict=True, ge=1, le=9)


class CompositeHeadingGolden(M1Schema):
    """One visual heading assembled from multiple Parser hint fragments."""

    heading_id: SafeIdentifier
    source_id: SafeIdentifier
    document_id: SafeIdentifier
    canonical_text: str = Field(strict=True, min_length=1, max_length=200)
    semantic_level: int = Field(strict=True, ge=1, le=9)
    components: list[HeadingHintReference] = Field(min_length=2, max_length=4)

    @field_validator("canonical_text")
    @classmethod
    def normalize_canonical_text(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("canonical heading text cannot have outer whitespace")
        return value

    @model_validator(mode="after")
    def validate_components(self) -> CompositeHeadingGolden:
        pages = {component.page_number for component in self.components}
        if len(pages) != 1:
            raise ValueError("composite heading components must share one page")
        keys = [
            (component.text, component.hint_occurrence) for component in self.components
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("composite heading components must be unique")
        combined = " ".join(component.text for component in self.components)
        if _normalize_heading_review_text(combined) != (
            _normalize_heading_review_text(self.canonical_text)
        ):
            raise ValueError("composite heading text must equal its ordered components")
        return self


class RejectedHeadingCandidate(HeadingHintReference):
    """A reviewed Parser hint that must never become independent heading metadata."""

    candidate_id: SafeIdentifier
    source_id: SafeIdentifier
    document_id: SafeIdentifier
    reason: RejectedHeadingReason


class TrustedHeadingContextCase(M1Schema):
    """A trusted heading path bound to one exact, non-heading body anchor."""

    case_id: SafeIdentifier
    source_id: SafeIdentifier
    document_id: SafeIdentifier
    source_type: Literal["pdf", "docx"]
    heading_path: list[str] = Field(min_length=1, max_length=9)
    heading_page_number: int = Field(strict=True, ge=1, le=2000)
    heading_exact_text: str = Field(strict=True, min_length=1, max_length=500)
    body_document_id: SafeIdentifier
    body_page_number: int = Field(strict=True, ge=1, le=2000)
    body_exact_text: str = Field(strict=True, min_length=1, max_length=1000)
    binding_scope: HeadingBindingScope

    @field_validator("heading_path")
    @classmethod
    def validate_heading_path(cls, value: list[str]) -> list[str]:
        if any(
            not isinstance(part, str) or not part.strip() or len(part.strip()) > 200
            for part in value
        ):
            raise ValueError("heading path parts must contain 1-200 characters")
        return [part.strip() for part in value]

    @field_validator("heading_exact_text", "body_exact_text")
    @classmethod
    def validate_exact_text(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("heading Golden text cannot have outer whitespace")
        return value

    @model_validator(mode="after")
    def validate_binding(self) -> TrustedHeadingContextCase:
        if self.body_document_id != self.document_id:
            raise ValueError("heading and body anchors must use the same document")
        if _normalize_heading_review_text(self.heading_exact_text) != (
            _normalize_heading_review_text(self.heading_path[-1])
        ):
            raise ValueError("heading span must match the terminal heading path part")
        if _normalize_heading_review_text(self.heading_exact_text) == (
            _normalize_heading_review_text(self.body_exact_text)
        ):
            raise ValueError("heading context requires a non-heading body anchor")
        if (
            self.binding_scope == "same_column"
            and self.heading_page_number != self.body_page_number
        ):
            raise ValueError("same-column heading and body anchors must share one page")
        return self


class ChunkHeadingGoldenDataset(M1Schema):
    """Versioned visual truth separate from heuristic Parser heading hints."""

    dataset_version: Literal[
        "m2-chunk-heading-golden-v1",
        "m2-chunk-heading-golden-v2",
    ]
    review_protocol_version: Literal["m2-source-visual-heading-review-v1"]
    source_corpus_versions: list[VersionLabel] = Field(min_length=1, max_length=8)
    reviewed_source_ids: list[SafeIdentifier] = Field(min_length=1, max_length=64)
    hint_audits: list[HeadingHintAuditSummary] = Field(min_length=1, max_length=64)
    trusted_heading_candidates: list[TrustedHeadingCandidate] = Field(
        min_length=1,
        max_length=1000,
    )
    composite_headings: list[CompositeHeadingGolden] = Field(
        default_factory=list,
        max_length=200,
    )
    rejected_heading_candidates: list[RejectedHeadingCandidate] = Field(
        default_factory=list,
        max_length=1000,
    )
    trusted_context_cases: list[TrustedHeadingContextCase] = Field(
        min_length=1,
        max_length=1000,
    )

    def canonical_json(self) -> str:
        return canonical_evaluation_json(self)

    def canonical_sha256(self) -> str:
        return canonical_evaluation_sha256(self)

    @model_validator(mode="after")
    def validate_dataset(self) -> ChunkHeadingGoldenDataset:
        if len(self.source_corpus_versions) != len(set(self.source_corpus_versions)):
            raise ValueError("heading Golden source corpus versions must be unique")
        if len(self.reviewed_source_ids) != len(set(self.reviewed_source_ids)):
            raise ValueError("heading Golden reviewed source IDs must be unique")

        audit_sources = [audit.source_id for audit in self.hint_audits]
        if len(audit_sources) != len(set(audit_sources)):
            raise ValueError("heading hint audit sources must be unique")
        reviewed = set(self.reviewed_source_ids)
        if set(audit_sources) != reviewed:
            raise ValueError("every reviewed source requires one heading hint audit")

        all_ids = [item.heading_id for item in self.trusted_heading_candidates]
        all_ids.extend(item.heading_id for item in self.composite_headings)
        all_ids.extend(item.candidate_id for item in self.rejected_heading_candidates)
        all_ids.extend(item.case_id for item in self.trusted_context_cases)
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("heading Golden identities must be globally unique")

        classified_keys: list[tuple[str, int, str, int]] = []
        for trusted_candidate in self.trusted_heading_candidates:
            classified_keys.append(
                (
                    trusted_candidate.source_id,
                    trusted_candidate.page_number,
                    trusted_candidate.text,
                    trusted_candidate.hint_occurrence,
                )
            )
        for composite_heading in self.composite_headings:
            for component in composite_heading.components:
                classified_keys.append(
                    (
                        composite_heading.source_id,
                        component.page_number,
                        component.text,
                        component.hint_occurrence,
                    )
                )
        for rejected_candidate in self.rejected_heading_candidates:
            classified_keys.append(
                (
                    rejected_candidate.source_id,
                    rejected_candidate.page_number,
                    rejected_candidate.text,
                    rejected_candidate.hint_occurrence,
                )
            )
        if len(classified_keys) != len(set(classified_keys)):
            raise ValueError(
                "each Parser heading hint occurrence needs one classification"
            )
        if {key[0] for key in classified_keys} != reviewed:
            raise ValueError("classified heading hints must cover reviewed sources")

        audit_by_source = {audit.source_id: audit for audit in self.hint_audits}
        for source_id in reviewed:
            standalone = sum(
                item.source_id == source_id for item in self.trusted_heading_candidates
            )
            composite_components = sum(
                len(item.components)
                for item in self.composite_headings
                if item.source_id == source_id
            )
            rejected = sum(
                item.source_id == source_id for item in self.rejected_heading_candidates
            )
            audit = audit_by_source[source_id]
            if (
                standalone != audit.standalone_heading_hints
                or composite_components != audit.composite_component_hints
                or rejected != audit.non_heading_hints
            ):
                raise ValueError(
                    "heading hint classifications must match audit partition"
                )

        trusted_terminals = {
            (
                item.source_id,
                item.page_number,
                _normalize_heading_review_text(item.text),
            )
            for item in self.trusted_heading_candidates
        }
        trusted_terminals.update(
            (
                item.source_id,
                item.components[0].page_number,
                _normalize_heading_review_text(item.canonical_text),
            )
            for item in self.composite_headings
        )
        for case in self.trusted_context_cases:
            if case.source_id not in reviewed:
                raise ValueError("heading context source must be reviewed")
            key = (
                case.source_id,
                case.heading_page_number,
                _normalize_heading_review_text(case.heading_exact_text),
            )
            if key not in trusted_terminals:
                raise ValueError("heading context must target a trusted heading")

        canonical_evaluation_bytes(self)
        return self


class ChunkEvaluationConfig(M1Schema):
    """The complete structure-aware Chunk configuration used by one experiment."""

    config_id: SafeIdentifier
    config_version: VersionLabel = "m2-rag-chunk-config-v1"
    target_tokens: int = Field(strict=True, ge=400, le=700)
    max_tokens: int = Field(strict=True, ge=400, le=1000)
    text_overlap_tokens: int = Field(strict=True, ge=80, le=120)
    heading_context_max_tokens: int = Field(strict=True, ge=20, le=200)
    table_row_overlap: int = Field(strict=True, ge=0, le=20)
    repeated_edge_min_pages: int = Field(default=2, strict=True, ge=2, le=20)
    repeat_table_headers: bool = True
    include_hidden_sheets: bool = True
    normalization_version: Literal["m2-chunk-normalization-v1"] = (
        "m2-chunk-normalization-v1"
    )
    chunker_name: Literal["structure_aware"] = "structure_aware"
    chunker_version: Literal[
        "m2-structure-aware-chunker-v1",
        "m2-structure-aware-chunker-v2",
        "m2-structure-aware-chunker-v3",
    ] = "m2-structure-aware-chunker-v3"
    token_counter_name: Literal["unicode_mixed"] = "unicode_mixed"
    token_counter_version: Literal["m2-unicode-token-counter-v1"] = (
        "m2-unicode-token-counter-v1"
    )

    @model_validator(mode="after")
    def validate_chunk_budgets(self) -> ChunkEvaluationConfig:
        if self.target_tokens > self.max_tokens:
            raise ValueError("chunk target cannot exceed max")
        if self.text_overlap_tokens >= self.target_tokens:
            raise ValueError("chunk overlap must be smaller than target")
        if self.heading_context_max_tokens >= self.target_tokens:
            raise ValueError("heading context must be smaller than target")
        return self


def default_chunk_evaluation_configs() -> list[ChunkEvaluationConfig]:
    """Return the four frozen first-round variants without mutating Settings."""

    common: dict[str, Any] = {
        "text_overlap_tokens": 100,
        "heading_context_max_tokens": 120,
        "table_row_overlap": 1,
        "repeated_edge_min_pages": 2,
        "repeat_table_headers": True,
        "include_hidden_sheets": True,
    }
    return [
        ChunkEvaluationConfig(
            config_id="chunk-compact", target_tokens=400, max_tokens=500, **common
        ),
        ChunkEvaluationConfig(
            config_id="chunk-medium", target_tokens=500, max_tokens=600, **common
        ),
        ChunkEvaluationConfig(
            config_id="chunk-current", target_tokens=600, max_tokens=700, **common
        ),
        ChunkEvaluationConfig(
            config_id="chunk-large", target_tokens=700, max_tokens=850, **common
        ),
    ]


class RetrievalContextEvaluationConfig(M1Schema):
    """Server-owned retrieval, Reranker, model, language, and Context identity."""

    config_id: SafeIdentifier
    config_version: VersionLabel
    dense_candidate_count: int = Field(strict=True, ge=5, le=100)
    lexical_candidate_count: int = Field(strict=True, ge=5, le=100)
    hybrid_candidate_count: int = Field(strict=True, ge=5, le=100)
    rrf_k: int = Field(strict=True, ge=1, le=200)
    reranker_top_k: int = Field(strict=True, ge=1, le=20)
    context_neighbor_window: int = Field(strict=True, ge=0, le=1)
    context_max_tokens: int = Field(strict=True, ge=700, le=16_000)
    embedding_model: ModelIdentifier
    embedding_version: VersionLabel
    reranker_model: ModelIdentifier
    reranker_version: VersionLabel
    query_languages: list[LanguageCode] = Field(min_length=1, max_length=8)
    dataset_version: VersionLabel

    @model_validator(mode="after")
    def validate_retrieval_relationships(self) -> RetrievalContextEvaluationConfig:
        if self.reranker_top_k > min(
            self.dense_candidate_count,
            self.lexical_candidate_count,
            self.hybrid_candidate_count,
        ):
            raise ValueError("Reranker top k cannot exceed any candidate count")
        if (
            self.hybrid_candidate_count
            > self.dense_candidate_count + self.lexical_candidate_count
        ):
            raise ValueError("Hybrid candidates cannot exceed the two input lists")
        if len(self.query_languages) != len(set(self.query_languages)):
            raise ValueError("query languages must be unique")
        return self


class EvaluationConfigurationCatalog(M1Schema):
    """A bounded catalog whose IDs remain unique across configuration kinds."""

    catalog_version: VersionLabel
    chunk_configs: list[ChunkEvaluationConfig] = Field(min_length=1, max_length=16)
    retrieval_context_configs: list[RetrievalContextEvaluationConfig] = Field(
        min_length=1, max_length=32
    )

    @model_validator(mode="after")
    def validate_config_ids(self) -> EvaluationConfigurationCatalog:
        config_ids = [item.config_id for item in self.chunk_configs] + [
            item.config_id for item in self.retrieval_context_configs
        ]
        if len(config_ids) != len(set(config_ids)):
            raise ValueError("config IDs must be unique across the catalog")
        return self


class JudgeParameters(M1Schema):
    """A small allow-list of Judge settings; arbitrary provider payloads are forbidden."""

    temperature: FiniteFloat = Field(ge=0, le=2)
    top_p: FiniteFloat = Field(gt=0, le=1)
    max_output_tokens: int = Field(strict=True, ge=128, le=8192)
    seed: int | None = Field(default=None, strict=True, ge=0, le=2**31 - 1)


class RetryPolicySummary(M1Schema):
    """Reproducible retry identity without executable callbacks or raw errors."""

    max_attempts: int = Field(strict=True, ge=1, le=5)
    timeout_ms: int = Field(strict=True, ge=100, le=120_000)


class EvaluatorIdentity(M1Schema):
    """Framework-neutral metric provenance, including an optional semantic Judge."""

    evaluator_id: SafeIdentifier
    evaluator_backend: Literal["project", "ragas"]
    evaluator_framework: SafeIdentifier
    evaluator_framework_version: VersionLabel
    metric_name: ProjectMetricName | RagasMetricName
    metric_source: Literal["project_deterministic", "ragas_semantic"]
    judge_provider: SafeIdentifier | None = None
    judge_model: ModelIdentifier | None = None
    judge_model_version: VersionLabel | None = None
    judge_parameters: JudgeParameters | None = None
    review_prompt_version: VersionLabel | None = None
    review_prompt_sha256: Sha256 | None = None
    retry_policy: RetryPolicySummary
    run_status: EvaluatorRunStatus
    failure_category: FailureCategory | None = None
    failure_summary: str | None = Field(
        default=None, strict=True, min_length=1, max_length=300
    )

    @field_validator("review_prompt_sha256")
    @classmethod
    def validate_prompt_hash(cls, value: str | None) -> str | None:
        return _validate_sha256(value)

    @field_validator("failure_summary")
    @classmethod
    def validate_failure_summary(cls, value: str | None) -> str | None:
        return _validate_safe_failure_summary(value)

    @model_validator(mode="after")
    def validate_evaluator(self) -> EvaluatorIdentity:
        judge_fields = (
            self.judge_provider,
            self.judge_model,
            self.judge_model_version,
            self.judge_parameters,
            self.review_prompt_version,
            self.review_prompt_sha256,
        )
        if self.evaluator_backend == "project":
            if (
                self.metric_source != "project_deterministic"
                or self.metric_name not in _PROJECT_METRIC_NAMES
            ):
                raise ValueError(
                    "project evaluator requires a project deterministic metric"
                )
            if any(value is not None for value in judge_fields):
                raise ValueError(
                    "project deterministic evaluator cannot declare a Judge"
                )
        else:
            if (
                self.metric_source != "ragas_semantic"
                or self.metric_name not in _RAGAS_METRIC_NAMES
            ):
                raise ValueError("Ragas evaluator requires a Ragas semantic metric")
            if not all(value is not None for value in judge_fields):
                raise ValueError(
                    "Ragas semantic evaluator requires complete Judge and Prompt identity"
                )
        if self.run_status in {"framework_failed", "judge_failed", "skipped"}:
            if self.failure_category is None or self.failure_summary is None:
                raise ValueError(
                    "non-success evaluator status requires a safe failure classification"
                )
        elif self.failure_category is not None or self.failure_summary is not None:
            raise ValueError("normal evaluator status cannot contain failure details")
        if (
            self.run_status == "framework_failed"
            and self.failure_category != "framework_error"
        ):
            raise ValueError(
                "framework failure requires framework_error classification"
            )
        if self.run_status == "judge_failed" and self.failure_category not in {
            "judge_provider_error",
            "judge_timeout",
            "rate_limited",
        }:
            raise ValueError("Judge failure requires a Judge failure classification")
        return self


_PROJECT_METRIC_NAMES = {
    "parser_fact_recovery_rate",
    "ocr_field_accuracy",
    "chunk_answer_containment_rate",
    "evidence_span_coverage_rate",
    "boundary_break_rate",
    "heading_retention_rate",
    "table_row_integrity_rate",
    "precision",
    "recall",
    "hit_rate",
    "mrr",
    "ndcg",
    "context_evidence_coverage_rate",
    "citation_precision",
    "citation_recall",
    "acl_security_pass_rate",
    "version_security_pass_rate",
    "latency_ms",
    "peak_memory_bytes",
}
_RAGAS_METRIC_NAMES = {
    "context_precision",
    "context_recall",
    "context_relevancy",
    "noise_sensitivity",
    "faithfulness",
    "response_relevancy",
    "factual_correctness",
    "semantic_similarity",
}
_LOWER_IS_BETTER_PROJECT_METRICS = {
    "boundary_break_rate",
    "latency_ms",
    "peak_memory_bytes",
}
_K_VALUES: dict[str, set[int]] = {
    "precision": {1, 3, 5, 8, 10, 20},
    "recall": {1, 3, 5, 8, 10, 20},
    "hit_rate": {1, 3, 5, 8, 10, 20},
    "mrr": {10},
    "ndcg": {5, 10},
}


class ProjectMetricResult(M1Schema):
    """One deterministic metric; calculation failure is never a numeric zero."""

    metric_source: Literal["project_deterministic"] = "project_deterministic"
    metric_name: ProjectMetricName
    status: ProjectMetricStatus
    value: FiniteFloat | None = None
    direction: MetricDirection
    k: int | None = Field(default=None, strict=True, ge=1, le=100)
    failure_category: FailureCategory | None = None
    failure_summary: str | None = Field(
        default=None, strict=True, min_length=1, max_length=300
    )

    @field_validator("failure_summary")
    @classmethod
    def validate_failure_summary(cls, value: str | None) -> str | None:
        return _validate_safe_failure_summary(value)

    @model_validator(mode="after")
    def validate_metric(self) -> ProjectMetricResult:
        expected_direction = (
            "lower_is_better"
            if self.metric_name in _LOWER_IS_BETTER_PROJECT_METRICS
            else "higher_is_better"
        )
        if self.direction != expected_direction:
            raise ValueError(
                "project metric direction contradicts the metric definition"
            )
        expected_k = _K_VALUES.get(self.metric_name)
        if expected_k is None and self.k is not None:
            raise ValueError("this project metric does not accept k")
        if expected_k is not None and self.k not in expected_k:
            raise ValueError("project metric k is not in the frozen evaluation set")
        if self.status == "completed":
            if (
                self.value is None
                or self.failure_category is not None
                or self.failure_summary is not None
            ):
                raise ValueError(
                    "completed project metric requires only a numeric value"
                )
            value = float(self.value)
            if self.metric_name in {"latency_ms", "peak_memory_bytes"}:
                if value < 0:
                    raise ValueError("resource metric cannot be negative")
            elif not 0 <= value <= 1:
                raise ValueError(
                    "rate and ranking metrics must be between zero and one"
                )
        else:
            if (
                self.value is not None
                or self.failure_category is None
                or self.failure_summary is None
            ):
                raise ValueError(
                    "failed or skipped project metric requires no value and a safe reason"
                )
        return self


class RagasMetricResult(M1Schema):
    """One semantic result whose framework/Judge failures remain non-numeric."""

    metric_source: Literal["ragas_semantic"] = "ragas_semantic"
    metric_name: RagasMetricName
    status: RagasMetricStatus
    value: FiniteFloat | None = None
    direction: Literal["higher_is_better"]
    failure_category: FailureCategory | None = None
    failure_summary: str | None = Field(
        default=None, strict=True, min_length=1, max_length=300
    )

    @field_validator("failure_summary")
    @classmethod
    def validate_failure_summary(cls, value: str | None) -> str | None:
        return _validate_safe_failure_summary(value)

    @model_validator(mode="after")
    def validate_metric(self) -> RagasMetricResult:
        if self.status == "completed":
            if self.value is None or not 0 <= float(self.value) <= 1:
                raise ValueError(
                    "completed Ragas metric requires a score from zero to one"
                )
            if self.failure_category is not None or self.failure_summary is not None:
                raise ValueError(
                    "completed Ragas metric cannot include failure details"
                )
        else:
            if (
                self.value is not None
                or self.failure_category is None
                or self.failure_summary is None
            ):
                raise ValueError(
                    "Ragas failure or skip requires no score and a safe reason"
                )
            if (
                self.status == "framework_failed"
                and self.failure_category != "framework_error"
            ):
                raise ValueError("framework failure requires framework_error")
            if self.status == "judge_failed" and self.failure_category not in {
                "judge_provider_error",
                "judge_timeout",
                "rate_limited",
            }:
                raise ValueError("Judge failure requires a Judge failure category")
        return self


class EvaluationLayerResult(M1Schema):
    """A deterministic Parser-to-safety layer result with bounded resources."""

    layer: EvaluationLayer
    status: LayerResultStatus
    source_id: SafeIdentifier | None = None
    case_id: SafeIdentifier | None = None
    config_id: SafeIdentifier | None = None
    artifact_sha256: Sha256 | None = None
    project_metrics: list[ProjectMetricResult] = Field(
        default_factory=list, max_length=32
    )
    latency_ms: int | None = Field(default=None, strict=True, ge=0, le=86_400_000)
    peak_memory_bytes: int | None = Field(
        default=None, strict=True, ge=0, le=MAX_SIGNED_64_BIT_INTEGER
    )
    failure_category: FailureCategory | None = None
    failure_summary: str | None = Field(
        default=None, strict=True, min_length=1, max_length=300
    )

    @field_validator("artifact_sha256")
    @classmethod
    def validate_artifact_hash(cls, value: str | None) -> str | None:
        return _validate_sha256(value)

    @field_validator("failure_summary")
    @classmethod
    def validate_failure_summary(cls, value: str | None) -> str | None:
        return _validate_safe_failure_summary(value)

    @model_validator(mode="after")
    def validate_layer(self) -> EvaluationLayerResult:
        metric_keys = [(item.metric_name, item.k) for item in self.project_metrics]
        if len(metric_keys) != len(set(metric_keys)):
            raise ValueError("layer project metric identities must be unique")
        if self.status == "completed":
            if not self.project_metrics:
                raise ValueError("completed layer requires deterministic metrics")
            if self.failure_category is not None or self.failure_summary is not None:
                raise ValueError("completed layer cannot include failure details")
        else:
            if self.failure_category is None or self.failure_summary is None:
                raise ValueError(
                    "failed or skipped layer requires a safe classified reason"
                )
        return self


class DeterministicEvaluationResults(M1Schema):
    """Project-owned Parser/OCR/Chunk/retrieval/answer/Citation/safety column."""

    result_source: Literal["project_deterministic"] = "project_deterministic"
    layers: list[EvaluationLayerResult] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def validate_unique_layers(self) -> DeterministicEvaluationResults:
        layers = [item.layer for item in self.layers]
        if len(layers) != len(set(layers)):
            raise ValueError("deterministic layer results must be unique")
        return self


class RagasEvaluationResults(M1Schema):
    """Ragas semantic column, physically separate from deterministic metrics."""

    result_source: Literal["ragas_semantic"] = "ragas_semantic"
    evaluator_ids: list[SafeIdentifier] = Field(default_factory=list, max_length=16)
    metrics: list[RagasMetricResult] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def validate_ragas_results(self) -> RagasEvaluationResults:
        if len(self.evaluator_ids) != len(set(self.evaluator_ids)):
            raise ValueError("Ragas evaluator IDs must be unique")
        metric_names = [item.metric_name for item in self.metrics]
        if len(metric_names) != len(set(metric_names)):
            raise ValueError("Ragas metric names must be unique")
        return self


class EvaluationCaseResult(M1Schema):
    """One case result with explicit deterministic and Ragas sections."""

    run_id: SafeIdentifier
    case_id: SafeIdentifier
    deterministic: DeterministicEvaluationResults
    ragas: RagasEvaluationResults


class ComponentIdentity(M1Schema):
    """Versioned Parser/OCR/answer component without cache or filesystem paths."""

    name: SafeIdentifier
    version: VersionLabel
    provider: SafeIdentifier | None = None
    model_id: ModelIdentifier | None = None
    model_revision: VersionLabel | None = None

    @model_validator(mode="after")
    def validate_model_identity(self) -> ComponentIdentity:
        if (self.model_id is None) != (self.model_revision is None):
            raise ValueError("model ID and revision must be provided together")
        return self


class EvaluationRunIdentity(M1Schema):
    """Reproducibility envelope for data, code, models, Chunk and retrieval config."""

    run_id: SafeIdentifier
    source_manifest_version: VersionLabel
    source_manifest_sha256: Sha256
    dataset_version: VersionLabel
    dataset_sha256: Sha256
    code_revision: str = Field(strict=True, pattern=r"^[0-9a-f]{7,64}$", max_length=64)
    code_dirty: bool
    parser: ComponentIdentity
    ocr: ComponentIdentity | None = None
    chunk_config: ChunkEvaluationConfig
    retrieval_context_config: RetrievalContextEvaluationConfig
    answer_model: ComponentIdentity | None = None
    evaluators: list[EvaluatorIdentity] = Field(min_length=1, max_length=32)
    run_status: EvaluatorRunStatus
    failure_category: FailureCategory | None = None
    failure_summary: str | None = Field(
        default=None, strict=True, min_length=1, max_length=300
    )

    @field_validator("source_manifest_sha256", "dataset_sha256")
    @classmethod
    def validate_run_hash(cls, value: str) -> str:
        validated = _validate_sha256(value)
        assert validated is not None
        return validated

    @field_validator("failure_summary")
    @classmethod
    def validate_failure_summary(cls, value: str | None) -> str | None:
        return _validate_safe_failure_summary(value)

    @model_validator(mode="after")
    def validate_run(self) -> EvaluationRunIdentity:
        evaluator_ids = [item.evaluator_id for item in self.evaluators]
        if len(evaluator_ids) != len(set(evaluator_ids)):
            raise ValueError("run evaluator IDs must be unique")
        if self.retrieval_context_config.dataset_version != self.dataset_version:
            raise ValueError(
                "run and retrieval configuration dataset versions must match"
            )
        if self.run_status in {"framework_failed", "judge_failed", "skipped"}:
            if self.failure_category is None or self.failure_summary is None:
                raise ValueError(
                    "failed or skipped run requires a safe classified reason"
                )
        elif self.failure_category is not None or self.failure_summary is not None:
            raise ValueError("normal run status cannot include failure details")
        canonical_evaluation_bytes(self)
        return self


class DiskBudgetPolicy(M1Schema):
    """Frozen byte limits; targets are enforced by the preflight contract."""

    unit: Literal["bytes"] = "bytes"
    external_raw_hard_limit_bytes: Literal[209715200] = 209715200
    processed_artifact_target_limit_bytes: Literal[314572800] = 314572800
    postgres_index_target_limit_bytes: Literal[629145600] = 629145600
    minimum_free_space_bytes: Literal[3221225472] = 3221225472
    existing_model_cache_counts_as_corpus: Literal[False] = False
    implicit_model_download_allowed: Literal[False] = False


class DiskPreflightInput(M1Schema):
    """Pure caller-supplied size facts; this contract never reads or cleans a disk."""

    unit: Literal["bytes"]
    external_raw_bytes: int = Field(strict=True, ge=0, le=MAX_SIGNED_64_BIT_INTEGER)
    processed_artifact_bytes: int = Field(
        strict=True, ge=0, le=MAX_SIGNED_64_BIT_INTEGER
    )
    postgres_index_bytes: int = Field(strict=True, ge=0, le=MAX_SIGNED_64_BIT_INTEGER)
    existing_model_cache_bytes: int = Field(
        strict=True, ge=0, le=MAX_SIGNED_64_BIT_INTEGER
    )
    available_free_bytes: int | None = Field(
        default=None, strict=True, ge=0, le=MAX_SIGNED_64_BIT_INTEGER
    )


class DiskPreflightResult(M1Schema):
    """Deterministic gate result with fixed, non-sensitive reason codes."""

    allowed: bool
    unit: Literal["bytes"] = "bytes"
    reason_codes: list[
        Literal[
            "missing_free_space",
            "insufficient_free_space",
            "external_raw_limit_exceeded",
            "processed_artifact_target_exceeded",
            "postgres_index_target_exceeded",
        ]
    ] = Field(default_factory=list, max_length=5)
    existing_model_cache_excluded: Literal[True] = True
    implicit_model_download_allowed: Literal[False] = False

    @model_validator(mode="after")
    def validate_result(self) -> DiskPreflightResult:
        if self.allowed == bool(self.reason_codes):
            raise ValueError("disk preflight status must match its reason codes")
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("disk preflight reason codes must be unique")
        return self


def evaluate_disk_preflight(
    request: DiskPreflightInput,
    *,
    policy: DiskBudgetPolicy | None = None,
) -> DiskPreflightResult:
    """Evaluate frozen byte limits without touching files, databases, or model caches."""

    resolved = policy or DiskBudgetPolicy()
    reasons: list[str] = []
    if request.available_free_bytes is None:
        reasons.append("missing_free_space")
    elif request.available_free_bytes < resolved.minimum_free_space_bytes:
        reasons.append("insufficient_free_space")
    if request.external_raw_bytes > resolved.external_raw_hard_limit_bytes:
        reasons.append("external_raw_limit_exceeded")
    if (
        request.processed_artifact_bytes
        > resolved.processed_artifact_target_limit_bytes
    ):
        reasons.append("processed_artifact_target_exceeded")
    if request.postgres_index_bytes > resolved.postgres_index_target_limit_bytes:
        reasons.append("postgres_index_target_exceeded")
    return DiskPreflightResult(allowed=not reasons, reason_codes=reasons)  # type: ignore[arg-type]


def _validate_json_value(value: object, *, depth: int) -> None:
    if depth > MAX_JSON_DEPTH:
        raise ValueError(f"evaluation JSON depth cannot exceed {MAX_JSON_DEPTH}")
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not (float("-inf") < value < float("inf")):
            raise ValueError("evaluation JSON numbers must be finite")
        return
    if isinstance(value, list):
        if len(value) > MAX_JSON_LIST_ITEMS:
            raise ValueError("evaluation JSON list exceeds its item limit")
        for item in value:
            _validate_json_value(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > MAX_JSON_KEYS:
            raise ValueError("evaluation JSON object exceeds its key limit")
        for key, item in value.items():
            if not isinstance(key, str) or not 1 <= len(key) <= 128:
                raise ValueError("evaluation JSON keys must contain 1-128 characters")
            _validate_json_value(item, depth=depth + 1)
        return
    raise ValueError("evaluation payload must contain only safe JSON values")


def canonical_evaluation_bytes(value: M1Schema | dict[str, Any] | list[Any]) -> bytes:
    """Return bounded canonical UTF-8 JSON and reject NaN or unsupported values."""

    payload: object = (
        value.model_dump(mode="json") if isinstance(value, M1Schema) else value
    )
    _validate_json_value(payload, depth=1)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > MAX_EVALUATION_SERIALIZED_BYTES:
        raise ValueError("evaluation payload exceeds its serialized size limit")
    return encoded


def canonical_evaluation_json(value: M1Schema | dict[str, Any] | list[Any]) -> str:
    return canonical_evaluation_bytes(value).decode("utf-8")


def canonical_evaluation_sha256(value: M1Schema | dict[str, Any] | list[Any]) -> str:
    return hashlib.sha256(canonical_evaluation_bytes(value)).hexdigest()


__all__ = [
    "EXTERNAL_RAW_DOWNLOAD_HARD_MAX_BYTES",
    "MINIMUM_FREE_SPACE_BYTES",
    "ChunkEvaluationConfig",
    "ComponentIdentity",
    "DeterministicEvaluationResults",
    "DiskBudgetPolicy",
    "DiskPreflightInput",
    "DiskPreflightResult",
    "EvaluationCase",
    "EvaluationCaseResult",
    "EvaluationConfigurationCatalog",
    "EvaluationDataset",
    "EvaluationLayerResult",
    "EvaluationRunIdentity",
    "EvaluationSource",
    "EvaluationSourceManifest",
    "EvaluatorIdentity",
    "ExpectedEvidenceSpan",
    "JudgeParameters",
    "ProjectMetricResult",
    "RagasEvaluationResults",
    "RagasMetricResult",
    "RetrievalContextEvaluationConfig",
    "RetryPolicySummary",
    "canonical_evaluation_json",
    "canonical_evaluation_sha256",
    "default_chunk_evaluation_configs",
    "evaluate_disk_preflight",
]
