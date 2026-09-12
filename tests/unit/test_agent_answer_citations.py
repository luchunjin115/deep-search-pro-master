from __future__ import annotations

from uuid import UUID

import pytest

from app.core.errors import AgentProviderOutputError
from app.llm.agent_evidence import (
    build_answer_evidence_set,
    validate_answer_citations,
)
from app.llm.agent_schemas import AgentAnswer, AnswerRequest
from app.schemas.agent import (
    BoundedJsonObject,
    CannotCompleteAction,
    FinishAction,
    ResourceUsage,
    WorkerObservation,
    WorkerResult,
)

DATABASE_EVIDENCE_ID = UUID("20000000-0000-0000-0000-000000000001")
DOCUMENT_EVIDENCE_ID = UUID("20000000-0000-0000-0000-000000000002")
FORGED_EVIDENCE_ID = UUID("20000000-0000-0000-0000-000000000003")
UNSELECTED_EVIDENCE_ID = UUID("20000000-0000-0000-0000-000000000004")


def usage() -> ResourceUsage:
    return ResourceUsage(
        model_calls=0,
        tool_calls=1,
        input_tokens=0,
        output_tokens=0,
        duration_ms=10,
    )


def business_result() -> WorkerResult:
    observation = WorkerObservation(
        observation_id=UUID("30000000-0000-0000-0000-000000000001"),
        status="success",
        public_summary="search_inventory执行成功。",
        structured_result=BoundedJsonObject(
            {
                "capability_id": "search_inventory",
                "data": {"sku": "LAMP-001", "available_quantity": 125},
            }
        ),
        evidence_ids=[DATABASE_EVIDENCE_ID],
        resource_usage=usage(),
    )
    return WorkerResult(
        task_id="inventory_task",
        worker_id="business_data",
        execution_status="completed",
        business_outcome="answered",
        business_result=BoundedJsonObject({"available_quantity": 125}),
        public_summary="德国库存事实已返回。",
        observations=[observation],
        evidence_ids=[DATABASE_EVIDENCE_ID],
        resource_usage=usage(),
    )


def knowledge_result() -> WorkerResult:
    observation = WorkerObservation(
        observation_id=UUID("30000000-0000-0000-0000-000000000002"),
        status="success",
        public_summary="search_knowledge执行成功。",
        structured_result=BoundedJsonObject(
            {
                "capability_id": "search_knowledge",
                "data": {
                    "supported": True,
                    "segments": [
                        {
                            "evidence_id": str(DOCUMENT_EVIDENCE_ID),
                            "citation_label": "[E1]",
                            "source_type": "knowledge",
                            "title": "补货手册",
                            "text": "库存低于安全阈值时应发起补货。",
                        }
                    ],
                },
            }
        ),
        evidence_ids=[DOCUMENT_EVIDENCE_ID],
        resource_usage=usage(),
    )
    return WorkerResult(
        task_id="knowledge_task",
        worker_id="knowledge",
        execution_status="completed",
        business_outcome="answered",
        business_result=BoundedJsonObject({"supported": True}),
        public_summary="内部补货规则已返回。",
        observations=[observation],
        evidence_ids=[DOCUMENT_EVIDENCE_ID],
        resource_usage=usage(),
    )


def request() -> AnswerRequest:
    return AnswerRequest(
        goal="说明德国库存并结合内部补货规则给出结论",
        public_context=BoundedJsonObject({"locale": "zh-CN"}),
        worker_results=(business_result(), knowledge_result()),
    )


def answer(
    summary: str,
    *,
    evidence_ids: list[UUID],
    outcome: str = "answered",
) -> AgentAnswer:
    return AgentAnswer(
        action=FinishAction(
            public_summary=summary,
            business_outcome=outcome,  # type: ignore[arg-type]
            evidence_ids=evidence_ids,
        )
    )


def test_answer_evidence_set_assigns_stable_cross_worker_labels() -> None:
    evidence_set = build_answer_evidence_set(request())

    assert [item.citation_label for item in evidence_set.items] == ["[E1]", "[E2]"]
    assert [item.evidence_id for item in evidence_set.items] == [
        DATABASE_EVIDENCE_ID,
        DOCUMENT_EVIDENCE_ID,
    ]
    assert [item.source_type for item in evidence_set.items] == [
        "database",
        "document",
    ]
    assert evidence_set.items[1].supporting_data.root["text"] == (
        "库存低于安全阈值时应发起补货。"
    )


def test_answer_evidence_set_includes_every_worker_candidate_once() -> None:
    selected = knowledge_result()
    observation = selected.observations[0]
    assert observation.structured_result is not None
    data = observation.structured_result.root["data"]
    assert isinstance(data, dict)
    segments = data["segments"]
    assert isinstance(segments, list)
    segments.append(
        {
            "evidence_id": str(UNSELECTED_EVIDENCE_ID),
            "citation_label": "[E2]",
            "source_type": "knowledge",
            "title": "颜色手册",
            "text": "这段未被Worker选中，不能进入最终回答模型。",
        }
    )
    observation.evidence_ids.append(UNSELECTED_EVIDENCE_ID)
    selected.evidence_ids.append(UNSELECTED_EVIDENCE_ID)

    evidence_set = build_answer_evidence_set(
        AnswerRequest(goal="说明补货规则", worker_results=(selected,))
    )

    assert [item.evidence_id for item in evidence_set.items] == [
        DOCUMENT_EVIDENCE_ID,
        UNSELECTED_EVIDENCE_ID,
    ]
    assert "未被Worker选中" in evidence_set.model_dump_json()


def test_answer_evidence_set_rejects_result_reference_without_observation() -> None:
    orphan = business_result().model_copy(
        update={"evidence_ids": [DATABASE_EVIDENCE_ID, FORGED_EVIDENCE_ID]}
    )
    invalid_request = AnswerRequest(goal="回答库存", worker_results=(orphan,))

    with pytest.raises(AgentProviderOutputError) as captured:
        build_answer_evidence_set(invalid_request)

    assert captured.value.stage == "answer_input_contract"


def test_answer_evidence_set_rejects_more_than_twelve_across_workers() -> None:
    results: list[WorkerResult] = []
    for index in range(13):
        evidence_id = UUID(int=index + 1)
        observation = WorkerObservation(
            observation_id=UUID(int=100 + index),
            status="success",
            public_summary=f"库存观察 {index}",
            structured_result=BoundedJsonObject(
                {
                    "capability_id": "search_inventory",
                    "data": {"available_quantity": index},
                }
            ),
            evidence_ids=[evidence_id],
            resource_usage=usage(),
        )
        results.append(
            WorkerResult(
                task_id=f"inventory_{index}",
                worker_id="business_data",
                execution_status="completed",
                business_outcome="answered",
                public_summary=f"库存结果 {index}",
                observations=[observation],
                evidence_ids=[evidence_id],
                resource_usage=usage(),
            )
        )

    with pytest.raises(AgentProviderOutputError):
        build_answer_evidence_set(
            AnswerRequest(goal="合并库存结果", worker_results=tuple(results))
        )


def test_answer_citations_map_labels_to_exact_server_owned_ids() -> None:
    validated = validate_answer_citations(
        request(),
        answer(
            "德国可售库存为125件 [E1]；内部规则建议检查补货阈值 [E2]。",
            evidence_ids=[DATABASE_EVIDENCE_ID, DOCUMENT_EVIDENCE_ID],
        ),
    )

    assert validated.action.evidence_ids == [
        DATABASE_EVIDENCE_ID,
        DOCUMENT_EVIDENCE_ID,
    ]


@pytest.mark.parametrize(
    "summary",
    [
        "引用了不存在的证据 [E3]。",
        "编号格式不规范 [E01]。",
        "编号不能小写 [e1]。",
        "编号不能使用全角括号 ［E1］。",
        "合法重复不能掩盖伪造 [E1] [E1] [E3]。",
        "合法重复不能掩盖畸形 [E1] [E1] [E01]。",
    ],
)
def test_answer_citations_reject_forged_or_malformed_labels(
    summary: str,
) -> None:
    with pytest.raises(AgentProviderOutputError):
        validate_answer_citations(
            request(),
            answer(summary, evidence_ids=[DATABASE_EVIDENCE_ID]),
        )


@pytest.mark.parametrize("outcome", ["answered", "partial"])
def test_repeated_body_citations_preserve_text_and_first_reference_order(
    outcome,
) -> None:
    summary = "补货规则 [E2]；库存125件 [E1]；再次说明规则 [E2]。"
    validated = validate_answer_citations(
        request(),
        answer(
            summary,
            evidence_ids=[DOCUMENT_EVIDENCE_ID, DATABASE_EVIDENCE_ID],
            outcome=outcome,
        ),
    )
    assert validated.action.public_summary == summary
    assert validated.action.evidence_ids == [DOCUMENT_EVIDENCE_ID, DATABASE_EVIDENCE_ID]
    with pytest.raises(AgentProviderOutputError):
        validate_answer_citations(
            request(),
            answer(summary, evidence_ids=[DATABASE_EVIDENCE_ID, DOCUMENT_EVIDENCE_ID]),
        )


def test_answer_citations_reject_label_and_uuid_disagreement() -> None:
    with pytest.raises(AgentProviderOutputError) as captured:
        validate_answer_citations(
            request(),
            answer("库存事实 [E1]。", evidence_ids=[DOCUMENT_EVIDENCE_ID]),
        )

    assert captured.value.stage == "citation_contract"


def test_answered_with_available_evidence_requires_at_least_one_label() -> None:
    with pytest.raises(AgentProviderOutputError):
        validate_answer_citations(
            request(),
            answer("德国可售库存为125件。", evidence_ids=[]),
        )


def test_no_evidence_and_cannot_complete_must_not_claim_citations() -> None:
    with pytest.raises(AgentProviderOutputError):
        validate_answer_citations(
            request(),
            answer(
                "没有足够证据，但仍引用 [E1] [E1]。",
                evidence_ids=[DATABASE_EVIDENCE_ID],
                outcome="no_evidence",
            ),
        )

    cannot_complete = AgentAnswer(
        action=CannotCompleteAction(
            public_summary="当前能力不支持该请求 [E1]。",
            business_outcome="unsupported",
        )
    )
    with pytest.raises(AgentProviderOutputError):
        validate_answer_citations(request(), cannot_complete)
