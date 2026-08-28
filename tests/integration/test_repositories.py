from collections.abc import Generator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import create_database_runtime
from app.models.catalog import Product, ProductSpec, ProductVariant
from app.models.identity import Tenant
from app.models.inventory import InventorySnapshot, Warehouse
from app.repositories.common import apply_statement_timeout
from app.repositories.inventory import InventoryRepository
from app.repositories.product import ProductRepository


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
def repository_session(
    postgres_engine: Engine,
) -> Generator[tuple[Session, dict[str, UUID]], None, None]:
    connection = postgres_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    ids = _insert_repository_fixtures(session)
    try:
        yield session, ids
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def _insert_repository_fixtures(session: Session) -> dict[str, UUID]:
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    session.add_all(
        [
            Tenant(id=tenant_id, name="Repository tenant"),
            Tenant(id=other_tenant_id, name="Other repository tenant"),
        ]
    )
    session.flush()

    product_id = uuid4()
    ambiguous_product_id = uuid4()
    other_product_id = uuid4()
    session.add_all(
        [
            Product(
                id=product_id,
                tenant_id=tenant_id,
                spu="LR-TL-MUSH",
                name_zh="橙色复古蘑菇台灯",
                name_en="LUMORIVA Orange Mushroom Table Lamp",
                aliases=["蘑菇灯", "mushroom lamp"],
            ),
            Product(
                id=ambiguous_product_id,
                tenant_id=tenant_id,
                spu="LR-TL-MINI-MUSH",
                name_zh="迷你蘑菇灯",
                name_en="LUMORIVA Mini Mushroom Lamp",
                aliases=["蘑菇灯"],
            ),
            Product(
                id=other_product_id,
                tenant_id=other_tenant_id,
                spu="LR-TL-MUSH",
                name_zh="其他租户蘑菇灯",
                name_en="Other Tenant Mushroom Lamp",
                aliases=["蘑菇灯"],
            ),
        ]
    )
    session.flush()

    variant_id = uuid4()
    ambiguous_variant_id = uuid4()
    other_variant_id = uuid4()
    session.add_all(
        [
            ProductVariant(
                id=variant_id,
                tenant_id=tenant_id,
                product_id=product_id,
                sku="LR-TL-MUSH-OR01",
                color="orange",
            ),
            ProductVariant(
                id=ambiguous_variant_id,
                tenant_id=tenant_id,
                product_id=ambiguous_product_id,
                sku="LR-TL-MINI-OR01",
                color="orange",
            ),
            ProductVariant(
                id=other_variant_id,
                tenant_id=other_tenant_id,
                product_id=other_product_id,
                sku="LR-TL-MUSH-OR01",
                color="orange",
            ),
        ]
    )
    session.flush()

    session.add(
        ProductSpec(
            id=uuid4(),
            tenant_id=tenant_id,
            variant_id=variant_id,
            name="height",
            value="30",
            unit="cm",
            source_type="synthetic_seed",
            source_id="repository-test",
            verification_status="demo_declared",
        )
    )

    warehouse_ids = {
        "de_fra": uuid4(),
        "de_ber": uuid4(),
        "fr_cdg": uuid4(),
        "other_de_fra": uuid4(),
    }
    session.add_all(
        [
            Warehouse(
                id=warehouse_ids["de_fra"],
                tenant_id=tenant_id,
                code="DE-FRA",
                market_code="DE",
                name="德国法兰克福测试仓",
            ),
            Warehouse(
                id=warehouse_ids["de_ber"],
                tenant_id=tenant_id,
                code="DE-BER",
                market_code="DE",
                name="德国柏林测试仓",
            ),
            Warehouse(
                id=warehouse_ids["fr_cdg"],
                tenant_id=tenant_id,
                code="FR-CDG",
                market_code="FR",
                name="法国巴黎测试仓",
            ),
            Warehouse(
                id=warehouse_ids["other_de_fra"],
                tenant_id=other_tenant_id,
                code="DE-FRA",
                market_code="DE",
                name="其他租户德国仓",
            ),
        ]
    )
    session.flush()

    old_time = datetime(2026, 8, 28, 5, 0, tzinfo=UTC)
    latest_time = datetime(2026, 8, 28, 6, 0, tzinfo=UTC)
    snapshot_data = [
        (tenant_id, variant_id, warehouse_ids["de_fra"], 100, old_time),
        (tenant_id, variant_id, warehouse_ids["de_fra"], 150, latest_time),
        (tenant_id, variant_id, warehouse_ids["de_ber"], 40, latest_time),
        (tenant_id, variant_id, warehouse_ids["fr_cdg"], 70, latest_time),
        (
            other_tenant_id,
            other_variant_id,
            warehouse_ids["other_de_fra"],
            999,
            latest_time,
        ),
    ]
    for (
        snapshot_tenant,
        snapshot_variant,
        warehouse_id,
        on_hand,
        observed_at,
    ) in snapshot_data:
        session.add(
            InventorySnapshot(
                id=uuid4(),
                tenant_id=snapshot_tenant,
                variant_id=snapshot_variant,
                warehouse_id=warehouse_id,
                on_hand=on_hand,
                reserved=20 if on_hand >= 100 else 5,
                unsellable=5 if on_hand >= 100 else 0,
                inbound=80,
                safety_stock=60,
                snapshot_at=observed_at,
            )
        )
    session.flush()
    return {
        "tenant": tenant_id,
        "other_tenant": other_tenant_id,
        "variant": variant_id,
        "other_variant": other_variant_id,
    }


def test_product_repository_prefers_exact_sku_and_supports_names_and_aliases(
    repository_session: tuple[Session, dict[str, UUID]],
) -> None:
    session, ids = repository_session
    repository = ProductRepository(session)

    exact = repository.find_candidates(ids["tenant"], "LR-TL-MUSH-OR01")
    chinese_name = repository.find_candidates(ids["tenant"], "橙色复古蘑菇台灯")
    english_name = repository.find_candidates(
        ids["tenant"], "lumoriva orange mushroom table lamp"
    )
    ambiguous_alias = repository.find_candidates(ids["tenant"], "蘑菇灯")

    assert [candidate.sku for candidate in exact] == ["LR-TL-MUSH-OR01"]
    assert [candidate.sku for candidate in chinese_name] == ["LR-TL-MUSH-OR01"]
    assert [candidate.sku for candidate in english_name] == ["LR-TL-MUSH-OR01"]
    assert [candidate.sku for candidate in ambiguous_alias] == [
        "LR-TL-MINI-OR01",
        "LR-TL-MUSH-OR01",
    ]


def test_product_repository_keeps_tenants_isolated_and_returns_specs(
    repository_session: tuple[Session, dict[str, UUID]],
) -> None:
    session, ids = repository_session
    repository = ProductRepository(session)

    current = repository.find_candidates(ids["tenant"], "LR-TL-MUSH-OR01")
    other = repository.find_candidates(ids["other_tenant"], "LR-TL-MUSH-OR01")
    missing = repository.find_candidates(ids["tenant"], "UNKNOWN-SKU")
    specs = repository.list_specs(ids["tenant"], ids["variant"])
    cross_tenant_specs = repository.list_specs(ids["other_tenant"], ids["variant"])

    assert current[0].name_zh == "橙色复古蘑菇台灯"
    assert other[0].name_zh == "其他租户蘑菇灯"
    assert missing == []
    assert [(spec.name, spec.value, spec.unit) for spec in specs] == [
        ("height", "30", "cm")
    ]
    assert cross_tenant_specs == []


def test_inventory_repository_returns_latest_per_warehouse_and_filters_market(
    repository_session: tuple[Session, dict[str, UUID]],
) -> None:
    session, ids = repository_session
    repository = InventoryRepository(session)

    germany = repository.find_latest(ids["tenant"], "LR-TL-MUSH-OR01", "DE")
    frankfurt = repository.find_latest(
        ids["tenant"],
        "LR-TL-MUSH-OR01",
        "DE",
        "DE-FRA",
    )
    france = repository.find_latest(ids["tenant"], "LR-TL-MUSH-OR01", "FR")

    assert [(record.warehouse_code, record.on_hand) for record in germany] == [
        ("DE-BER", 40),
        ("DE-FRA", 150),
    ]
    assert [(record.warehouse_code, record.on_hand) for record in frankfurt] == [
        ("DE-FRA", 150)
    ]
    assert [(record.warehouse_code, record.on_hand) for record in france] == [
        ("FR-CDG", 70)
    ]
    assert all(record.synthetic_data for record in germany + frankfurt + france)


def test_inventory_repository_keeps_tenants_isolated_and_returns_empty_for_missing(
    repository_session: tuple[Session, dict[str, UUID]],
) -> None:
    session, ids = repository_session
    repository = InventoryRepository(session)

    current = repository.find_latest(ids["tenant"], "LR-TL-MUSH-OR01", "DE", "DE-FRA")
    other = repository.find_latest(
        ids["other_tenant"], "LR-TL-MUSH-OR01", "DE", "DE-FRA"
    )
    wrong_market = repository.find_latest(
        ids["tenant"], "LR-TL-MUSH-OR01", "FR", "DE-FRA"
    )
    missing = repository.find_latest(ids["tenant"], "UNKNOWN-SKU", "DE")

    assert current[0].on_hand == 150
    assert other[0].on_hand == 999
    assert wrong_market == []
    assert missing == []


def test_repository_queries_bind_values_instead_of_interpolating_sql(
    repository_session: tuple[Session, dict[str, UUID]],
) -> None:
    session, ids = repository_session
    connection = session.get_bind()
    assert isinstance(connection, Connection)
    captured: list[tuple[str, object]] = []

    def capture_statement(
        _connection: Connection,
        _cursor: object,
        statement: str,
        parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        captured.append((statement, parameters))

    event.listen(connection, "before_cursor_execute", capture_statement)
    try:
        ProductRepository(session).find_candidates(ids["tenant"], "LR-TL-MUSH-OR01")
        InventoryRepository(session).find_latest(
            ids["tenant"], "LR-TL-MUSH-OR01", "DE", "DE-FRA"
        )
    finally:
        event.remove(connection, "before_cursor_execute", capture_statement)

    business_selects = [
        (statement, parameters)
        for statement, parameters in captured
        if "FROM products JOIN product_variants" in statement
        or "FROM inventory_snapshots JOIN product_variants" in statement
    ]
    assert len(business_selects) == 2
    for statement, parameters in business_selects:
        assert "LR-TL-MUSH-OR01" not in statement
        assert str(ids["tenant"]) not in statement
        assert parameters


def test_statement_timeout_is_transaction_local_and_actually_cancels_query(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        apply_statement_timeout(session, 10)
        assert session.scalar(text("SELECT current_setting('statement_timeout')")) == (
            "10ms"
        )
        with pytest.raises(OperationalError):
            session.execute(text("SELECT pg_sleep(0.05)"))
        session.rollback()


@pytest.mark.parametrize("timeout_ms", [0, 30001])
def test_statement_timeout_rejects_unsafe_configuration(
    repository_session: tuple[Session, dict[str, UUID]],
    timeout_ms: int,
) -> None:
    session, _ids = repository_session
    with pytest.raises(ValueError, match="statement timeout"):
        apply_statement_timeout(session, timeout_ms)
