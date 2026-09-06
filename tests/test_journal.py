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

    def test_invalidating_plan_and_revoking_qa_persists(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            journal = RunJournal.create(
                root,
                brief="test",
                model="model",
                renderer="moderngl",
                repair_attempts=2,
                smoke_timeout=8,
            )
            journal.complete_task("plan", "artifacts/planning/plan.json")
            journal.approve_qa_contract()

            journal.invalidate_task("plan", "shader contract changed")
            journal.revoke_qa_contract()
            loaded = RunJournal.load(root)

            self.assertEqual(loaded.state["tasks"]["plan"]["status"], "pending")
            self.assertEqual(
                loaded.state["tasks"]["plan"]["error"], "shader contract changed"
            )
            self.assertFalse(loaded.state["qa_approved"])

    def test_provider_change_persists_for_explicit_resume_switch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            journal = RunJournal.create(
                root,
                brief="test",
                model="local-model",
                renderer="pygame",
                repair_attempts=2,
                smoke_timeout=8,
                provider="ollama",
                provider_host="http://localhost:11434",
            )

            journal.change_provider("openai", "api-model")
            loaded = RunJournal.load(root)

            self.assertEqual(loaded.state["provider"], "openai")
            self.assertEqual(loaded.state["model"], "api-model")
            self.assertEqual(loaded.state["provider_host"], "")

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
