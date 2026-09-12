"""Provider-neutral RAG review evidence; unbound in ordinary user requests.

This is a private diagnostic copy, never a Provider input or a public report.
Text is untrusted business content. Redaction is conservative, not a DLP guarantee.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from time import perf_counter
from typing import Literal

from pydantic import ValidationError

from app.core.errors import AgentProviderOutputError, ProviderTimeoutError
from app.schemas.common import M1Schema

_PRIVATE_KEYS = frozenset(
    {
        "authorization",
        "api_key",
        "password",
        "secret",
        "tenant_id",
        "user_id",
        "owner_user_id",
        "acl",
        "roles",
        "market_scopes",
        "storage_key",
        "path",
        "local_path",
        "sql",
        "exception",
        "stack",
        "reasoning",
        "reasoning_content",
        "trusted_user_fixture_id",
        "acl_fixture_id",
        "version_fixture_id",
    }
)
_SENSITIVE = re.compile(
    r"(?i)(?:\bsk-[\w-]+|\bBearer\s+\S+|[A-Z]:[\\/]|"
    r"/(?:home|Users|tmp|etc|var)/|\b(?:SELECT\s+.+?\s+FROM|INSERT\s+INTO|DELETE\s+FROM)\b|"
    r"[\"']?(?:tenant_id|user_id|api_key|password|authorization|reasoning_content|acl)[\"']?\s*[:=])"
)


def review_value(value: object) -> object:
    """Drop private keys and visibly suppress suspicious text, without exceptions."""
    if isinstance(value, dict):
        return {
            key: review_value(item)
            for key, item in value.items()
            if isinstance(key, str) and key.lower() not in _PRIVATE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [review_value(item) for item in value]
    if isinstance(value, str) and _SENSITIVE.search(value):
        return "[REDACTED]"
    return value


@dataclass(slots=True)
class RagReviewTrace:
    """None means not captured; an empty results list means observed empty."""

    retrieval: dict[str, object] | None = None
    reranked: dict[str, object] | None = None
    context: dict[str, object] | None = None
    resource_usage: dict[str, object] | None = None
    answer_attempts: list[dict[str, object]] = field(default_factory=list)


_ACTIVE_REVIEW: ContextVar[RagReviewTrace | None] = ContextVar(
    "rag_review", default=None
)
_ACTIVE_ATTEMPT: ContextVar[dict[str, object] | None] = ContextVar(
    "rag_answer_attempt", default=None
)


@contextmanager
def rag_review_trace(trace: RagReviewTrace) -> Iterator[None]:
    token = _ACTIVE_REVIEW.set(trace)
    try:
        yield
    finally:
        _ACTIVE_REVIEW.reset(token)


def record_rag_stage(
    stage: Literal["retrieval", "reranked", "context", "resource_usage"],
    value: M1Schema,
) -> None:
    trace = _ACTIVE_REVIEW.get()
    if trace is not None:
        setattr(trace, stage, value.model_dump(mode="json"))


@contextmanager
def answer_review_attempt(
    prompt: str,
    payload: dict[str, object],
    schema: dict[str, object],
) -> Iterator[None]:
    trace = _ACTIVE_REVIEW.get()
    if trace is None:
        yield
        return
    attempt: dict[str, object] = {
        "attempt": len(trace.answer_attempts) + 1,
        "system_prompt": prompt,
        "input_payload": copy.deepcopy(payload),
        "output_schema": copy.deepcopy(schema),
        "validation_stage": None,
        "validation_reason": None,
        "model_output_text": None,
        "model_output_sha256": None,
        "schema_issues": [],
        "transport": None,
    }
    trace.answer_attempts.append(attempt)
    token = _ACTIVE_ATTEMPT.set(attempt)
    started = perf_counter()
    try:
        yield
        attempt["validation_stage"] = "completed"
    except AgentProviderOutputError as error:
        attempt["validation_stage"] = error.stage
        raise
    except Exception as error:
        attempt["validation_stage"] = (
            "provider_timeout"
            if isinstance(error, ProviderTimeoutError)
            else "execution_error"
        )
        raise
    finally:
        attempt["duration_ms"] = round((perf_counter() - started) * 1000)
        _ACTIVE_ATTEMPT.reset(token)


def record_answer_output(text: str) -> None:
    attempt = _ACTIVE_ATTEMPT.get()
    if attempt is not None:
        attempt["model_output_sha256"] = hashlib.sha256(text.encode()).hexdigest()
        # Never retain arbitrary model-added JSON fields (including reasoning).
        try:
            decoded = json.loads(text)
        except ValueError:
            decoded = None
        if isinstance(decoded, dict) and isinstance(decoded.get("action"), dict):
            projected = {
                "action": {
                    key: value
                    for key, value in decoded["action"].items()
                    if key
                    in {
                        "type",
                        "public_summary",
                        "business_outcome",
                        "citation_labels",
                        "artifact_ids",
                    }
                }
            }
            retained = (
                text
                if projected == decoded
                else json.dumps(projected, ensure_ascii=False)
            )
        elif isinstance(decoded, dict):
            retained = "{}"
        else:
            retained = text
        attempt["model_output_text"] = review_value(retained)
        attempt["model_output_redacted"] = attempt["model_output_text"] != text


def record_answer_schema_error(error: ValidationError) -> None:
    attempt = _ACTIVE_ATTEMPT.get()
    if attempt is not None:
        allowed = {
            "action",
            "finish",
            "cannot_complete",
            "type",
            "public_summary",
            "business_outcome",
            "citation_labels",
            "artifact_ids",
        }
        attempt["schema_issues"] = [
            {
                "type": item["type"],
                "location": [
                    part if isinstance(part, int) or part in allowed else "<field>"
                    for part in item["loc"]
                ],
            }
            for item in error.errors(
                include_input=False, include_context=False, include_url=False
            )
        ]


def record_answer_reason(
    reason: Literal[
        "unknown_label",
        "malformed_label",
        "repeated_label",
        "refusal_with_citation",
        "missing_citation",
        "citation_order_or_set_mismatch",
        "action_schema",
    ],
) -> None:
    attempt = _ACTIVE_ATTEMPT.get()
    if attempt is not None:
        attempt["validation_reason"] = reason


def record_answer_transport(
    *,
    role: str,
    provider: str,
    model: str,
    max_output_tokens: int,
    http_status: int | None,
    usage: object,
) -> None:
    attempt = _ACTIVE_ATTEMPT.get()
    if role != "answer" or attempt is None:
        return
    token_usage = usage if isinstance(usage, dict) else {}
    attempt["transport"] = {
        "provider": provider,
        "model": model,
        "temperature": 0,
        "thinking": False,
        "max_output_tokens": max_output_tokens,
        "http_status": http_status,
        "usage": {
            key: value
            for key, value in token_usage.items()
            if key
            in {
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "prompt_tokens",
                "completion_tokens",
            }
            and type(value) is int
            and value >= 0
        },
    }
