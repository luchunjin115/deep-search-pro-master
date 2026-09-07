"""Frozen G0-G7 migration acceptance samples for the engineered Agent path."""

from __future__ import annotations

from copy import deepcopy
from typing import Final

AGENT_ACCEPTANCE_FIXTURE_VERSION: Final = "m2-agent-acceptance-v1"

_COMMON_SUCCESS_EXPECTATIONS: Final[dict[str, object]] = {
    "gateway_root_runs": 1,
    "orphan_worker_runs": 0,
    "tool_call_inherits": ("identity", "budget", "trace"),
    "citation_validation_before_answer_persist": True,
    "maximum_answer_evidence": 12,
    "public_forbidden_fields": (
        "prompt",
        "sql",
        "local_path",
        "storage_key",
        "secret",
        "raw_exception",
    ),
}

_AGENT_ACCEPTANCE_CASES: Final[tuple[dict[str, object], ...]] = (
    {
        "case_id": "G0",
        "scenario": "single_public_entrypoint",
        "request": {
            "method": "POST",
            "path_template": "/api/v1/threads/{thread_id}/messages",
            "message": "解释安全库存是什么意思",
        },
        "expected": {
            "gateway_root_runs": 1,
            "client_routing_fields": (),
            "root_agent": "agent_gateway",
        },
    },
    {
        "case_id": "G1",
        "scenario": "no_legacy_graph_or_fallback",
        "request": {
            "method": "POST",
            "path_template": "/api/v1/threads/{thread_id}/messages",
            "message": "查询德国仓蘑菇灯库存",
        },
        "expected": {
            "legacy_inventory_graph_calls": 0,
            "workers": ("business_data",),
            "gateway_failure_outcome": "system_error",
            "legacy_fallback_allowed": False,
        },
    },
    {
        "case_id": "G2",
        "scenario": "business_single_tool",
        "request": {
            "method": "POST",
            "path_template": "/api/v1/threads/{thread_id}/messages",
            "messages": (
                "查询LR-TL-MUSH-OR01在德国的库存",
                "查询蘑菇灯规格",
            ),
        },
        "expected": {
            "workers": ("business_data",),
            "tool_names_by_message": (
                ("search_inventory",),
                ("get_product_spec",),
            ),
            "evidence_source_types": ("database",),
        },
    },
    {
        "case_id": "G3",
        "scenario": "knowledge_single_tool",
        "request": {
            "method": "POST",
            "path_template": "/api/v1/threads/{thread_id}/messages",
            "message": "蘑菇灯手册如何要求清洁？",
        },
        "expected": {
            "workers": ("knowledge",),
            "minimum_tool_calls": 1,
            "maximum_tool_calls": 1,
            "evidence_source_types": ("document",),
            "requires_current_authorization": True,
        },
    },
    {
        "case_id": "G4",
        "scenario": "cross_worker",
        "request": {
            "method": "POST",
            "path_template": "/api/v1/threads/{thread_id}/messages",
            "message": "德国库存能否满足手册要求的安全备货？",
        },
        "expected": {
            "workers": ("business_data", "knowledge"),
            "child_runs_share_one_root": True,
            "worker_capabilities_are_isolated": True,
            "answer_fact_classes": (
                "database_fact",
                "document_fact",
                "cross_source_inference",
            ),
        },
    },
    {
        "case_id": "G5",
        "scenario": "clarification_and_resume",
        "request": {
            "method": "POST",
            "path_template": "/api/v1/threads/{thread_id}/messages",
            "messages": ("查询这个灯的库存", "指橙色蘑菇灯，德国市场"),
        },
        "expected": {
            "first_execution_status": "waiting_user",
            "first_evidence_count": 0,
            "resume_reauthorizes": True,
            "resume_executes_only_incomplete_tasks": True,
        },
    },
    {
        "case_id": "G6",
        "scenario": "unsupported_and_budget_termination",
        "request": {
            "method": "POST",
            "path_template": "/api/v1/threads/{thread_id}/messages",
            "messages": ("把德国库存改成999", "立即自动下单"),
        },
        "expected": {
            "tool_calls": 0,
            "unsupported_outcome": "unsupported",
            "loop_terminates_within_budget": True,
            "false_success_allowed": False,
        },
    },
    {
        "case_id": "G7",
        "scenario": "citation_validation",
        "request": {
            "method": "POST",
            "path_template": "/api/v1/threads/{thread_id}/messages",
            "message": "根据手册回答并给出引用",
        },
        "expected": {
            "citation_maps_to_answer_evidence": True,
            "rejects_forged_citations": True,
            "rejects_duplicate_citations": True,
            "rejects_over_limit_citations": True,
            "reauthorizes_before_response": True,
        },
    },
)


def agent_acceptance_cases() -> tuple[dict[str, object], ...]:
    """Return a copy so tests cannot mutate the frozen canonical samples."""

    return deepcopy(_AGENT_ACCEPTANCE_CASES)


def agent_acceptance_suite() -> dict[str, object]:
    """Return the versioned, JSON-safe suite consumed by later migration tests."""

    return {
        "fixture_version": AGENT_ACCEPTANCE_FIXTURE_VERSION,
        "common_success_expectations": deepcopy(_COMMON_SUCCESS_EXPECTATIONS),
        "cases": agent_acceptance_cases(),
    }
