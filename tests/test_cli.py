from __future__ import annotations

import unittest
from unittest.mock import patch

from agentic_game_dev.cli import (
    _load_environment,
    _read_specification,
    _require_credentials,
    _resolve_model,
    build_parser,
)


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

    def test_create_parses_specification_path(self) -> None:
        args = build_parser().parse_args(
            ["create", "--spec", "adventure.md", "Build this game"]
        )

        self.assertEqual(str(args.spec), "adventure.md")

    def test_reads_nonempty_utf8_specification(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "game.md"
            path.write_text("# Game\nKeep the parser deterministic.\n", encoding="utf-8")

            content, source = _read_specification(path)

            self.assertIn("parser deterministic", content)
            self.assertEqual(source, str(path.resolve()))

    def test_ollama_options_and_model_environment(self) -> None:
        args = build_parser().parse_args(
            [
                "--provider",
                "ollama",
                "--ollama-host",
                "http://192.168.1.25:11434",
                "create",
                "A game",
            ]
        )
        with patch.dict("os.environ", {"OLLAMA_MODEL": "qwen-test"}, clear=False):
            model = _resolve_model(args.provider, args.model)

        self.assertEqual(model, "qwen-test")
        self.assertEqual(args.ollama_host, "http://192.168.1.25:11434")

    def test_ollama_requires_a_configured_model(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            self.assertRaisesRegex(RuntimeError, "OLLAMA_MODEL"),
        ):
            _resolve_model("ollama", None)

    def test_openai_options_model_and_credentials(self) -> None:
        args = build_parser().parse_args(
            ["--provider", "openai", "--model", "api-model", "create", "A game"]
        )
        self.assertEqual(args.provider, "openai")
        self.assertEqual(_resolve_model(args.provider, args.model), "api-model")

        with patch.dict(
            "os.environ",
            {
                "OPENAI_MODEL": "environment-model",
                "OPENAI_API_KEY": "test-key",
            },
            clear=True,
        ):
            self.assertEqual(_resolve_model("openai", None), "environment-model")
            _require_credentials("openai")

    def test_openai_requires_model_and_api_key(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            self.assertRaisesRegex(RuntimeError, "OPENAI_MODEL"),
        ):
            _resolve_model("openai", None)
        with (
            patch.dict("os.environ", {}, clear=True),
            self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"),
        ):
            _require_credentials("openai")

    def test_resume_parses_additional_repair_budget(self) -> None:
        args = build_parser().parse_args(
            [
                "resume",
                "--add-repair-attempts",
                "2",
                "--switch-provider",
                "openai",
                "--switch-model",
                "api-model",
            ]
        )

        self.assertEqual(args.add_repair_attempts, 2)
        self.assertEqual(args.switch_provider, "openai")
        self.assertEqual(args.switch_model, "api-model")

    def test_run_command_parses_without_iteration_options(self) -> None:
        args = build_parser().parse_args(["--output", "game", "run"])

        self.assertEqual(args.command, "run")

    def test_create_rejects_invalid_iteration_counts(self) -> None:
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["create", "A game", "--design-iterations", "0"])
        with self.assertRaises(SystemExit):
            build_parser().parse_args(
                ["create", "A game", "--implementation-iterations", "-1"]
            )


if __name__ == "__main__":
    unittest.main()
