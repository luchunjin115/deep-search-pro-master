from __future__ import annotations

from scripts.benchmark_m2_docling import (
    GOLDEN_PROBES,
    READING_ORDER_TOKENS,
    evaluate_facts,
    normalize_text,
    tokens_are_in_order,
)


def test_fact_evaluation_normalizes_spacing_case_and_full_width_text() -> None:
    text = "batch-scan-42\nSAMPLE SIZE: ２０  PCS"

    facts = evaluate_facts("scanned_receiving_ticket", text)

    assert [fact["passed"] for fact in facts] == [True, True]
    assert normalize_text(" 18 EUR ") == "18eur"


def test_table_fact_requires_supplier_and_value_relationship_tokens() -> None:
    facts = evaluate_facts(
        "merged_header_cost_table",
        "合成供应商C 20.90\n合成供应商B 的值缺失",
    )

    assert facts[0]["passed"] is True
    assert facts[1]["passed"] is False
    assert facts[1]["missing_probes"] == ["1.20"]
    assert set(GOLDEN_PROBES) == {
        "scanned_receiving_ticket",
        "two_column_market_brief",
        "merged_header_cost_table",
        "visual_quality_notice",
        "multi_region_replenishment",
    }


def test_reading_order_check_rejects_column_reordering() -> None:
    ordered = "\n".join(READING_ORDER_TOKENS)
    reordered = "\n".join((READING_ORDER_TOKENS[3], *READING_ORDER_TOKENS[:3]))

    assert tokens_are_in_order(ordered, READING_ORDER_TOKENS) is True
    assert tokens_are_in_order(reordered, READING_ORDER_TOKENS) is False
