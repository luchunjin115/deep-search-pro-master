from collections.abc import Generator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import EvidencePersistenceError, InventoryNotFoundError
from app.db.session import create_database_runtime
from app.models.catalog import Product, ProductVariant
from app.models.identity import Tenant, User
from app.models.inventory import InventorySnapshot, Warehouse
from app.models.runtime import AgentRun, Evidence, Thread, ToolCall
from app.repositories.inventory import InventoryRepository
from app.schemas.inventory import SearchInventoryInput
from app.services.evidence import EvidenceService, EvidenceWriteContext
from app.services.inventory import InventoryService


@pytest.fixture
def postgres_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    settings = Settings(_env_file=".env.example", app_env="test")
    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    return settings


@pytest.fixture
def postgres_engine(postgres_settings: Settings) -> Generator[Engine, None, None]:
    command.upgrade(Config("alembic.ini"), "head")
    runtime = create_database_runtime(postgres_settings)
    yield runtime.engine
    runtime.engine.dispose()


@pytest.fixture
def inventory_service_fixture(
    postgres_engine: Engine,
) -> Generator[
    tuple[Session, InventoryService, EvidenceWriteContext, dict[str, UUID]],
    None,
    None,
]:
    connection = postgres_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    context, ids = _insert_inventory_runtime(session)
    service = InventoryService(
        InventoryRepository(session),
        EvidenceService(session),
    )
    try:
        yield session, service, context, ids
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def _insert_inventory_runtime(
    session: Session,
) -> tuple[EvidenceWriteContext, dict[str, UUID]]:
    tenant_id = uuid4()
    user_id = uuid4()
    thread_id = uuid4()
    agent_run_id = uuid4()
    tool_call_id = uuid4()
    session.add(Tenant(id=tenant_id, name="Inventory evidence tenant"))
    session.flush()
    session.add(
        User(
            id=user_id,
            tenant_id=tenant_id,
            email="inventory.evidence@example.com",
            display_name="Inventory Evidence Tester",
            password_hash="$argon2id$test-only-hash",
        )
    )
    session.flush()
    session.add(
        Thread(
            id=thread_id,
            tenant_id=tenant_id,
            user_id=user_id,
            title="Inventory evidence test",
        )
    )
    session.flush()
    session.add(
        AgentRun(
            id=agent_run_id,
            tenant_id=tenant_id,
            thread_id=thread_id,
            user_id=user_id,
            trace_id=uuid4(),
            route="inventory_query",
            status="running",
        )
    )
    session.flush()
    session.add(
        ToolCall(
            id=tool_call_id,
            tenant_id=tenant_id,
            agent_run_id=agent_run_id,
            sequence_no=1,
            tool_name="search_inventory",
            tool_version="1.0.0",
            arguments_summary={"sku": "LR-TL-MUSH-OR01", "market": "DE"},
            permission_result="allowed",
            status="running",
        )
    )
    session.flush()

    product_id = uuid4()
    variant_id = uuid4()
    warehouse_id = uuid4()
    old_snapshot_id = uuid4()
    latest_snapshot_id = uuid4()
    session.add(
        Product(
            id=product_id,
            tenant_id=tenant_id,
            spu="LR-TL-MUSH",
            name_zh="橙色复古蘑菇台灯",
            name_en="LUMORIVA Orange Mushroom Table Lamp",
            aliases=["蘑菇灯"],
        )
    )
    session.flush()
    session.add(
        ProductVariant(
            id=variant_id,
            tenant_id=tenant_id,
            product_id=product_id,
            sku="LR-TL-MUSH-OR01",
            color="orange",
        )
    )
    session.add(
        Warehouse(
            id=warehouse_id,
            tenant_id=tenant_id,
            code="DE-FRA",
            market_code="DE",
            name="德国法兰克福测试仓",
        )
    )
    session.flush()
    session.add_all(
        [
            InventorySnapshot(
                id=old_snapshot_id,
                tenant_id=tenant_id,
                variant_id=variant_id,
                warehouse_id=warehouse_id,
                on_hand=100,
                reserved=10,
                unsellable=5,
                inbound=40,
                safety_stock=50,
                snapshot_at=datetime(2026, 8, 28, 5, 0, tzinfo=UTC),
            ),
            InventorySnapshot(
                id=latest_snapshot_id,
                tenant_id=tenant_id,
                variant_id=variant_id,
                warehouse_id=warehouse_id,
                on_hand=150,
                reserved=20,
                unsellable=5,
                inbound=80,
                safety_stock=60,
                snapshot_at=datetime(2026, 8, 28, 6, 0, tzinfo=UTC),
            ),
        ]
    )
    session.flush()
    return (
        EvidenceWriteContext(
            tenant_id=tenant_id,
            agent_run_id=agent_run_id,
            tool_call_id=tool_call_id,
        ),
        {
            "latest_snapshot": latest_snapshot_id,
            "tool_call": tool_call_id,
            "agent_run": agent_run_id,
        },
    )


def test_inventory_service_persists_latest_snapshot_evidence_before_success(
    inventory_service_fixture: tuple[
        Session,
        InventoryService,
        EvidenceWriteContext,
        dict[str, UUID],
    ],
) -> None:
    session, service, context, ids = inventory_service_fixture
    request = SearchInventoryInput(
        sku="LR-TL-MUSH-OR01",
        market_code="DE",
        warehouse_code="DE-FRA",
    )

    result = service.search_inventory(context, request)
    evidence_row = session.get(Evidence, result.evidence.id)

    assert result.inventory.available == 125
    assert result.inventory.snapshot_at == datetime(2026, 8, 28, 6, 0, tzinfo=UTC)
    assert result.evidence.source_locator == (
        f"inventory_snapshots/{ids['latest_snapshot']}"
    )
    assert result.evidence.structured_data == result.inventory
    assert evidence_row is not None
    assert evidence_row.agent_run_id == ids["agent_run"]
    assert evidence_row.tool_call_id == ids["tool_call"]
    assert evidence_row.query_summary == {
        "sku": "LR-TL-MUSH-OR01",
        "market_code": "DE",
        "warehouse_code": "DE-FRA",
    }
    assert evidence_row.structured_data["available"] == 125
    assert evidence_row.access_scope == {
        "tenant_id": str(context.tenant_id),
        "market_codes": ["DE"],
    }
    assert evidence_row.synthetic_data is True


def test_inventory_service_does_not_write_evidence_for_missing_inventory(
    inventory_service_fixture: tuple[
        Session,
        InventoryService,
        EvidenceWriteContext,
        dict[str, UUID],
    ],
) -> None:
    session, service, context, _ids = inventory_service_fixture
    before = session.scalar(select(func.count()).select_from(Evidence))

    with pytest.raises(InventoryNotFoundError):
        service.search_inventory(
            context,
            SearchInventoryInput(
                sku="LR-TL-MUSH-OR01",
                market_code="FR",
                warehouse_code="FR-CDG",
            ),
        )

    after = session.scalar(select(func.count()).select_from(Evidence))
    assert before == after == 0


def test_evidence_foreign_key_mismatch_becomes_safe_persistence_error(
    inventory_service_fixture: tuple[
        Session,
        InventoryService,
        EvidenceWriteContext,
        dict[str, UUID],
    ],
) -> None:
    session, service, context, _ids = inventory_service_fixture
    invalid_context = EvidenceWriteContext(
        tenant_id=context.tenant_id,
        agent_run_id=uuid4(),
        tool_call_id=context.tool_call_id,
    )

    with (
        pytest.raises(EvidencePersistenceError) as captured,
        session.begin_nested(),
    ):
        service.search_inventory(
            invalid_context,
            SearchInventoryInput(
                sku="LR-TL-MUSH-OR01",
                market_code="DE",
                warehouse_code="DE-FRA",
            ),
        )

    assert captured.value.to_detail().model_dump() == {
        "code": "INTERNAL_ERROR",
        "message": "库存证据保存失败",
        "retryable": True,
        "field": None,
    }
