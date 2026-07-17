from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from .activity import TerminalActivity

ADAPTIVE_MODEL_PREFIXES = (
    "claude-sonnet-5",
    "claude-sonnet-4-6",
    "claude-opus-4-",
    "claude-fable-5",
    "claude-mythos-5",
)


class AgentError(RuntimeError):
    pass


class ClaudeProvider:
    """Small adapter that keeps Anthropic-specific parsing out of orchestration."""

    provider_name = "anthropic"

    def __init__(
        self,
        model: str,
        max_tokens: int = 32768,
        effort: str = "medium",
        max_retries: int = 3,
        retry_delay: float = 2.0,
        progress: Callable[[str], None] = print,
        activity: TerminalActivity | None = None,
    ) -> None:
        try:
            from anthropic import APIError, AsyncAnthropic
        except ImportError as exc:
            raise AgentError(
                "The Anthropic SDK is not installed. Run: python -m pip install -e ."
            ) from exc
        self.model = model
        self.max_tokens = max_tokens
        self.effort = effort
        self.max_retries = max(0, max_retries)
        self.retry_delay = max(0.0, retry_delay)
        self.progress = progress
        self.activity = activity
        self._api_error_type = APIError
        self._client = AsyncAnthropic()

    async def _create_message(self, **kwargs: Any) -> Any:
        async with self._activity("Waiting for Anthropic"):
            for attempt in range(self.max_retries + 1):
                try:
                    async with self._client.messages.stream(**kwargs) as stream:
                        return await stream.get_final_message()
                except self._api_error_type as exc:
                    if self._is_transient(exc) and attempt < self.max_retries:
                        delay = self.retry_delay * (2**attempt)
                        self.progress(
                            f"  Anthropic is temporarily unavailable; retrying in {delay:g}s "
                            f"({attempt + 1}/{self.max_retries})..."
                        )
                        await asyncio.sleep(delay)
                        continue
                    self._raise_api_error(exc)
        raise AgentError("Anthropic request exhausted its retry budget")

    def _raise_api_error(self, exc: BaseException) -> None:
        status = getattr(exc, "status_code", None)
        if status == 404:
            raise AgentError(
                f"Anthropic could not find model {self.model!r}. "
                "Set ANTHROPIC_MODEL=claude-sonnet-5 in .env, "
                "or choose another model available to your account with --model."
            ) from exc
        detail = getattr(exc, "message", None) or str(exc)
        status_text = f" ({status})" if status is not None else ""
        raise AgentError(f"Anthropic API request failed{status_text}: {detail}") from exc

    @staticmethod
    def _is_transient(exc: BaseException) -> bool:
        status = getattr(exc, "status_code", None)
        detail = str(getattr(exc, "message", None) or exc).lower()
        return status in {408, 429, 500, 502, 503, 504, 529} or any(
            marker in detail
            for marker in ("overloaded_error", "overloaded", "temporarily unavailable")
        )

    def _generation_options(self) -> dict[str, Any]:
        if self.model.startswith(ADAPTIVE_MODEL_PREFIXES):
            return {
                "thinking": {"type": "adaptive"},
                "output_config": {"effort": self.effort},
            }
        return {}

    async def text(self, *, role: str, prompt: str) -> str:
        response = await self._create_message(
            model=self.model,
            max_tokens=self.max_tokens,
            system=role,
            messages=[{"role": "user", "content": prompt}],
            **self._generation_options(),
        )
        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        ).strip()
        if not text:
            raise AgentError(self._empty_response_message(response, "text"))
        return text

    async def structured(
        self,
        *,
        role: str,
        prompt: str,
        tool_name: str,
        description: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        response = await self._create_message(
            model=self.model,
            max_tokens=self.max_tokens,
            system=role,
            messages=[{"role": "user", "content": prompt}],
            tools=[{
                "name": tool_name,
                "description": description,
                "input_schema": schema,
            }],
            tool_choice={"type": "tool", "name": tool_name},
            **self._generation_options(),
        )
        for block in response.content:
            if getattr(block, "type", "") == "tool_use" and block.name == tool_name:
                return dict(block.input)
        raise AgentError(self._empty_response_message(response, f"tool call {tool_name!r}"))

    def _empty_response_message(self, response: Any, expected: str) -> str:
        stop_reason = getattr(response, "stop_reason", None) or "unknown"
        block_types = [
            str(getattr(block, "type", type(block).__name__))
            for block in getattr(response, "content", [])
        ]
        usage = getattr(response, "usage", None)
        output_tokens = getattr(usage, "output_tokens", None)
        details = (
            f"stop_reason={stop_reason}, content={block_types or ['empty']}, "
            f"output_tokens={output_tokens if output_tokens is not None else 'unknown'}"
        )
        if stop_reason == "max_tokens":
            return (
                f"Agent exhausted the {self.max_tokens}-token output budget before producing "
                f"{expected} ({details}). The failed task is checkpointed and can be resumed."
            )
        if stop_reason == "refusal":
            return f"Agent refused to produce {expected} ({details})"
        return f"Agent did not produce {expected} ({details})"

    @asynccontextmanager
    async def _activity(self, label: str) -> AsyncIterator[None]:
        activity = getattr(self, "activity", None)
        if activity is None:
            yield
            return
        async with activity.track(label):
            yield


class OllamaProvider:
    """Provider adapter for an Ollama server on this machine or the local network."""

    provider_name = "ollama"

    def __init__(
        self,
        model: str,
        *,
        host: str = "http://localhost:11434",
        max_tokens: int = 32768,
        activity: TerminalActivity | None = None,
    ) -> None:
        try:
            from ollama import AsyncClient, RequestError, ResponseError
        except ImportError as exc:
            raise AgentError(
                "The Ollama SDK is not installed. Run: python -m pip install -e ."
            ) from exc
        self.model = model
        self.host = host
        self.max_tokens = max_tokens
        self.activity = activity
        self._response_error_type = ResponseError
        self._request_error_type = RequestError
        self._client = AsyncClient(host=host)

    async def text(self, *, role: str, prompt: str) -> str:
        response = await self._chat(role=role, prompt=prompt)
        text = self._message_content(response).strip()
        if not text:
            raise AgentError("Ollama agent returned no text")
        return text

    async def structured(
        self,
        *,
        role: str,
        prompt: str,
        tool_name: str,
        description: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        structured_prompt = (
            f"{prompt}\n\nReturn only JSON for {tool_name}: {description}. "
            "The response must satisfy the supplied JSON schema."
        )
        response = await self._chat(
            role=role,
            prompt=structured_prompt,
            format_schema=schema,
        )
        content = self._message_content(response).strip()
        try:
            value = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AgentError(f"Ollama returned invalid JSON for {tool_name}: {exc}") from exc
        if not isinstance(value, dict):
            raise AgentError(f"Ollama returned a non-object response for {tool_name}")
        return value

    async def _chat(
        self,
        *,
        role: str,
        prompt: str,
        format_schema: dict[str, Any] | None = None,
    ) -> Any:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": role},
                {"role": "user", "content": prompt},
            ],
            "options": {"num_predict": self.max_tokens},
        }
        if format_schema is not None:
            kwargs["format"] = format_schema
        try:
            async with self._activity("Waiting for Ollama"):
                return await self._client.chat(**kwargs)
        except self._response_error_type as exc:
            status = getattr(exc, "status_code", None)
            detail = getattr(exc, "error", None) or str(exc)
            suffix = f" ({status})" if status is not None else ""
            raise AgentError(
                f"Ollama request failed{suffix} for {self.host} using {self.model!r}: {detail}"
            ) from exc
        except (self._request_error_type, OSError) as exc:
            raise AgentError(f"Cannot reach Ollama at {self.host}: {exc}") from exc

    @staticmethod
    def _message_content(response: Any) -> str:
        message = getattr(response, "message", None)
        if message is not None:
            content = getattr(message, "content", None)
            if content is not None:
                return str(content)
        if isinstance(response, dict):
            return str(response.get("message", {}).get("content", ""))
        return ""

    @asynccontextmanager
    async def _activity(self, label: str) -> AsyncIterator[None]:
        if self.activity is None:
            yield
            return
        async with self.activity.track(label):
            yield
