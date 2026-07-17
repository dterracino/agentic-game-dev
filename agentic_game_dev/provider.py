from __future__ import annotations

from typing import Any


class AgentError(RuntimeError):
    pass


class ClaudeProvider:
    """Small adapter that keeps Anthropic-specific parsing out of orchestration."""

    def __init__(self, model: str, max_tokens: int = 8192) -> None:
        try:
            from anthropic import APIError, AsyncAnthropic
        except ImportError as exc:
            raise AgentError(
                "The Anthropic SDK is not installed. Run: python -m pip install -e ."
            ) from exc
        self.model = model
        self.max_tokens = max_tokens
        self._api_error_type = APIError
        self._client = AsyncAnthropic()

    async def _create_message(self, **kwargs: Any) -> Any:
        try:
            return await self._client.messages.create(**kwargs)
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

    async def text(self, *, role: str, prompt: str) -> str:
        response = await self._create_message(
            model=self.model,
            max_tokens=self.max_tokens,
            system=role,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        ).strip()
        if not text:
            raise AgentError("Agent returned no text")
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
        )
        for block in response.content:
            if getattr(block, "type", "") == "tool_use" and block.name == tool_name:
                return dict(block.input)
        raise AgentError(f"Agent did not call required tool {tool_name!r}")
