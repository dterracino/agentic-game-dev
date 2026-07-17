from __future__ import annotations

import unittest
from types import SimpleNamespace

from agentic_game_dev.provider import AgentError, ClaudeProvider


class FakeAPIError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class FakeStreamManager:
    def __init__(
        self,
        *,
        response: object | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error

    async def __aenter__(self) -> "FakeStreamManager":
        if self.error is not None:
            raise self.error
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get_final_message(self) -> object:
        return self.response


class FailingMessages:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def stream(self, **kwargs: object) -> FakeStreamManager:
        return FakeStreamManager(error=self.error)


class SequencedMessages:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls = 0

    def stream(self, **kwargs: object) -> FakeStreamManager:
        outcome = self.outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            return FakeStreamManager(error=outcome)
        return FakeStreamManager(response=outcome)


class ResponseMessages:
    def __init__(self, response: object) -> None:
        self.response = response
        self.kwargs: dict[str, object] = {}

    def stream(self, **kwargs: object) -> FakeStreamManager:
        self.kwargs = kwargs
        return FakeStreamManager(response=self.response)


class FakeClient:
    def __init__(self, messages: object) -> None:
        self.messages = messages


def provider_with_messages(messages: object) -> ClaudeProvider:
    provider = ClaudeProvider.__new__(ClaudeProvider)
    provider.model = "claude-sonnet-5"
    provider.max_tokens = 32768
    provider.effort = "medium"
    provider.max_retries = 3
    provider.retry_delay = 0
    provider.progress = lambda _message: None
    provider._api_error_type = FakeAPIError
    provider._client = FakeClient(messages)
    return provider


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_not_found_has_actionable_error(self) -> None:
        provider = provider_with_messages(FailingMessages(FakeAPIError(404, "not found")))
        provider.model = "retired-model"

        with self.assertRaisesRegex(
            AgentError,
            "ANTHROPIC_MODEL=claude-sonnet-5",
        ):
            await provider._create_message(model=provider.model)

    async def test_other_api_errors_are_wrapped(self) -> None:
        provider = provider_with_messages(FailingMessages(FakeAPIError(401, "invalid key")))

        with self.assertRaisesRegex(AgentError, "401.*invalid key"):
            await provider._create_message(model=provider.model)

    async def test_streaming_overload_retries_then_succeeds(self) -> None:
        response = SimpleNamespace(
            content=[SimpleNamespace(type="text", text="recovered")],
            stop_reason="end_turn",
            usage=SimpleNamespace(output_tokens=10),
        )
        messages = SequencedMessages(
            [
                FakeAPIError(200, "{'type': 'overloaded_error', 'message': 'Overloaded'}"),
                FakeAPIError(529, "temporarily unavailable"),
                response,
            ]
        )
        provider = provider_with_messages(messages)
        progress: list[str] = []
        provider.progress = progress.append

        result = await provider.text(role="role", prompt="prompt")

        self.assertEqual(result, "recovered")
        self.assertEqual(messages.calls, 3)
        self.assertEqual(len(progress), 2)

    async def test_sonnet_5_uses_medium_adaptive_thinking_with_headroom(self) -> None:
        messages = ResponseMessages(
            SimpleNamespace(
                content=[SimpleNamespace(type="text", text="proposal")],
                stop_reason="end_turn",
                usage=SimpleNamespace(output_tokens=10),
            )
        )
        provider = provider_with_messages(messages)

        result = await provider.text(role="role", prompt="prompt")

        self.assertEqual(result, "proposal")
        self.assertEqual(messages.kwargs["max_tokens"], 32768)
        self.assertEqual(messages.kwargs["thinking"], {"type": "adaptive"})
        self.assertEqual(messages.kwargs["output_config"], {"effort": "medium"})

    async def test_thinking_only_truncation_reports_stop_reason(self) -> None:
        messages = ResponseMessages(
            SimpleNamespace(
                content=[SimpleNamespace(type="thinking", thinking="summary")],
                stop_reason="max_tokens",
                usage=SimpleNamespace(output_tokens=8192),
            )
        )
        provider = provider_with_messages(messages)

        with self.assertRaisesRegex(
            AgentError,
            "exhausted.*stop_reason=max_tokens.*thinking.*output_tokens=8192",
        ):
            await provider.text(role="role", prompt="prompt")


if __name__ == "__main__":
    unittest.main()
