from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from agentic_game_dev.environment import GameEnvironment
from agentic_game_dev.models import DependencySpec


class EnvironmentTests(unittest.TestCase):
    def test_creates_environment_and_installs_with_game_python(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            calls: list[list[str]] = []
            environment: GameEnvironment

            def runner(command: list[str], **kwargs: object) -> SimpleNamespace:
                calls.append(command)
                if command[1:3] == ["-m", "venv"]:
                    environment.python.parent.mkdir(parents=True, exist_ok=True)
                    environment.python.touch()
                return SimpleNamespace(returncode=0, stdout="", stderr="")

            environment = GameEnvironment(
                root,
                base_python=Path(os.__file__),
                runner=runner,
                progress=lambda _message: None,
            )
            dependencies = [
                DependencySpec("pygame-ce", "pygame", ">=2.5,<3", "runtime"),
                DependencySpec("numpy", "numpy", ">=2,<3", "vectors"),
            ]

            environment.ensure(dependencies)

            self.assertEqual(calls[0][1:3], ["-m", "venv"])
            self.assertEqual(Path(calls[1][0]), environment.python)
            self.assertEqual(calls[1][1:4], ["-m", "pip", "install"])
            requirements = (root / "requirements.txt").read_text(encoding="utf-8")
            self.assertEqual(requirements, "numpy>=2,<3\npygame-ce>=2.5,<3\n")
            marker = json.loads(
                (root / ".agentic" / "environment.json").read_text(encoding="utf-8")
            )
            self.assertEqual(marker["python"], str(environment.python))
            self.assertTrue(environment.is_ready(dependencies))

    def test_requirement_rejects_command_syntax(self) -> None:
        dependency = DependencySpec(
            "numpy --extra-index-url=bad",
            "numpy",
            "",
            "unsafe",
        )
        with self.assertRaisesRegex(ValueError, "Unsafe dependency name"):
            dependency.validate()


if __name__ == "__main__":
    unittest.main()
