from __future__ import annotations

import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from typing import Any

from agentic_game_dev.journal import RunJournal
from agentic_game_dev.models import DependencySpec, FileSpec, GamePlan
from agentic_game_dev.orchestrator import GameBuilder
from agentic_game_dev.validation import ValidationResult
from agentic_game_dev.workspace import GameWorkspace


class FakeEnvironment:
    def __init__(self) -> None:
        self.python = Path(sys.executable)
        self.ready = False
        self.ensure_calls: list[list[str]] = []

    def is_ready(self, dependencies: list[DependencySpec]) -> bool:
        return self.ready

    def ensure(self, dependencies: list[DependencySpec]) -> None:
        self.ensure_calls.append([item.requirement for item in dependencies])
        self.ready = True


class FakeProvider:
    model = "test-model"

    def __init__(self, *, fail_file_once: str | None = None) -> None:
        self.fail_file_once = fail_file_once
        self.failed = False
        self.calls: Counter[str] = Counter()
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
        name = "designer" if "game designer" in role else "architecture"
        self.calls[name] += 1
        return f"A focused {name} proposal."

    async def structured(
        self,
        *,
        role: str,
        prompt: str,
        tool_name: str,
        description: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls[tool_name] += 1
        if tool_name == "submit_game_plan":
            return {
                "title": "Tiny Test",
                "pitch": "A deterministic test game.",
                "core_loop": ["move", "decide", "score"],
                "controls": ["Arrows"],
                "quality_bar": ["clear", "fair", "responsive", "complete"],
                "dependencies": [],
                "files": [
                    {"name": "main.py", "purpose": "Entry", "public_api": ["main() -> None"]},
                    {"name": "game.py", "purpose": "Game state", "public_api": ["Game"]},
                ],
            }
        if tool_name == "submit_python_file":
            name = "main.py" if "Your assigned file: main.py" in prompt else "game.py"
            self.calls[f"file:{name}"] += 1
            if name == self.fail_file_once and not self.failed:
                self.failed = True
                raise RuntimeError(f"simulated failure for {name}")
            return {"filename": name, "content": self.files[name]}
        raise AssertionError(f"Unexpected tool: {tool_name}")


def make_builder(
    provider: FakeProvider,
    workspace: GameWorkspace,
    environment: FakeEnvironment,
    messages: list[str],
) -> GameBuilder:
    return GameBuilder(
        provider,
        workspace,
        environment=environment,
        dependency_approver=lambda _deps, _reason: True,
        progress=messages.append,
        repair_attempts=0,
    )


class OrchestratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_builds_checkpointed_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            provider = FakeProvider()
            environment = FakeEnvironment()
            messages: list[str] = []

            result = await make_builder(provider, workspace, environment, messages).create(
                "A small game"
            )

            self.assertTrue(result.ok, result.report)
            state = RunJournal.load(workspace.root).state
            self.assertEqual(state["status"], "complete")
            self.assertEqual(state["tasks"]["file:main.py"]["status"], "complete")
            self.assertEqual(state["tasks"]["file:game.py"]["status"], "complete")
            self.assertEqual(environment.ensure_calls, [["pygame-ce>=2.5,<3"]])
            self.assertEqual(
                (workspace.root / "requirements.txt").read_text(encoding="utf-8"),
                "pygame-ce>=2.5,<3\n",
            )
            self.assertTrue((workspace.root / ".agentic" / "artifacts").is_dir())
            self.assertTrue(any("[4/5]" in message for message in messages))

    async def test_resume_reuses_paid_calls_and_completed_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            environment = FakeEnvironment()
            first = FakeProvider(fail_file_once="game.py")

            with self.assertRaisesRegex(RuntimeError, "simulated failure"):
                await make_builder(first, workspace, environment, []).create("A small game")

            interrupted = RunJournal.load(workspace.root).state
            self.assertEqual(interrupted["tasks"]["file:main.py"]["status"], "complete")
            self.assertEqual(interrupted["tasks"]["file:game.py"]["status"], "failed")

            second = FakeProvider()
            result = await make_builder(second, workspace, environment, []).resume()

            self.assertTrue(result.ok, result.report)
            self.assertEqual(second.calls["designer"], 0)
            self.assertEqual(second.calls["architecture"], 0)
            self.assertEqual(second.calls["submit_game_plan"], 0)
            self.assertEqual(second.calls["file:main.py"], 0)
            self.assertEqual(second.calls["file:game.py"], 1)

    def test_missing_module_can_be_approved_and_added(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            workspace.prepare(False)
            environment = FakeEnvironment()
            approved: list[str] = []
            builder = GameBuilder(
                FakeProvider(),
                workspace,
                environment=environment,
                dependency_approver=lambda deps, _reason: approved.extend(
                    item.distribution for item in deps
                ) or True,
                repair_attempts=0,
            )
            builder.journal = RunJournal.create(
                workspace.root,
                brief="test",
                model="test-model",
                renderer="pygame",
                repair_attempts=0,
                smoke_timeout=8,
            )
            plan = GamePlan(
                title="Test",
                pitch="Test",
                core_loop=["a", "b", "c"],
                controls=[],
                quality_bar=["a", "b", "c", "d"],
                files=[FileSpec("main.py", "entry")],
                dependencies=[
                    DependencySpec("pygame-ce", "pygame", ">=2.5,<3", "runtime")
                ],
            )
            workspace.write_plan(plan)
            artifact = builder.journal.write_json_artifact("planning/plan.json", plan.as_dict())
            builder.journal.complete_task("plan", artifact)
            builder._run_validation = lambda: ValidationResult(True, "passed")  # type: ignore[method-assign]

            result = builder._handle_missing_dependency(
                plan,
                ValidationResult(False, "ModuleNotFoundError: No module named 'numpy'"),
            )

            self.assertTrue(result.ok)
            self.assertIn("numpy", approved)
            self.assertIsNotNone(plan.dependency_for_import("numpy"))
            saved = json.loads((workspace.root / "game_plan.json").read_text(encoding="utf-8"))
            self.assertTrue(
                any(item["distribution"] == "numpy" for item in saved["dependencies"])
            )


if __name__ == "__main__":
    unittest.main()
