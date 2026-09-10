"""Isolated Docling provider and adapter into the project-owned artifact."""

from __future__ import annotations

import io
import logging
import multiprocessing
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from multiprocessing.connection import Connection
from multiprocessing.context import SpawnContext
from multiprocessing.process import BaseProcess
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Literal,
    NoReturn,
    Protocol,
    Self,
    TypeAlias,
)

import psutil  # type: ignore[import-untyped]
from pydantic import Field, model_validator

from app.schemas.common import M1Schema
from app.services.documents.artifacts import (
    DOCLING_ADAPTER_VERSION,
    ArtifactBlock,
    ArtifactBoundingBox,
    ArtifactTableBlock,
    ArtifactTableCell,
    ArtifactTableRow,
    ArtifactTextBlock,
    ArtifactWarning,
    CanonicalParsedArtifact,
    build_canonical_artifact,
)
from app.services.documents.parsers.base import (
    DocumentEnhancementError,
    SourceLocator,
)

if TYPE_CHECKING:
    from app.core.config import Settings

DoclingSourceType = Literal["pdf", "docx", "xlsx"]
DOCLING_PARSER_NAME: Literal["docling"] = "docling"
_LOGGER = logging.getLogger(__name__)
_WORKER_READY = b"R"
_WORKER_SUCCESS = b"S"
_WORKER_FAILURE = b"F"
_PROCESS_POLL_SECONDS = 0.05
_PROCESS_SHUTDOWN_GRACE_SECONDS = 2.0


class DoclingTextSnapshot(M1Schema):
    """One third-party-independent text item in Docling reading order."""

    kind: Literal["text"] = "text"
    text: str
    label: str = Field(min_length=1, max_length=100)
    page_number: int | None = Field(default=None, ge=1, le=2000)
    heading_level: int | None = Field(default=None, ge=1, le=9)
    heading_path: list[str] = Field(default_factory=list, max_length=9)
    bounding_box: ArtifactBoundingBox | None = None


class DoclingTableCellSnapshot(M1Schema):
    """One original Docling table cell before expansion to a rectangular grid."""

    text: str
    start_row: int = Field(ge=0, le=1_048_575)
    end_row: int = Field(ge=1, le=1_048_576)
    start_column: int = Field(ge=0, le=16_383)
    end_column: int = Field(ge=1, le=16_384)
    row_header: bool = False
    column_header: bool = False
    bounding_box: ArtifactBoundingBox | None = None

    @model_validator(mode="after")
    def validate_span(self) -> DoclingTableCellSnapshot:
        if self.start_row >= self.end_row or self.start_column >= self.end_column:
            raise ValueError("Docling table cell span must have positive area")
        return self


class DoclingTableSnapshot(M1Schema):
    """One table with original spans and a stable source locator."""

    kind: Literal["table"] = "table"
    table_number: int = Field(ge=1, le=100_000)
    row_count: int = Field(ge=1, le=1_048_576)
    column_count: int = Field(ge=1, le=16_384)
    page_number: int | None = Field(default=None, ge=1, le=2000)
    heading_path: list[str] = Field(default_factory=list, max_length=9)
    cells: list[DoclingTableCellSnapshot] = Field(max_length=2_000_000)
    bounding_box: ArtifactBoundingBox | None = None

    @model_validator(mode="after")
    def validate_cell_bounds(self) -> DoclingTableSnapshot:
        if any(
            cell.end_row > self.row_count or cell.end_column > self.column_count
            for cell in self.cells
        ):
            raise ValueError("Docling table cell exceeds its table bounds")
        return self


DoclingSnapshotItem = Annotated[
    DoclingTextSnapshot | DoclingTableSnapshot,
    Field(discriminator="kind"),
]


class DoclingParseSnapshot(M1Schema):
    """Small stable boundary returned by a real or fake Docling provider."""

    source_type: DoclingSourceType
    parser_name: Literal["docling"] = DOCLING_PARSER_NAME
    parser_version: str = Field(min_length=1, max_length=200)
    page_count: int | None = Field(default=None, ge=1, le=2000)
    items: list[DoclingSnapshotItem] = Field(max_length=1_100_000)
    warning_codes: list[str] = Field(default_factory=list, max_length=100)


class _DoclingWorkerConfig(M1Schema):
    """Only non-secret, bounded settings may cross into a Docling worker."""

    model_cache_root: Path
    device: Literal["cpu"]
    num_threads: int = Field(ge=1, le=4)
    document_timeout_seconds: int = Field(ge=90, le=300)
    ocr_engine: Literal["rapidocr"]
    enable_remote_services: Literal[False]
    allow_external_plugins: Literal[False]
    max_pages: int = Field(ge=1, le=2000)
    max_file_size_bytes: int = Field(ge=1 * 1024 * 1024, le=100 * 1024 * 1024)
    max_snapshot_bytes: int = Field(ge=1024, le=100 * 1024 * 1024)

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        return cls(
            model_cache_root=settings.docling_model_cache_root,
            device=settings.docling_device,
            num_threads=settings.docling_num_threads,
            document_timeout_seconds=settings.docling_document_timeout_seconds,
            ocr_engine=settings.docling_ocr_engine,
            enable_remote_services=False,
            allow_external_plugins=False,
            max_pages=settings.pdf_max_pages,
            max_file_size_bytes=settings.upload_max_file_size_bytes,
            max_snapshot_bytes=settings.docling_process_max_snapshot_bytes,
        )


DoclingWorkerTarget: TypeAlias = Callable[
    [Connection, dict[str, object], str, DoclingSourceType, bytes],
    None,
]


@dataclass(slots=True)
class _ProcessObservation:
    ready_ms: int | None = None
    peak_rss_bytes: int = 0


class _ProcessBoundaryFailure(Exception):
    """Private failure category used only for safe operational logging."""

    def __init__(self, status: str) -> None:
        super().__init__(status)
        self.status = status


class _ReadableProcessConnection(Protocol):
    def poll(self, timeout: float = 0.0) -> bool: ...

    def recv_bytes(self, maxlength: int | None = None) -> bytes: ...

    def close(self) -> None: ...


class DoclingProvider(Protocol):
    """Replaceable boundary so routine tests never load ML models."""

    def parse(
        self,
        *,
        source_name: str,
        source_type: DoclingSourceType,
        content: bytes,
    ) -> DoclingParseSnapshot: ...


def adapt_docling_snapshot(
    snapshot: DoclingParseSnapshot,
    *,
    source_sha256: str,
) -> CanonicalParsedArtifact:
    """Convert the stable snapshot, not Docling classes, into Canonical form."""

    blocks: list[ArtifactBlock] = []
    for item in snapshot.items:
        block_id = f"b{len(blocks) + 1:06d}"
        if isinstance(item, DoclingTextSnapshot):
            blocks.append(
                ArtifactTextBlock(
                    block_id=block_id,
                    text=item.text,
                    locator=SourceLocator(
                        page_number=item.page_number,
                        block_number=len(blocks) + 1,
                        heading_path=item.heading_path,
                    ),
                    heading_level=item.heading_level,
                    heading_path=item.heading_path,
                    style_name=f"docling:{item.label}",
                    bounding_box=item.bounding_box,
                )
            )
            continue
        blocks.append(_adapt_table(item, block_id=block_id))

    character_count = sum(
        sum(not character.isspace() for character in block.text)
        if isinstance(block, ArtifactTextBlock)
        else sum(
            sum(not character.isspace() for character in cell.display_text)
            for row in block.rows
            for cell in row.cells
        )
        for block in blocks
    )
    warnings = [
        ArtifactWarning(
            code=code,
            message="Docling返回了可继续使用的非致命解析警告",
            locator=SourceLocator(),
        )
        for code in snapshot.warning_codes
    ]
    return build_canonical_artifact(
        source_type=snapshot.source_type,
        source_sha256=source_sha256,
        parser_name=snapshot.parser_name,
        parser_version=snapshot.parser_version,
        provider="docling",
        adapter_version=DOCLING_ADAPTER_VERSION,
        blocks=blocks,
        warnings=warnings,
        source_character_count=character_count,
        page_count=(snapshot.page_count if snapshot.source_type == "pdf" else None),
        sheet_count=None,
    )


def _adapt_table(
    item: DoclingTableSnapshot,
    *,
    block_id: str,
) -> ArtifactTableBlock:
    by_coordinate: dict[tuple[int, int], DoclingTableCellSnapshot] = {}
    for cell in item.cells:
        for row in range(cell.start_row, cell.end_row):
            for column in range(cell.start_column, cell.end_column):
                by_coordinate[(row, column)] = cell

    rows: list[ArtifactTableRow] = []
    for row_index in range(item.row_count):
        cells: list[ArtifactTableCell] = []
        for column_index in range(item.column_count):
            source = by_coordinate.get((row_index, column_index))
            is_anchor = source is not None and (
                source.start_row == row_index and source.start_column == column_index
            )
            anchor = source if is_anchor else None
            text = anchor.text if anchor is not None else ""
            locator = SourceLocator(
                page_number=item.page_number,
                table_number=item.table_number,
                row_number=row_index + 1,
                column_number=column_index + 1,
            )
            cells.append(
                ArtifactTableCell(
                    column_number=column_index + 1,
                    value=text,
                    display_text=text,
                    data_type=("text" if text else "empty"),
                    row_span=(
                        anchor.end_row - anchor.start_row if anchor is not None else 1
                    ),
                    column_span=(
                        anchor.end_column - anchor.start_column
                        if anchor is not None
                        else 1
                    ),
                    row_header=bool(anchor and anchor.row_header),
                    column_header=bool(anchor and anchor.column_header),
                    locator=locator,
                    bounding_box=(anchor.bounding_box if anchor is not None else None),
                )
            )
        rows.append(
            ArtifactTableRow(
                row_number=row_index + 1,
                is_empty=all(not cell.display_text.strip() for cell in cells),
                locator=SourceLocator(
                    page_number=item.page_number,
                    table_number=item.table_number,
                ),
                cells=cells,
            )
        )

    first_row = rows[0].cells
    header_row_number = 1 if any(cell.column_header for cell in first_row) else None
    return ArtifactTableBlock(
        block_id=block_id,
        source_kind="document_table",
        locator=SourceLocator(
            page_number=item.page_number,
            table_number=item.table_number,
            heading_path=item.heading_path,
        ),
        heading_path=item.heading_path,
        headers=(
            [cell.display_text for cell in first_row]
            if header_row_number is not None
            else []
        ),
        header_row_number=header_row_number,
        rows=rows,
        bounding_box=item.bounding_box,
    )


def _send_worker_message(connection: Connection, payload: bytes) -> bool:
    try:
        connection.send_bytes(payload)
    except (BrokenPipeError, EOFError, OSError):
        return False
    return True


def _exit_docling_worker(connection: Connection, *, exit_code: int) -> NoReturn:
    """Close the one-shot result pipe, then bypass lingering library threads."""

    try:
        connection.close()
    finally:
        os._exit(exit_code)


def _docling_worker_entry(
    connection: Connection,
    config_payload: dict[str, object],
    source_name: str,
    source_type: DoclingSourceType,
    content: bytes,
) -> None:
    """Build and consume one Converter entirely inside one disposable process."""

    exit_code = 1
    try:
        config = _DoclingWorkerConfig.model_validate(config_payload)
        if not _send_worker_message(connection, _WORKER_READY):
            return
        snapshot = _parse_docling_in_worker(
            config=config,
            source_name=source_name,
            source_type=source_type,
            content=content,
        )
        payload = _WORKER_SUCCESS + snapshot.model_dump_json().encode("utf-8")
        if len(payload) > config.max_snapshot_bytes:
            payload = _WORKER_FAILURE
        exit_code = 0 if _send_worker_message(connection, payload) else 1
    except (Exception, MemoryError):  # noqa: BLE001 - details never cross the boundary.
        exit_code = 0 if _send_worker_message(connection, _WORKER_FAILURE) else 1
    finally:
        _exit_docling_worker(connection, exit_code=exit_code)


def _parse_docling_in_worker(
    *,
    config: _DoclingWorkerConfig,
    source_name: str,
    source_type: DoclingSourceType,
    content: bytes,
) -> DoclingParseSnapshot:
    from docling.datamodel.document import DocumentStream

    converter = _build_converter(config)
    converted = converter.convert(
        DocumentStream(
            name=Path(source_name).name,
            stream=io.BytesIO(content),
        ),
        raises_on_error=True,
        max_num_pages=config.max_pages,
        max_file_size=config.max_file_size_bytes,
    )
    return _snapshot_document(
        converted.document,
        source_type=source_type,
        parser_version=_docling_parser_version(),
        has_warnings=bool(converted.errors),
    )


def _receive_worker_message(
    connection: _ReadableProcessConnection,
    *,
    max_snapshot_bytes: int,
) -> bytes:
    try:
        return connection.recv_bytes(maxlength=max_snapshot_bytes)
    except EOFError:
        raise _ProcessBoundaryFailure("worker_crash") from None
    except OSError:
        raise _ProcessBoundaryFailure("result_too_large") from None


def _poll_worker_connection(
    connection: _ReadableProcessConnection,
    timeout_seconds: float,
) -> bool:
    try:
        return connection.poll(timeout_seconds)
    except (EOFError, OSError):
        raise _ProcessBoundaryFailure("worker_crash") from None


def _process_tree_rss_bytes(process_id: int) -> int:
    try:
        root = psutil.Process(process_id)
        processes = [root, *root.children(recursive=True)]
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        return 0
    except psutil.AccessDenied:
        raise _ProcessBoundaryFailure("memory_probe_failed") from None

    total = 0
    for process in processes:
        try:
            total += int(process.memory_info().rss)
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
        except psutil.AccessDenied:
            raise _ProcessBoundaryFailure("memory_probe_failed") from None
    return total


def _wait_for_worker_result(
    *,
    process: BaseProcess,
    connection: _ReadableProcessConnection,
    started_at: float,
    timeout_seconds: float,
    max_rss_bytes: int,
    max_snapshot_bytes: int,
    observation: _ProcessObservation,
) -> bytes:
    deadline = started_at + timeout_seconds
    while True:
        if _poll_worker_connection(connection, 0):
            payload = _receive_worker_message(
                connection,
                max_snapshot_bytes=max_snapshot_bytes,
            )
            if payload == _WORKER_READY:
                if observation.ready_ms is None:
                    observation.ready_ms = round(
                        (time.perf_counter() - started_at) * 1000
                    )
                continue
            return payload

        if not process.is_alive():
            raise _ProcessBoundaryFailure("worker_crash")

        process_id = process.pid
        if process_id is None:
            raise _ProcessBoundaryFailure("worker_start_failed")
        current_rss = _process_tree_rss_bytes(process_id)
        observation.peak_rss_bytes = max(observation.peak_rss_bytes, current_rss)
        if current_rss > max_rss_bytes:
            raise _ProcessBoundaryFailure("memory_limit")

        remaining_seconds = deadline - time.perf_counter()
        if remaining_seconds <= 0:
            raise _ProcessBoundaryFailure("timeout")
        _poll_worker_connection(
            connection,
            min(_PROCESS_POLL_SECONDS, remaining_seconds),
        )


def _stop_process(process: BaseProcess) -> None:
    process_id = process.pid
    if process_id is None:
        return
    try:
        descendants = psutil.Process(process_id).children(recursive=True)
    except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
        descendants = []
    if process.is_alive():
        try:
            process.terminate()
        except OSError:
            pass
    for descendant in reversed(descendants):
        try:
            descendant.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if process.is_alive():
        process.join(_PROCESS_SHUTDOWN_GRACE_SECONDS)
    if process.is_alive():
        try:
            process.kill()
        except OSError:
            pass
        process.join(_PROCESS_SHUTDOWN_GRACE_SECONDS)
    _, remaining_descendants = psutil.wait_procs(
        descendants,
        timeout=_PROCESS_SHUTDOWN_GRACE_SECONDS,
    )
    for descendant in remaining_descendants:
        try:
            descendant.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if remaining_descendants:
        psutil.wait_procs(
            remaining_descendants,
            timeout=_PROCESS_SHUTDOWN_GRACE_SECONDS,
        )


def _decode_worker_snapshot(
    payload: bytes,
    *,
    expected_source_type: DoclingSourceType,
) -> DoclingParseSnapshot:
    if payload == _WORKER_FAILURE:
        raise _ProcessBoundaryFailure("worker_failure")
    if not payload.startswith(_WORKER_SUCCESS):
        raise _ProcessBoundaryFailure("protocol_failure")
    try:
        snapshot = DoclingParseSnapshot.model_validate_json(payload[1:])
    except (ValueError, TypeError):
        raise _ProcessBoundaryFailure("protocol_failure") from None
    if snapshot.source_type != expected_source_type:
        raise _ProcessBoundaryFailure("protocol_failure")
    return snapshot


def _run_isolated_docling(
    *,
    config: _DoclingWorkerConfig,
    source_name: str,
    source_type: DoclingSourceType,
    content: bytes,
    timeout_seconds: float,
    max_rss_bytes: int,
    worker_target: DoclingWorkerTarget,
    process_context: SpawnContext,
) -> DoclingParseSnapshot:
    if len(content) > config.max_file_size_bytes:
        raise DocumentEnhancementError

    receive_connection, send_connection = process_context.Pipe(duplex=False)
    process = process_context.Process(
        target=worker_target,
        args=(
            send_connection,
            config.model_dump(mode="json"),
            source_name,
            source_type,
            content,
        ),
        name="m2-docling-worker",
    )
    started_at = time.perf_counter()
    observation = _ProcessObservation()
    status = "parent_failure"
    worker_pid: int | None = None
    spawn_ms: int | None = None
    send_connection_closed = False
    try:
        process.start()
        worker_pid = process.pid
        spawn_ms = round((time.perf_counter() - started_at) * 1000)
        send_connection.close()
        send_connection_closed = True
        payload = _wait_for_worker_result(
            process=process,
            connection=receive_connection,
            started_at=started_at,
            timeout_seconds=timeout_seconds,
            max_rss_bytes=max_rss_bytes,
            max_snapshot_bytes=config.max_snapshot_bytes,
            observation=observation,
        )
        process.join(_PROCESS_SHUTDOWN_GRACE_SECONDS)
        if process.is_alive():
            raise _ProcessBoundaryFailure("shutdown_timeout")
        if process.exitcode != 0:
            raise _ProcessBoundaryFailure("worker_crash")
        snapshot = _decode_worker_snapshot(
            payload,
            expected_source_type=source_type,
        )
        status = "success"
        return snapshot
    except _ProcessBoundaryFailure as exc:
        status = exc.status
        raise DocumentEnhancementError from None
    except (Exception, MemoryError):  # noqa: BLE001 - parent details remain private.
        raise DocumentEnhancementError from None
    finally:
        if not send_connection_closed:
            send_connection.close()
        _stop_process(process)
        receive_connection.close()
        try:
            process.close()
        except ValueError:
            pass
        elapsed_ms = round((time.perf_counter() - started_at) * 1000)
        log = _LOGGER.info if status == "success" else _LOGGER.warning
        log(
            "docling_process status=%s source_type=%s worker_pid=%s "
            "spawn_ms=%s ready_ms=%s total_ms=%s peak_rss_bytes=%s",
            status,
            source_type,
            worker_pid,
            spawn_ms,
            observation.ready_ms,
            elapsed_ms,
            observation.peak_rss_bytes,
        )


class LocalDoclingProvider:
    """Run each offline CPU-only Docling conversion in a disposable process."""

    def __init__(
        self,
        settings: Settings,
        *,
        worker_target: DoclingWorkerTarget = _docling_worker_entry,
        process_context: SpawnContext | None = None,
    ) -> None:
        self._settings = settings
        self._worker_target = worker_target
        self._process_context = process_context or multiprocessing.get_context("spawn")

    def parse(
        self,
        *,
        source_name: str,
        source_type: DoclingSourceType,
        content: bytes,
    ) -> DoclingParseSnapshot:
        if self._settings.docling_backend != "docling":
            raise DocumentEnhancementError
        config = _DoclingWorkerConfig.from_settings(self._settings)
        return _run_isolated_docling(
            config=config,
            source_name=source_name,
            source_type=source_type,
            content=content,
            timeout_seconds=self._settings.docling_process_timeout_seconds,
            max_rss_bytes=self._settings.docling_process_max_rss_bytes,
            worker_target=self._worker_target,
            process_context=self._process_context,
        )


def _build_converter(settings: _DoclingWorkerConfig) -> Any:
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

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    pipeline = PdfPipelineOptions(
        artifacts_path=settings.model_cache_root.resolve(),
        document_timeout=float(settings.document_timeout_seconds),
        accelerator_options=AcceleratorOptions(
            num_threads=settings.num_threads,
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


def _snapshot_document(
    document: Any,
    *,
    source_type: DoclingSourceType,
    parser_version: str,
    has_warnings: bool,
) -> DoclingParseSnapshot:
    from docling_core.types.doc.items.table.table import TableItem
    from docling_core.types.doc.items.text import SectionHeaderItem, TextItem, TitleItem

    items: list[DoclingSnapshotItem] = []
    heading_path: list[str] = []
    table_number = 0
    for source, _level in document.iterate_items():
        if isinstance(source, TextItem):
            text = source.text.strip()
            if not text:
                continue
            heading_level: int | None = None
            if isinstance(source, TitleItem):
                heading_level = 1
            elif isinstance(source, SectionHeaderItem):
                heading_level = min(9, max(1, int(source.level)))
            if heading_level is not None:
                heading_path = heading_path[: heading_level - 1] + [text]
            page_number, bounding_box = _item_location(document, source)
            label = getattr(source.label, "value", str(source.label))
            items.append(
                DoclingTextSnapshot(
                    text=text,
                    label=label,
                    page_number=page_number,
                    heading_level=heading_level,
                    heading_path=list(heading_path),
                    bounding_box=bounding_box,
                )
            )
            continue
        if isinstance(source, TableItem):
            table_number += 1
            page_number, bounding_box = _item_location(document, source)
            cell_snapshots = [
                DoclingTableCellSnapshot(
                    text=cell.text,
                    start_row=cell.start_row_offset_idx,
                    end_row=cell.end_row_offset_idx,
                    start_column=cell.start_col_offset_idx,
                    end_column=cell.end_col_offset_idx,
                    row_header=cell.row_header,
                    column_header=cell.column_header,
                    bounding_box=_bounding_box(
                        document,
                        page_number=page_number,
                        source_box=cell.bbox,
                    ),
                )
                for cell in source.data.table_cells
            ]
            if source.data.num_rows > 0 and source.data.num_cols > 0:
                items.append(
                    DoclingTableSnapshot(
                        table_number=table_number,
                        row_count=source.data.num_rows,
                        column_count=source.data.num_cols,
                        page_number=page_number,
                        heading_path=list(heading_path),
                        cells=cell_snapshots,
                        bounding_box=bounding_box,
                    )
                )

    return DoclingParseSnapshot(
        source_type=source_type,
        parser_version=parser_version,
        page_count=(len(document.pages) if source_type == "pdf" else None),
        items=items,
        warning_codes=(["docling_partial_result"] if has_warnings else []),
    )


def _item_location(
    document: Any,
    item: Any,
) -> tuple[int | None, ArtifactBoundingBox | None]:
    provenance = getattr(item, "prov", None) or []
    if not provenance:
        return None, None
    first = provenance[0]
    page_number = int(first.page_no)
    return page_number, _bounding_box(
        document,
        page_number=page_number,
        source_box=first.bbox,
    )


def _bounding_box(
    document: Any,
    *,
    page_number: int | None,
    source_box: Any | None,
) -> ArtifactBoundingBox | None:
    if page_number is None or source_box is None:
        return None
    page = document.pages.get(page_number)
    if page is None or page.size.width <= 0 or page.size.height <= 0:
        return None
    box = source_box.to_top_left_origin(page.size.height)
    left = max(0.0, min(float(box.l), float(page.size.width)))
    right = max(0.0, min(float(box.r), float(page.size.width)))
    top = max(0.0, min(float(box.t), float(page.size.height)))
    bottom = max(0.0, min(float(box.b), float(page.size.height)))
    if left >= right or top >= bottom:
        return None
    return ArtifactBoundingBox(
        page_number=page_number,
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        page_width=float(page.size.width),
        page_height=float(page.size.height),
    )


def _docling_parser_version() -> str:
    try:
        package_version = version("docling")
    except PackageNotFoundError:
        raise DocumentEnhancementError from None
    return f"m2-docling-v1+docling-{package_version}"
