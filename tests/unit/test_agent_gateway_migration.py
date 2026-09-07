from datetime import UTC, datetime
from inspect import getsource
from uuid import uuid4

import pytest

from app.agents.gateway import AgentGatewayLimits
from app.api.routers import threads
from app.schemas.chat import ChatSuccessResponse, ExecutionSummary
from app.schemas.evidence import DocumentEvidenceSummary

NOW = datetime(2026, 9, 5, 8, 0, tzinfo=UTC)


def test_public_chat_router_has_no_legacy_graph_or_direct_tool_wiring() -> None:
    source = getsource(threads)

    assert "InventoryQueryAgent" not in source
    assert "InventoryQueryInput" not in source
    assert "create_m1_tool_registry" not in source
    assert "AgentGatewayDependency" in source


def test_chat_contract_exposes_gateway_outcome_and_document_evidence() -> None:
    summary = ExecutionSummary(
        trace_id=uuid4(),
        route="agent_gateway",
        tool_names=[
            "get_product_spec",
            "search_inventory",
            "search_knowledge",
            "read_uploaded_file",
            "get_evidence_detail",
        ],
        duration_ms=12,
        status="completed",
        business_outcome="partial",
    )
    response = ChatSuccessResponse(
        request_id=uuid4(),
        thread_id=uuid4(),
        message_id=uuid4(),
        answer="库存事实已返回，手册部分暂时无法读取。[E1]",
        evidence=[
            DocumentEvidenceSummary(
                id=uuid4(),
                source_type="knowledge",
                title="合成蘑菇灯手册",
                excerpt="清洁前断电。",
                observed_at=NOW,
            )
        ],
        execution=summary,
    )

    assert response.execution.route == "agent_gateway"
    assert response.execution.business_outcome == "partial"
    assert response.evidence[0].source_type == "knowledge"


def test_parallel_worker_reservations_fit_one_trusted_root_budget() -> None:
    limits = AgentGatewayLimits()

    assert limits.business_child.max_evidence == 4
    assert limits.knowledge_child.max_evidence == 8
    assert (
        limits.business_child.max_evidence + limits.knowledge_child.max_evidence
        == limits.root.max_evidence
    )
    with pytest.raises(ValueError, match="parallel Worker reservations"):
        AgentGatewayLimits(business_child=limits.knowledge_child)
