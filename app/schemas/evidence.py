"""Database Evidence response contracts for M1."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints

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
