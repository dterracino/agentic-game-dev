from __future__ import annotations

import unittest

from agentic_game_dev.provider import AgentError, ClaudeProvider


class FakeAPIError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class FailingMessages:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def create(self, **kwargs: object) -> None:
        raise self.error


class FakeClient:
    def __init__(self, error: Exception) -> None:
        self.messages = FailingMessages(error)


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_not_found_has_actionable_error(self) -> None:
        provider = ClaudeProvider.__new__(ClaudeProvider)
        provider.model = "retired-model"
        provider._api_error_type = FakeAPIError
        provider._client = FakeClient(FakeAPIError(404, "not found"))

        with self.assertRaisesRegex(
            AgentError,
            "ANTHROPIC_MODEL=claude-sonnet-5",
        ):
            await provider._create_message(model=provider.model)

    async def test_other_api_errors_are_wrapped(self) -> None:
        provider = ClaudeProvider.__new__(ClaudeProvider)
        provider.model = "claude-sonnet-5"
        provider._api_error_type = FakeAPIError
        provider._client = FakeClient(FakeAPIError(401, "invalid key"))

        with self.assertRaisesRegex(AgentError, "401.*invalid key"):
            await provider._create_message(model=provider.model)


if __name__ == "__main__":
    unittest.main()
