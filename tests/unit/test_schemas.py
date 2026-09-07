from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.auth import CurrentUser, LoginRequest, LoginResponse
from app.schemas.chat import ChatMessageRequest, ChatSuccessResponse, ExecutionSummary
from app.schemas.common import ApiErrorResponse, ErrorDetail, ToolEnvelope, ToolMeta
from app.schemas.evidence import EvidenceAccessScope, EvidenceDetail, EvidenceSummary
from app.schemas.inventory import InventoryIntent, InventoryResult, SearchInventoryInput
from app.schemas.product import (
    GetProductSpecInput,
    ProductSpecItem,
    ProductSpecResult,
)

NOW = datetime(2026, 8, 28, 6, 0, tzinfo=UTC)


def product_result() -> ProductSpecResult:
    return ProductSpecResult(
        product_id=uuid4(),
        variant_id=uuid4(),
        sku="LR-TL-MUSH-OR01",
        name_zh="橙色复古蘑菇台灯",
        name_en="LUMORIVA Orange Mushroom Table Lamp",
        status="candidate",
        specs=[
            ProductSpecItem(
                name="height",
                value="30",
                unit="cm",
                verification_status="demo_declared",
            )
        ],
        synthetic_data=True,
    )


def inventory_result() -> InventoryResult:
    return InventoryResult(
        sku="LR-TL-MUSH-OR01",
        product_name="橙色复古蘑菇台灯",
        market_code="DE",
        warehouse_code="DE-FRA",
        warehouse_name="德国法兰克福合成演示仓",
        on_hand=150,
        reserved=20,
        unsellable=5,
        available=125,
        inbound=80,
        safety_stock=60,
        snapshot_at=NOW,
        synthetic_data=True,
    )


def tool_meta(tool: str = "search_inventory") -> ToolMeta:
    return ToolMeta(
        tool=tool,
        version="1.0.0",
        duration_ms=83,
        source_time=NOW,
        trace_id=uuid4(),
        synthetic_data=True,
    )


def test_product_input_strips_whitespace_and_rejects_trusted_context_fields() -> None:
    request = GetProductSpecInput(product_query="  蘑菇灯  ")
    assert request.product_query == "蘑菇灯"

    with pytest.raises(ValidationError, match="tenant_id"):
        GetProductSpecInput(product_query="蘑菇灯", tenant_id=str(uuid4()))


@pytest.mark.parametrize("sku", ["sku@@@", "lower-case", "A", "SKU WITH SPACE"])
def test_inventory_input_rejects_invalid_sku(sku: str) -> None:
    with pytest.raises(ValidationError):
        SearchInventoryInput(sku=sku, market_code="DE")


def test_inventory_input_rejects_invalid_or_mismatched_market() -> None:
    with pytest.raises(ValidationError):
        SearchInventoryInput(sku="LR-TL-MUSH-OR01", market_code="US")

    with pytest.raises(ValidationError, match="warehouse_code"):
        SearchInventoryInput(
            sku="LR-TL-MUSH-OR01",
            market_code="DE",
            warehouse_code="FR-CDG",
        )


def test_inventory_intent_has_no_sql_or_tenant_escape_hatch() -> None:
    intent = InventoryIntent(product_query="蘑菇灯", market_code="DE")
    assert intent.intent == "inventory_query"

    with pytest.raises(ValidationError):
        InventoryIntent(
            product_query="蘑菇灯",
            market_code="DE",
            sql="SELECT * FROM inventory_snapshots",
        )

    with pytest.raises(ValidationError):
        InventoryIntent(
            product_query="蘑菇灯",
            market_code="DE",
            tenant_id=str(uuid4()),
        )


def test_inventory_result_requires_formula_nonnegative_values_and_aware_time() -> None:
    valid = inventory_result()
    assert valid.available == 125

    with pytest.raises(ValidationError, match="available must equal"):
        InventoryResult(**(valid.model_dump() | {"available": 126}))

    with pytest.raises(ValidationError):
        InventoryResult(**(valid.model_dump() | {"on_hand": -1}))

    naive_time = NOW.replace(tzinfo=None)
    with pytest.raises(ValidationError):
        InventoryResult(**(valid.model_dump() | {"snapshot_at": naive_time}))


def test_product_result_requires_fields_and_synthetic_marker() -> None:
    valid = product_result()
    assert valid.sku == "LR-TL-MUSH-OR01"

    payload = valid.model_dump()
    del payload["specs"]
    with pytest.raises(ValidationError, match="specs"):
        ProductSpecResult(**payload)

    with pytest.raises(ValidationError, match="synthetic_data"):
        ProductSpecResult(**(valid.model_dump() | {"synthetic_data": False}))


def test_login_contract_normalizes_email_and_keeps_password_out_of_json() -> None:
    request = LoginRequest(
        email="  DE.OPERATOR@DEMO.DEEPSEARCH.LOCAL  ",
        password="M1-demo-only-change-me",
    )
    assert request.email == "de.operator@demo.deepsearch.local"
    assert "M1-demo-only-change-me" not in request.model_dump_json()

    with pytest.raises(ValidationError):
        LoginRequest(
            email="de.operator@demo.deepsearch.local",
            password="M1-demo-only-change-me",
            password_hash="$argon2id$must-not-enter",
        )


def test_login_response_contains_no_password_hash() -> None:
    user = CurrentUser(
        user_id=uuid4(),
        tenant_id=uuid4(),
        email="de.operator@demo.deepsearch.local",
        display_name="演示德国运营",
        roles=["amazon_operator"],
        market_scopes=["DE"],
        synthetic_data=True,
    )
    response = LoginResponse(
        access_token="x" * 40,
        expires_in_seconds=3600,
        user=user,
    )
    assert response.token_type == "bearer"
    assert "password" not in response.model_dump_json()


def test_tool_envelope_requires_coherent_success_or_error_payload() -> None:
    evidence_id = uuid4()
    success = ToolEnvelope[InventoryResult](
        status="success",
        data=inventory_result(),
        evidence_ids=[evidence_id],
        meta=tool_meta(),
    )
    assert success.evidence_ids == [evidence_id]

    error = ErrorDetail(
        code="FORBIDDEN",
        message="当前账号无权查询德国市场库存",
        retryable=False,
        field="market_code",
    )
    failed = ToolEnvelope[InventoryResult](
        status="error",
        error=error,
        meta=tool_meta(),
    )
    assert failed.data is None

    with pytest.raises(ValidationError, match="must include data"):
        ToolEnvelope[InventoryResult](status="success", meta=tool_meta())

    with pytest.raises(ValidationError, match="cannot expose evidence"):
        ToolEnvelope[InventoryResult](
            status="error",
            error=error,
            evidence_ids=[evidence_id],
            meta=tool_meta(),
        )


def test_error_contract_rejects_unknown_codes_and_sensitive_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ErrorDetail(code="UNKNOWN", message="bad", retryable=False)

    for forbidden_field in ("sql", "stack", "connection_string", "api_key"):
        with pytest.raises(ValidationError, match=forbidden_field):
            ErrorDetail(
                code="INTERNAL_ERROR",
                message="请求处理失败",
                retryable=False,
                **{forbidden_field: "must not leak"},
            )

    response = ApiErrorResponse(
        error=ErrorDetail(
            code="DATABASE_TIMEOUT",
            message="库存查询超时",
            retryable=True,
        ),
        trace_id=uuid4(),
    )
    assert set(response.model_dump()) == {"status", "error", "trace_id"}


def test_evidence_contract_is_database_only_typed_and_synthetic() -> None:
    result = inventory_result()
    evidence = EvidenceDetail(
        id=uuid4(),
        source_type="database",
        source_name="synthetic_inventory",
        source_locator=f"inventory_snapshots/{uuid4()}",
        title="德国仓蘑菇灯库存",
        excerpt="DE-FRA可售库存125件",
        query_summary={
            "sku": "LR-TL-MUSH-OR01",
            "market_code": "DE",
            "warehouse_code": "DE-FRA",
        },
        structured_data=result,
        observed_at=NOW,
        confidence="1.000",
        access_scope=EvidenceAccessScope(
            tenant_id=uuid4(),
            market_codes=["DE"],
        ),
        synthetic_data=True,
        created_at=NOW,
    )
    assert evidence.source_type == "database"

    payload = evidence.model_dump()
    payload["query_summary"] = {
        "sku": "LR-TL-MUSH-OR01",
        "market_code": "DE",
        "sql": "SELECT secret",
    }
    with pytest.raises(ValidationError):
        EvidenceDetail(**payload)

    with pytest.raises(ValidationError):
        EvidenceDetail(**(evidence.model_dump() | {"synthetic_data": False}))


def test_chat_contract_rejects_empty_message_and_unknown_sql_field() -> None:
    with pytest.raises(ValidationError):
        ChatMessageRequest(message="   ")

    with pytest.raises(ValidationError):
        ChatMessageRequest(message="查询库存", sql="SELECT *")


def test_chat_success_response_contains_execution_and_evidence_summary() -> None:
    trace_id = uuid4()
    response = ChatSuccessResponse(
        request_id=uuid4(),
        thread_id=uuid4(),
        message_id=uuid4(),
        answer="德国仓蘑菇灯可售库存为125件。",
        evidence=[
            EvidenceSummary(
                id=uuid4(),
                source_name="synthetic_inventory",
                title="德国仓蘑菇灯库存",
                excerpt="DE-FRA可售库存125件",
                observed_at=NOW,
            )
        ],
        execution=ExecutionSummary(
            trace_id=trace_id,
            route="inventory_query",
            tool_names=["get_product_spec", "search_inventory"],
            duration_ms=83,
            status="completed",
        ),
    )
    assert response.execution.trace_id == trace_id
    assert response.status == "completed"


def test_every_public_schema_forbids_unknown_fields_in_json_schema() -> None:
    public_models = [
        LoginRequest,
        LoginResponse,
        ChatMessageRequest,
        ChatSuccessResponse,
        GetProductSpecInput,
        ProductSpecResult,
        InventoryIntent,
        SearchInventoryInput,
        InventoryResult,
        EvidenceSummary,
        EvidenceDetail,
        ErrorDetail,
        ApiErrorResponse,
        ToolMeta,
    ]
    for model in public_models:
        assert model.model_json_schema()["additionalProperties"] is False
