"""Run the offline Native-versus-Docling benchmark for m2-complex-v1."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import threading
import time
import unicodedata
from collections.abc import Callable
from functools import partial
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, TypeVar

import psutil  # type: ignore[import-untyped]

from app.core.config import Settings
from app.services.documents.parsers import DocxParser, PdfParser, XlsxParser
from scripts.seed_m2_complex_files import (
    generate_complex_sources,
    load_complex_seed_definition,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "output" / "m2_docling_benchmark.json"

# These are the actual immutable files consumed by the benchmark.  Docling's
# friendly revision labels are recorded separately in MODEL_REVISIONS.
MODEL_FILES = {
    "docling-project--docling-layout-heron/model.safetensors": (
        "00333a43451945aaf89db8ca9c0a17e75d1537c17db60fdb91aa95f4c7929e0c"
    ),
    "docling-project--docling-layout-heron-onnx/model.onnx": (
        "59c81a3a2923042d85034ffc487f8f47e4854117e879aef89b2b9f728fb4922a"
    ),
    "docling-project--docling-models/model_artifacts/tableformer/accurate/"
    "tableformer_accurate.safetensors": (
        "2a7d6c924b3cd12fb99a09280ca9c33a89c5d60b93253617d2e088c1a40374d9"
    ),
    "RapidOcr/PP-OCRv6_det_small.onnx": (
        "090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f"
    ),
    "RapidOcr/PP-OCRv6_rec_small.onnx": (
        "6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884"
    ),
}
MODEL_REVISIONS = {
    "layout_transformers": "8f39ad3c0b4c58e9c2d2c84a38465abf757272d8",
    "layout_onnx": "40bde044036bb181c130ddf6c51792187268748f",
    "tableformer": "v2.3.0@fc0f2d45e2218ea24bce5045f58a389aed16dc23",
    "rapidocr": "rapidocr-3.9.2/PP-OCRv6/onnxruntime/en",
}

# A fact may need several tokens because a table answer is defined by a row
# relationship rather than one contiguous sentence in exported Markdown.
GOLDEN_PROBES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "scanned_receiving_ticket": (("BATCH-SCAN-42",), ("20 PCS",)),
    "two_column_market_brief": (("18 EUR",), ("80件",)),
    "merged_header_cost_table": (
        ("合成供应商C", "20.90"),
        ("合成供应商B", "1.20"),
    ),
    "visual_quality_notice": (("QC-VISUAL-17",), ("12 PCS",)),
    "multi_region_replenishment": (("100",), ("=B10+C10",)),
}

READING_ORDER_TOKENS = (
    "德国站合成销量：139件",
    "退货率：2.1%",
    "主搜索词：mushroom table lamp",
    "优先补充暖光场景图",
    "广告预算上限：每日18 EUR",
    "复盘日期：2026-09-05",
    "DE-FRA可售库存：125件",
    "预计覆盖：27天",
    "补货触发线：80件",
    "本页只含合成演示数据",
    "运输缓冲：7天",
    "负责人：DE运营组",
)

T = TypeVar("T")


def normalize_text(value: str) -> str:
    """Normalize presentation differences without changing semantic tokens."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if not character.isspace())


def evaluate_facts(document_key: str, text: str) -> list[dict[str, Any]]:
    """Return one explicit pass/fail result for each formal golden fact."""

    normalized = normalize_text(text)
    results: list[dict[str, Any]] = []
    for fact_number, probes in enumerate(GOLDEN_PROBES[document_key], start=1):
        missing = [probe for probe in probes if normalize_text(probe) not in normalized]
        results.append(
            {
                "fact_number": fact_number,
                "probes": list(probes),
                "passed": not missing,
                "missing_probes": missing,
            }
        )
    return results


def tokens_are_in_order(text: str, tokens: tuple[str, ...]) -> bool:
    """Check that every token occurs after the preceding token."""

    normalized = normalize_text(text)
    cursor = 0
    for token in tokens:
        position = normalized.find(normalize_text(token), cursor)
        if position < 0:
            return False
        cursor = position + len(normalize_text(token))
    return True


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model_cache(root: Path) -> dict[str, Any]:
    """Refuse partial or changed local models before offline inference."""

    checked: list[dict[str, Any]] = []
    for relative_path, expected_hash in MODEL_FILES.items():
        model_path = root / Path(relative_path)
        if not model_path.is_file():
            raise RuntimeError(f"Docling model file is missing: {relative_path}")
        actual_hash = sha256_file(model_path)
        if actual_hash != expected_hash:
            raise RuntimeError(f"Docling model hash differs: {relative_path}")
        checked.append(
            {
                "path": relative_path,
                "size_bytes": model_path.stat().st_size,
                "sha256": actual_hash,
            }
        )
    return {"root": root.as_posix(), "revisions": MODEL_REVISIONS, "files": checked}


def package_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "not-installed"


def measure_call(call: Callable[[], T]) -> tuple[T, dict[str, float]]:
    """Measure elapsed time and this process's sampled RSS around one call."""

    process = psutil.Process()
    start_rss = process.memory_info().rss
    peak_rss = start_rss
    stopped = threading.Event()

    def sample() -> None:
        nonlocal peak_rss
        while not stopped.wait(0.05):
            peak_rss = max(peak_rss, process.memory_info().rss)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    started = time.perf_counter()
    try:
        result = call()
    finally:
        elapsed = time.perf_counter() - started
        stopped.set()
        sampler.join(timeout=1)
        peak_rss = max(peak_rss, process.memory_info().rss)
    mebibyte = 1024 * 1024
    return result, {
        "elapsed_seconds": round(elapsed, 3),
        "rss_start_mib": round(start_rss / mebibyte, 1),
        "rss_peak_mib": round(peak_rss / mebibyte, 1),
        "rss_peak_delta_mib": round((peak_rss - start_rss) / mebibyte, 1),
    }


def native_text(source_format: str, content: bytes) -> tuple[str, dict[str, Any]]:
    parsers = {"pdf": PdfParser, "docx": DocxParser, "xlsx": XlsxParser}
    parser = parsers[source_format]()
    parsed = parser.parse(io.BytesIO(content))
    return parsed.model_dump_json(), {
        "parser_name": parser.parser_name,
        "parser_version": parser.parser_version,
    }


def build_docling_converter(settings: Settings) -> Any:
    """Build the one local-only CPU converter used by this benchmark."""

    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    from docling.datamodel.accelerator_options import (
        AcceleratorDevice,
        AcceleratorOptions,
    )
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.object_detection_engine_options import (
        OnnxRuntimeObjectDetectionEngineOptions,
    )
    from docling.datamodel.pipeline_options import (
        LayoutObjectDetectionOptions,
        OcrMode,
        PdfPipelineOptions,
        RapidOcrOptions,
        TableFormerMode,
        TableStructureOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    model_root = (PROJECT_ROOT / settings.docling_model_cache_root).resolve()
    pipeline = PdfPipelineOptions(
        artifacts_path=model_root,
        document_timeout=float(settings.docling_document_timeout_seconds),
        accelerator_options=AcceleratorOptions(
            num_threads=settings.docling_num_threads,
            device=AcceleratorDevice.CPU,
        ),
        enable_remote_services=False,
        allow_external_plugins=False,
        do_ocr=True,
        ocr_options=RapidOcrOptions(
            backend="onnxruntime",
            lang=["english"],
            mode=OcrMode.DEFAULT,
        ),
        do_table_structure=True,
        table_structure_options=TableStructureOptions(
            mode=TableFormerMode.ACCURATE,
            do_cell_matching=True,
        ),
        layout_options=LayoutObjectDetectionOptions(
            engine_options=OnnxRuntimeObjectDetectionEngineOptions(
                providers=["CPUExecutionProvider"],
            )
        ),
    )
    return DocumentConverter(
        allowed_formats=[InputFormat.PDF, InputFormat.DOCX, InputFormat.XLSX],
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline,
                backend=PyPdfiumDocumentBackend,
            )
        },
    )


def docling_text(converter: Any, name: str, content: bytes) -> tuple[str, dict[str, Any]]:
    from docling.datamodel.document import DocumentStream

    converted = converter.convert(
        DocumentStream(name=name, stream=io.BytesIO(content)),
        raises_on_error=True,
        max_num_pages=500,
        max_file_size=25 * 1024 * 1024,
    )
    document = converted.document
    provenance_items = 0
    for item, _level in document.iterate_items():
        if getattr(item, "prov", None):
            provenance_items += 1
    markdown = document.export_to_markdown()
    return markdown, {
        "status": str(converted.status),
        "errors": [str(error)[:300] for error in converted.errors],
        "page_count": len(document.pages),
        "table_count": len(document.tables),
        "picture_count": len(document.pictures),
        "provenance_item_count": provenance_items,
    }


def benchmark_engine(
    engine: str,
    document_key: str,
    call: Callable[[], tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    try:
        (text, metadata), resources = measure_call(call)
    except Exception as error:  # noqa: BLE001 - preserve all benchmark documents
        return {
            "engine": engine,
            "success": False,
            "error_type": type(error).__name__,
            "error": str(error)[:300],
            "facts": [],
            "facts_passed": 0,
            "facts_total": 2,
        }
    facts = evaluate_facts(document_key, text)
    return {
        "engine": engine,
        "success": True,
        "extracted_characters": len(text),
        "text_preview": text[:1000],
        "facts": facts,
        "facts_passed": sum(item["passed"] for item in facts),
        "facts_total": len(facts),
        "reading_order_passed": (
            tokens_are_in_order(text, READING_ORDER_TOKENS)
            if document_key == "two_column_market_brief"
            else None
        ),
        "resources": resources,
        **metadata,
    }


def aggregate(documents: list[dict[str, Any]], engine: str) -> dict[str, Any]:
    results = [document[engine] for document in documents]
    successful = [result for result in results if result["success"]]
    return {
        "documents_total": len(results),
        "documents_succeeded": len(successful),
        "facts_passed": sum(result["facts_passed"] for result in results),
        "facts_total": sum(result["facts_total"] for result in results),
        "max_elapsed_seconds": max(
            (result["resources"]["elapsed_seconds"] for result in successful),
            default=None,
        ),
        "max_rss_peak_delta_mib": max(
            (result["resources"]["rss_peak_delta_mib"] for result in successful),
            default=None,
        ),
    }


def run_benchmark(settings: Settings, only_document: str | None = None) -> dict[str, Any]:
    """Execute both engines against reviewed, generated in-memory sources."""

    if settings.docling_backend != "docling":
        raise RuntimeError("Set DOCLING_BACKEND=docling for the explicit real benchmark")
    if settings.docling_device != "cpu":
        raise RuntimeError("M2-11.2 is fixed to the verified CPU device")

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["DOCLING_SERVE_ENABLE_UI"] = "false"
    model_root = (PROJECT_ROOT / settings.docling_model_cache_root).resolve()
    model_manifest = verify_model_cache(model_root)
    data = load_complex_seed_definition()
    sources = generate_complex_sources(data)
    if only_document is not None:
        sources = [source for source in sources if source.definition["key"] == only_document]
        if not sources:
            raise RuntimeError(f"Unknown complex document key: {only_document}")

    converter, converter_resources = measure_call(partial(build_docling_converter, settings))
    documents: list[dict[str, Any]] = []
    for source in sources:
        key = source.definition["key"]
        source_format = source.definition["format"]
        documents.append(
            {
                "key": key,
                "format": source_format,
                "requires_ocr": source.definition["requires_ocr"],
                "sha256": source.sha256,
                "native": benchmark_engine(
                    "native",
                    key,
                    partial(native_text, source_format, source.content),
                ),
                "docling": benchmark_engine(
                    "docling",
                    key,
                    partial(
                        docling_text,
                        converter,
                        source.definition["original_name"],
                        source.content,
                    ),
                ),
            }
        )

    native = aggregate(documents, "native")
    docling = aggregate(documents, "docling")
    full_corpus = only_document is None
    scanned = next(
        (item["docling"] for item in documents if item["key"] == "scanned_receiving_ticket"),
        None,
    )
    qualifies = bool(
        full_corpus
        and docling["documents_succeeded"] == docling["documents_total"]
        and scanned is not None
        and scanned["facts_passed"] == 2
        and docling["facts_passed"] >= native["facts_passed"]
        and (docling["max_elapsed_seconds"] or float("inf"))
        <= settings.docling_document_timeout_seconds
        and (docling["max_rss_peak_delta_mib"] or float("inf")) <= 4096
    )

    try:
        import torch

        cuda_available = torch.cuda.is_available()
        torch_cuda = torch.version.cuda
    except ImportError:
        cuda_available = False
        torch_cuda = None

    return {
        "schema_version": "m2-docling-benchmark-v1",
        "corpus_version": data["version"],
        "synthetic_data": True,
        "offline_inference": True,
        "configuration": {
            "device": settings.docling_device,
            "threads": settings.docling_num_threads,
            "document_timeout_seconds": settings.docling_document_timeout_seconds,
            "ocr_engine": settings.docling_ocr_engine,
            "ocr_language": "english",
            "layout_engine": "onnxruntime",
            "pdf_backend": "pypdfium2",
            "tableformer_mode": "accurate",
            "remote_services": False,
            "external_plugins": False,
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "logical_cpu_count": psutil.cpu_count(logical=True),
            "physical_memory_mib": round(psutil.virtual_memory().total / 1024 / 1024, 1),
            "packages": {
                package: package_version(package)
                for package in ("docling", "rapidocr", "torch", "onnxruntime", "psutil")
            },
            "gpu": {
                "cuda_available": cuda_available,
                "torch_cuda_version": torch_cuda,
                "benchmark_run": False,
                "not_run_reason": (
                    "CUDA is unavailable in the installed CPU-only PyTorch runtime"
                    if not cuda_available
                    else "M2-11.2 configuration is intentionally fixed to CPU"
                ),
            },
        },
        "model_manifest": model_manifest,
        "converter_initialization": converter_resources,
        "document_filter": only_document,
        "documents": documents,
        "aggregate": {"native": native, "docling": docling},
        "decision": {
            "ready_for_m2_11_3": qualifies,
            "rule": (
                "full corpus; all Docling conversions succeed; both scanned facts recover; "
                "Docling fact score is not below Native; each document <= configured timeout; "
                "sampled RSS delta <= 4096 MiB"
            ),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--document", choices=sorted(GOLDEN_PROBES), default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = run_benchmark(Settings(), only_document=args.document)  # type: ignore[call-arg]
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["aggregate"], ensure_ascii=False, indent=2))
    print(f"report={output}")


if __name__ == "__main__":
    main()
