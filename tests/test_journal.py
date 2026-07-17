from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentic_game_dev.journal import RunJournal


class JournalTests(unittest.TestCase):
    def test_running_task_becomes_pending_after_reload(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            journal = RunJournal.create(
                root,
                brief="test",
                model="model",
                renderer="pygame",
                repair_attempts=2,
                smoke_timeout=8,
            )
            journal.start_task("designer")

            resumed = RunJournal.load(root)

            self.assertEqual(resumed.state["tasks"]["designer"]["status"], "pending")

    def test_artifacts_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            journal = RunJournal.create(
                Path(temp),
                brief="test",
                model="model",
                renderer="pygame",
                repair_attempts=2,
                smoke_timeout=8,
            )
            relative = journal.write_json_artifact("planning/test.json", {"ok": True})
            journal.complete_task("test", relative)

            loaded = RunJournal.load(Path(temp))
            self.assertEqual(loaded.read_json_artifact(relative), {"ok": True})


if __name__ == "__main__":
    unittest.main()
