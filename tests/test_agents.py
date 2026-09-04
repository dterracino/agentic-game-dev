from __future__ import annotations

import unittest

from agentic_game_dev.agents import DesignerRole


class DesignerRoleTests(unittest.TestCase):
    def test_without_specification_uses_open_design_brief(self) -> None:
        prompt = DesignerRole.build_prompt("A tiny puzzle game", "")

        self.assertIn("Create a concise game design critique and proposal", prompt)
        self.assertNotIn("source of truth", prompt)

    def test_with_specification_reviews_without_replacing_it(self) -> None:
        prompt = DesignerRole.build_prompt(
            "Build my parser adventure",
            "# Inventory\nThere is no carrying limit.",
            round_number=1,
            total_rounds=2,
        )

        self.assertIn("Authoritative game specification", prompt)
        self.assertIn("There is no carrying limit.", prompt)
        self.assertIn("source of truth", prompt)
        self.assertIn("fill only genuine gaps", prompt)


if __name__ == "__main__":
    unittest.main()
