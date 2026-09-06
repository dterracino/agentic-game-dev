from __future__ import annotations

import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from typing import Any
from unittest.mock import patch

from agentic_game_dev.journal import RunJournal
from agentic_game_dev.models import (
    DependencySpec,
    FileSpec,
    GamePlan,
    RenderEffectSpec,
    VisualAssetSpec,
)
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
        self.prompts: list[tuple[str, str]] = []
        self.role_prompts: list[str] = []
        self.main_saw_game_checkpoint = False
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
            "game.py": "class Game:\n    ready = True\n",
            "shaders/glow.frag": (
                "#version 330\n"
                "out vec4 frag_color;\n"
                "void main() { frag_color = vec4(1.0); }\n"
            ),
        }

    async def text(self, *, role: str, prompt: str) -> str:
        self.role_prompts.append(role)
        if "lead game designer" in role:
            name = "designer"
        elif "game-design implementation reviewer" in role:
            name = "gameplay_review"
        elif "game-engineering reviewer" in role:
            name = "technical_review"
        else:
            name = "architecture"
        self.calls[name] += 1
        self.prompts.append((name, prompt))
        if name == "architecture":
            return """# Test Architecture

## Module Responsibilities
game.py owns game state; main.py owns startup.

## Rendering Pipeline
Draw the scene, effects, and UI in order.

## Shader Source Manifest
| Experience | Technique | Owner | Runtime integration | Validation |
|---|---|---|---|---|
| Scene | Vertex transform | shaders/scene.vert | renderer.py | Compiles |
| Scene | Fragment color | shaders/scene.frag | renderer.py | Visible output |

## Visual Asset Manifest
| Experience | Technique | Owner | Runtime integration | Validation |
|---|---|---|---|---|
| Player | Procedural surface | game.py | Scene draw | Visible sprite |

## Audio Asset Manifest
| Experience | Technique | Owner | Runtime integration | Validation |
|---|---|---|---|---|
| Feedback | Synthesized tone | game.py | Game event | Audible cue |

## Cross-File APIs
Game is imported by main.

## Lifecycle and Cleanup
Resources are released on shutdown.

## Validation Strategy
Compile, test, and smoke-test the game.
"""
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
        self.role_prompts.append(role)
        self.calls[tool_name] += 1
        self.prompts.append((tool_name, prompt))
        if tool_name == "submit_game_plan":
            return {
                "title": "Tiny Test",
                "pitch": "A deterministic test game.",
                "core_loop": ["move", "decide", "score"],
                "controls": ["Arrows"],
                "quality_bar": ["clear", "fair", "responsive", "complete"],
                "rendering_strategy": "Use pygame-ce for a clear 2D presentation.",
                "render_effects": [],
                "dependencies": [],
                "files": [
                    {"name": "game.py", "purpose": "Game state", "public_api": ["Game"]},
                    {"name": "main.py", "purpose": "Entry", "public_api": ["main() -> None"]},
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
                    "rendering_strategy": "Use pygame-ce for a clear 2D presentation.",
                    "render_effects": [],
                    "dependencies": [],
                    "files": [
                        {"name": "game.py", "purpose": "Game state", "public_api": ["Game"]},
                        {"name": "main.py", "purpose": "Entry", "public_api": ["main() -> None"]},
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
        if tool_name == "submit_source_file":
            name = next(
                (
                    candidate
                    for candidate in self.files
                    if f"Your assigned file: {candidate}" in prompt
                ),
                "game.py",
            )
            self.calls[f"file:{name}"] += 1
            if name == "main.py" and "Project implemented so far:" in prompt:
                self.main_saw_game_checkpoint = "class Game:" in prompt
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


class FileRepairProvider(FakeProvider):
    def __init__(self, *, no_change: bool = False) -> None:
        super().__init__()
        self.no_change = no_change

    async def structured(
        self,
        *,
        role: str,
        prompt: str,
        tool_name: str,
        description: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        marker = "Your sole repair target is "
        if tool_name != "submit_replacements" or marker not in prompt:
            return await super().structured(
                role=role,
                prompt=prompt,
                tool_name=tool_name,
                description=description,
                schema=schema,
            )
        self.calls[tool_name] += 1
        self.prompts.append((tool_name, prompt))
        filename = prompt.split(marker, 1)[1].split(". Return", 1)[0]
        content = self.files[filename]
        if not self.no_change:
            content = content.rstrip() + "\nrepaired: bool = True\n"
        return {
            "files": [{"filename": filename, "content": content}],
            "summary": f"Repaired {filename}",
        }


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
        type_checker=lambda _root, _python: ValidationResult(
            True, "Strict Pyright validation passed: 0 errors"
        ),
        **kwargs,
    )


class OrchestratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_completed_file_repair_is_regenerated(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            workspace.prepare(False)
            provider = FileRepairProvider()
            provider.files["audio.py"] = (
                "def set_volume(value: float) -> float:\n    return value\n"
            )
            plan = GamePlan(
                title="Audio repair",
                pitch="Replace a poisoned checkpoint",
                core_loop=["a", "b", "c"],
                controls=[],
                quality_bar=["a", "b", "c", "d"],
                files=[FileSpec("audio.py", "audio"), FileSpec("main.py", "entry")],
            )
            workspace.write_plan(plan)
            workspace.write_generated_source("audio.py", provider.files["audio.py"])
            workspace.write_generated_source("main.py", provider.files["main.py"])
            builder = GameBuilder(
                provider,
                workspace,
                environment=FakeEnvironment(),
                progress=lambda _message: None,
            )
            builder.journal = RunJournal.create(
                workspace.root,
                brief="test",
                model="test-model",
                renderer="pygame",
                repair_attempts=1,
                smoke_timeout=8,
            )
            invalid_patch = {
                "files": [
                    {
                        "filename": "audio.py",
                        "content": "def set_volume(value: float) -> float:\n    pass\n",
                    }
                ],
                "summary": "Incomplete repair",
            }
            artifact = builder.journal.write_json_artifact(
                "repairs/001/audio.py.json", invalid_patch
            )
            task_name = "repair_file:001:audio.py"
            builder.journal.complete_task(task_name, artifact)

            patch_result = await builder._review_file_checkpoint(
                attempt=1,
                filename="audio.py",
                validation_report="audio.py:1: error: test",
                allowed_names={"audio.py", "main.py"},
            )

            self.assertEqual(provider.calls["submit_replacements"], 1)
            self.assertIn("repaired: bool = True", patch_result["files"][0]["content"])
            state = RunJournal.load(workspace.root).state
            self.assertEqual(state["tasks"][task_name]["status"], "complete")
            saved = builder.journal.read_json_artifact(
                state["tasks"][task_name]["artifact"]
            )
            self.assertIn("repaired: bool = True", saved["files"][0]["content"])

    async def test_completed_validation_skips_invalid_legacy_repair_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            workspace.prepare(False)
            plan = GamePlan(
                title="Resume test",
                pitch="Reuse validation",
                core_loop=["a", "b", "c"],
                controls=[],
                quality_bar=["a", "b", "c", "d"],
                files=[FileSpec("game.py", "game"), FileSpec("main.py", "entry")],
            )
            workspace.write_plan(plan)
            workspace.write_generated_source("game.py", "ready: bool = True\n")
            workspace.write_generated_source("main.py", "def main() -> None:\n    return None\n")
            builder = GameBuilder(
                FakeProvider(),
                workspace,
                environment=FakeEnvironment(),
                repair_attempts=1,
                progress=lambda _message: None,
            )
            builder.journal = RunJournal.create(
                workspace.root,
                brief="test",
                model="test-model",
                renderer="pygame",
                repair_attempts=1,
                smoke_timeout=8,
            )
            invalid_patch = {
                "files": [
                    {
                        "filename": "new_module.py",
                        "content": "value: int = 1\n",
                    }
                ],
                "summary": "Invalid stale repair",
            }
            artifact = builder.journal.write_json_artifact(
                "repairs/1.json", invalid_patch
            )
            builder.journal.complete_task("repair:1", artifact)
            builder.journal.complete_task("validation")

            with patch.object(builder, "_run_validation") as validation:
                result = await builder._validate_and_repair(plan)

            self.assertTrue(result.ok, result.report)
            validation.assert_not_called()
            self.assertFalse((workspace.root / "new_module.py").exists())
            state = RunJournal.load(workspace.root).state
            self.assertEqual(state["tasks"]["repair:1"]["status"], "pending")

    async def test_repairs_validation_failures_one_file_per_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            workspace.prepare(False)
            provider = FileRepairProvider()
            provider.files.update(
                {
                    "a.py": "value: str = 'a'\n",
                    "b.py": "value: str = 'b'\n",
                }
            )
            plan = GamePlan(
                title="Repair test",
                pitch="Repair files individually",
                core_loop=["a", "b", "c"],
                controls=[],
                quality_bar=["a", "b", "c", "d"],
                files=[
                    FileSpec("a.py", "first"),
                    FileSpec("b.py", "second"),
                    FileSpec("main.py", "entry"),
                ],
            )
            workspace.write_plan(plan)
            for filename in ("a.py", "b.py", "main.py"):
                workspace.write_generated_source(filename, provider.files[filename])
            builder = GameBuilder(
                provider,
                workspace,
                environment=FakeEnvironment(),
                repair_attempts=1,
                progress=lambda _message: None,
            )
            builder.journal = RunJournal.create(
                workspace.root,
                brief="test",
                model="test-model",
                renderer="pygame",
                repair_attempts=1,
                smoke_timeout=8,
            )
            failed = ValidationResult(
                False,
                f"{workspace.root / 'a.py'}:1:1 - error: bad a\n"
                f"{workspace.root / 'b.py'}:1:1 - error: bad b",
            )
            with patch.object(
                builder,
                "_run_validation",
                side_effect=[failed, ValidationResult(True, "passed")],
            ):
                result = await builder._validate_and_repair(plan)

            self.assertTrue(result.ok, result.report)
            self.assertEqual(provider.calls["submit_replacements"], 2)
            self.assertIn("repaired: bool = True", (workspace.root / "a.py").read_text())
            self.assertIn("repaired: bool = True", (workspace.root / "b.py").read_text())
            tasks = RunJournal.load(workspace.root).state["tasks"]
            self.assertEqual(tasks["repair_file:001:a.py"]["status"], "complete")
            self.assertEqual(tasks["repair_file:001:b.py"]["status"], "complete")

    async def test_repair_stops_when_file_checkpoints_make_no_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            workspace.prepare(False)
            provider = FileRepairProvider(no_change=True)
            plan = GamePlan(
                title="Repair test",
                pitch="Stop stalled repairs",
                core_loop=["a", "b", "c"],
                controls=[],
                quality_bar=["a", "b", "c", "d"],
                files=[FileSpec("game.py", "game"), FileSpec("main.py", "entry")],
            )
            workspace.write_plan(plan)
            workspace.write_generated_source("game.py", provider.files["game.py"])
            workspace.write_generated_source("main.py", provider.files["main.py"])
            builder = GameBuilder(
                provider,
                workspace,
                environment=FakeEnvironment(),
                repair_attempts=3,
                progress=lambda _message: None,
            )
            builder.journal = RunJournal.create(
                workspace.root,
                brief="test",
                model="test-model",
                renderer="pygame",
                repair_attempts=3,
                smoke_timeout=8,
            )
            failed = ValidationResult(False, "game.py:1:1 - error: still broken")
            with patch.object(builder, "_run_validation", return_value=failed):
                result = await builder._validate_and_repair(plan)

            self.assertFalse(result.ok)
            self.assertIn("remaining repair passes were not spent", result.report)
            self.assertEqual(provider.calls["submit_replacements"], 1)
    def test_moderngl_architecture_rejects_folder_only_asset_plan(self) -> None:
        builder = object.__new__(GameBuilder)
        builder.renderer = "moderngl"
        architecture = """# Architecture

## Module Responsibilities
renderer.py renders.

## Rendering Pipeline
Draw the scene.

## Cross-File APIs
Renderer is called by main.

## Lifecycle and Cleanup
Release the context.

## Validation Strategy
Smoke test.

assets/ contains assets not included in the spec.
shaders/ contains shaders.
"""

        with self.assertRaisesRegex(ValueError, "missing required architecture sections"):
            builder._validate_architecture(architecture)

    async def test_specification_is_snapshotted_and_propagated(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            provider = FakeProvider()
            environment = FakeEnvironment()

            result = await make_builder(
                provider, workspace, environment, []
            ).create(
                "Build this parser adventure",
                specification="# Rules\nInventory has no capacity limit.",
                specification_source="adventure.md",
            )

            self.assertTrue(result.ok, result.report)
            journal = RunJournal.load(workspace.root)
            self.assertIn("Inventory has no capacity limit", journal.read_specification())
            for name in ("designer", "architecture", "submit_game_plan", "submit_qa_contract"):
                prompts = [prompt for kind, prompt in provider.prompts if kind == name]
                self.assertTrue(prompts, name)
                self.assertIn("Inventory has no capacity limit", prompts[0])
            implementation_prompts = [
                prompt
                for kind, prompt in provider.prompts
                if kind == "submit_source_file"
            ]
            self.assertTrue(implementation_prompts)
            self.assertTrue(
                all(
                    "Inventory has no capacity limit" in prompt
                    for prompt in implementation_prompts
                )
            )

    def test_normalize_plan_preserves_inferred_ui_toolkit_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            builder = GameBuilder(
                FakeProvider(),
                GameWorkspace(Path(temp) / "game"),
                environment=FakeEnvironment(),
            )
            plan = GamePlan(
                title="Parser Adventure",
                pitch="A graphical parser-driven story.",
                core_loop=["read", "enter a command", "observe the changed world"],
                controls=["Type commands and press Enter"],
                quality_bar=["clear", "responsive", "coherent", "complete"],
                files=[
                    FileSpec("main.py", "Pygame entry point"),
                    FileSpec("game.py", "Toolkit-independent game rules"),
                ],
                dependencies=[
                    DependencySpec(
                        "pygame-gui",
                        "pygame_gui",
                        ">=0.6,<1",
                        "Graphical text interface",
                    )
                ],
            )

            normalized = builder._normalize_plan(plan)

            self.assertEqual(
                [dependency.requirement for dependency in normalized.dependencies],
                ["pygame-gui>=0.6,<0.7", "pygame-ce>=2.5,<3"],
            )
            self.assertIsNotNone(normalized.dependency_for_import("pygame_gui"))
            self.assertEqual([item.name for item in normalized.files], ["game.py", "main.py"])

    def test_normalize_plan_promotes_referenced_shader_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            builder = GameBuilder(
                FakeProvider(),
                GameWorkspace(Path(temp) / "game"),
                environment=FakeEnvironment(),
                renderer="moderngl",
            )
            plan = GamePlan(
                title="Shader game",
                pitch="A GPU-rendered game.",
                core_loop=["move", "claim", "escape"],
                controls=["Arrows"],
                quality_bar=["clear", "responsive", "coherent", "complete"],
                files=[
                    FileSpec("renderer.py", "ModernGL renderer"),
                    FileSpec("main.py", "Entry point"),
                ],
                render_effects=[
                    RenderEffectSpec(
                        experience="Claim sweep",
                        technique="vertex and fragment shader pass",
                        owner="renderer.py",
                        validation="Sweep is visible after claiming a tile",
                        source_files=[
                            "shaders/claim_sweep.vert",
                            "shaders/claim_sweep.frag",
                        ],
                    )
                ],
            )

            normalized = builder._normalize_plan(plan)

            self.assertEqual(
                [item.name for item in normalized.files],
                [
                    "renderer.py",
                    "shaders/claim_sweep.vert",
                    "shaders/claim_sweep.frag",
                    "main.py",
                ],
            )
            builder._validate_plan(normalized)

    async def test_completed_plan_is_normalized_when_resumed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            workspace.prepare(False)
            builder = GameBuilder(
                FakeProvider(),
                workspace,
                environment=FakeEnvironment(),
            )
            builder.journal = RunJournal.create(
                workspace.root,
                brief="test",
                model="test-model",
                renderer="pygame",
                repair_attempts=0,
                smoke_timeout=8,
            )
            stale = GamePlan(
                title="Parser Adventure",
                pitch="Test",
                core_loop=["read", "command", "respond"],
                controls=[],
                quality_bar=["a", "b", "c", "d"],
                files=[
                    FileSpec("main.py", "entry"),
                    FileSpec("game.py", "rules"),
                ],
                dependencies=[
                    DependencySpec(
                        "pygame-gui",
                        "pygame_gui",
                        ">=0.7.2,<1",
                        "Graphical text interface",
                    )
                ],
            )
            artifact = builder.journal.write_json_artifact(
                "planning/plan.json", stale.as_dict()
            )
            builder.journal.complete_task("plan", artifact)

            resumed = await builder._plan_checkpoint("", "", "")

            self.assertEqual(
                [item.requirement for item in resumed.dependencies],
                ["pygame-gui>=0.6,<0.7", "pygame-ce>=2.5,<3"],
            )
            self.assertEqual([item.name for item in resumed.files], ["game.py", "main.py"])

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
            self.assertTrue(provider.main_saw_game_checkpoint)
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
                type_checker=lambda _root, _python: ValidationResult(
                    True, "Strict Pyright validation passed: 0 errors"
                ),
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

    async def test_generates_standalone_shader_checkpoint(self) -> None:
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
                renderer="moderngl",
                repair_attempts=0,
                smoke_timeout=0.05,
            )
            spec = FileSpec("shaders/glow.frag", "Soft glow fragment shader")
            plan = GamePlan(
                title="Test",
                pitch="Test",
                core_loop=["move", "decide", "score"],
                controls=["Arrows"],
                quality_bar=["clear", "fair", "responsive", "complete"],
                files=[spec, FileSpec("main.py", "Entry")],
            )

            await builder._generate_file_checkpoint(spec, plan, "Approved QA")

            shader = workspace.root / "shaders" / "glow.frag"
            self.assertTrue(shader.is_file())
            self.assertIn("#version 330", shader.read_text(encoding="utf-8"))
            self.assertTrue(builder.journal.task_complete("file:shaders/glow.frag"))

    async def test_resume_reuses_paid_calls_and_completed_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            environment = FakeEnvironment()
            first = FakeProvider(fail_file_once="main.py")

            with self.assertRaisesRegex(RuntimeError, "simulated failure"):
                await make_builder(first, workspace, environment, []).create("A small game")

            interrupted = RunJournal.load(workspace.root).state
            self.assertEqual(interrupted["tasks"]["file:game.py"]["status"], "complete")
            self.assertEqual(interrupted["tasks"]["file:main.py"]["status"], "failed")

            second = FakeProvider()
            result = await make_builder(second, workspace, environment, []).resume()

            self.assertTrue(result.ok, result.report)
            self.assertEqual(second.calls["designer"], 0)
            self.assertEqual(second.calls["architecture"], 0)
            self.assertEqual(second.calls["submit_game_plan"], 0)
            self.assertEqual(second.calls["file:game.py"], 0)
            self.assertEqual(second.calls["file:main.py"], 1)

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
            self.assertTrue(
                any("Planned file updates (1): game.py" in item for item in messages)
            )
            self.assertTrue(
                any("Implementation round 1 complete" in item for item in messages)
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
            with patch.object(
                builder,
                "_run_validation",
                return_value=ValidationResult(True, "passed"),
            ):
                result = builder._handle_missing_dependency(
                    plan,
                    ValidationResult(
                        False, "ModuleNotFoundError: No module named 'pygame_gui'"
                    ),
                )

            self.assertTrue(result.ok)
            self.assertIn("pygame-gui", approved)
            self.assertIsNotNone(plan.dependency_for_import("pygame_gui"))
            saved = json.loads((workspace.root / "game_plan.json").read_text(encoding="utf-8"))
            self.assertTrue(
                any(item["distribution"] == "pygame-gui" for item in saved["dependencies"])
            )


    def test_plan_file_count_is_not_artificially_limited(self) -> None:
        files = [
            FileSpec(f"systems/system_{index}.py", f"system {index}")
            for index in range(24)
        ]
        files.append(FileSpec("main.py", "entry"))
        plan = GamePlan(
            title="Many responsibilities",
            pitch="Separated systems",
            core_loop=["a", "b", "c"],
            controls=[],
            quality_bar=["a", "b", "c", "d"],
            files=files,
        )

        builder = object.__new__(GameBuilder)
        builder.renderer = "pygame"
        builder._validate_plan(plan)

    def test_plan_rejects_unplanned_effect_and_asset_owners(self) -> None:
        plan = GamePlan(
            title="Broken contracts",
            pitch="Missing owners",
            core_loop=["a", "b", "c"],
            controls=[],
            quality_bar=["a", "b", "c", "d"],
            files=[FileSpec("game.py", "game"), FileSpec("main.py", "entry")],
            render_effects=[
                RenderEffectSpec(
                    "Glow",
                    "layered surfaces",
                    "render/effects.py",
                    "glow is visible",
                )
            ],
            visual_assets=[
                VisualAssetSpec(
                    "Player sprite",
                    "sprite",
                    "assets/sprites.py",
                    "procedural pixel atlas",
                    "player has a distinct silhouette",
                )
            ],
        )
        builder = object.__new__(GameBuilder)
        builder.renderer = "pygame"

        with self.assertRaisesRegex(ValueError, "owner is not a planned file"):
            builder._validate_plan(plan)

    def test_moderngl_plan_requires_referenced_vertex_and_fragment_sources(self) -> None:
        plan = GamePlan(
            title="GPU game",
            pitch="Rendered with shaders",
            core_loop=["a", "b", "c"],
            controls=[],
            quality_bar=["a", "b", "c", "d"],
            files=[
                FileSpec("renderer.py", "ModernGL renderer"),
                FileSpec("main.py", "entry"),
            ],
            render_effects=[],
        )
        builder = object.__new__(GameBuilder)
        builder.renderer = "moderngl"

        with self.assertRaisesRegex(ValueError, "separate planned vertex and fragment"):
            builder._validate_plan(plan)

        plan.files[1:1] = [
            FileSpec("shaders/scene.vert", "Vertex transform"),
            FileSpec("shaders/scene.frag", "Pixel treatment"),
        ]
        plan.render_effects.append(
            RenderEffectSpec(
                "Rendered scene",
                "vertex and fragment shader pass",
                "renderer.py",
                "scene is visibly rendered",
                ["shaders/scene.vert", "shaders/scene.frag"],
            )
        )
        builder._validate_plan(plan)

    def test_plan_accepts_multiple_planned_effect_owners(self) -> None:
        plan = GamePlan(
            title="GPU game",
            pitch="Rendered with shaders",
            core_loop=["move", "claim", "escape"],
            controls=["Arrows"],
            quality_bar=["clear", "responsive", "coherent", "complete"],
            files=[
                FileSpec("pixel_vault/presentation.py", "presentation"),
                FileSpec("pixel_vault/scene_layout.py", "scene layout"),
                FileSpec("main.py", "entry"),
            ],
            render_effects=[
                RenderEffectSpec(
                    "Layered scene",
                    "surface composition",
                    "pixel_vault/presentation.py and pixel_vault/scene_layout.py",
                    "layers are visible",
                )
            ],
        )
        builder = object.__new__(GameBuilder)
        builder.renderer = "pygame"

        builder._validate_plan(plan)

    def test_plan_accepts_comma_separated_effect_owners_with_final_and(self) -> None:
        plan = GamePlan(
            title="GPU game",
            pitch="Rendered with shaders",
            core_loop=["move", "claim", "escape"],
            controls=["Arrows"],
            quality_bar=["clear", "responsive", "coherent", "complete"],
            files=[
                FileSpec("pixel_vault/presentation.py", "presentation"),
                FileSpec("pixel_vault/ui_layout.py", "UI layout"),
                FileSpec("pixel_vault/renderer.py", "renderer"),
                FileSpec("main.py", "entry"),
            ],
            render_effects=[
                RenderEffectSpec(
                    "Layered UI",
                    "layout and compositing",
                    (
                        "pixel_vault/presentation.py, pixel_vault/ui_layout.py, "
                        "and pixel_vault/renderer.py"
                    ),
                    "UI layers are visible",
                )
            ],
        )
        builder = object.__new__(GameBuilder)
        builder.renderer = "pygame"

        builder._validate_plan(plan)

if __name__ == "__main__":
    unittest.main()
