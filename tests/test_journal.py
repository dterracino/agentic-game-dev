from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agentic_game_dev.journal import RunJournal


class JournalTests(unittest.TestCase):
    def test_specification_is_snapshotted_and_read_from_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            journal = RunJournal.create(
                root,
                brief="test",
                model="test-model",
                renderer="pygame",
                repair_attempts=2,
                smoke_timeout=8,
            )

            artifact = journal.record_specification(
                "C:/designs/game.md", "# Game\nAuthoritative rule."
            )
            loaded = RunJournal.load(root)

            self.assertEqual(artifact, "artifacts/input/game_spec.md")
            self.assertEqual(
                loaded.read_specification(), "# Game\nAuthoritative rule.\n"
            )
            self.assertEqual(
                loaded.state["specification"]["source"], "C:/designs/game.md"
            )

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

    def test_add_repair_attempts_persists_extended_budget(self) -> None:
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

            journal.add_repair_attempts(2)

            self.assertEqual(RunJournal.load(root).state["repair_attempts"], 4)

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
