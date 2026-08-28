from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import OperationalError

from app.core.errors import (
    DatabaseQueryError,
    DatabaseTimeoutError,
    InventoryDataContractError,
    InventoryNotFoundError,
    WarehouseRequiredError,
)
from app.repositories.inventory import InventoryRecord
from app.schemas.evidence import EvidenceAccessScope, EvidenceDetail
from app.schemas.inventory import InventoryResult, SearchInventoryInput
from app.services.evidence import EvidenceWriteContext
from app.services.inventory import InventoryService

NOW = datetime(2026, 8, 28, 6, 0, tzinfo=UTC)


class FakeInventoryRepository:
    def __init__(
        self,
        records: list[InventoryRecord] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.records = records or []
        self.error = error
        self.calls: list[tuple[UUID, str, str, str | None]] = []

    def find_latest(
        self,
        tenant_id: UUID,
        sku: str,
        market_code: str,
        warehouse_code: str | None = None,
    ) -> list[InventoryRecord]:
        self.calls.append((tenant_id, sku, market_code, warehouse_code))
        if self.error is not None:
            raise self.error
        return self.records


class FakeEvidenceWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[EvidenceWriteContext, SearchInventoryInput, UUID]] = []

    def persist_inventory_evidence(
        self,
        context: EvidenceWriteContext,
        request: SearchInventoryInput,
        inventory: InventoryResult,
        snapshot_id: UUID,
    ) -> EvidenceDetail:
        self.calls.append((context, request, snapshot_id))
        return EvidenceDetail(
            id=uuid4(),
            source_type="database",
            source_name="synthetic_inventory",
            source_locator=f"inventory_snapshots/{snapshot_id}",
            title="DE-FRA 蘑菇灯库存",
            excerpt=f"可售库存{inventory.available}件",
            query_summary={
                "sku": request.sku,
                "market_code": request.market_code,
                "warehouse_code": inventory.warehouse_code,
            },
            structured_data=inventory,
            observed_at=inventory.snapshot_at,
            confidence=Decimal("1.000"),
            trust_level="internal_demo",
            access_scope=EvidenceAccessScope(
                tenant_id=context.tenant_id,
                market_codes=[inventory.market_code],
            ),
            synthetic_data=True,
            created_at=NOW,
        )


def context() -> EvidenceWriteContext:
    return EvidenceWriteContext(
        tenant_id=uuid4(),
        agent_run_id=uuid4(),
        tool_call_id=uuid4(),
    )


def record(
    *,
    warehouse_code: str = "DE-FRA",
    on_hand: int = 150,
    reserved: int = 20,
    unsellable: int = 5,
    synthetic_data: bool = True,
) -> InventoryRecord:
    return InventoryRecord(
        snapshot_id=uuid4(),
        product_id=uuid4(),
        variant_id=uuid4(),
        warehouse_id=uuid4(),
        sku="LR-TL-MUSH-OR01",
        product_name="橙色复古蘑菇台灯",
        market_code="DE",
        warehouse_code=warehouse_code,
        warehouse_name=f"{warehouse_code}测试仓",
        on_hand=on_hand,
        reserved=reserved,
        unsellable=unsellable,
        inbound=80,
        safety_stock=60,
        snapshot_at=NOW,
        synthetic_data=synthetic_data,
    )


def request() -> SearchInventoryInput:
    return SearchInventoryInput(
        sku="LR-TL-MUSH-OR01",
        market_code="DE",
        warehouse_code="DE-FRA",
    )


def test_inventory_service_calculates_available_and_requires_evidence() -> None:
    runtime_context = context()
    stock = record()
    repository = FakeInventoryRepository([stock])
    evidence_writer = FakeEvidenceWriter()
    service = InventoryService(repository, evidence_writer)

    result = service.search_inventory(runtime_context, request())

    assert result.inventory.available == 125
    assert result.inventory.snapshot_at == NOW
    assert result.evidence.structured_data == result.inventory
    assert repository.calls == [
        (runtime_context.tenant_id, "LR-TL-MUSH-OR01", "DE", "DE-FRA")
    ]
    assert evidence_writer.calls == [(runtime_context, request(), stock.snapshot_id)]


def test_inventory_service_treats_zero_as_valid_stock_not_missing() -> None:
    evidence_writer = FakeEvidenceWriter()
    service = InventoryService(
        FakeInventoryRepository([record(on_hand=0, reserved=0, unsellable=0)]),
        evidence_writer,
    )

    result = service.search_inventory(context(), request())

    assert result.inventory.available == 0
    assert len(evidence_writer.calls) == 1


def test_inventory_service_maps_no_record_without_writing_evidence() -> None:
    evidence_writer = FakeEvidenceWriter()
    service = InventoryService(FakeInventoryRepository([]), evidence_writer)

    with pytest.raises(InventoryNotFoundError) as captured:
        service.search_inventory(context(), request())

    assert captured.value.to_detail().code == "INVENTORY_NOT_FOUND"
    assert evidence_writer.calls == []


def test_inventory_service_requires_warehouse_when_market_has_multiple() -> None:
    evidence_writer = FakeEvidenceWriter()
    service = InventoryService(
        FakeInventoryRepository(
            [record(warehouse_code="DE-BER"), record(warehouse_code="DE-FRA")]
        ),
        evidence_writer,
    )

    market_request = SearchInventoryInput(
        sku="LR-TL-MUSH-OR01",
        market_code="DE",
    )
    with pytest.raises(WarehouseRequiredError) as captured:
        service.search_inventory(context(), market_request)

    assert captured.value.to_detail().field == "warehouse_code"
    assert evidence_writer.calls == []


def test_inventory_service_rejects_invalid_or_non_demo_repository_data() -> None:
    evidence_writer = FakeEvidenceWriter()
    invalid_service = InventoryService(
        FakeInventoryRepository([record(on_hand=10, reserved=9, unsellable=2)]),
        evidence_writer,
    )
    with pytest.raises(InventoryDataContractError):
        invalid_service.search_inventory(context(), request())

    non_demo_service = InventoryService(
        FakeInventoryRepository([record(synthetic_data=False)]),
        evidence_writer,
    )
    with pytest.raises(InventoryDataContractError):
        non_demo_service.search_inventory(context(), request())

    assert evidence_writer.calls == []


class TimeoutDriverError(Exception):
    sqlstate = "57014"


def test_inventory_service_maps_statement_timeout_to_retryable_error() -> None:
    operational_error = OperationalError(
        "SELECT inventory",
        {},
        TimeoutDriverError("statement timeout"),
    )
    service = InventoryService(
        FakeInventoryRepository(error=operational_error),
        FakeEvidenceWriter(),
    )

    with pytest.raises(DatabaseTimeoutError) as captured:
        service.search_inventory(context(), request())

    detail = captured.value.to_detail()
    assert detail.code == "DATABASE_TIMEOUT"
    assert detail.retryable is True
    assert "SELECT inventory" not in detail.message


def test_inventory_service_hides_non_timeout_database_errors() -> None:
    operational_error = OperationalError(
        "SELECT secret",
        {"password": "must-not-leak"},
        RuntimeError("driver detail"),
    )
    service = InventoryService(
        FakeInventoryRepository(error=operational_error),
        FakeEvidenceWriter(),
    )

    with pytest.raises(DatabaseQueryError) as captured:
        service.search_inventory(context(), request())

    detail_json = captured.value.to_detail().model_dump_json()
    assert "SELECT secret" not in detail_json
    assert "must-not-leak" not in detail_json
    assert "driver detail" not in detail_json
