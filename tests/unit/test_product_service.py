from uuid import UUID, uuid4

import pytest

from app.core.errors import (
    AmbiguousProductError,
    InternalDataContractError,
    ProductNotFoundError,
)
from app.repositories.product import ProductCandidate, ProductSpecRecord
from app.schemas.product import GetProductSpecInput
from app.services.product import ProductSpecService


class FakeProductRepository:
    def __init__(
        self,
        candidates: list[ProductCandidate],
        specs: list[ProductSpecRecord],
    ) -> None:
        self.candidates = candidates
        self.specs = specs
        self.calls: list[tuple[str, UUID, object]] = []

    def find_candidates(
        self,
        tenant_id: UUID,
        product_query: str,
    ) -> list[ProductCandidate]:
        self.calls.append(("find_candidates", tenant_id, product_query))
        return self.candidates

    def list_specs(
        self,
        tenant_id: UUID,
        variant_id: UUID,
    ) -> list[ProductSpecRecord]:
        self.calls.append(("list_specs", tenant_id, variant_id))
        return self.specs


def candidate(
    sku: str = "LR-TL-MUSH-OR01",
    *,
    synthetic_data: bool = True,
) -> ProductCandidate:
    return ProductCandidate(
        product_id=uuid4(),
        variant_id=uuid4(),
        sku=sku,
        name_zh="橙色复古蘑菇台灯",
        name_en="LUMORIVA Orange Mushroom Table Lamp",
        product_status="candidate",
        variant_status="candidate",
        synthetic_data=synthetic_data,
    )


def spec(variant_id: UUID) -> ProductSpecRecord:
    return ProductSpecRecord(
        spec_id=uuid4(),
        variant_id=variant_id,
        name="height",
        value="30",
        unit="cm",
        source_type="synthetic_seed",
        source_id="m1-v1",
        verification_status="demo_declared",
    )


def test_product_service_returns_strict_result_for_one_candidate() -> None:
    tenant_id = uuid4()
    match = candidate()
    repository = FakeProductRepository([match], [spec(match.variant_id)])
    service = ProductSpecService(repository)

    result = service.get_product_spec(
        tenant_id,
        GetProductSpecInput(product_query="蘑菇灯"),
    )

    assert result.sku == "LR-TL-MUSH-OR01"
    assert result.status == "candidate"
    assert result.synthetic_data is True
    assert [(item.name, item.value, item.unit) for item in result.specs] == [
        ("height", "30", "cm")
    ]
    assert repository.calls == [
        ("find_candidates", tenant_id, "蘑菇灯"),
        ("list_specs", tenant_id, match.variant_id),
    ]


def test_product_service_maps_no_candidates_to_safe_not_found_error() -> None:
    service = ProductSpecService(FakeProductRepository([], []))

    with pytest.raises(ProductNotFoundError) as captured:
        service.get_product_spec(
            uuid4(),
            GetProductSpecInput(product_query="不存在的商品"),
        )

    assert captured.value.to_detail().model_dump() == {
        "code": "PRODUCT_NOT_FOUND",
        "message": "未找到匹配的商品，请检查商品名称或SKU",
        "retryable": False,
        "field": "product_query",
    }


def test_product_service_rejects_ambiguous_matches_without_reading_specs() -> None:
    first = candidate("LR-TL-MUSH-OR01")
    second = candidate("LR-TL-MINI-OR01")
    repository = FakeProductRepository([first, second], [])
    service = ProductSpecService(repository)

    with pytest.raises(AmbiguousProductError) as captured:
        service.get_product_spec(
            uuid4(),
            GetProductSpecInput(product_query="蘑菇灯"),
        )

    assert captured.value.candidate_skus == (
        "LR-TL-MINI-OR01",
        "LR-TL-MUSH-OR01",
    )
    assert captured.value.to_detail().code == "AMBIGUOUS_PRODUCT"
    assert all(call[0] != "list_specs" for call in repository.calls)


def test_product_service_rejects_product_without_specs() -> None:
    service = ProductSpecService(FakeProductRepository([candidate()], []))

    with pytest.raises(ProductNotFoundError) as captured:
        service.get_product_spec(
            uuid4(),
            GetProductSpecInput(product_query="LR-TL-MUSH-OR01"),
        )

    assert captured.value.code == "PRODUCT_NOT_FOUND"
    assert captured.value.message == "已找到商品，但没有可用的商品规格"


def test_product_service_rejects_non_demo_data_in_m1() -> None:
    match = candidate(synthetic_data=False)
    service = ProductSpecService(
        FakeProductRepository([match], [spec(match.variant_id)])
    )

    with pytest.raises(InternalDataContractError) as captured:
        service.get_product_spec(
            uuid4(),
            GetProductSpecInput(product_query="LR-TL-MUSH-OR01"),
        )

    assert captured.value.to_detail().code == "INTERNAL_ERROR"


def test_product_service_maps_invalid_repository_data_to_safe_internal_error() -> None:
    match = candidate()
    invalid_spec = spec(match.variant_id)
    invalid_spec = ProductSpecRecord(
        spec_id=invalid_spec.spec_id,
        variant_id=invalid_spec.variant_id,
        name=invalid_spec.name,
        value=invalid_spec.value,
        unit=invalid_spec.unit,
        source_type=invalid_spec.source_type,
        source_id=invalid_spec.source_id,
        verification_status="unexpected_status",
    )
    service = ProductSpecService(FakeProductRepository([match], [invalid_spec]))

    with pytest.raises(InternalDataContractError) as captured:
        service.get_product_spec(
            uuid4(),
            GetProductSpecInput(product_query="LR-TL-MUSH-OR01"),
        )

    assert captured.value.message == "商品数据不符合M1演示合同"
