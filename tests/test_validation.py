from __future__ import annotations

import sys
from contextlib import redirect_stdout
from io import StringIO
import tempfile
import unittest
from pathlib import Path

from agentic_game_dev.validation import run_game, smoke_test, validate_project


class ValidationTests(unittest.TestCase):
    def test_static_compilation_reports_syntax_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "main.py").write_text("def broken(:\n", encoding="utf-8")

            result = validate_project(root)

            self.assertFalse(result.ok)
            self.assertIn("invalid syntax", result.report)

    def test_runtime_probe_rejects_clean_immediate_exit_and_logs_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "main.py").write_text(
                "def main():\n    return None\n\nif __name__ == '__main__':\n    main()\n",
                encoding="utf-8",
            )

            result = smoke_test(root, Path(sys.executable), 0.2)

            self.assertFalse(result.ok)
            self.assertIn("Game exited", result.report)
            log = (root / ".agentic" / "runtime.log").read_text(encoding="utf-8")
            self.assertIn("exit 0", log)

    def test_runtime_probe_accepts_game_that_remains_active(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "main.py").write_text(
                "import time\n\ndef main():\n"
                "    while True:\n        time.sleep(0.01)\n\n"
                "if __name__ == '__main__':\n    main()\n",
                encoding="utf-8",
            )

            result = smoke_test(root, Path(sys.executable), 0.1)

            self.assertTrue(result.ok, result.report)
            log = (root / ".agentic" / "runtime.log").read_text(encoding="utf-8")
            self.assertIn("active", log)

    def test_logged_run_captures_process_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "main.py").write_text(
                "print('playtest marker')\n",
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()):
                return_code = run_game(root, Path(sys.executable))

            self.assertEqual(return_code, 0)
            log = (root / ".agentic" / "playtest.log").read_text(encoding="utf-8")
            self.assertIn("playtest marker", log)
            self.assertIn("Exit code 0", log)


if __name__ == "__main__":
    unittest.main()
