"""Run only the formal M2-22.6 retrieval evaluation boundary."""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Sequence
from pathlib import Path

from app.core.config import BGE_M3_REVISION, Settings
from app.evals.retrieval_runner import (
    FrozenChunkCandidate,
    build_frozen_chunk_candidates,
    run_m2_retrieval_evaluation,
)

_RAGAS_SELECTED_CONFIG_ID = "chunk-compact-overlap-100"


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data/evals/runtime/reports"),
    )
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument(
        "--config-id",
        choices=[item.config.config_id for item in build_frozen_chunk_candidates()],
    )
    parser.add_argument("--case-id", action="append")
    parser.add_argument("--no-ragas", action="store_true")
    parser.add_argument(
        "--ragas-selected-only",
        action="store_true",
        help=(
            "Rebuild only compact/100 and run depth 10, RRF 60, and the "
            "retrieval-only Ragas Judge"
        ),
    )
    args = parser.parse_args(argv)
    if args.baseline_only and args.config_id is not None:
        parser.error("--baseline-only and --config-id are mutually exclusive")
    if args.ragas_selected_only and (
        args.baseline_only
        or args.config_id is not None
        or args.case_id
        or args.no_ragas
    ):
        parser.error(
            "--ragas-selected-only cannot be combined with baseline, config, "
            "case, or no-ragas options"
        )
    return args


def _resolve_run_scope(
    args: argparse.Namespace,
) -> tuple[
    list[FrozenChunkCandidate] | None,
    tuple[int, ...],
    tuple[int, ...],
]:
    """Resolve either the formal matrix or the exact authorized Ragas resume."""

    selected_candidates = None
    depths: tuple[int, ...] = (10, 20, 30)
    rrf_constants: tuple[int, ...] = (20, 60, 100)
    if args.ragas_selected_only:
        selected_candidates = [
            next(
                candidate
                for candidate in build_frozen_chunk_candidates()
                if candidate.config.config_id == _RAGAS_SELECTED_CONFIG_ID
            )
        ]
        depths = (10,)
        rrf_constants = (60,)
    elif args.baseline_only or args.config_id is not None:
        selected_candidates = [
            next(
                candidate
                for candidate in build_frozen_chunk_candidates()
                if (
                    candidate.production_baseline
                    if args.baseline_only
                    else candidate.config.config_id == args.config_id
                )
            )
        ]
    return selected_candidates, depths, rrf_constants


def main() -> None:
    args = _parse_args()
    logging.basicConfig(level=logging.INFO)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    production_settings = Settings()
    settings = production_settings.model_copy(
        update={
            "embedding_backend": "bge",
            "embedding_revision": BGE_M3_REVISION,
            # Evaluation-only throughput override; batch size is absent from the
            # logical Embedding identity and does not change stored vectors.
            "embedding_batch_size": 16,
            # The compact VAT Index Set exceeded the current production 2 s
            # write boundary. This evaluation-only override collects ranking
            # evidence without changing the production default.
            "database_statement_timeout_ms": 30_000,
            "model_local_files_only": True,
            "docling_backend": "docling",
        }
    )
    selected_candidates, depths, rrf_constants = _resolve_run_scope(args)
    report = run_m2_retrieval_evaluation(
        settings,
        output_root=args.output_root,
        case_ids=set(args.case_id) if args.case_id else None,
        chunk_candidates=selected_candidates,
        depths=depths,
        rrf_constants=rrf_constants,
        run_ragas=not args.no_ragas,
        production_database_statement_timeout_ms=(
            production_settings.database_statement_timeout_ms
        ),
        production_index_timeout_observed=True,
    )
    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
