from __future__ import annotations

import unittest
from unittest.mock import patch

from agentic_game_dev.cli import _load_environment


class CliEnvironmentTests(unittest.TestCase):
    def test_dotenv_overrides_stale_process_values(self) -> None:
        with patch("dotenv.load_dotenv") as load_dotenv:
            _load_environment()

        load_dotenv.assert_called_once_with(override=True)


if __name__ == "__main__":
    unittest.main()
