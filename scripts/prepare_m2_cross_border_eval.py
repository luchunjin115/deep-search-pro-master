"""Prepare one reviewed M2 evaluation source through a bounded local pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

import httpx

from app.schemas.evaluation import (
    MAX_MANIFEST_SERIALIZED_BYTES,
    DiskPreflightInput,
    EvaluationSource,
    EvaluationSourceManifest,
    canonical_evaluation_bytes,
    evaluate_disk_preflight,
)

PROJECT_ROOT: Final = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_PATH: Final = (
    PROJECT_ROOT / "data" / "evals" / "m2_cross_border_sources_v1.json"
)
DEFAULT_DATA_ROOT: Final = PROJECT_ROOT / "data" / "evals" / "runtime"
TRANSFORMATION_VERSION: Final = "m2-eval-transform-v1"
_CHUNK_SIZE: Final = 64 * 1024
_SUPPORTED_CONTENT_TYPES: Final = {
    "pdf": {"application/pdf"},
    "docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
    },
    "xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
    },
    "csv": {"text/csv", "text/plain", "application/csv"},
    "png": {"image/png"},
    "jpeg": {"image/jpeg"},
}
_EXTENSIONS: Final = {
    "pdf": ".pdf",
    "docx": ".docx",
    "xlsx": ".xlsx",
    "csv": ".csv",
    "png": ".png",
    "jpeg": ".jpg",
}


class EvaluationPreparationError(RuntimeError):
    """A bounded operational error that never exposes a URL or local path."""


class StreamingResponse(Protocol):
    status_code: int
    headers: httpx.Headers | dict[str, str]

    def iter_bytes(self, chunk_size: int | None = None) -> Iterator[bytes]: ...


StreamFactory = Callable[[str], AbstractContextManager[StreamingResponse]]


@dataclass(frozen=True, slots=True)
class PreparedEvaluationSource:
    """Safe summary of one verified local source."""

    source_id: str
    actual_size_bytes: int
    raw_sha256: str
    processed_sha256: str
    raw_relative_path: str
    processed_relative_path: str
    transformation_method: str
    transformation_version: str
    reused: bool


def load_source_manifest(path: Path) -> EvaluationSourceManifest:
    """Load a bounded, strict Manifest without returning raw parse failures."""

    try:
        payload = path.read_bytes()
        if len(payload) > MAX_MANIFEST_SERIALIZED_BYTES:
            raise EvaluationPreparationError("source manifest exceeds its size limit")
        return EvaluationSourceManifest.model_validate_json(payload)
    except EvaluationPreparationError:
        raise
    except Exception:  # noqa: BLE001 - CLI and tests require a stable safe boundary.
        raise EvaluationPreparationError("source manifest is invalid") from None


def prepare_evaluation_source(
    *,
    source_id: str,
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    data_root: Path = DEFAULT_DATA_ROOT,
    allow_download: bool,
    stream_factory: StreamFactory | None = None,
    available_free_bytes: int | None = None,
) -> PreparedEvaluationSource:
    """Download, verify, transform, and record one Manifest-whitelisted source."""

    manifest = load_source_manifest(manifest_path)
    source = next(
        (
            candidate
            for candidate in manifest.sources
            if candidate.source_id == source_id
        ),
        None,
    )
    if source is None:
        raise EvaluationPreparationError("source ID is not in the Manifest allow-list")

    raw_relative, processed_relative = _managed_relative_paths(source)
    root = _resolved_data_root(data_root)
    raw_path = _contained_path(root, raw_relative)
    processed_path = _contained_path(root, processed_relative)

    rehydrating = source.lifecycle_status == "verified"
    if rehydrating:
        _validate_recorded_paths(source)
        raw_exists = raw_path.is_file() and not raw_path.is_symlink()
        processed_exists = processed_path.is_file() and not processed_path.is_symlink()
        if raw_exists and processed_exists:
            return _verify_recorded_source(source, raw_path, processed_path)
        if (
            raw_path.exists()
            or raw_path.is_symlink()
            or processed_path.exists()
            or processed_path.is_symlink()
        ):
            raise EvaluationPreparationError(
                "existing file conflict; verified source is only partly present"
            )
    elif source.lifecycle_status != "planned":
        raise EvaluationPreparationError("source lifecycle is not preparable")
    if not allow_download:
        raise EvaluationPreparationError("source download was not explicitly allowed")
    _validate_download_authorization(source)
    _refuse_existing_targets(raw_path, processed_path)
    _run_disk_preflight(
        root,
        source,
        available_free_bytes=available_free_bytes,
    )

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    processed_path.parent.mkdir(parents=True, exist_ok=True)
    raw_part = raw_path.with_name(f"{raw_path.name}.part")
    processed_part = processed_path.with_name(f"{processed_path.name}.part")
    _refuse_existing_targets(raw_part, processed_part)

    created_final_paths: list[Path] = []
    try:
        actual_size, streaming_hash = _download_to_partial(
            source,
            raw_part,
            stream_factory=stream_factory,
        )
        reread_hash = _sha256_file(raw_part)
        if reread_hash != streaming_hash:
            raise EvaluationPreparationError("downloaded SHA-256 verification failed")
        if rehydrating and (
            actual_size != source.actual_size_bytes or reread_hash != source.raw_sha256
        ):
            raise EvaluationPreparationError(
                "downloaded file differs from the pinned SHA-256 or size"
            )
        if source.expected_size_bytes is not None and (
            actual_size != source.expected_size_bytes
        ):
            raise EvaluationPreparationError("downloaded size differs from Manifest")

        method = _write_processed_partial(source, raw_part, processed_part)
        processed_hash = _sha256_file(processed_part)
        if rehydrating and (
            method != source.transformation_method
            or processed_hash != source.processed_sha256
            or source.transformation_version != TRANSFORMATION_VERSION
        ):
            raise EvaluationPreparationError(
                "processed file differs from the pinned SHA-256 or transform"
            )
        _replace_new_file(raw_part, raw_path)
        created_final_paths.append(raw_path)
        raw_path.chmod(stat.S_IREAD)
        _replace_new_file(processed_part, processed_path)
        created_final_paths.append(processed_path)

        verified = EvaluationSource.model_validate(
            source.model_dump(mode="json")
            | {
                "lifecycle_status": "verified",
                "expected_size_bytes": actual_size,
                "actual_size_bytes": actual_size,
                "raw_sha256": reread_hash,
                "processed_sha256": processed_hash,
                "raw_relative_path": raw_relative.as_posix(),
                "processed_relative_path": processed_relative.as_posix(),
                "transformation_method": method,
                "transformation_version": TRANSFORMATION_VERSION,
            }
        )
        updated_manifest = _replace_manifest_source(manifest, verified)
        _write_manifest_atomically(manifest_path, updated_manifest)
    except EvaluationPreparationError:
        _cleanup_owned_files(raw_part, processed_part, *created_final_paths)
        raise
    except Exception:  # noqa: BLE001 - network/filesystem libraries vary by platform.
        _cleanup_owned_files(raw_part, processed_part, *created_final_paths)
        raise EvaluationPreparationError("source download failed") from None

    return _result_from_source(verified, reused=False)


def _validate_download_authorization(source: EvaluationSource) -> None:
    if (
        source.license_status
        not in {"allowed_redistribution", "allowed_no_redistribution"}
        or not source.download_allowed
        or source.license_name is None
        or source.license_url is None
    ):
        raise EvaluationPreparationError("source license is not approved for download")
    if source.source_version is None:
        raise EvaluationPreparationError("source version is not pinned")
    if source.source_format not in _SUPPORTED_CONTENT_TYPES:
        raise EvaluationPreparationError("source format is not a selected file format")
    if source.source_format in {"png", "jpeg"}:
        if source.source_kind != "deterministic_transform":
            raise EvaluationPreparationError(
                "image source requires deterministic transform"
            )
    elif source.source_kind != "public_source":
        raise EvaluationPreparationError("file source kind is not approved")


def _managed_relative_paths(source: EvaluationSource) -> tuple[Path, Path]:
    extension = _EXTENSIONS.get(source.source_format)
    if extension is None:
        raise EvaluationPreparationError("source format is not a selected file format")
    raw = Path("raw") / source.dataset_version / f"{source.source_id}{extension}"
    processed_extension = (
        ".pdf" if source.source_format in {"png", "jpeg"} else extension
    )
    processed = (
        Path("processed")
        / source.dataset_version
        / f"{source.source_id}{processed_extension}"
    )
    return raw, processed


def _resolved_data_root(data_root: Path) -> Path:
    try:
        root = data_root.resolve(strict=False)
    except OSError:
        raise EvaluationPreparationError("evaluation data root is invalid") from None
    project_root = PROJECT_ROOT.resolve()
    default_root = DEFAULT_DATA_ROOT.resolve()
    if (
        root == Path(root.anchor)
        or root == project_root
        or (root.is_relative_to(project_root) and not root.is_relative_to(default_root))
    ):
        raise EvaluationPreparationError("evaluation data root is too broad")
    return root


def _contained_path(root: Path, relative: Path) -> Path:
    target = (root / relative).resolve(strict=False)
    if not target.is_relative_to(root):
        raise EvaluationPreparationError("managed evaluation path escaped its root")
    return target


def _refuse_existing_targets(*paths: Path) -> None:
    if any(path.exists() or path.is_symlink() for path in paths):
        raise EvaluationPreparationError(
            "existing file conflict; nothing was overwritten"
        )


def _run_disk_preflight(
    root: Path,
    source: EvaluationSource,
    *,
    available_free_bytes: int | None,
) -> None:
    if available_free_bytes is None:
        probe = root
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        try:
            available_free_bytes = shutil.disk_usage(probe).free
        except OSError:
            available_free_bytes = None

    current_raw = _tree_size(root / "raw")
    current_processed = _tree_size(root / "processed")
    predicted_processed = source.max_download_bytes
    if source.source_format in {"png", "jpeg"}:
        predicted_processed *= 2
    gate = evaluate_disk_preflight(
        DiskPreflightInput(
            unit="bytes",
            external_raw_bytes=current_raw + source.max_download_bytes,
            processed_artifact_bytes=current_processed + predicted_processed,
            postgres_index_bytes=0,
            existing_model_cache_bytes=0,
            available_free_bytes=available_free_bytes,
        )
    )
    if not gate.allowed:
        raise EvaluationPreparationError(
            f"disk preflight rejected preparation: {','.join(gate.reason_codes)}"
        )


def _tree_size(root: Path) -> int:
    if not root.exists():
        return 0
    total = 0
    try:
        for path in root.rglob("*"):
            if path.is_file() and not path.is_symlink():
                total += path.stat().st_size
    except OSError:
        raise EvaluationPreparationError(
            "evaluation data size cannot be measured"
        ) from None
    return total


def _default_stream_factory(url: str) -> AbstractContextManager[StreamingResponse]:
    client = httpx.Client(
        follow_redirects=False,
        timeout=httpx.Timeout(30.0, connect=15.0),
        headers={
            "Accept-Encoding": "identity",
            "User-Agent": "deep-search-pro-m2-eval/1",
        },
    )
    return _ClientStream(client, url)


class _ClientStream:
    def __init__(self, client: httpx.Client, url: str) -> None:
        self._client = client
        self._stream = client.stream("GET", url)

    def __enter__(self) -> StreamingResponse:
        try:
            return self._stream.__enter__()
        except Exception:
            self._client.close()
            raise

    def __exit__(self, *args: object) -> None:
        try:
            self._stream.__exit__(*args)
        finally:
            self._client.close()


def _download_to_partial(
    source: EvaluationSource,
    target: Path,
    *,
    stream_factory: StreamFactory | None,
) -> tuple[int, str]:
    factory = stream_factory or _default_stream_factory
    try:
        with factory(source.official_source_url) as response:
            if 300 <= response.status_code < 400:
                raise EvaluationPreparationError(
                    "source redirect is forbidden; pin the final URL in the Manifest"
                )
            if response.status_code != 200:
                raise EvaluationPreparationError(
                    "source download returned a non-success status"
                )
            declared_size = _declared_content_length(response.headers)
            if declared_size is not None and declared_size > source.max_download_bytes:
                raise EvaluationPreparationError(
                    "source declared size exceeds its budget"
                )
            _validate_content_type(source, response.headers)

            digest = hashlib.sha256()
            actual_size = 0
            with target.open("xb") as destination:
                for chunk in response.iter_bytes():
                    if not chunk:
                        continue
                    actual_size += len(chunk)
                    if actual_size > source.max_download_bytes:
                        raise EvaluationPreparationError(
                            "source streamed size exceeds its budget"
                        )
                    destination.write(chunk)
                    digest.update(chunk)
            if actual_size == 0:
                raise EvaluationPreparationError("source download was empty")
            if declared_size is not None and actual_size != declared_size:
                raise EvaluationPreparationError(
                    "source streamed size differs from declared size"
                )
            _validate_file_signature(source.source_format, target)
            return actual_size, digest.hexdigest()
    except EvaluationPreparationError:
        raise
    except Exception:  # noqa: BLE001 - httpx and injected streams have varied failures.
        raise EvaluationPreparationError("source download failed") from None


def _declared_content_length(headers: httpx.Headers | dict[str, str]) -> int | None:
    raw = headers.get("content-length")
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise EvaluationPreparationError("source declared size is invalid") from None
    if value < 1:
        raise EvaluationPreparationError("source declared size is invalid")
    return value


def _validate_content_type(
    source: EvaluationSource,
    headers: httpx.Headers | dict[str, str],
) -> None:
    content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in _SUPPORTED_CONTENT_TYPES[source.source_format]:
        raise EvaluationPreparationError("source content type does not match Manifest")


def _validate_file_signature(source_format: str, path: Path) -> None:
    with path.open("rb") as source:
        prefix = source.read(8)
    valid = True
    if source_format == "pdf":
        valid = prefix.startswith(b"%PDF-")
    elif source_format in {"docx", "xlsx"}:
        valid = prefix.startswith(b"PK\x03\x04")
    elif source_format == "png":
        valid = prefix == b"\x89PNG\r\n\x1a\n"
    elif source_format == "jpeg":
        valid = prefix.startswith(b"\xff\xd8\xff")
    if not valid:
        raise EvaluationPreparationError(
            "source file signature does not match Manifest"
        )


def _write_processed_partial(
    source: EvaluationSource,
    raw_path: Path,
    processed_path: Path,
) -> str:
    if source.source_format not in {"png", "jpeg"}:
        _copy_file(raw_path, processed_path, max_bytes=source.max_download_bytes)
        return "identity_copy"
    _convert_image_to_pdf(raw_path, processed_path, source.max_download_bytes * 2)
    return "image_to_pdf"


def _copy_file(source: Path, target: Path, *, max_bytes: int) -> None:
    copied = 0
    with source.open("rb") as input_stream, target.open("xb") as output_stream:
        while block := input_stream.read(_CHUNK_SIZE):
            copied += len(block)
            if copied > max_bytes:
                raise EvaluationPreparationError("processed file exceeds its budget")
            output_stream.write(block)


def _convert_image_to_pdf(source: Path, target: Path, max_bytes: int) -> None:
    try:
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen.canvas import Canvas

        image = ImageReader(str(source))
        width, height = image.getSize()
        if width < 1 or height < 1 or width > 20_000 or height > 20_000:
            raise EvaluationPreparationError("image dimensions are outside safe limits")
        canvas = Canvas(
            str(target),
            pagesize=(float(width), float(height)),
            invariant=1,
            pageCompression=1,
        )
        canvas.drawImage(image, 0, 0, width=width, height=height, mask="auto")
        canvas.showPage()
        canvas.save()
        if target.stat().st_size > max_bytes:
            raise EvaluationPreparationError("processed file exceeds its budget")
        _validate_file_signature("pdf", target)
    except EvaluationPreparationError:
        raise
    except Exception:  # noqa: BLE001 - image codecs can raise many safe-to-mask errors.
        raise EvaluationPreparationError("image conversion failed") from None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            while block := source.read(_CHUNK_SIZE):
                digest.update(block)
    except OSError:
        raise EvaluationPreparationError("file SHA-256 verification failed") from None
    return digest.hexdigest()


def _replace_new_file(partial: Path, final: Path) -> None:
    if final.exists() or final.is_symlink():
        raise EvaluationPreparationError(
            "existing file conflict; nothing was overwritten"
        )
    partial.replace(final)


def _replace_manifest_source(
    manifest: EvaluationSourceManifest,
    replacement: EvaluationSource,
) -> EvaluationSourceManifest:
    return EvaluationSourceManifest.model_validate(
        manifest.model_dump(mode="json")
        | {
            "sources": [
                replacement.model_dump(mode="json")
                if source.source_id == replacement.source_id
                else source.model_dump(mode="json")
                for source in manifest.sources
            ]
        }
    )


def _write_manifest_atomically(
    path: Path,
    manifest: EvaluationSourceManifest,
) -> None:
    payload = canonical_evaluation_bytes(manifest)
    if len(payload) > MAX_MANIFEST_SERIALIZED_BYTES:
        raise EvaluationPreparationError("source manifest exceeds its size limit")
    temporary = path.with_name(f"{path.name}.part")
    if temporary.exists() or temporary.is_symlink():
        raise EvaluationPreparationError(
            "existing file conflict; nothing was overwritten"
        )
    try:
        temporary.write_text(
            json.dumps(
                manifest.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    except OSError:
        _cleanup_owned_files(temporary)
        raise EvaluationPreparationError("source manifest update failed") from None


def _verify_recorded_source(
    source: EvaluationSource,
    raw_path: Path,
    processed_path: Path,
) -> PreparedEvaluationSource:
    _validate_recorded_paths(source)
    if not raw_path.is_file() or not processed_path.is_file():
        raise EvaluationPreparationError(
            "existing file conflict; verified file is missing"
        )
    if (
        raw_path.stat().st_size != source.actual_size_bytes
        or _sha256_file(raw_path) != source.raw_sha256
        or _sha256_file(processed_path) != source.processed_sha256
    ):
        raise EvaluationPreparationError(
            "existing file conflict; verified hash differs"
        )
    return _result_from_source(source, reused=True)


def _validate_recorded_paths(source: EvaluationSource) -> None:
    expected_paths = (
        source.raw_relative_path,
        source.processed_relative_path,
    )
    generated_paths = _managed_relative_paths(source)
    if expected_paths != tuple(path.as_posix() for path in generated_paths):
        raise EvaluationPreparationError("recorded managed path is inconsistent")


def _result_from_source(
    source: EvaluationSource,
    *,
    reused: bool,
) -> PreparedEvaluationSource:
    if not all(
        (
            source.actual_size_bytes,
            source.raw_sha256,
            source.processed_sha256,
            source.raw_relative_path,
            source.processed_relative_path,
            source.transformation_method,
            source.transformation_version,
        )
    ):
        raise EvaluationPreparationError("verified source record is incomplete")
    return PreparedEvaluationSource(
        source_id=source.source_id,
        actual_size_bytes=source.actual_size_bytes,  # type: ignore[arg-type]
        raw_sha256=source.raw_sha256,  # type: ignore[arg-type]
        processed_sha256=source.processed_sha256,  # type: ignore[arg-type]
        raw_relative_path=source.raw_relative_path,  # type: ignore[arg-type]
        processed_relative_path=source.processed_relative_path,  # type: ignore[arg-type]
        transformation_method=source.transformation_method,  # type: ignore[arg-type]
        transformation_version=source.transformation_version,  # type: ignore[arg-type]
        reused=reused,
    )


def _cleanup_owned_files(*paths: Path) -> None:
    for path in paths:
        try:
            if path.is_file() or path.is_symlink():
                path.chmod(stat.S_IWRITE | stat.S_IREAD)
                path.unlink()
        except OSError:
            continue


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--allow-download", action="store_true")
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    try:
        result = prepare_evaluation_source(
            source_id=arguments.source_id,
            manifest_path=arguments.manifest,
            data_root=arguments.data_root,
            allow_download=arguments.allow_download,
        )
    except EvaluationPreparationError as exc:
        print(f"M2 evaluation source preparation failed: {exc}")
        return 1
    print(f"source_id={result.source_id}")
    print(f"size_bytes={result.actual_size_bytes}")
    print(f"raw_sha256={result.raw_sha256}")
    print(f"processed_sha256={result.processed_sha256}")
    print(f"reused={str(result.reused).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
