"""Offline, replaceable image OCR used by the DOCX parser."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Protocol

from pydantic import Field

from app.schemas.common import M1Schema
from app.services.documents.parsers.base import DocumentEnhancementError

_DETECTION_MODEL = "PP-OCRv6_det_small.onnx"
_CLASSIFICATION_MODEL = "ch_ppocr_mobile_v2.0_cls_mobile.onnx"
_RECOGNITION_MODEL = "PP-OCRv6_rec_small.onnx"


class DocxImageOcrOutput(M1Schema):
    """One OCR result with enough provenance to audit it later."""

    text: str
    provider_name: str = Field(min_length=1, max_length=100)
    provider_version: str = Field(min_length=1, max_length=200)
    mean_confidence: float | None = Field(default=None, ge=0, le=1)


class DocxImageOcrProvider(Protocol):
    """Replaceable boundary; tests never need to load a real OCR model."""

    def extract(self, image_bytes: bytes) -> DocxImageOcrOutput: ...


class LocalRapidOcrProvider:
    """Run fixed RapidOCR ONNX models locally without remote downloads."""

    def __init__(self, *, model_cache_root: Path, num_threads: int) -> None:
        if not 1 <= num_threads <= 4:
            raise ValueError("DOCX OCR threads must stay between 1 and 4")
        self._model_root = model_cache_root / "RapidOcr"
        self._num_threads = num_threads
        self._engine: Any | None = None

    def extract(self, image_bytes: bytes) -> DocxImageOcrOutput:
        try:
            engine = self._engine or self._build_engine()
            self._engine = engine
            result = engine(image_bytes)
            texts = tuple(result.txts or ())
            scores = tuple(float(score) for score in (result.scores or ()))
        except Exception:  # noqa: BLE001 - provider internals remain private.
            raise DocumentEnhancementError from None

        normalized_lines = [
            " ".join(str(item).replace("\r", "\n").split())
            for item in texts
            if str(item).strip()
        ]
        return DocxImageOcrOutput(
            text="\n".join(normalized_lines),
            provider_name="rapidocr",
            provider_version=_provider_version(),
            mean_confidence=(sum(scores) / len(scores) if scores else None),
        )

    def _build_engine(self) -> Any:
        paths = {
            "Det.model_path": self._model_root / _DETECTION_MODEL,
            "Cls.model_path": self._model_root / _CLASSIFICATION_MODEL,
            "Rec.model_path": self._model_root / _RECOGNITION_MODEL,
        }
        if any(not path.is_file() for path in paths.values()):
            raise DocumentEnhancementError

        try:
            from rapidocr import RapidOCR

            return RapidOCR(
                params={
                    **{name: str(path.resolve()) for name, path in paths.items()},
                    "EngineConfig.onnxruntime.intra_op_num_threads": (
                        self._num_threads
                    ),
                    "EngineConfig.onnxruntime.inter_op_num_threads": 1,
                    "Global.log_level": "warning",
                }
            )
        except Exception:  # noqa: BLE001 - model/runtime details remain private.
            raise DocumentEnhancementError from None


def _provider_version() -> str:
    try:
        package_version = version("rapidocr")
    except PackageNotFoundError:
        package_version = "unknown"
    return f"rapidocr-{package_version}+pp-ocrv6-small-onnxruntime-cpu"
