"""Fixed, tenant-scoped product and specification reads for M1."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import any_, func, or_, select
from sqlalchemy.orm import Session

from app.models.catalog import Product, ProductSpec, ProductVariant
from app.repositories.common import apply_statement_timeout


@dataclass(frozen=True, slots=True)
class ProductCandidate:
    """One product/SKU candidate returned without exposing an ORM object."""

    product_id: UUID
    variant_id: UUID
    sku: str
    name_zh: str
    name_en: str
    product_status: str
    variant_status: str
    synthetic_data: bool


@dataclass(frozen=True, slots=True)
class ProductSpecRecord:
    """One specification fact with the source fields needed by Evidence later."""

    spec_id: UUID
    variant_id: UUID
    name: str
    value: str
    unit: str | None
    source_type: str
    source_id: str | None
    verification_status: str


class ProductRepository:
    """Read products through prewritten SQLAlchemy SELECT statements only."""

    def __init__(self, session: Session, statement_timeout_ms: int = 2000) -> None:
        self._session = session
        self._statement_timeout_ms = statement_timeout_ms

    def find_candidates(
        self,
        tenant_id: UUID,
        product_query: str,
    ) -> list[ProductCandidate]:
        """Resolve exact SKU first, then exact names and controlled aliases."""

        apply_statement_timeout(self._session, self._statement_timeout_ms)
        normalized_query = product_query.strip()

        exact_sku_statement = (
            select(Product, ProductVariant)
            .join(
                ProductVariant,
                (ProductVariant.tenant_id == Product.tenant_id)
                & (ProductVariant.product_id == Product.id),
            )
            .where(
                Product.tenant_id == tenant_id,
                ProductVariant.tenant_id == tenant_id,
                ProductVariant.sku == normalized_query,
            )
            .order_by(ProductVariant.sku)
        )
        exact_rows = self._session.execute(exact_sku_statement).all()
        if exact_rows:
            return [
                self._candidate(product, variant) for product, variant in exact_rows
            ]

        normalized_casefold = normalized_query.casefold()
        name_statement = (
            select(Product, ProductVariant)
            .join(
                ProductVariant,
                (ProductVariant.tenant_id == Product.tenant_id)
                & (ProductVariant.product_id == Product.id),
            )
            .where(
                Product.tenant_id == tenant_id,
                ProductVariant.tenant_id == tenant_id,
                or_(
                    Product.name_zh == normalized_query,
                    func.lower(Product.name_en) == normalized_casefold,
                    any_(Product.aliases) == normalized_query,
                ),
            )
            .order_by(ProductVariant.sku)
        )
        rows = self._session.execute(name_statement).all()
        return [self._candidate(product, variant) for product, variant in rows]

    def list_specs(
        self,
        tenant_id: UUID,
        variant_id: UUID,
    ) -> list[ProductSpecRecord]:
        """Read specifications only when both tenant and variant match."""

        apply_statement_timeout(self._session, self._statement_timeout_ms)
        statement = (
            select(ProductSpec)
            .where(
                ProductSpec.tenant_id == tenant_id,
                ProductSpec.variant_id == variant_id,
            )
            .order_by(ProductSpec.name)
        )
        specs = self._session.scalars(statement).all()
        return [
            ProductSpecRecord(
                spec_id=spec.id,
                variant_id=spec.variant_id,
                name=spec.name,
                value=spec.value,
                unit=spec.unit,
                source_type=spec.source_type,
                source_id=spec.source_id,
                verification_status=spec.verification_status,
            )
            for spec in specs
        ]

    @staticmethod
    def _candidate(product: Product, variant: ProductVariant) -> ProductCandidate:
        return ProductCandidate(
            product_id=product.id,
            variant_id=variant.id,
            sku=variant.sku,
            name_zh=product.name_zh,
            name_en=product.name_en,
            product_status=product.status,
            variant_status=variant.status,
            synthetic_data=product.is_demo,
        )
