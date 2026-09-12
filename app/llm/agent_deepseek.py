"""DeepSeek Responses API transport for the shared engineered Agent core."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from pydantic import SecretStr, ValidationError

from app.core.errors import (
    AgentProviderOutputError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from app.core.rag_trace import (
    record_answer_output,
    record_answer_schema_error,
    record_answer_transport,
)
from app.llm.agent_structured import (
    OutputT,
    StructuredAgentProvider,
    strict_json_schema,
)


@dataclass(frozen=True, slots=True)
class DeepSeekUsage:
    """Safe token counters from DeepSeek; response bodies are never retained."""

    api_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class DeepSeekAgentProvider(StructuredAgentProvider):
    """Use DeepSeek Responses transport without granting server-side tools."""

    provider_name = "deepseek"
    api_dialect = "responses"

    def __init__(
        self,
        *,
        api_key: SecretStr,
        model: str,
        base_url: str,
        timeout_seconds: float,
        max_output_tokens: int,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.get_secret_value().strip():
            raise ValueError("DeepSeek API key must not be empty")
        parsed = urlsplit(base_url.rstrip("/"))
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "DeepSeek Agent base URL must be a credential-free HTTPS URL"
            )
        if not 1 <= timeout_seconds <= 30:
            raise ValueError("DeepSeek Agent timeout must be 1-30 seconds")
        if not 256 <= max_output_tokens <= 8192:
            raise ValueError("DeepSeek Agent output limit must be 256-8192 tokens")
        self._api_key = api_key
        self._model = model
        self._endpoint = f"{base_url.rstrip('/')}/responses"
        self._timeout_seconds = timeout_seconds
        self._max_output_tokens = max_output_tokens
        self._owns_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient()
        self._last_usage: DeepSeekUsage | None = None
        self._total_usage = DeepSeekUsage()

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def last_usage(self) -> DeepSeekUsage | None:
        return self._last_usage

    @property
    def total_usage(self) -> DeepSeekUsage:
        return self._total_usage

    async def aclose(self) -> None:
        """Close only the HTTP client created by this Provider."""

        if self._owns_client:
            await self._http_client.aclose()

    async def _invoke(
        self,
        *,
        role: str,
        system_prompt: str,
        input_payload: dict[str, object],
        output_type: type[OutputT],
        output_schema: dict[str, object] | None = None,
    ) -> OutputT:
        record_answer_transport(
            role=role,
            provider=self.provider_name,
            model=self._model,
            max_output_tokens=self._max_output_tokens,
            http_status=None,
            usage=None,
        )
        self._last_usage = None
        self._total_usage = DeepSeekUsage(
            api_calls=self._total_usage.api_calls + 1,
            input_tokens=self._total_usage.input_tokens,
            output_tokens=self._total_usage.output_tokens,
            total_tokens=self._total_usage.total_tokens,
        )
        try:
            response = await self._http_client.post(
                self._endpoint,
                headers={
                    "Authorization": f"Bearer {self._api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "instructions": system_prompt,
                    "input": json.dumps(
                        input_payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": f"engineered_agent_{role}",
                            "schema": output_schema or strict_json_schema(output_type),
                        }
                    },
                    "reasoning": {"effort": "none"},
                    "temperature": 0,
                    "stream": False,
                    "max_output_tokens": self._max_output_tokens,
                },
                timeout=self._timeout_seconds,
            )
        except httpx.TimeoutException:
            raise ProviderTimeoutError from None
        except httpx.RequestError:
            raise ProviderUnavailableError from None

        if response.status_code >= 400:
            record_answer_transport(
                role=role,
                provider=self.provider_name,
                model=self._model,
                max_output_tokens=self._max_output_tokens,
                http_status=response.status_code,
                usage=None,
            )
            retryable = (
                response.status_code in (408, 429) or response.status_code >= 500
            )
            raise ProviderUnavailableError(retryable=retryable)

        try:
            payload = response.json()
        except ValueError:
            raise AgentProviderOutputError("provider_envelope") from None

        usage = _parse_usage(payload)
        record_answer_transport(
            role=role,
            provider=self.provider_name,
            model=self._model,
            max_output_tokens=self._max_output_tokens,
            http_status=response.status_code,
            usage=payload.get("usage") if isinstance(payload, dict) else None,
        )
        if usage is not None:
            self._last_usage = usage
            self._total_usage = DeepSeekUsage(
                api_calls=self._total_usage.api_calls,
                input_tokens=self._total_usage.input_tokens + usage.input_tokens,
                output_tokens=self._total_usage.output_tokens + usage.output_tokens,
                total_tokens=self._total_usage.total_tokens + usage.total_tokens,
            )
        try:
            if payload["status"] != "completed":
                raise TypeError
            output = payload["output"]
            if not isinstance(output, list):
                raise TypeError
            messages = [
                item
                for item in output
                if isinstance(item, dict)
                and item.get("type") == "message"
                and item.get("role") == "assistant"
                and item.get("status") == "completed"
            ]
            if len(messages) != 1:
                raise TypeError
            content = messages[0].get("content")
            if not isinstance(content, list):
                raise TypeError
            output_texts = [
                item.get("text")
                for item in content
                if isinstance(item, dict) and item.get("type") == "output_text"
            ]
            if (
                len(output_texts) != 1
                or not isinstance(output_texts[0], str)
                or not output_texts[0].strip()
            ):
                raise TypeError
        except (KeyError, IndexError, TypeError):
            raise AgentProviderOutputError("provider_envelope") from None

        if role == "answer":
            record_answer_output(output_texts[0])
        try:
            decoded = json.loads(output_texts[0])
        except (TypeError, ValueError):
            raise AgentProviderOutputError("model_json") from None
        if not isinstance(decoded, dict):
            raise AgentProviderOutputError("model_json")
        try:
            return output_type.model_validate(decoded)
        except ValidationError as error:
            if role == "answer":
                record_answer_schema_error(error)
            raise AgentProviderOutputError("model_schema") from None


def _parse_usage(payload: object) -> DeepSeekUsage | None:
    if not isinstance(payload, dict):
        return None
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    total_tokens = usage.get("total_tokens")
    if not all(
        isinstance(value, int) and value >= 0
        for value in (input_tokens, output_tokens, total_tokens)
    ):
        return None
    assert isinstance(input_tokens, int)
    assert isinstance(output_tokens, int)
    assert isinstance(total_tokens, int)
    if total_tokens != input_tokens + output_tokens:
        return None
    return DeepSeekUsage(
        api_calls=1,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )
