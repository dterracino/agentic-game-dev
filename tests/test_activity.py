from __future__ import annotations

import asyncio
import io
import unittest

from agentic_game_dev.activity import TerminalActivity


class ActivityTests(unittest.IsolatedAsyncioTestCase):
    async def test_noninteractive_activity_prints_a_waiting_message(self) -> None:
        output = io.StringIO()
        activity = TerminalActivity(output)

        async with activity.track("Waiting for test model"):
            await asyncio.sleep(0)

        self.assertIn("Waiting for test model", output.getvalue())


if __name__ == "__main__":
    unittest.main()
