"""Database Evidence response contracts for M1."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal, TypeAlias
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from app.schemas.common import SKU, M1Schema, MarketCode, ProductQuery, WarehouseCode
from app.schemas.context import CitationLabel
from app.schemas.inventory import InventoryResult
from app.schemas.product import ProductSpecResult
from app.schemas.retrieval import (
    RetrievalCandidateIdentity,
    RetrievalDocumentMetadata,
    RetrievalSourceLocator,
)

SourceName = Literal["synthetic_inventory", "synthetic_product_catalog"]
SourceLocator = Annotated[
    str,
    StringConstraints(
        strict=True,
        strip_whitespace=True,
        max_length=255,
        pattern=(
            r"^(inventory_snapshots|product_specs|product_variants)/"
            r"[0-9a-fA-F-]{36}$"
        ),
    ),
]


class ProductEvidenceQuery(M1Schema):
    """Safe normalized query facts for product-catalog Evidence."""

    product_query: ProductQuery
    sku: SKU


class InventoryEvidenceQuery(M1Schema):
    """Safe normalized query facts for inventory Evidence."""

    sku: SKU
    market_code: MarketCode
    warehouse_code: WarehouseCode | None = None


class EvidenceAccessScope(M1Schema):
    """Tenant and market boundaries used for one Evidence query."""

    tenant_id: UUID
    market_codes: list[MarketCode] = Field(min_length=1, max_length=2)


class EvidenceSummary(M1Schema):
    """Compact Evidence shown beside a chat answer."""

    id: UUID
    source_type: Literal["database"] = "database"
    source_name: SourceName
    title: str = Field(min_length=1, max_length=200)
    excerpt: str = Field(min_length=1, max_length=500)
    observed_at: AwareDatetime
    synthetic_data: Literal[True] = True


class EvidenceDetail(EvidenceSummary):
    """Authorized Evidence detail without database credentials or raw SQL."""

    source_locator: SourceLocator
    query_summary: ProductEvidenceQuery | InventoryEvidenceQuery
    structured_data: ProductSpecResult | InventoryResult
    confidence: Decimal | None = Field(default=None, ge=0, le=1, decimal_places=3)
    trust_level: Literal["internal_demo"] = "internal_demo"
    access_scope: EvidenceAccessScope
    created_at: AwareDatetime


class DocumentEvidenceSummary(M1Schema):
    """Compact knowledge/user-file Evidence without internal access-scope fields."""

    schema_version: Literal["m2-document-evidence-v1"] = "m2-document-evidence-v1"
    id: UUID
    source_type: Literal["knowledge", "user_file"]
    title: str = Field(min_length=1, max_length=300)
    excerpt: str = Field(min_length=1, max_length=1000)
    observed_at: AwareDatetime
    synthetic_data: Literal[True] = True


class DocumentEvidenceDetail(DocumentEvidenceSummary):
    """Traceable document Evidence with public locators but no tenant or ACL data."""

    context_id: UUID
    citation_label: CitationLabel
    identity: RetrievalCandidateIdentity
    document: RetrievalDocumentMetadata
    source_locator: RetrievalSourceLocator
    source_content_sha256: Annotated[
        str,
        StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$"),
    ]
    context_text_sha256: Annotated[
        str,
        StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$"),
    ]
    trust_level: Literal["document_snapshot"] = "document_snapshot"
    created_at: AwareDatetime


class ToolDocumentEvidenceDetail(DocumentEvidenceDetail):
    """Document Evidence Tool detail with the next public file-ID hop."""

    file_id: UUID


EvidenceToolDetail: TypeAlias = Annotated[
    EvidenceDetail | ToolDocumentEvidenceDetail,
    Field(discriminator="source_type"),
]


class GetEvidenceDetailInput(M1Schema):
    """The only model-controlled argument accepted by get_evidence_detail."""

    evidence_id: UUID = Field(
        description="需要按当前身份和权限重新验证并展开的公开Evidence ID"
    )


class GetEvidenceDetailResult(M1Schema):
    """One authorized database or document Evidence detail."""

    detail: EvidenceToolDetail

    @property
    def evidence_id(self) -> UUID:
        """Return the verified ID used by the success ToolEnvelope."""

        return self.detail.id


class AnswerEvidenceReference(M1Schema):
    """One stable final-answer label mapped to one opaque Evidence ID."""

    citation_label: CitationLabel
    evidence_id: UUID


class AnswerEvidenceMapping(M1Schema):
    """The ordered, bounded Evidence set persisted for one root Agent run."""

    root_run_id: UUID
    references: list[AnswerEvidenceReference] = Field(max_length=12)

    @model_validator(mode="after")
    def validate_order_and_identity(self) -> AnswerEvidenceMapping:
        evidence_ids = [reference.evidence_id for reference in self.references]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Evidence ID 不能重复")
        expected_labels = [
            f"[E{ordinal}]" for ordinal in range(1, len(self.references) + 1)
        ]
        actual_labels = [reference.citation_label for reference in self.references]
        if actual_labels != expected_labels:
            raise ValueError("Evidence 引用标签必须从 [E1] 开始连续排列")
        return self
