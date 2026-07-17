from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentic_game_dev.models import FileSpec, GamePlan
from agentic_game_dev.workspace import GameWorkspace, WorkspaceError


class WorkspaceTests(unittest.TestCase):
    def test_rejects_unsafe_filenames(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            workspace.prepare(replace=False)
            for name in ("../escape.py", "folder/file.py", "not-python.txt", "_hidden.py"):
                with self.subTest(name=name):
                    with self.assertRaises(WorkspaceError):
                        workspace.path_for(name)

    def test_writes_plan_and_valid_python(self) -> None:
        plan = GamePlan(
            title="Test",
            pitch="Test pitch",
            core_loop=["move", "choose", "score"],
            controls=["Arrows"],
            quality_bar=["clear", "fair", "juicy", "complete"],
            files=[FileSpec("main.py", "Entry point", ["main() -> None"])],
        )
        with tempfile.TemporaryDirectory() as temp:
            workspace = GameWorkspace(Path(temp) / "game")
            workspace.prepare(replace=False)
            workspace.write_plan(plan)
            workspace.write_python("main.py", "def main():\n    return None\n")
            self.assertTrue((workspace.root / "game_plan.json").is_file())
            self.assertIn("def main", workspace.read_python_files()["main.py"])

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
