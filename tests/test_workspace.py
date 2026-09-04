from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentic_game_dev.models import FileSpec, GamePlan, RenderEffectSpec
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
                with self.subTest(name=name):
                    with self.assertRaises(WorkspaceError):
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
