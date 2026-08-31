"""Run the formal M2 complex corpus through the real parser router."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.services.documents.artifacts import artifact_to_markdown
from app.services.documents.routing import DocumentParserRouter
from scripts.benchmark_m2_docling import evaluate_facts
from scripts.seed_m2_complex_files import (
    generate_complex_sources,
    load_complex_seed_definition,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "output" / "m2_parser_router_report.json"


def run_router_verification(settings: Settings) -> dict[str, Any]:
    """Return an auditable Native/Docling/Router comparison for five sources."""

    if settings.docling_backend != "docling":
        raise RuntimeError("Set DOCLING_BACKEND=docling for real Router verification")
    router = DocumentParserRouter(settings)
    documents: list[dict[str, Any]] = []
    for source in generate_complex_sources(load_complex_seed_definition()):
        key = source.definition["key"]
        result = router.parse(
            source_name=source.definition["original_name"],
            content=source.content,
        )
        native_facts = evaluate_facts(
            key,
            artifact_to_markdown(result.native_artifact),
        )
        docling_facts = (
            evaluate_facts(
                key,
                artifact_to_markdown(result.docling_artifact),
            )
            if result.docling_artifact is not None
            else []
        )
        selected_facts = evaluate_facts(
            key,
            artifact_to_markdown(result.selected_artifact),
        )
        documents.append(
            {
                "key": key,
                "source_sha256": source.sha256,
                "source_type": result.selected_artifact.source_type,
                "route": result.route,
                "reasons": result.reasons,
                "complexity_tags": result.quality.complexity_tags,
                "native": {
                    "parser": result.native_artifact.parser.model_dump(mode="json"),
                    "warnings": [
                        warning.model_dump(mode="json")
                        for warning in result.native_artifact.warnings
                    ],
                    "facts": native_facts,
                    "facts_passed": sum(fact["passed"] for fact in native_facts),
                },
                "docling": {
                    "parser": result.docling_artifact.parser.model_dump(mode="json"),
                    "warnings": [
                        warning.model_dump(mode="json")
                        for warning in result.docling_artifact.warnings
                    ],
                    "facts": docling_facts,
                    "facts_passed": sum(fact["passed"] for fact in docling_facts),
                }
                if result.docling_artifact is not None
                else None,
                "selected": {
                    "provider": result.selected_artifact.parser.provider,
                    "content_sha256": result.selected_artifact.content_sha256,
                    "facts": selected_facts,
                    "facts_passed": sum(fact["passed"] for fact in selected_facts),
                },
                "comparison": (
                    result.comparison.model_dump(mode="json")
                    if result.comparison is not None
                    else None
                ),
            }
        )

    return {
        "schema_version": "m2-parser-router-report-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "offline_inference": True,
        "documents": documents,
        "aggregate": {
            "documents_total": len(documents),
            "docling_entries": sum(
                document["docling"] is not None for document in documents
            ),
            "selected_facts_passed": sum(
                document["selected"]["facts_passed"] for document in documents
            ),
            "selected_facts_total": 2 * len(documents),
            "routes": {
                route: sum(document["route"] == route for document in documents)
                for route in ("native", "docling", "hybrid")
            },
        },
    }


def main() -> None:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    report = run_router_verification(Settings())
    DEFAULT_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["aggregate"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
