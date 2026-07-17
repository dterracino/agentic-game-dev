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
from agentic_game_dev.workspace import GameWorkspace, WorkspaceError


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
    provider_name = "anthropic"

    def __init__(
        self,
        *,
        fail_file_once: str | None = None,
        fail_iteration_once: bool = False,
        syntax_error_once: str | None = None,
    ) -> None:
        self.fail_file_once = fail_file_once
        self.fail_iteration_once = fail_iteration_once
        self.syntax_error_once = syntax_error_once
        self.failed = False
        self.iteration_failed = False
        self.syntax_failed = False
        self.calls: Counter[str] = Counter()
        self.game_saw_main_checkpoint = False
        self.files = {
            "main.py": (
                "import time\n"
                "from game import Game\n\n"
                "def main():\n"
                "    Game()\n"
                "    while True:\n"
                "        time.sleep(0.01)\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
            "game.py": "class Game:\n    pass\n",
        }

    async def text(self, *, role: str, prompt: str) -> str:
        if "lead game designer" in role:
            name = "designer"
        elif "game-design implementation reviewer" in role:
            name = "gameplay_review"
        elif "game-engineering reviewer" in role:
            name = "technical_review"
        else:
            name = "architecture"
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
        if tool_name == "submit_qa_contract":
            return {
                "summary": "The core loop must be demonstrably playable.",
                "criteria": [
                    {
                        "id": f"QA-{number}",
                        "requirement": f"Gameplay requirement {number}",
                        "rationale": "Proves the promised mechanic.",
                        "automated_test": "Run a deterministic state assertion.",
                        "scripted_playtest": "Execute the related input sequence.",
                        "visual_evidence": "Capture the resulting gameplay state.",
                        "blocking": True,
                    }
                    for number in range(1, 7)
                ],
            }
        if tool_name == "submit_iteration_plan":
            return {
                "updated_plan": {
                    "title": "Tiny Test",
                    "pitch": "A deterministic improved test game.",
                    "core_loop": ["move", "decide", "score"],
                    "controls": ["Arrows"],
                    "quality_bar": ["clear", "fair", "responsive", "complete"],
                    "dependencies": [],
                    "files": [
                        {"name": "main.py", "purpose": "Entry", "public_api": ["main() -> None"]},
                        {"name": "game.py", "purpose": "Game state", "public_api": ["Game"]},
                    ],
                },
                "files_to_change": [
                    {"filename": "game.py", "reason": "Add the reviewed improvement"}
                ],
                "review_summary": "Improve the game state.",
            }
        if tool_name == "submit_replacements":
            return {
                "files": [
                    {
                        "filename": "render/text.py",
                        "content": "def draw_text(value: str) -> str:\n    return value\n",
                    }
                ],
                "summary": "Add a separated text-rendering responsibility.",
            }
        if tool_name == "submit_python_file":
            name = "main.py" if "Your assigned file: main.py" in prompt else "game.py"
            self.calls[f"file:{name}"] += 1
            if name == "game.py" and "Project implemented so far:" in prompt:
                self.game_saw_main_checkpoint = "def main():" in prompt
            is_iteration = "Reason for change:" in prompt
            if is_iteration and self.fail_iteration_once and not self.iteration_failed:
                self.iteration_failed = True
                raise RuntimeError("simulated iteration failure")
            if name == self.fail_file_once and not self.failed:
                self.failed = True
                raise RuntimeError(f"simulated failure for {name}")
            if name == self.syntax_error_once and not self.syntax_failed:
                self.syntax_failed = True
                return {
                    "filename": name,
                    "content": "def broken():\n    global first,\n    second\n",
                }
            content = self.files[name]
            if is_iteration and name == "game.py":
                content = "class Game:\n    improved = True\n"
            return {"filename": name, "content": content}
        raise AssertionError(f"Unexpected tool: {tool_name}")


def make_builder(
    provider: FakeProvider,
    workspace: GameWorkspace,
    environment: FakeEnvironment,
    messages: list[str],
    **kwargs: object,
) -> GameBuilder:
    return GameBuilder(
        provider,
        workspace,
        environment=environment,
        dependency_approver=lambda _deps, _reason: True,
        progress=messages.append,
        repair_attempts=0,
        smoke_timeout=0.05,
        **kwargs,
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
            self.assertTrue(state["qa_approved"])
            self.assertEqual(state["tasks"]["qa_contract"]["status"], "complete")
            self.assertTrue((workspace.root / "QA_ACCEPTANCE.md").is_file())
            self.assertEqual(state["tasks"]["file:main.py"]["status"], "complete")
            self.assertEqual(state["tasks"]["file:game.py"]["status"], "complete")
            self.assertTrue(provider.game_saw_main_checkpoint)
            self.assertEqual(environment.ensure_calls, [["pygame-ce>=2.5,<3"]])
            self.assertEqual(
                (workspace.root / "requirements.txt").read_text(encoding="utf-8"),
                "pygame-ce>=2.5,<3\n",
            )
            self.assertTrue((workspace.root / ".agentic" / "artifacts").is_dir())
            self.assertTrue(any("[5/8]" in message for message in messages))

    async def test_rejected_qa_contract_stops_before_implementation_and_resumes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            environment = FakeEnvironment()
            first = FakeProvider()
            builder = GameBuilder(
                first,
                workspace,
                environment=environment,
                dependency_approver=lambda _deps, _reason: True,
                qa_approver=lambda _contract, _path: False,
                repair_attempts=0,
                smoke_timeout=0.05,
                progress=lambda _message: None,
            )

            with self.assertRaisesRegex(WorkspaceError, "QA acceptance contract was not approved"):
                await builder.create("A small game")

            paused = RunJournal.load(workspace.root).state
            self.assertFalse(paused["qa_approved"])
            self.assertEqual(paused["tasks"]["qa_contract"]["status"], "complete")
            self.assertNotIn("file:main.py", paused["tasks"])

            second = FakeProvider()
            resumed = await GameBuilder(
                second,
                workspace,
                environment=environment,
                dependency_approver=lambda _deps, _reason: True,
                qa_approver=lambda _contract, _path: True,
                repair_attempts=0,
                smoke_timeout=0.05,
                progress=lambda _message: None,
            ).resume()

            self.assertTrue(resumed.ok, resumed.report)
            self.assertEqual(second.calls["submit_qa_contract"], 0)
            self.assertTrue(RunJournal.load(workspace.root).state["qa_approved"])
    async def test_invalid_python_is_retried_with_diagnostic_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            environment = FakeEnvironment()
            provider = FakeProvider(syntax_error_once="game.py")
            messages: list[str] = []

            result = await make_builder(
                provider, workspace, environment, messages
            ).create("A small game")

            self.assertTrue(result.ok, result.report)
            self.assertEqual(provider.calls["file:game.py"], 2)
            failed_path = (
                workspace.root
                / ".agentic"
                / "artifacts"
                / "files"
                / "game.py.failed_01.json"
            )
            self.assertTrue(failed_path.is_file())
            failed = json.loads(failed_path.read_text(encoding="utf-8"))
            self.assertIn("invalid syntax", failed["validation_error"])
            self.assertTrue(
                any("game.py failed source validation" in message for message in messages)
            )
            state = RunJournal.load(workspace.root).state
            self.assertEqual(state["tasks"]["file:game.py"]["status"], "complete")
            self.assertEqual(
                state["tasks"]["file:game.py"]["artifact"],
                "artifacts/files/game.py.json",
            )

    async def test_failed_legacy_artifact_is_ignored_and_regenerated(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            workspace.prepare(False)
            environment = FakeEnvironment()
            provider = FakeProvider()
            builder = make_builder(provider, workspace, environment, [])
            builder.journal = RunJournal.create(
                workspace.root,
                brief="test",
                model=provider.model,
                renderer="pygame",
                repair_attempts=0,
                smoke_timeout=0.05,
            )
            spec = FileSpec("game.py", "Game state", ["Game"])
            task_name = "file:game.py"
            builder.journal.start_task(task_name)
            artifact = builder.journal.write_json_artifact(
                "files/game.py.json",
                {
                    "filename": "game.py",
                    "content": "def broken():\n    global first,\n    second\n",
                },
            )
            builder.journal.set_task_artifact(task_name, artifact)
            builder.journal.fail_task(task_name, "invalid syntax (game.py, line 2)")

            self.assertFalse(builder._restore_completed_file(spec))
            plan = GamePlan(
                title="Test",
                pitch="Test",
                core_loop=["move", "decide", "score"],
                controls=["Arrows"],
                quality_bar=["clear", "fair", "responsive", "complete"],
                files=[spec],
            )
            await builder._generate_file_checkpoint(spec, plan, "Approved QA")

            self.assertEqual(provider.calls["file:game.py"], 1)
            self.assertIn("class Game", (workspace.root / "game.py").read_text())
            self.assertTrue(builder.journal.task_complete(task_name))
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

    async def test_runs_checkpointed_design_and_implementation_iterations(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            provider = FakeProvider()
            environment = FakeEnvironment()
            messages: list[str] = []
            builder = make_builder(
                provider,
                workspace,
                environment,
                messages,
                design_iterations=3,
                implementation_iterations=1,
            )

            result = await builder.create("A small game")

            self.assertTrue(result.ok, result.report)
            self.assertEqual(provider.calls["designer"], 3)
            self.assertEqual(provider.calls["gameplay_review"], 1)
            self.assertEqual(provider.calls["technical_review"], 1)
            self.assertEqual(provider.calls["submit_iteration_plan"], 1)
            self.assertIn("improved = True", (workspace.root / "game.py").read_text())
            state = RunJournal.load(workspace.root).state
            self.assertEqual(state["design_iterations"], 3)
            self.assertEqual(state["implementation_iterations"], 1)
            self.assertEqual(
                state["tasks"]["iteration:001:file:game.py"]["status"], "complete"
            )
            self.assertEqual(
                state["tasks"]["iteration:001:validation"]["status"], "complete"
            )

    async def test_resume_replays_iteration_without_repeating_paid_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            environment = FakeEnvironment()
            first = FakeProvider(fail_iteration_once=True)
            with self.assertRaisesRegex(RuntimeError, "simulated iteration failure"):
                await make_builder(
                    first,
                    workspace,
                    environment,
                    [],
                    implementation_iterations=1,
                ).create("A small game")

            second = FakeProvider()
            result = await make_builder(second, workspace, environment, []).resume()

            self.assertTrue(result.ok, result.report)
            self.assertEqual(second.calls["designer"], 0)
            self.assertEqual(second.calls["architecture"], 0)
            self.assertEqual(second.calls["submit_game_plan"], 0)
            self.assertEqual(second.calls["gameplay_review"], 0)
            self.assertEqual(second.calls["technical_review"], 0)
            self.assertEqual(second.calls["submit_iteration_plan"], 0)
            self.assertEqual(second.calls["file:main.py"], 0)
            self.assertEqual(second.calls["file:game.py"], 1)
            self.assertIn("improved = True", (workspace.root / "game.py").read_text())

    async def test_refine_adds_new_file_to_plan_and_resume_checkpoints(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            environment = FakeEnvironment()
            provider = FakeProvider()
            builder = make_builder(provider, workspace, environment, [])
            created = await builder.create("A small game")
            self.assertTrue(created.ok, created.report)

            refined = await builder.refine("Add readable menu text")

            self.assertTrue(refined.ok, refined.report)
            self.assertTrue((workspace.root / "render" / "text.py").is_file())
            plan = workspace.read_plan()
            self.assertIn("render/text.py", {spec.name for spec in plan.files})
            state = RunJournal.load(workspace.root).state
            self.assertEqual(state["tasks"]["refine:001"]["status"], "complete")

            (workspace.root / "render" / "text.py").unlink()
            resumed = await make_builder(FakeProvider(), workspace, environment, []).resume()
            self.assertTrue(resumed.ok, resumed.report)
            self.assertTrue((workspace.root / "render" / "text.py").is_file())

    def test_normalizes_json_encoded_repair_files(self) -> None:
        patch = GameBuilder._normalize_patch(
            {
                "files": (
                    '[{"filename": "game.py", "content": '
                    '"class Game:\n    label = "game"\n"}]'
                ),
                "summary": "Fix startup",
            }
        )

        self.assertEqual(patch["files"][0]["filename"], "game.py")
        self.assertEqual(patch["summary"], "Fix startup")

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


    def test_plan_file_count_is_not_artificially_limited(self) -> None:
        files = [FileSpec("main.py", "entry")]
        files.extend(
            FileSpec(f"systems/system_{index}.py", f"system {index}")
            for index in range(24)
        )
        plan = GamePlan(
            title="Many responsibilities",
            pitch="Separated systems",
            core_loop=["a", "b", "c"],
            controls=[],
            quality_bar=["a", "b", "c", "d"],
            files=files,
        )

        GameBuilder._validate_plan(plan)

if __name__ == "__main__":
    unittest.main()
