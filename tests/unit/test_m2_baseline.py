import ast
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from pydantic import ValidationError

from app.core.config import BGE_RERANKER_REVISION, Settings

M2_ENVIRONMENT_VARIABLES = (
    "STORAGE_BACKEND",
    "LOCAL_STORAGE_ROOT",
    "MODEL_CACHE_ROOT",
    "DOCLING_BACKEND",
    "DOCLING_MODEL_CACHE_ROOT",
    "DOCLING_DEVICE",
    "DOCLING_NUM_THREADS",
    "DOCLING_DOCUMENT_TIMEOUT_SECONDS",
    "DOCLING_OCR_ENGINE",
    "DOCLING_ENABLE_REMOTE_SERVICES",
    "DOCLING_ALLOW_EXTERNAL_PLUGINS",
    "UPLOAD_ALLOWED_EXTENSIONS",
    "UPLOAD_MAX_FILE_SIZE_BYTES",
    "UPLOAD_MAX_FILES_PER_REQUEST",
    "UPLOAD_STREAM_CHUNK_SIZE_BYTES",
    "PDF_MAX_PAGES",
    "PDF_MAX_EXTRACTED_CHARACTERS",
    "PDF_LOW_TEXT_CHARACTER_THRESHOLD",
    "DOCX_MAX_ARCHIVE_MEMBERS",
    "DOCX_MAX_UNCOMPRESSED_BYTES",
    "DOCX_MAX_COMPRESSION_RATIO",
    "DOCX_MAX_BLOCKS",
    "DOCX_MAX_TABLE_CELLS",
    "DOCX_MAX_EXTRACTED_CHARACTERS",
    "XLSX_MAX_ARCHIVE_MEMBERS",
    "XLSX_MAX_UNCOMPRESSED_BYTES",
    "XLSX_MAX_COMPRESSION_RATIO",
    "XLSX_MAX_SHEETS",
    "XLSX_MAX_ROWS_PER_SHEET",
    "XLSX_MAX_COLUMNS",
    "XLSX_MAX_CELLS",
    "XLSX_MAX_EXTRACTED_CHARACTERS",
    "CSV_MAX_ROWS",
    "CSV_MAX_COLUMNS",
    "CSV_MAX_CELLS",
    "CSV_MAX_EXTRACTED_CHARACTERS",
    "EMBEDDING_BACKEND",
    "EMBEDDING_MODEL",
    "EMBEDDING_REVISION",
    "EMBEDDING_DIMENSIONS",
    "EMBEDDING_NORMALIZE",
    "EMBEDDING_BATCH_SIZE",
    "EMBEDDING_POOLING",
    "EMBEDDING_MAX_LENGTH",
    "EMBEDDING_PRECISION",
    "RERANKER_BACKEND",
    "RERANKER_MODEL",
    "RERANKER_REVISION",
    "RERANKER_BATCH_SIZE",
    "RERANKER_MAX_LENGTH",
    "RERANKER_PRECISION",
    "MODEL_DEVICE",
    "MODEL_LOCAL_FILES_ONLY",
    "CHUNK_TARGET_TOKENS",
    "CHUNK_MAX_TOKENS",
    "CHUNK_OVERLAP_TOKENS",
    "CHUNK_HEADING_CONTEXT_MAX_TOKENS",
    "CHUNK_TABLE_ROW_OVERLAP",
    "CHUNK_REPEATED_EDGE_MIN_PAGES",
    "DENSE_CANDIDATE_COUNT",
    "LEXICAL_CANDIDATE_COUNT",
    "HYBRID_CANDIDATE_COUNT",
    "RETRIEVAL_QUERY_MAX_CHARACTERS",
    "RRF_K",
    "RERANKER_TOP_K",
)


def settings_without_env(**overrides: object) -> Settings:
    """Keep Pydantic Settings' runtime-only _env_file hook in one typed boundary."""

    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        **overrides,  # type: ignore[arg-type]
    )


@pytest.fixture(autouse=True)
def clear_m2_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent local shell configuration from changing M2 contract tests."""

    for variable_name in M2_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(variable_name, raising=False)


def test_m2_settings_use_safe_local_defaults() -> None:
    settings = settings_without_env()

    assert settings.storage_backend == "local"
    assert settings.local_storage_root == Path("data/storage")
    assert settings.model_cache_root == Path("data/model-cache")
    assert settings.docling_backend == "disabled"
    assert settings.docling_model_cache_root == Path("data/model-cache/docling")
    assert settings.docling_device == "cpu"
    assert settings.docling_num_threads == 4
    assert settings.docling_document_timeout_seconds == 120
    assert settings.docling_ocr_engine == "rapidocr"
    assert settings.docling_enable_remote_services is False
    assert settings.docling_allow_external_plugins is False
    assert set(settings.upload_allowed_extensions) == {
        ".pdf",
        ".docx",
        ".xlsx",
        ".csv",
    }
    assert settings.upload_max_file_size_bytes == 25 * 1024 * 1024
    assert settings.pdf_max_pages == 500
    assert settings.pdf_max_extracted_characters == 5_000_000
    assert settings.pdf_low_text_character_threshold == 20
    assert settings.docx_max_archive_members == 5000
    assert settings.docx_max_uncompressed_bytes == 100 * 1024 * 1024
    assert settings.docx_max_compression_ratio == 200
    assert settings.docx_max_blocks == 50_000
    assert settings.docx_max_table_cells == 200_000
    assert settings.docx_max_extracted_characters == 5_000_000
    assert settings.xlsx_max_archive_members == 5000
    assert settings.xlsx_max_uncompressed_bytes == 100 * 1024 * 1024
    assert settings.xlsx_max_compression_ratio == 200
    assert settings.xlsx_max_sheets == 100
    assert settings.xlsx_max_rows_per_sheet == 100_000
    assert settings.xlsx_max_columns == 500
    assert settings.xlsx_max_cells == 500_000
    assert settings.xlsx_max_extracted_characters == 5_000_000
    assert settings.csv_max_rows == 200_000
    assert settings.csv_max_columns == 500
    assert settings.csv_max_cells == 500_000
    assert settings.csv_max_extracted_characters == 5_000_000
    assert settings.embedding_backend == "fake"
    assert settings.embedding_model == "BAAI/bge-m3"
    assert settings.embedding_dimensions == 1024
    assert settings.embedding_normalize is True
    assert settings.embedding_pooling == "cls"
    assert settings.embedding_max_length == 8192
    assert settings.embedding_precision == "float32"
    assert settings.reranker_backend == "fake"
    assert settings.reranker_model == "BAAI/bge-reranker-v2-m3"
    assert settings.reranker_revision == BGE_RERANKER_REVISION
    assert settings.reranker_max_length == 8192
    assert settings.reranker_precision == "float32"
    assert settings.model_device == "cpu"
    assert settings.model_local_files_only is True
    assert settings.docling_backend == "disabled"
    assert settings.docling_device == "cpu"
    assert settings.docling_enable_remote_services is False
    assert settings.docling_allow_external_plugins is False
    assert settings.chunk_target_tokens == 600
    assert settings.chunk_max_tokens == 700
    assert settings.chunk_overlap_tokens == 100
    assert settings.chunk_heading_context_max_tokens == 120
    assert settings.chunk_table_row_overlap == 1
    assert settings.chunk_repeated_edge_min_pages == 2
    assert settings.dense_candidate_count == 30
    assert settings.lexical_candidate_count == 30
    assert settings.hybrid_candidate_count == 30
    assert settings.retrieval_query_max_characters == 2000
    assert settings.rrf_k == 60
    assert settings.reranker_top_k == 8


def test_env_example_contains_a_valid_m2_configuration() -> None:
    settings = Settings(_env_file=".env.example")  # type: ignore[call-arg]

    assert settings.upload_allowed_extensions == (
        ".pdf",
        ".docx",
        ".xlsx",
        ".csv",
    )
    assert settings.embedding_backend == "fake"
    assert settings.reranker_backend == "fake"
    assert settings.model_local_files_only is True


@pytest.mark.parametrize(
    ("overrides", "message"),
    (
        (
            {"upload_allowed_extensions": [".pdf", ".docx", ".xlsx"]},
            "UPLOAD_ALLOWED_EXTENSIONS",
        ),
        (
            {"local_storage_root": "data/shared", "model_cache_root": "data/shared"},
            "LOCAL_STORAGE_ROOT",
        ),
        ({"local_storage_root": "."}, "M2托管目录"),
        (
            {"docling_model_cache_root": "outside/docling"},
            "DOCLING_MODEL_CACHE_ROOT",
        ),
        (
            {"docling_enable_remote_services": True},
            "DOCLING_ENABLE_REMOTE_SERVICES",
        ),
        (
            {"docling_allow_external_plugins": True},
            "DOCLING_ALLOW_EXTERNAL_PLUGINS",
        ),
        (
            {
                "upload_max_file_size_bytes": 1024 * 1024,
                "upload_stream_chunk_size_bytes": 2 * 1024 * 1024,
            },
            "上传流式读取块",
        ),
        ({"pdf_max_pages": 0}, "pdf_max_pages"),
        ({"pdf_max_extracted_characters": 9999}, "pdf_max_extracted_characters"),
        ({"pdf_low_text_character_threshold": 0}, "pdf_low_text_character_threshold"),
        ({"docx_max_archive_members": 9}, "docx_max_archive_members"),
        (
            {"docx_max_uncompressed_bytes": 9 * 1024 * 1024},
            "docx_max_uncompressed_bytes",
        ),
        ({"docx_max_compression_ratio": 9}, "docx_max_compression_ratio"),
        ({"docx_max_blocks": 99}, "docx_max_blocks"),
        ({"docx_max_table_cells": 99}, "docx_max_table_cells"),
        ({"docx_max_extracted_characters": 9999}, "docx_max_extracted_characters"),
        ({"xlsx_max_archive_members": 9}, "xlsx_max_archive_members"),
        (
            {"xlsx_max_uncompressed_bytes": 9 * 1024 * 1024},
            "xlsx_max_uncompressed_bytes",
        ),
        ({"xlsx_max_compression_ratio": 9}, "xlsx_max_compression_ratio"),
        ({"xlsx_max_sheets": 0}, "xlsx_max_sheets"),
        ({"xlsx_max_rows_per_sheet": 99}, "xlsx_max_rows_per_sheet"),
        ({"xlsx_max_columns": 9}, "xlsx_max_columns"),
        ({"xlsx_max_cells": 999}, "xlsx_max_cells"),
        ({"xlsx_max_extracted_characters": 9999}, "xlsx_max_extracted_characters"),
        ({"csv_max_rows": 99}, "csv_max_rows"),
        ({"csv_max_columns": 1}, "csv_max_columns"),
        ({"csv_max_cells": 999}, "csv_max_cells"),
        ({"csv_max_extracted_characters": 9999}, "csv_max_extracted_characters"),
        (
            {"chunk_overlap_tokens": 121},
            "chunk_overlap_tokens",
        ),
        (
            {"chunk_target_tokens": 650, "chunk_max_tokens": 600},
            "CHUNK_TARGET_TOKENS",
        ),
        (
            {"chunk_target_tokens": 400, "chunk_overlap_tokens": 400},
            "chunk_overlap_tokens",
        ),
        (
            {"chunk_heading_context_max_tokens": 201},
            "chunk_heading_context_max_tokens",
        ),
        ({"chunk_table_row_overlap": 21}, "chunk_table_row_overlap"),
        ({"chunk_repeated_edge_min_pages": 1}, "chunk_repeated_edge_min_pages"),
        (
            {"dense_candidate_count": 5, "reranker_top_k": 8},
            "RERANKER_TOP_K",
        ),
        (
            {
                "dense_candidate_count": 5,
                "lexical_candidate_count": 5,
                "hybrid_candidate_count": 11,
                "reranker_top_k": 5,
            },
            "HYBRID_CANDIDATE_COUNT",
        ),
        (
            {"hybrid_candidate_count": 5, "reranker_top_k": 8},
            "RERANKER_TOP_K",
        ),
        ({"retrieval_query_max_characters": 0}, "retrieval_query_max_characters"),
        (
            {"retrieval_query_max_characters": 2001},
            "retrieval_query_max_characters",
        ),
        ({"embedding_dimensions": 768}, "1024"),
        ({"embedding_normalize": False}, "True"),
        ({"embedding_backend": "bge"}, "EMBEDDING_REVISION"),
        (
            {"reranker_backend": "bge", "reranker_revision": "main"},
            "RERANKER_REVISION",
        ),
    ),
)
def test_m2_settings_reject_inconsistent_values(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        settings_without_env(**overrides)


def test_secret_values_are_masked_in_serialized_settings() -> None:
    qwen_secret = "m2-test-qwen-secret-value"
    jwt_secret = "m2-test-jwt-secret-value"
    settings = settings_without_env(
        llm_provider="qwen",
        qwen_api_key=qwen_secret,
        jwt_secret_key=jwt_secret,
    )

    rendered = settings.model_dump_json()

    assert qwen_secret not in rendered
    assert jwt_secret not in rendered


def test_m2_runtime_dependencies_are_declared_without_legacy_ragflow() -> None:
    requirements_path = Path(__file__).parents[2] / "requirements.txt"
    requirements = {
        Requirement(line).name.lower()
        for line in requirements_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert {
        "python-multipart",
        "pymupdf",
        "python-docx",
        "openpyxl",
        "pandas",
        "filetype",
        "charset-normalizer",
        "pgvector",
        "jieba",
        "flagembedding",
        "docling",
        "rapidocr",
        "onnxruntime",
    } <= requirements
    assert "ragflow-sdk" not in requirements

    development_requirements = {
        Requirement(line).name.lower()
        for line in (Path(__file__).parents[2] / "requirements-dev.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.lstrip().startswith(("#", "-r"))
    }
    assert "reportlab" in development_requirements
    assert "psutil" in development_requirements


def test_new_app_ast_does_not_import_legacy_file_or_ragflow_runtime() -> None:
    app_root = Path(__file__).parents[2] / "app"
    forbidden_roots = {"agent", "api", "tools", "rawflow", "utils", "ragflow_sdk"}

    for source_file in app_root.rglob("*.py"):
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=source_file)
        imported_roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(
                    alias.name.split(".", 1)[0] for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".", 1)[0])

        assert imported_roots.isdisjoint(forbidden_roots), source_file


def test_m2_17_5_adds_formal_reranker_verification_without_api_or_rag() -> None:
    project_root = Path(__file__).parents[2]

    assert (project_root / "app/services/storage").is_dir()
    assert (project_root / "app/schemas/files.py").is_file()
    assert (project_root / "app/schemas/knowledge.py").is_file()
    assert (project_root / "app/repositories/files.py").is_file()
    assert (project_root / "app/repositories/documents.py").is_file()
    assert (project_root / "app/services/documents").is_dir()
    parsers = project_root / "app/services/documents/parsers"
    assert (parsers / "base.py").is_file()
    assert (parsers / "pdf.py").is_file()
    assert (parsers / "docx.py").is_file()
    assert (parsers / "xlsx.py").is_file()
    assert (parsers / "csv.py").is_file()
    assert (parsers / "native.py").is_file()
    assert (parsers / "docling.py").is_file()
    assert (project_root / "app/services/documents/artifacts.py").is_file()
    assert (project_root / "app/services/documents/quality.py").is_file()
    assert (project_root / "app/services/documents/routing.py").is_file()
    assert (project_root / "app/services/documents/parser_service.py").is_file()
    chunking = project_root / "app/services/documents/chunking"
    assert (chunking / "contracts.py").is_file()
    assert (chunking / "token_counting.py").is_file()
    assert (chunking / "normalization.py").is_file()
    assert (chunking / "chunker.py").is_file()
    assert (chunking / "tables.py").is_file()
    assert (chunking / "service.py").is_file()
    knowledge_model = (project_root / "app/models/knowledge.py").read_text(
        encoding="utf-8"
    )
    assert "class DocumentChunkSet" in knowledge_model
    assert "class DocumentIndexSet" in knowledge_model
    assert "class DocumentChunk" in knowledge_model
    assert (
        project_root / "migrations/versions/20260831_0005_document_chunk_sets.py"
    ).is_file()
    assert (
        project_root / "migrations/versions/20260831_0006_document_chunks_fts_vector.py"
    ).is_file()
    assert (
        project_root / "migrations/versions/20260831_0007_document_index_sets.py"
    ).is_file()
    assert (
        project_root / "migrations/versions/20260831_0008_versioned_jieba_fts.py"
    ).is_file()
    assert (project_root / "scripts/seed_m2_files.py").is_file()
    assert (project_root / "scripts/m2_seed_content.py").is_file()
    assert (project_root / "scripts/verify_m2_chunk_pipeline.py").is_file()
    assert (project_root / "data/seed/m2_seed.json").is_file()
    assert (project_root / "app/services/retrieval/embedding.py").is_file()
    assert not (project_root / "app/services/indexing").exists()
    assert (project_root / "app/api/routers/files.py").is_file()
    indexing = project_root / "app/services/documents/indexing"
    assert (indexing / "contracts.py").is_file()
    assert (indexing / "mapping.py").is_file()
    assert (indexing / "service.py").is_file()
    assert (project_root / "app/api/routers/documents.py").is_file()
    assert (project_root / "scripts/verify_m2_index_pipeline.py").is_file()
    assert (project_root / "tests/smoke/test_document_index_bge_smoke.py").is_file()
    assert (project_root / "scripts/verify_m2_retrieval.py").is_file()
    assert (project_root / "tests/unit/test_m2_retrieval_verification.py").is_file()
    assert (project_root / "tests/smoke/test_m2_retrieval_bge_smoke.py").is_file()

    retrieval = project_root / "app/services/retrieval"
    assert (project_root / "app/schemas/retrieval.py").is_file()
    assert (retrieval / "errors.py").is_file()
    assert (retrieval / "lexical_text.py").is_file()
    assert (project_root / "app/repositories/retrieval.py").is_file()
    assert (retrieval / "dense.py").is_file()
    assert (retrieval / "lexical.py").is_file()
    assert (retrieval / "result_mapping.py").is_file()
    assert (retrieval / "hybrid.py").is_file()
    assert not (retrieval / "keyword.py").exists()
    assert (retrieval / "reranker_provider.py").is_file()
    assert (retrieval / "reranker.py").is_file()
    assert (project_root / "scripts/download_m2_reranker.py").is_file()
    assert (project_root / "scripts/benchmark_m2_reranker.py").is_file()
    assert (project_root / "tests/smoke/test_bge_reranker_smoke.py").is_file()
    assert (project_root / "scripts/verify_m2_reranker.py").is_file()
    assert (project_root / "tests/unit/test_m2_reranker_verification.py").is_file()
    assert not (project_root / "app/api/routers/retrieval.py").exists()
    assert not (project_root / "app/api/routers/search.py").exists()
