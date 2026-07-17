from __future__ import annotations

import unittest
from unittest.mock import patch

from agentic_game_dev.cli import _load_environment, build_parser


class CliEnvironmentTests(unittest.TestCase):
    def test_dotenv_overrides_stale_process_values(self) -> None:
        with patch("dotenv.load_dotenv") as load_dotenv:
            _load_environment()

        load_dotenv.assert_called_once_with(override=True)

    def test_create_parses_iteration_counts(self) -> None:
        args = build_parser().parse_args(
            [
                "create",
                "A game",
                "--design-iterations",
                "3",
                "--implementation-iterations",
                "2",
            ]
        )

        self.assertEqual(args.design_iterations, 3)
        self.assertEqual(args.implementation_iterations, 2)

    def test_create_rejects_invalid_iteration_counts(self) -> None:
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["create", "A game", "--design-iterations", "0"])
        with self.assertRaises(SystemExit):
            build_parser().parse_args(
                ["create", "A game", "--implementation-iterations", "-1"]
            )


if __name__ == "__main__":
    unittest.main()
