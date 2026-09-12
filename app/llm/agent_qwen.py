"""Qwen Chat Completions transport for the shared engineered Agent core."""

from __future__ import annotations

import json
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


class QwenAgentProvider(StructuredAgentProvider):
    """Use Qwen transport without changing shared roles or safety validation."""

    provider_name = "qwen"
    api_dialect = "chat_completions"

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
            raise ValueError("Qwen API key must not be empty")
        parsed = urlsplit(base_url.rstrip("/"))
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Qwen Agent base URL must be a credential-free HTTPS URL")
        if not 1 <= timeout_seconds <= 30:
            raise ValueError("Qwen Agent timeout must be 1-30 seconds")
        if not 256 <= max_output_tokens <= 8192:
            raise ValueError("Qwen Agent output limit must be 256-8192 tokens")
        self._api_key = api_key
        self._model = model
        self._endpoint = f"{base_url.rstrip('/')}/chat/completions"
        self._timeout_seconds = timeout_seconds
        self._max_output_tokens = max_output_tokens
        self._owns_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient()

    @property
    def model_name(self) -> str:
        return self._model

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
        try:
            response = await self._http_client.post(
                self._endpoint,
                headers={
                    "Authorization": f"Bearer {self._api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": json.dumps(
                                input_payload,
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                        },
                    ],
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": f"engineered_agent_{role}",
                            "strict": True,
                            "schema": output_schema or strict_json_schema(output_type),
                        },
                    },
                    "temperature": 0,
                    "stream": False,
                    "enable_search": False,
                    "enable_thinking": False,
                    "max_tokens": self._max_output_tokens,
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
        record_answer_transport(
            role=role,
            provider=self.provider_name,
            model=self._model,
            max_output_tokens=self._max_output_tokens,
            http_status=response.status_code,
            usage=payload.get("usage") if isinstance(payload, dict) else None,
        )
        try:
            choices = payload["choices"]
            if not isinstance(choices, list) or len(choices) != 1:
                raise TypeError
            content = choices[0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise TypeError
        except (KeyError, IndexError, TypeError):
            raise AgentProviderOutputError("provider_envelope") from None
        if role == "answer":
            record_answer_output(content)
        try:
            decoded = json.loads(content)
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
