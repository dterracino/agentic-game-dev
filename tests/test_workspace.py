from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agentic_game_dev.models import (
    AudioAssetSpec,
    FileSpec,
    GamePlan,
    RenderEffectSpec,
)
from agentic_game_dev.workspace import GameWorkspace, WorkspaceError


class WorkspaceTests(unittest.TestCase):
    def test_rejects_unsafe_filenames(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            workspace.prepare(replace=False)
            unsafe = (
                "../escape.py",
                "/absolute.py",
                "C:/drive.py",
                "folder\\file.py",
                "folder/../escape.py",
                "not-python.txt",
                "bad-dir!/file.py",
            )
            for name in unsafe:
                with self.subTest(name=name), self.assertRaises(WorkspaceError):
                    workspace.path_for(name)

    def test_writes_nested_python_packages(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            workspace.prepare(replace=False)

            workspace.write_python(
                "game/core/constants.py",
                "SCREEN_WIDTH = 1280\n",
            )
            workspace.write_python("game/__init__.py", '"""Game package."""\n')

            self.assertTrue((workspace.root / "game" / "core" / "constants.py").is_file())
            self.assertEqual(
                sorted(workspace.read_python_files()),
                ["game/__init__.py", "game/core/constants.py"],
            )

    def test_writes_and_reads_standalone_shader_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            workspace.prepare(replace=False)

            workspace.write_generated_source(
                "shaders/bloom.vert",
                "#version 330\nvoid main() { gl_Position = vec4(0.0); }",
            )
            workspace.write_generated_source(
                "shaders/bloom.frag",
                "#version 330\nout vec4 color;\nvoid main() { color = vec4(1.0); }",
            )

            sources = workspace.read_generated_sources()
            self.assertEqual(
                sorted(sources),
                ["shaders/bloom.frag", "shaders/bloom.vert"],
            )

    def test_rejects_empty_shader_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            workspace.prepare(replace=False)

            with self.assertRaisesRegex(WorkspaceError, "shader source is empty"):
                workspace.write_generated_source("shaders/empty.glsl", "  \n")

    def test_rejects_placeholder_generated_python(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            workspace.prepare(replace=False)

            with self.assertRaisesRegex(WorkspaceError, "stub class"):
                workspace.write_generated_source("game.py", "class Game:\n    pass\n")
            with self.assertRaisesRegex(WorkspaceError, "provisional implementation"):
                workspace.write_generated_source(
                    "effects.py",
                    "def render():\n    # Placeholder for now\n    return None\n",
                )

    def test_allows_protocol_and_overload_declarations(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            workspace.prepare(replace=False)

            workspace.write_generated_source(
                "interfaces.py",
                "from typing import Protocol, overload\n\n"
                "class Channel(Protocol):\n"
                "    def set_volume(self, value: float) -> None:\n"
                "        \"\"\"Set playback volume.\"\"\"\n"
                "        ...\n\n"
                "@overload\n"
                "def convert(value: int) -> str: ...\n"
                "@overload\n"
                "def convert(value: str) -> int: ...\n"
                "def convert(value: int | str) -> str | int:\n"
                "    return str(value) if isinstance(value, int) else len(value)\n",
            )

            self.assertTrue((workspace.root / "interfaces.py").is_file())

    def test_rejects_type_check_suppressions_in_generated_python(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            workspace.prepare(replace=False)

            for comment in (
                "# type: ignore",
                "# pyright: ignore[reportAssignmentType]",
                "# pyright: basic",
                "# pyright: reportUnknownVariableType=false",
            ):
                with self.subTest(comment=comment), self.assertRaisesRegex(
                    WorkspaceError, "prohibited type-check suppression"
                ):
                    workspace.write_generated_source(
                        "game.py", f"value: int = 1  {comment}\n"
                    )

    def test_writes_strict_pyright_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            workspace.prepare(replace=False)

            workspace.write_typecheck_config()

            config = json.loads(
                (workspace.root / "pyrightconfig.json").read_text(encoding="utf-8")
            )
            self.assertEqual(config["typeCheckingMode"], "strict")
            self.assertNotIn("ignore", config)

    def test_writes_plan_and_valid_python(self) -> None:
        plan = GamePlan(
            title="Test",
            pitch="Test pitch",
            core_loop=["move", "choose", "score"],
            controls=["Arrows"],
            quality_bar=["clear", "fair", "juicy", "complete"],
            files=[FileSpec("main.py", "Entry point", ["main() -> None"])],
            rendering_strategy="Use a composited 2D presentation.",
            render_effects=[
                RenderEffectSpec(
                    experience="Soft glow around clues",
                    technique="Layered translucent surfaces",
                    owner="rendering/effects.py",
                    validation="Screenshot shows a halo without obscuring text",
                )
            ],
            audio_assets=[
                AudioAssetSpec(
                    experience="Readable confirmation cue",
                    kind="sound effect",
                    owner="audio.py",
                    technique="synthesized sine wave with a short decay envelope",
                    validation="cue is audible when an action succeeds",
                )
            ],
        )
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            workspace.prepare(replace=False)
            workspace.write_plan(plan)
            workspace.write_python("main.py", "def main():\n    return None\n")
            self.assertTrue((workspace.root / "game_plan.json").is_file())
            self.assertIn("def main", workspace.read_python_files()["main.py"])
            restored = workspace.read_plan()
            self.assertEqual(restored.rendering_strategy, plan.rendering_strategy)
            self.assertEqual(restored.render_effects, plan.render_effects)
            self.assertEqual(restored.audio_assets, plan.audio_assets)

    def test_does_not_replace_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            root.mkdir()
            (root / ".git").mkdir()
            (root / "keep.txt").write_text("keep", encoding="utf-8")
            with self.assertRaises(WorkspaceError):
                GameWorkspace(root).prepare(replace=True)
            self.assertTrue((root / "keep.txt").exists())


if __name__ == "__main__":
    unittest.main()
