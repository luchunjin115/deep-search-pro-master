"""Explicitly download and hash the pinned M2 BGE-Reranker snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Final, cast

from app.core.config import BGE_RERANKER_MODEL_ID, BGE_RERANKER_REVISION, Settings
from app.services.retrieval.reranker_provider import (
    BGE_RERANKER_REQUIRED_FILES,
    RERANKER_SNAPSHOT_MANIFEST_NAME,
    RERANKER_SNAPSHOT_SCHEMA_VERSION,
    verify_reranker_snapshot,
)

_DOWNLOAD_IGNORE_PATTERNS: Final = (
    "assets/**",
    "*.md",
    ".gitattributes",
    "onnx/**",
    "**/.DS_Store",
)


class RerankerSnapshotError(RuntimeError):
    """A fixed operational failure without URLs, paths, tokens, or raw causes."""


def reranker_snapshot_path(model_cache_root: Path) -> Path:
    """Return the deterministic managed location without network access."""

    return Path(model_cache_root) / "bge-reranker-v2-m3" / BGE_RERANKER_REVISION


def ensure_reranker_snapshot(
    model_cache_root: Path,
    *,
    allow_download: bool,
    downloader: Callable[..., str] | None = None,
) -> Path:
    """Reuse a hash-verified snapshot or explicitly download the pinned commit."""

    target = reranker_snapshot_path(model_cache_root)
    if verify_reranker_snapshot(target):
        return target
    if not allow_download:
        raise RerankerSnapshotError(
            "本地BGE-Reranker固定快照不存在或Hash错误；"
            "只有显式传入--allow-download才允许下载"
        )

    saved_offline = {
        name: os.environ.pop(name, None)
        for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
    }
    try:
        if downloader is None:
            from huggingface_hub import snapshot_download

            downloader = cast(Callable[..., str], snapshot_download)
        downloaded = downloader(
            repo_id=BGE_RERANKER_MODEL_ID,
            revision=BGE_RERANKER_REVISION,
            local_dir=target,
            token=False,
            ignore_patterns=list(_DOWNLOAD_IGNORE_PATTERNS),
            max_workers=1,
        )
    except Exception:  # noqa: BLE001 - network/Hub failures vary.
        raise RerankerSnapshotError("BGE-Reranker固定快照下载失败") from None
    finally:
        for name, value in saved_offline.items():
            if value is not None:
                os.environ[name] = value

    try:
        if Path(downloaded).resolve() != target.resolve() or not target.is_dir():
            raise RerankerSnapshotError("BGE-Reranker固定快照下载结果无效")
        if not all((target / name).is_file() for name in BGE_RERANKER_REQUIRED_FILES):
            raise RerankerSnapshotError("BGE-Reranker固定快照缺少运行文件")
        manifest = {
            "schema_version": RERANKER_SNAPSHOT_SCHEMA_VERSION,
            "model_id": BGE_RERANKER_MODEL_ID,
            "revision": BGE_RERANKER_REVISION,
            "files": _snapshot_files(target),
        }
        manifest_path = target / RERANKER_SNAPSHOT_MANIFEST_NAME
        temporary = manifest_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(manifest_path)
    except RerankerSnapshotError:
        raise
    except OSError:
        raise RerankerSnapshotError("BGE-Reranker快照Hash清单写入失败") from None
    if not verify_reranker_snapshot(target):
        raise RerankerSnapshotError("BGE-Reranker固定快照Hash复核失败")
    return target


def _snapshot_files(target: Path) -> dict[str, dict[str, object]]:
    files: dict[str, dict[str, object]] = {}
    for path in sorted(target.rglob("*")):
        relative = path.relative_to(target)
        if (
            not path.is_file()
            or ".cache" in relative.parts
            or relative.as_posix() == RERANKER_SNAPSHOT_MANIFEST_NAME
        ):
            continue
        size = path.stat().st_size
        if size <= 0:
            raise RerankerSnapshotError("BGE-Reranker固定快照包含空文件")
        files[relative.as_posix()] = {
            "sha256": _sha256_file(path),
            "size_bytes": size,
        }
    if not set(BGE_RERANKER_REQUIRED_FILES).issubset(files):
        raise RerankerSnapshotError("BGE-Reranker固定快照缺少运行文件")
    return files


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-download", action="store_true")
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    try:
        settings = Settings()
        snapshot = ensure_reranker_snapshot(
            settings.model_cache_root,
            allow_download=arguments.allow_download,
        )
    except Exception:  # noqa: BLE001 - CLI never prints raw causes.
        print("M2 Reranker快照准备失败；请检查下载授权、网络和缓存空间")
        return 1
    del snapshot
    print(f"snapshot=data/model-cache/bge-reranker-v2-m3/{BGE_RERANKER_REVISION}")
    print(f"model={BGE_RERANKER_MODEL_ID}@{BGE_RERANKER_REVISION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
