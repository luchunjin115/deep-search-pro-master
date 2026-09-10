from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from app.schemas.evaluation import MINIMUM_FREE_SPACE_BYTES, EvaluationSourceManifest
from scripts.prepare_m2_cross_border_eval import (
    PROJECT_ROOT,
    EvaluationPreparationError,
    prepare_evaluation_source,
)


class FakeResponse:
    def __init__(
        self,
        chunks: list[bytes],
        *,
        status_code: int = 200,
        content_length: int | None = None,
        content_type: str = "application/pdf",
        fail_after_chunk: bool = False,
    ) -> None:
        self.status_code = status_code
        self.headers: dict[str, str] = {"content-type": content_type}
        if content_length is not None:
            self.headers["content-length"] = str(content_length)
        self._chunks = chunks
        self._fail_after_chunk = fail_after_chunk
        self.iterated = False

    def iter_bytes(self) -> Iterator[bytes]:
        self.iterated = True
        yield from self._chunks
        if self._fail_after_chunk:
            raise OSError("simulated interrupted connection")


class FakeStreamFactory:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.urls: list[str] = []

    @contextmanager
    def __call__(self, url: str) -> Iterator[FakeResponse]:
        self.urls.append(url)
        yield self.response


def _source(**changes: Any) -> dict[str, Any]:
    source: dict[str, Any] = {
        "source_id": "eu-vat-guide-test",
        "dataset_version": "m2-cross-border-sources-v1",
        "source_group": "cross_border_core",
        "source_kind": "public_source",
        "source_name": "Official VAT guide",
        "source_organization": "European Commission",
        "official_source_url": "https://example.europa.eu/files/vat-guide.pdf",
        "source_format": "pdf",
        "languages": ["en"],
        "business_purpose": "Test a bounded official cross-border guide.",
        "counts_toward_core_score": True,
        "license_status": "allowed_redistribution",
        "license_name": "Creative Commons Attribution 4.0 International",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "download_allowed": True,
        "redistribution_allowed": True,
        "accessed_on": "2026-09-07",
        "published_on": "2026-07-24",
        "source_version": "2026-07-24",
        "lifecycle_status": "planned",
        "max_download_bytes": 1024,
        "expected_size_bytes": None,
        "actual_size_bytes": None,
        "raw_sha256": None,
        "processed_sha256": None,
        "raw_relative_path": None,
        "processed_relative_path": None,
        "transformation_method": None,
        "transformation_version": None,
        "rejection_reason": None,
    }
    source.update(changes)
    return source


def _write_manifest(path: Path, *sources: dict[str, Any]) -> None:
    payload = {
        "manifest_version": "m2-cross-border-sources-v1",
        "dataset_version": "m2-cross-border-sources-v1",
        "sources": list(sources),
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _pdf_bytes(label: bytes = b"bounded fixture") -> bytes:
    return b"%PDF-1.4\n" + label + b"\n%%EOF\n"


def _prepare(
    manifest_path: Path,
    data_root: Path,
    factory: FakeStreamFactory,
    *,
    source_id: str = "eu-vat-guide-test",
    free_bytes: int = MINIMUM_FREE_SPACE_BYTES,
):
    return prepare_evaluation_source(
        source_id=source_id,
        manifest_path=manifest_path,
        data_root=data_root,
        allow_download=True,
        stream_factory=factory,
        available_free_bytes=free_bytes,
    )


def test_download_requires_explicit_permission_reviewed_license_and_manifest_id(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    _write_manifest(manifest, _source())
    factory = FakeStreamFactory(FakeResponse([_pdf_bytes()]))

    with pytest.raises(EvaluationPreparationError, match="explicitly allowed"):
        prepare_evaluation_source(
            source_id="eu-vat-guide-test",
            manifest_path=manifest,
            data_root=tmp_path / "data",
            allow_download=False,
            stream_factory=factory,
            available_free_bytes=MINIMUM_FREE_SPACE_BYTES,
        )
    with pytest.raises(EvaluationPreparationError, match="allow-list"):
        _prepare(manifest, tmp_path / "data", factory, source_id="not-listed")

    _write_manifest(
        manifest,
        _source(
            license_status="pending_review",
            license_name=None,
            license_url=None,
            download_allowed=False,
            redistribution_allowed=False,
        ),
    )
    with pytest.raises(EvaluationPreparationError, match="license"):
        _prepare(manifest, tmp_path / "data", factory)
    assert factory.urls == []


def test_data_root_cannot_target_repository_metadata_or_runtime_storage(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    _write_manifest(manifest, _source())
    factory = FakeStreamFactory(FakeResponse([_pdf_bytes()]))

    with pytest.raises(EvaluationPreparationError, match="too broad"):
        _prepare(manifest, PROJECT_ROOT / ".git" / "evaluation", factory)
    with pytest.raises(EvaluationPreparationError, match="too broad"):
        _prepare(manifest, PROJECT_ROOT / "data" / "storage" / "evaluation", factory)
    assert factory.urls == []


def test_content_length_and_disk_gate_fail_before_streaming(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    _write_manifest(manifest, _source(max_download_bytes=64))
    oversized = FakeResponse(
        [_pdf_bytes()], content_length=65, content_type="application/pdf"
    )
    factory = FakeStreamFactory(oversized)

    with pytest.raises(EvaluationPreparationError, match="declared size"):
        _prepare(manifest, tmp_path / "data", factory)
    assert oversized.iterated is False

    factory = FakeStreamFactory(FakeResponse([_pdf_bytes()]))
    with pytest.raises(EvaluationPreparationError, match="disk preflight"):
        _prepare(
            manifest,
            tmp_path / "data",
            factory,
            free_bytes=MINIMUM_FREE_SPACE_BYTES - 1,
        )
    assert factory.urls == []


def test_stream_limit_and_interruption_remove_only_partial_files(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    _write_manifest(manifest, _source(max_download_bytes=16))
    data_root = tmp_path / "data"

    with pytest.raises(EvaluationPreparationError, match="streamed size"):
        _prepare(
            manifest,
            data_root,
            FakeStreamFactory(FakeResponse([_pdf_bytes(b"too large")])),
        )
    assert list(data_root.rglob("*.part")) == []
    assert list(data_root.rglob("*.pdf")) == []

    _write_manifest(manifest, _source(max_download_bytes=1024))
    interrupted = FakeResponse([b"%PDF-1.4\n"], fail_after_chunk=True)
    with pytest.raises(EvaluationPreparationError, match="download failed"):
        _prepare(manifest, data_root, FakeStreamFactory(interrupted))
    assert list(data_root.rglob("*.part")) == []
    assert list(data_root.rglob("*.pdf")) == []


@pytest.mark.parametrize(
    ("status_code", "content_type", "content", "message"),
    [
        (302, "application/pdf", _pdf_bytes(), "redirect"),
        (200, "text/html", b"<html>login</html>", "content type"),
        (200, "application/pdf", b"not really a pdf", "file signature"),
    ],
)
def test_redirect_wrong_content_type_and_spoofed_file_are_rejected(
    tmp_path: Path,
    status_code: int,
    content_type: str,
    content: bytes,
    message: str,
) -> None:
    manifest = tmp_path / "manifest.json"
    _write_manifest(manifest, _source())
    response = FakeResponse(
        [content], status_code=status_code, content_type=content_type
    )

    with pytest.raises(EvaluationPreparationError, match=message):
        _prepare(manifest, tmp_path / "data", FakeStreamFactory(response))
    assert list((tmp_path / "data").rglob("*.part")) == []


def test_success_hashes_raw_and_deterministic_processed_pdf_and_updates_manifest(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    content = _pdf_bytes()
    _write_manifest(manifest_path, _source(expected_size_bytes=len(content)))
    data_root = tmp_path / "data"
    factory = FakeStreamFactory(
        FakeResponse([content[:8], content[8:]], content_length=len(content))
    )

    result = _prepare(manifest_path, data_root, factory)
    manifest = EvaluationSourceManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    source = manifest.sources[0]
    expected_hash = hashlib.sha256(content).hexdigest()

    assert result.source_id == source.source_id
    assert source.lifecycle_status == "verified"
    assert source.expected_size_bytes == len(content)
    assert source.actual_size_bytes == len(content)
    assert source.raw_sha256 == expected_hash
    assert source.processed_sha256 == expected_hash
    assert source.transformation_method == "identity_copy"
    assert source.transformation_version == "m2-eval-transform-v1"
    raw = data_root / str(source.raw_relative_path)
    processed = data_root / str(source.processed_relative_path)
    assert raw.read_bytes() == processed.read_bytes() == content
    assert raw.stat().st_mode & 0o222 == 0
    assert list(data_root.rglob("*.part")) == []


def test_verified_rerun_is_offline_and_conflict_is_never_overwritten(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    content = _pdf_bytes()
    _write_manifest(manifest_path, _source())
    data_root = tmp_path / "data"
    first_factory = FakeStreamFactory(FakeResponse([content]))
    first = _prepare(manifest_path, data_root, first_factory)

    unused_factory = FakeStreamFactory(FakeResponse([b"should not be used"]))
    second = _prepare(manifest_path, data_root, unused_factory)
    assert first.reused is False
    assert second.reused is True
    assert second.raw_sha256 == first.raw_sha256
    assert second.processed_sha256 == first.processed_sha256
    assert unused_factory.urls == []

    raw_path = data_root / first.raw_relative_path
    raw_path.chmod(0o666)
    raw_path.write_bytes(b"corrupt")
    with pytest.raises(EvaluationPreparationError, match="existing file conflict"):
        _prepare(manifest_path, data_root, unused_factory)
    assert raw_path.read_bytes() == b"corrupt"
    assert unused_factory.urls == []


def test_untracked_existing_target_is_not_silently_overwritten(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, _source())
    target = (
        tmp_path
        / "data"
        / "raw"
        / "m2-cross-border-sources-v1"
        / "eu-vat-guide-test.pdf"
    )
    target.parent.mkdir(parents=True)
    target.write_bytes(b"user data")
    factory = FakeStreamFactory(FakeResponse([_pdf_bytes()]))

    with pytest.raises(EvaluationPreparationError, match="existing file conflict"):
        _prepare(manifest_path, tmp_path / "data", factory)
    assert target.read_bytes() == b"user data"
    assert factory.urls == []


def test_verified_manifest_can_rehydrate_missing_ignored_files_and_checks_pinned_hash(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    content = _pdf_bytes()
    _write_manifest(manifest_path, _source())
    first_root = tmp_path / "first"
    _prepare(
        manifest_path,
        first_root,
        FakeStreamFactory(FakeResponse([content])),
    )

    second_root = tmp_path / "second"
    restored = _prepare(
        manifest_path,
        second_root,
        FakeStreamFactory(FakeResponse([content])),
    )
    assert restored.reused is False
    assert (second_root / restored.raw_relative_path).read_bytes() == content

    third_root = tmp_path / "third"
    with pytest.raises(EvaluationPreparationError, match="pinned SHA-256"):
        _prepare(
            manifest_path,
            third_root,
            FakeStreamFactory(FakeResponse([_pdf_bytes(b"changed upstream")])),
        )
    assert list(third_root.rglob("*.part")) == []
    assert list(third_root.rglob("*.pdf")) == []


def test_licensed_png_is_wrapped_as_a_deterministic_single_page_pdf(
    tmp_path: Path,
) -> None:
    buffer = BytesIO()
    Image.new("RGB", (2, 2), (12, 34, 56)).save(buffer, format="PNG")
    png = buffer.getvalue()
    outputs: list[bytes] = []
    for ordinal in (1, 2):
        manifest = tmp_path / f"manifest-{ordinal}.json"
        _write_manifest(
            manifest,
            _source(
                source_kind="deterministic_transform",
                source_format="png",
                official_source_url="https://example.europa.eu/files/receipt.png",
                expected_size_bytes=len(png),
            ),
        )
        root = tmp_path / f"data-{ordinal}"
        result = _prepare(
            manifest,
            root,
            FakeStreamFactory(
                FakeResponse(
                    [png],
                    content_length=len(png),
                    content_type="image/png",
                )
            ),
        )
        outputs.append((root / result.processed_relative_path).read_bytes())
        assert result.transformation_method == "image_to_pdf"

    assert outputs[0].startswith(b"%PDF-")
    assert outputs[0] == outputs[1]
