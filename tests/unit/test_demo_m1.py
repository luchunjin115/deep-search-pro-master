from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from scripts.demo_m1 import (
    DemoVerificationError,
    load_demo_password,
    normalize_server_url,
    run_demo,
)

TENANT_ID = "10000000-0000-0000-0000-000000000001"
DE_USER_ID = "20000000-0000-0000-0000-000000000003"
FR_USER_ID = "20000000-0000-0000-0000-000000000004"
DE_THREAD_ID = "70000000-0000-0000-0000-000000000001"
FR_THREAD_ID = "70000000-0000-0000-0000-000000000002"
MESSAGE_ID = "71000000-0000-0000-0000-000000000001"
EVIDENCE_ID = "72000000-0000-0000-0000-000000000001"
TRACE_ID = "73000000-0000-0000-0000-000000000001"
SNAPSHOT_ID = "50000000-0000-0000-0000-000000000001"
NOW = datetime(2026, 8, 28, 6, tzinfo=UTC).isoformat()
PASSWORD = "safe-demo-password"


def user_payload(email: str) -> dict[str, object]:
    is_de = email.startswith("de.")
    return {
        "user_id": DE_USER_ID if is_de else FR_USER_ID,
        "tenant_id": TENANT_ID,
        "email": email,
        "display_name": "演示德国运营" if is_de else "演示法国运营",
        "roles": ["amazon_operator"],
        "market_scopes": ["DE" if is_de else "FR"],
        "synthetic_data": True,
    }


def test_public_demo_uses_only_http_contracts_and_returns_safe_summary() -> None:
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        body = json.loads(request.content) if request.content else {}
        if request.url.path == "/health":
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "service": "Deep Search Pro M1",
                    "environment": "test",
                    "database": "connected",
                },
            )
        if request.url.path == "/api/v1/auth/login":
            assert body["password"] == PASSWORD
            email = body["email"]
            return httpx.Response(
                200,
                json={
                    "access_token": f"demo-token-for-{email}",
                    "token_type": "bearer",
                    "expires_in_seconds": 3600,
                    "user": user_payload(email),
                },
            )
        authorization = request.headers.get("Authorization", "")
        is_de = "de.operator" in authorization
        if request.url.path == "/api/v1/me":
            return httpx.Response(
                200,
                json=user_payload("de.operator@demo.deepsearch.local"),
            )
        if request.url.path == "/api/v1/threads":
            return httpx.Response(
                201,
                json={
                    "thread_id": DE_THREAD_ID if is_de else FR_THREAD_ID,
                    "title": body["title"],
                    "status": "active",
                    "created_at": NOW,
                },
            )
        if request.url.path == f"/api/v1/threads/{DE_THREAD_ID}/messages":
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "thread_id": DE_THREAD_ID,
                    "message_id": MESSAGE_ID,
                    "answer": "德国市场DE-FRA仓的可售库存为125件（合成演示数据）。",
                    "evidence": [
                        {
                            "id": EVIDENCE_ID,
                            "source_type": "database",
                            "source_name": "synthetic_inventory",
                            "title": "DE-FRA库存快照",
                            "excerpt": "可售库存125件",
                            "observed_at": NOW,
                            "synthetic_data": True,
                        }
                    ],
                    "execution": {
                        "trace_id": TRACE_ID,
                        "route": "inventory_query",
                        "tool_names": ["get_product_spec", "search_inventory"],
                        "duration_ms": 12,
                        "status": "completed",
                    },
                },
            )
        if request.url.path == f"/api/v1/evidence/{EVIDENCE_ID}":
            return httpx.Response(
                200,
                json={
                    "id": EVIDENCE_ID,
                    "source_type": "database",
                    "source_name": "synthetic_inventory",
                    "title": "DE-FRA库存快照",
                    "excerpt": "可售库存125件",
                    "observed_at": NOW,
                    "synthetic_data": True,
                    "source_locator": f"inventory_snapshots/{SNAPSHOT_ID}",
                    "query_summary": {
                        "sku": "LR-TL-MUSH-OR01",
                        "market_code": "DE",
                        "warehouse_code": "DE-FRA",
                    },
                    "structured_data": {
                        "sku": "LR-TL-MUSH-OR01",
                        "product_name": "蘑菇灯",
                        "market_code": "DE",
                        "warehouse_code": "DE-FRA",
                        "warehouse_name": "德国法兰克福演示仓",
                        "on_hand": 150,
                        "reserved": 20,
                        "unsellable": 5,
                        "inbound": 30,
                        "safety_stock": 25,
                        "available": 125,
                        "snapshot_at": NOW,
                        "synthetic_data": True,
                    },
                    "confidence": "1.000",
                    "trust_level": "internal_demo",
                    "access_scope": {
                        "tenant_id": TENANT_ID,
                        "market_codes": ["DE"],
                    },
                    "created_at": NOW,
                },
            )
        if request.url.path == f"/api/v1/threads/{FR_THREAD_ID}/messages":
            return httpx.Response(
                403,
                json={
                    "status": "error",
                    "error": {
                        "code": "FORBIDDEN",
                        "message": "当前账号无权访问该市场数据",
                        "retryable": False,
                        "field": None,
                    },
                    "trace_id": str(UUID(int=UUID(TRACE_ID).int + 1)),
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    with httpx.Client(
        base_url="http://m1.test",
        transport=httpx.MockTransport(handler),
    ) as client:
        result = run_demo(client, PASSWORD)

    summary = "\n".join(result.lines())
    assert result.available == 125
    assert result.forbidden_code == "FORBIDDEN"
    assert PASSWORD not in summary
    assert "demo-token" not in summary
    assert seen_paths == [
        "/health",
        "/api/v1/auth/login",
        "/api/v1/me",
        "/api/v1/threads",
        f"/api/v1/threads/{DE_THREAD_ID}/messages",
        f"/api/v1/evidence/{EVIDENCE_ID}",
        "/api/v1/auth/login",
        "/api/v1/threads",
        f"/api/v1/threads/{FR_THREAD_ID}/messages",
    ]


def test_demo_rejects_credentialed_or_versioned_server_urls() -> None:
    assert normalize_server_url("http://127.0.0.1:8000/") == "http://127.0.0.1:8000"
    with pytest.raises(DemoVerificationError, match="credential-free"):
        normalize_server_url("http://user:secret@127.0.0.1:8000")
    with pytest.raises(DemoVerificationError, match="credential-free"):
        normalize_server_url("http://127.0.0.1:8000/api/v1")


def test_demo_password_loader_reads_only_the_named_local_value(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "M1_DEMO_PASSWORD=from-local-file\nQWEN_API_KEY=fake\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("M1_DEMO_PASSWORD", raising=False)

    assert load_demo_password(env_file) == "from-local-file"
