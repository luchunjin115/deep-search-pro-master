"""Run the public M1 inventory demo without exposing credentials or tokens."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values
from pydantic import BaseModel, ValidationError

from app.schemas.auth import CurrentUser, LoginResponse
from app.schemas.chat import ChatSuccessResponse, ThreadResponse
from app.schemas.common import ApiErrorResponse
from app.schemas.evidence import EvidenceDetail
from app.schemas.inventory import InventoryResult

DE_EMAIL = "de.operator@demo.deepsearch.local"
FR_EMAIL = "fr.operator@demo.deepsearch.local"
QUESTION = "德国仓蘑菇灯还有多少可售库存？"
EXPECTED_SKU = "LR-TL-MUSH-OR01"
EXPECTED_WAREHOUSE = "DE-FRA"
EXPECTED_AVAILABLE = 125
SchemaT = TypeVar("SchemaT", bound=BaseModel)


class DemoVerificationError(RuntimeError):
    """A credential-safe explanation that the public demo contract was not met."""


@dataclass(frozen=True, slots=True)
class DemoResult:
    """Small, safe summary suitable for terminal output and a live presentation."""

    service: str
    de_answer: str
    sku: str
    warehouse_code: str
    available: int
    evidence_source: str
    forbidden_code: str

    def lines(self) -> tuple[str, ...]:
        return (
            "M1 public API demo passed.",
            f"Health: {self.service} / database connected",
            f"DE answer: {self.de_answer}",
            (
                "Evidence: "
                f"{self.sku} / {self.warehouse_code} / available {self.available}"
            ),
            f"Evidence source: {self.evidence_source}",
            f"FR-to-DE permission check: {self.forbidden_code} (expected)",
            "Data notice: synthetic demo data only.",
        )


def normalize_server_url(value: str) -> str:
    """Accept one credential-free HTTP(S) server origin."""

    normalized = value.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise DemoVerificationError(
            "--server-url must be a credential-free HTTP(S) origin, "
            "for example http://127.0.0.1:8000"
        )
    return normalized


def load_demo_password(env_file: Path = Path(".env")) -> str:
    """Read the local demo password without printing or returning other secrets."""

    configured = os.getenv("M1_DEMO_PASSWORD")
    if configured is None and env_file.is_file():
        candidate = dotenv_values(env_file).get("M1_DEMO_PASSWORD")
        configured = candidate if isinstance(candidate, str) else None
    password = configured.strip() if configured is not None else ""
    if len(password) < 8:
        raise DemoVerificationError(
            "M1_DEMO_PASSWORD is missing or too short; check the local .env file"
        )
    return password


def _parse_success(
    response: httpx.Response,
    expected_status: int,
    schema: type[SchemaT],
    operation: str,
) -> SchemaT:
    if response.status_code != expected_status:
        raise DemoVerificationError(
            f"{operation} expected HTTP {expected_status}, got {response.status_code}"
        )
    try:
        return schema.model_validate(response.json())
    except (ValueError, ValidationError) as error:
        raise DemoVerificationError(
            f"{operation} returned a response outside the M1 schema"
        ) from error


def _login(client: httpx.Client, email: str, password: str) -> LoginResponse:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    return _parse_success(response, 200, LoginResponse, f"login for {email}")


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_thread(
    client: httpx.Client,
    token: str,
    title: str,
) -> ThreadResponse:
    response = client.post(
        "/api/v1/threads",
        headers=_bearer(token),
        json={"title": title},
    )
    return _parse_success(response, 201, ThreadResponse, "create demo thread")


def run_demo(client: httpx.Client, password: str) -> DemoResult:
    """Exercise health, success, Evidence, and denial through public HTTP APIs."""

    health = client.get("/health")
    if health.status_code != 200:
        raise DemoVerificationError(
            f"health check expected HTTP 200, got {health.status_code}"
        )
    try:
        health_payload = health.json()
    except ValueError as error:
        raise DemoVerificationError("health check did not return JSON") from error
    if health_payload.get("database") != "connected":
        raise DemoVerificationError("health check did not report database connected")
    service = health_payload.get("service")
    if not isinstance(service, str) or not service:
        raise DemoVerificationError("health check did not identify the M1 service")

    de_login = _login(client, DE_EMAIL, password)
    me_response = client.get("/api/v1/me", headers=_bearer(de_login.access_token))
    current_user = _parse_success(me_response, 200, CurrentUser, "read DE identity")
    if current_user.email != DE_EMAIL or current_user.market_scopes != ["DE"]:
        raise DemoVerificationError("DE demo account returned an unexpected data scope")

    de_thread = _create_thread(client, de_login.access_token, "M1-21 Demo DE")
    chat_response = client.post(
        f"/api/v1/threads/{de_thread.thread_id}/messages",
        headers=_bearer(de_login.access_token),
        json={"message": QUESTION},
    )
    chat = _parse_success(chat_response, 200, ChatSuccessResponse, "DE inventory query")
    if len(chat.evidence) != 1:
        raise DemoVerificationError(
            "DE inventory query did not return one Evidence item"
        )

    evidence_response = client.get(
        f"/api/v1/evidence/{chat.evidence[0].id}",
        headers=_bearer(de_login.access_token),
    )
    evidence = _parse_success(
        evidence_response,
        200,
        EvidenceDetail,
        "read inventory Evidence",
    )
    inventory = evidence.structured_data
    if not isinstance(inventory, InventoryResult):
        raise DemoVerificationError("Evidence did not contain an inventory result")
    if (
        inventory.sku != EXPECTED_SKU
        or inventory.warehouse_code != EXPECTED_WAREHOUSE
        or inventory.available != EXPECTED_AVAILABLE
    ):
        raise DemoVerificationError("Evidence did not match the fixed M1 demo fact")

    fr_login = _login(client, FR_EMAIL, password)
    fr_thread = _create_thread(client, fr_login.access_token, "M1-21 Demo FR denial")
    forbidden_response = client.post(
        f"/api/v1/threads/{fr_thread.thread_id}/messages",
        headers=_bearer(fr_login.access_token),
        json={"message": QUESTION},
    )
    forbidden = _parse_success(
        forbidden_response,
        403,
        ApiErrorResponse,
        "FR-to-DE permission check",
    )
    if forbidden.error.code != "FORBIDDEN":
        raise DemoVerificationError("FR-to-DE query was not rejected as FORBIDDEN")
    if str(EXPECTED_AVAILABLE) in forbidden_response.text:
        raise DemoVerificationError("permission error leaked the DE inventory answer")

    return DemoResult(
        service=service,
        de_answer=chat.answer,
        sku=inventory.sku,
        warehouse_code=inventory.warehouse_code,
        available=inventory.available,
        evidence_source=evidence.source_locator,
        forbidden_code=forbidden.error.code,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify the complete M1 public inventory-query demo.",
    )
    parser.add_argument(
        "--server-url",
        default="http://127.0.0.1:8000",
        help="FastAPI server origin without /api/v1 (default: %(default)s)",
    )
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    try:
        server_url = normalize_server_url(arguments.server_url)
        password = load_demo_password()
        with httpx.Client(
            base_url=server_url,
            timeout=20.0,
            trust_env=False,
        ) as client:
            result = run_demo(client, password)
    except (DemoVerificationError, httpx.HTTPError) as error:
        print(f"M1 public API demo failed: {error}")
        return 1

    for line in result.lines():
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
