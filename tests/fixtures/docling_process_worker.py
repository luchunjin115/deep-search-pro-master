"""Spawn-safe fake workers for Docling process-boundary tests."""

from __future__ import annotations

import json
import os
import time
from multiprocessing.connection import Connection
from threading import Thread

_WORKER_RUN_COUNT = 0


def controlled_docling_worker(
    connection: Connection,
    _config: dict[str, object],
    source_name: str,
    source_type: str,
    _content: bytes,
) -> None:
    """Exercise timeout, crash, oversize, and clean-success paths."""

    global _WORKER_RUN_COUNT
    _WORKER_RUN_COUNT += 1
    connection.send_bytes(b"R")
    if source_name == "timeout.pdf" or source_name == "memory.pdf":
        time.sleep(30)
        return
    if source_name == "crash.pdf":
        os._exit(17)
    if source_name == "oversized.pdf":
        connection.send_bytes(b"S" + (b"x" * 4096))
        return

    if source_name in {"lingering.pdf", "hard-exit-lingering.pdf"}:
        Thread(target=time.sleep, args=(30,), daemon=False).start()
    if source_name == "hard-exit-lingering.pdf":
        from app.services.documents.parsers.docling import _exit_docling_worker

    snapshot = {
        "source_type": source_type,
        "parser_name": "docling",
        "parser_version": "fake-spawn-worker-v1",
        "page_count": 1,
        "items": [
            {
                "kind": "text",
                "text": f"pid={os.getpid()};run_count={_WORKER_RUN_COUNT}",
                "label": "text",
                "page_number": 1,
            }
        ],
        "warning_codes": [],
    }
    connection.send_bytes(b"S" + json.dumps(snapshot).encode("utf-8"))
    if source_name == "hard-exit-lingering.pdf":
        _exit_docling_worker(connection, exit_code=0)
