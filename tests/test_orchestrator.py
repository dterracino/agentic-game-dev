from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from agentic_game_dev.orchestrator import GameBuilder
from agentic_game_dev.workspace import GameWorkspace


class FakeProvider:
    def __init__(self) -> None:
        self.files = {
            "main.py": (
                "from game import Game\n\n"
                "def main():\n"
                "    return Game()\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
            "game.py": "class Game:\n    pass\n",
        }

    async def text(self, *, role: str, prompt: str) -> str:
        return "A focused, testable proposal."

    async def structured(
        self,
        *,
        role: str,
        prompt: str,
        tool_name: str,
        description: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        if tool_name == "submit_game_plan":
            return {
                "title": "Tiny Test",
                "pitch": "A deterministic test game.",
                "core_loop": ["move", "decide", "score"],
                "controls": ["Arrows"],
                "quality_bar": ["clear", "fair", "responsive", "complete"],
                "files": [
                    {"name": "main.py", "purpose": "Entry", "public_api": ["main() -> None"]},
                    {"name": "game.py", "purpose": "Game state", "public_api": ["Game"]},
                ],
            }
        if tool_name == "submit_python_file":
            name = "main.py" if "Your assigned file: main.py" in prompt else "game.py"
            return {"filename": name, "content": self.files[name]}
        raise AssertionError(f"Unexpected tool: {tool_name}")


class OrchestratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_builds_and_smoke_tests_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            messages: list[str] = []
            builder = GameBuilder(
                FakeProvider(),
                workspace,
                progress=messages.append,
                repair_attempts=0,
            )
            result = await builder.create("A small game")
            self.assertTrue(result.ok, result.report)
            self.assertTrue((workspace.root / "main.py").exists())
            self.assertTrue(any("[3/4]" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
