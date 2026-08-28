from collections.abc import Generator
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AmbiguousProductError, ProductNotFoundError
from app.db.session import create_database_runtime
from app.models.catalog import Product, ProductSpec, ProductVariant
from app.models.identity import Tenant
from app.repositories.product import ProductRepository
from app.schemas.product import GetProductSpecInput
from app.services.product import ProductSpecService


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
def product_service_fixture(
    postgres_engine: Engine,
) -> Generator[tuple[ProductSpecService, dict[str, UUID]], None, None]:
    connection = postgres_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    ids = _insert_products(session)
    service = ProductSpecService(ProductRepository(session))
    try:
        yield service, ids
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def _insert_products(session: Session) -> dict[str, UUID]:
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    session.add_all(
        [
            Tenant(id=tenant_id, name="Product service tenant"),
            Tenant(id=other_tenant_id, name="Other product service tenant"),
        ]
    )
    session.flush()

    product_rows = [
        (
            tenant_id,
            "LR-TL-MUSH",
            "橙色复古蘑菇台灯",
            "LUMORIVA Orange Mushroom Table Lamp",
            ["橙色蘑菇灯", "台灯"],
            "LR-TL-MUSH-OR01",
        ),
        (
            tenant_id,
            "LR-TL-MINI-MUSH",
            "迷你蘑菇灯",
            "LUMORIVA Mini Mushroom Lamp",
            ["台灯"],
            "LR-TL-MINI-OR01",
        ),
        (
            other_tenant_id,
            "OTHER-TL-MUSH",
            "其他租户专属蘑菇灯",
            "Other Tenant Exclusive Mushroom Lamp",
            ["其他租户商品"],
            "OTHER-TL-MUSH-01",
        ),
    ]
    variant_ids: list[UUID] = []
    for product_tenant, spu, name_zh, name_en, aliases, sku in product_rows:
        product_id = uuid4()
        variant_id = uuid4()
        variant_ids.append(variant_id)
        session.add(
            Product(
                id=product_id,
                tenant_id=product_tenant,
                spu=spu,
                name_zh=name_zh,
                name_en=name_en,
                aliases=aliases,
            )
        )
        session.flush()
        session.add(
            ProductVariant(
                id=variant_id,
                tenant_id=product_tenant,
                product_id=product_id,
                sku=sku,
                color="orange",
            )
        )
        session.flush()
        session.add(
            ProductSpec(
                id=uuid4(),
                tenant_id=product_tenant,
                variant_id=variant_id,
                name="height",
                value="30",
                unit="cm",
                source_type="synthetic_seed",
                source_id="product-service-test",
                verification_status="demo_declared",
            )
        )
    session.flush()
    return {"tenant": tenant_id, "other_tenant": other_tenant_id}


def test_product_service_with_real_repository_covers_resolution_and_isolation(
    product_service_fixture: tuple[ProductSpecService, dict[str, UUID]],
) -> None:
    service, ids = product_service_fixture

    by_sku = service.get_product_spec(
        ids["tenant"],
        GetProductSpecInput(product_query="LR-TL-MUSH-OR01"),
    )
    by_chinese_alias = service.get_product_spec(
        ids["tenant"],
        GetProductSpecInput(product_query="橙色蘑菇灯"),
    )
    by_english_name = service.get_product_spec(
        ids["tenant"],
        GetProductSpecInput(product_query="lumoriva orange mushroom table lamp"),
    )

    assert by_sku.sku == "LR-TL-MUSH-OR01"
    assert by_chinese_alias.sku == by_sku.sku
    assert by_english_name.sku == by_sku.sku
    assert by_sku.specs[0].value == "30"

    with pytest.raises(ProductNotFoundError):
        service.get_product_spec(
            ids["tenant"],
            GetProductSpecInput(product_query="不存在的商品"),
        )

    with pytest.raises(AmbiguousProductError) as ambiguous:
        service.get_product_spec(
            ids["tenant"],
            GetProductSpecInput(product_query="台灯"),
        )
    assert ambiguous.value.candidate_skus == (
        "LR-TL-MINI-OR01",
        "LR-TL-MUSH-OR01",
    )

    with pytest.raises(ProductNotFoundError):
        service.get_product_spec(
            ids["tenant"],
            GetProductSpecInput(product_query="OTHER-TL-MUSH-01"),
        )
    other_tenant_result = service.get_product_spec(
        ids["other_tenant"],
        GetProductSpecInput(product_query="OTHER-TL-MUSH-01"),
    )
    assert other_tenant_result.name_zh == "其他租户专属蘑菇灯"
