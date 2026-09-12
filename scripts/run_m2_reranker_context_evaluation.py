"""Run only the deterministic Fake M2-22.7.2 Reranker/Context boundary."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from app.evals.reranker_context_report import write_public_report
from app.evals.reranker_context_runner import (
    DeterministicFakeReranker,
    InMemoryFakeContextReader,
    build_fake_case_inputs_from_dataset,
    run_m2_reranker_context_fake_evaluation,
)
from app.schemas.evaluation import RerankerTopK

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = PROJECT_ROOT / "data" / "evals" / "m2_cross_border_rag_smoke_v1.jsonl"
DEFAULT_OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "evals"
    / "runtime"
    / "reports"
    / "m2-reranker-context-fake-report.json"
)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--selected-top-k",
        type=int,
        choices=(5, 8),
        default=5,
        help="TopK selected only for the six downstream fake Context points",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    cases, dataset_version, dataset_sha256 = build_fake_case_inputs_from_dataset(
        DATASET_PATH
    )
    report = run_m2_reranker_context_fake_evaluation(
        cases=cases,
        dataset_version=dataset_version,
        dataset_sha256=dataset_sha256,
        selected_top_k=cast(RerankerTopK, args.selected_top_k),
        scorer=DeterministicFakeReranker(),
        context_reader=InMemoryFakeContextReader(),
    )
    write_public_report(args.output, report)
    print(
        json.dumps(
            {
                "run_id": report.run_id,
                "run_status": report.run_status,
                "answerable_cases": len(report.answerable_results),
                "safety_cases": len(report.safety_results),
                "provider_score_calls": report.cache.provider_score_calls,
                "quality_gate_passed": report.quality_gate_passed,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
