from __future__ import annotations

import unittest

from agentic_game_dev.agents import ArchitectRole, DesignerRole
from agentic_game_dev.policies import DEFAULT_ENGINEERING_POLICY, get_renderer_profile


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

    def test_technical_role_composes_shared_policy_and_renderer_profile(self) -> None:
        prompt = ArchitectRole.system_prompt(
            DEFAULT_ENGINEERING_POLICY.prompt_section(),
            get_renderer_profile("moderngl").prompt_section(),
        )

        self.assertIn("Engineering policy", prompt)
        self.assertIn("separation of concerns", prompt)
        self.assertIn("Renderer profile (moderngl", prompt)
        self.assertIn("Translate technology-neutral visual descriptions", prompt)


if __name__ == "__main__":
    unittest.main()
