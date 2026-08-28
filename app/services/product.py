"""Deterministic product resolution and specification business rules for M1."""

from __future__ import annotations

from typing import Protocol, cast
from uuid import UUID

from pydantic import ValidationError

from app.core.errors import (
    AmbiguousProductError,
    InternalDataContractError,
    ProductNotFoundError,
)
from app.repositories.product import ProductCandidate, ProductSpecRecord
from app.schemas.common import ProductStatus, VerificationStatus
from app.schemas.product import (
    GetProductSpecInput,
    ProductSpecItem,
    ProductSpecResult,
)


class ProductReader(Protocol):
    """The two read operations ProductSpecService is allowed to use."""

    def find_candidates(
        self,
        tenant_id: UUID,
        product_query: str,
    ) -> list[ProductCandidate]: ...

    def list_specs(
        self,
        tenant_id: UUID,
        variant_id: UUID,
    ) -> list[ProductSpecRecord]: ...


class ProductSpecService:
    """Turn repository facts into one strict product result or a business error."""

    def __init__(self, repository: ProductReader) -> None:
        self._repository = repository

    def get_product_spec(
        self,
        tenant_id: UUID,
        request: GetProductSpecInput,
    ) -> ProductSpecResult:
        """Resolve a unique SKU and return its declared M1 specifications."""

        candidates = self._repository.find_candidates(
            tenant_id,
            request.product_query,
        )
        if not candidates:
            raise ProductNotFoundError
        if len(candidates) > 1:
            raise AmbiguousProductError(candidate.sku for candidate in candidates)

        candidate = candidates[0]
        specs = self._repository.list_specs(tenant_id, candidate.variant_id)
        if not specs:
            raise ProductNotFoundError(missing_specs=True)
        if not candidate.synthetic_data:
            raise InternalDataContractError

        try:
            return ProductSpecResult(
                product_id=candidate.product_id,
                variant_id=candidate.variant_id,
                sku=candidate.sku,
                name_zh=candidate.name_zh,
                name_en=candidate.name_en,
                status=cast(ProductStatus, candidate.variant_status),
                specs=[
                    ProductSpecItem(
                        name=spec.name,
                        value=spec.value,
                        unit=spec.unit,
                        verification_status=cast(
                            VerificationStatus,
                            spec.verification_status,
                        ),
                    )
                    for spec in specs
                ],
                synthetic_data=True,
            )
        except ValidationError:
            raise InternalDataContractError from None
