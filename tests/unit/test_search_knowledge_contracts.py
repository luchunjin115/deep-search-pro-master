from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.schemas import SearchKnowledgeInput, SearchKnowledgeResult
from app.schemas.common import ToolEnvelope, ToolMeta
from app.schemas.context import ContextBundle, ContextSegment
from app.schemas.knowledge import (
    SearchKnowledgeInput as DirectSearchKnowledgeInput,
)
from app.schemas.retrieval import (
    PdfRetrievalSourceLocator,
    RetrievalCandidateIdentity,
    RetrievalDocumentMetadata,
)
from app.tools import create_m2_tool_registry
from app.tools.registry import create_m1_tool_registry


def context_segment(ordinal: int) -> ContextSegment:
    return ContextSegment(
        citation_label=f"[E{ordinal}]",
        evidence_id=uuid4(),
        source_type="knowledge",
        role="anchor",
        reranker_rank=min(ordinal, 8),
        identity=RetrievalCandidateIdentity(
            document_id=uuid4(),
            version_id=uuid4(),
            index_set_id=uuid4(),
            chunk_id=uuid4(),
        ),
        document=RetrievalDocumentMetadata(
            title=f"合成知识文档{ordinal}",
            document_type="product_manual",
            language="zh-CN",
            market="DE",
        ),
        source_locator=PdfRetrievalSourceLocator(page_number=ordinal),
        text=f"第{ordinal}条合成知识证据。",
        text_sha256=f"{ordinal:x}" * 64,
        token_count=10,
        overlap_trimmed=False,
    )


def context_bundle(segment_count: int) -> ContextBundle:
    segments = [context_segment(index) for index in range(1, segment_count + 1)]
    return ContextBundle(
        context_id=uuid4(),
        query_sha256="a" * 64,
        context_sha256="b" * 64,
        max_tokens=4000,
        total_tokens=sum(segment.token_count for segment in segments),
        supported=bool(segments),
        segments=segments,
    )


def tool_meta() -> ToolMeta:
    return ToolMeta(
        tool="search_knowledge",
        version="1.0.0",
        duration_ms=1,
        trace_id=uuid4(),
        synthetic_data=True,
    )


def test_search_knowledge_input_accepts_only_one_strict_bounded_query() -> None:
    request = SearchKnowledgeInput(query="  蘑菇灯应如何清洁？  ")

    assert request.query == "蘑菇灯应如何清洁？"
    assert DirectSearchKnowledgeInput is SearchKnowledgeInput
    schema = SearchKnowledgeInput.model_json_schema()
    assert schema["required"] == ["query"]
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"query"}
    assert schema["properties"]["query"]["minLength"] == 1
    assert schema["properties"]["query"]["maxLength"] == 2000

    for invalid_query in (" ", "x" * 2001, 1, None):
        with pytest.raises(ValidationError):
            SearchKnowledgeInput(query=invalid_query)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "forbidden_field",
    (
        "tenant_id",
        "user_id",
        "role",
        "market",
        "sql",
        "path",
        "file_id",
        "document_id",
        "candidate_count",
        "top_k",
        "embedding_model",
        "reranker_model",
        "context_max_tokens",
    ),
)
def test_search_knowledge_input_rejects_backend_owned_or_unsafe_fields(
    forbidden_field: str,
) -> None:
    with pytest.raises(ValidationError, match=forbidden_field):
        SearchKnowledgeInput(
            query="合成资料中额定电压是多少？",
            **{forbidden_field: "must-not-enter"},
        )


def test_search_knowledge_result_only_wraps_public_context_in_evidence_order() -> None:
    context = context_bundle(3)
    result = SearchKnowledgeResult(context=context)

    assert set(result.model_dump()) == {"context"}
    assert result.context is context
    assert result.evidence_ids == tuple(
        segment.evidence_id for segment in context.segments
    )
    rendered = result.model_dump_json()
    for forbidden in (
        "tenant_id",
        "owner_user_id",
        "acl",
        "storage_key",
        "local_path",
        "sql",
        "vector",
        "reranker_score",
    ):
        assert forbidden not in rendered


def test_search_knowledge_result_defends_supported_segments_contract() -> None:
    supported = context_bundle(1)
    contradictory = ContextBundle.model_construct(
        **(supported.model_dump() | {"supported": False})
    )

    with pytest.raises(ValidationError, match="supported"):
        SearchKnowledgeResult(context=contradictory)

    unsupported = context_bundle(0)
    result = SearchKnowledgeResult(context=unsupported)
    assert result.context.supported is False
    assert result.context.segments == []
    assert result.evidence_ids == ()

    envelope = ToolEnvelope[SearchKnowledgeResult](
        status="success",
        data=result,
        evidence_ids=list(result.evidence_ids),
        meta=tool_meta(),
    )
    assert envelope.status == "success"
    assert envelope.data == result
    assert envelope.evidence_ids == []


def test_tool_envelope_accepts_twelve_context_evidence_ids_but_not_thirteen() -> None:
    context = context_bundle(12)
    result = SearchKnowledgeResult(context=context)
    evidence_ids = list(result.evidence_ids)

    envelope = ToolEnvelope[SearchKnowledgeResult](
        status="success",
        data=result,
        evidence_ids=evidence_ids,
        meta=tool_meta(),
    )

    assert envelope.evidence_ids == evidence_ids
    with pytest.raises(ValidationError):
        ToolEnvelope[SearchKnowledgeResult](
            status="success",
            data=result,
            evidence_ids=evidence_ids + [uuid4()],
            meta=tool_meta(),
        )


def test_m1_and_m2_registries_are_exactly_isolated_and_versioned() -> None:
    m1_registry = create_m1_tool_registry()
    m2_registry = create_m2_tool_registry()

    assert m1_registry.names == ("get_product_spec", "search_inventory")
    assert m2_registry.names == (
        "get_evidence_detail",
        "get_product_spec",
        "read_uploaded_file",
        "search_inventory",
        "search_knowledge",
    )
    knowledge = m2_registry.get("search_knowledge")
    assert knowledge.version == "1.0.0"
    assert knowledge.input_schema is SearchKnowledgeInput
    assert knowledge.output_schema is SearchKnowledgeResult
    assert knowledge.timeout_ms == 8_000
    assert knowledge.allowed_roles == frozenset(
        {"company_owner", "product_scout", "amazon_operator"}
    )
    assert knowledge.data_scope == "tenant"
    assert knowledge.side_effect == "read"


def test_search_knowledge_model_spec_explains_use_return_and_restrictions() -> None:
    registry = create_m2_tool_registry()
    definition = registry.get("search_knowledge")
    description = definition.description

    for phrase in (
        "知识库",
        "返回",
        "Context",
        "Evidence",
        "只读",
        "合成演示数据",
        "不接受",
        "tenant",
        "SQL",
        "路径",
        "文件或文档ID",
        "候选数",
        "top k",
        "模型参数",
        "Context预算",
    ):
        assert phrase in description

    spec = registry.model_specs(("search_knowledge",))[0]
    assert spec.name == "search_knowledge"
    assert spec.parameters["required"] == ["query"]
    assert spec.parameters["additionalProperties"] is False
    assert set(spec.parameters["properties"]) == {"query"}
    assert "自然语言问题" in spec.parameters["properties"]["query"]["description"]


def test_m2_20_5_keeps_knowledge_agent_and_api_absent() -> None:
    project_root = Path(__file__).parents[2]

    assert (project_root / "app/services/knowledge.py").is_file()
    assert (project_root / "app/tools/search_knowledge.py").is_file()
    assert (project_root / "app/tools/read_uploaded_file.py").is_file()
    assert (project_root / "app/tools/get_evidence_detail.py").is_file()
    assert not (project_root / "app/agents/graphs/knowledge_query.py").exists()
    assert not (project_root / "app/api/routes/knowledge.py").exists()
    inventory_graph = (project_root / "app/agents/graphs/inventory_query.py").read_text(
        encoding="utf-8"
    )
    assert "search_knowledge" not in inventory_graph


def test_result_evidence_ids_are_uuid_values() -> None:
    result = SearchKnowledgeResult(context=context_bundle(2))

    assert all(isinstance(evidence_id, UUID) for evidence_id in result.evidence_ids)
