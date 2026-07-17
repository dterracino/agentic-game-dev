from __future__ import annotations

from typing import Any


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

    def __init__(
        self,
        model: str,
        max_tokens: int = 32768,
        effort: str = "medium",
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
        self._api_error_type = APIError
        self._client = AsyncAnthropic()

    async def _create_message(self, **kwargs: Any) -> Any:
        try:
            async with self._client.messages.stream(**kwargs) as stream:
                return await stream.get_final_message()
        except self._api_error_type as exc:
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
