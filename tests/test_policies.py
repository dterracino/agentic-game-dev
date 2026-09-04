from __future__ import annotations

import unittest

from agentic_game_dev.policies import DEFAULT_ENGINEERING_POLICY, get_renderer_profile


class PolicyTests(unittest.TestCase):
    def test_engineering_policy_centralizes_architecture_rules(self) -> None:
        prompt = DEFAULT_ENGINEERING_POLICY.prompt_section()

        self.assertIn("separation of concerns", prompt)
        self.assertIn("DRY", prompt)
        self.assertIn("imports acyclic", prompt)
        self.assertIn("testable without opening a window", prompt)

    def test_moderngl_profile_maps_experiences_to_gpu_techniques(self) -> None:
        profile = get_renderer_profile("moderngl")
        prompt = profile.prompt_section()

        self.assertIn("real ModernGL context", prompt)
        self.assertIn("fragment shader passes", prompt)
        self.assertIn("Map every visual effect", prompt)

    def test_unknown_renderer_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown renderer"):
            get_renderer_profile("unknown")


if __name__ == "__main__":
    unittest.main()
