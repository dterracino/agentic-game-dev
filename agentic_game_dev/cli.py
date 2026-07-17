from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from .activity import TerminalActivity
from .environment import GameEnvironment, GameEnvironmentError
from .journal import JournalError, RunJournal
from .models import DependencySpec
from .orchestrator import GameBuilder
from .provider import AgentError, ClaudeProvider, OllamaProvider
from .validation import run_game
from .workspace import GameWorkspace, WorkspaceError

DEFAULT_MODEL = "claude-sonnet-5"


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def _nonnegative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be at least 0")
    return number


def _load_environment() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise RuntimeError(
            "python-dotenv is not installed. Run: python -m pip install -e ."
        ) from exc
    load_dotenv(override=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-game-dev",
        description="Build a checkpointed Pygame game with a coordinated agent team.",
    )
    parser.add_argument(
        "--provider",
        choices=("anthropic", "ollama"),
        default=os.getenv("AGENT_PROVIDER", "anthropic").lower(),
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name; defaults to ANTHROPIC_MODEL or OLLAMA_MODEL for the provider",
    )
    parser.add_argument(
        "--ollama-host",
        default=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        help="Ollama server URL, including a server elsewhere on the local network",
    )
    parser.add_argument(
        "--qa-policy",
        choices=("ask", "approve"),
        default="ask",
        help="Display and ask to approve the QA contract, or approve it non-interactively",
    )
    parser.add_argument("--output", type=Path, default=Path("generated_game"))
    parser.add_argument("--renderer", choices=("pygame", "moderngl"), default="pygame")
    parser.add_argument("--repair-attempts", type=int, default=2)
    parser.add_argument("--smoke-timeout", type=float, default=8.0)
    parser.add_argument(
        "--dependency-policy",
        choices=("ask", "allow", "never"),
        default="ask",
        help="Ask before installs, approve structured dependencies, or forbid installs",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create", help="Design and generate a new game")
    create.add_argument("brief", nargs="?", help="Game description; prompted for when omitted")
    create.add_argument(
        "--replace", action="store_true", help="Replace a non-empty output directory"
    )
    create.add_argument(
        "--design-iterations",
        type=_positive_int,
        default=1,
        help="Total design passes before architecture (default: 1)",
    )
    create.add_argument(
        "--implementation-iterations",
        type=_nonnegative_int,
        default=0,
        help="Review-and-improve rounds after initial implementation (default: 0)",
    )
    create.add_argument("--run", action="store_true", help="Run generated code after validation")

    resume = subparsers.add_parser("resume", help="Continue an interrupted generated game")
    resume.add_argument(
        "--add-repair-attempts",
        type=_nonnegative_int,
        default=0,
        help="Extend the saved repair budget before resuming",
    )
    resume.add_argument("--run", action="store_true", help="Run the game after completion")

    subparsers.add_parser("run", help="Run an existing game and append output to its playtest log")

    refine = subparsers.add_parser("refine", help="Apply playtest feedback to an existing game")
    refine.add_argument("feedback", nargs="?", help="Feedback; prompted for when omitted")
    refine.add_argument("--run", action="store_true", help="Run the game after refinement")
    return parser


def _resolve_model(provider_name: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    if provider_name == "ollama":
        model = os.getenv("OLLAMA_MODEL", "").strip()
        if not model:
            raise RuntimeError(
                "OLLAMA_MODEL is not set. Add it to .env or pass --model for an Ollama run."
            )
        return model
    return os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)


def _require_credentials(provider_name: str) -> None:
    if provider_name == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set")


def _make_provider(
    provider_name: str,
    model: str,
    *,
    ollama_host: str,
    activity: TerminalActivity,
):
    if provider_name == "ollama":
        return OllamaProvider(model, host=ollama_host, activity=activity)
    return ClaudeProvider(model, activity=activity)


def _qa_approver(policy: str):
    def approve(_contract: str, path: Path) -> bool:
        print(f"QA contract saved to: {path}")
        if policy == "approve":
            print("QA policy approves this contract.")
            return True
        answer = input("Approve this gameplay contract and begin implementation? [y/N]: ")
        return answer.strip().lower() in {"y", "yes"}

    return approve


def _dependency_approver(policy: str):
    def approve(dependencies: Sequence[DependencySpec], reason: str) -> bool:
        print(reason)
        for dependency in dependencies:
            explanation = f" - {dependency.reason}" if dependency.reason else ""
            print(f"  {dependency.requirement} (import {dependency.import_name}){explanation}")
        if policy == "allow":
            print("Dependency policy allows this installation.")
            return True
        if policy == "never":
            print("Dependency policy forbids this installation.")
            return False
        answer = input("Install these packages into the game's .venv? [y/N]: ")
        return answer.strip().lower() in {"y", "yes"}

    return approve


async def _execute(args: argparse.Namespace) -> int:
    workspace = GameWorkspace(args.output)
    progress = print
    game_environment = GameEnvironment(workspace.root, progress=progress)
    if args.command == "run":
        if not (workspace.root / "main.py").is_file():
            raise WorkspaceError(f"No generated game with main.py found at: {workspace.root}")
        print(f"Running game; output log: {workspace.root / '.agentic' / 'playtest.log'}")
        return run_game(workspace.root, game_environment.python)

    approver = _dependency_approver(args.dependency_policy)
    qa_approver = _qa_approver(args.qa_policy)
    activity = TerminalActivity()

    if args.command == "resume":
        workspace.prepare_resume()
        saved_journal = RunJournal.load(workspace.root)
        if args.add_repair_attempts:
            saved_journal.add_repair_attempts(args.add_repair_attempts)
        saved = saved_journal.state
        provider_name = str(saved.get("provider", "anthropic"))
        model = str(saved["model"])
        provider_host = str(saved.get("provider_host", "") or args.ollama_host)
        _require_credentials(provider_name)
        provider = _make_provider(
            provider_name,
            model,
            ollama_host=provider_host,
            activity=activity,
        )
        builder = GameBuilder(
            provider,
            workspace,
            renderer=str(saved["renderer"]),
            repair_attempts=int(saved["repair_attempts"]),
            smoke_timeout=float(saved["smoke_timeout"]),
            environment=game_environment,
            dependency_approver=approver,
            qa_approver=qa_approver,
            progress=progress,
        )
        result = await builder.resume()
    else:
        provider_name = str(args.provider)
        model = _resolve_model(provider_name, args.model)
        _require_credentials(provider_name)
        provider = _make_provider(
            provider_name,
            model,
            ollama_host=args.ollama_host,
            activity=activity,
        )
        builder = GameBuilder(
            provider,
            workspace,
            renderer=args.renderer,
            repair_attempts=max(0, args.repair_attempts),
            smoke_timeout=max(1.0, args.smoke_timeout),
            design_iterations=(
                max(1, args.design_iterations) if args.command == "create" else 1
            ),
            implementation_iterations=(
                max(0, args.implementation_iterations) if args.command == "create" else 0
            ),
            environment=game_environment,
            dependency_approver=approver,
            qa_approver=qa_approver,
            progress=progress,
        )
        if args.command == "create":
            brief = args.brief or input("Describe the game you want to create: ").strip()
            result = await builder.create(brief, replace=args.replace)
        else:
            feedback = args.feedback or input("Describe what should improve: ").strip()
            result = await builder.refine(feedback)

    print(result.report)
    if not result.ok:
        print(
            f"Generation stopped with validation errors. Resume or inspect: {workspace.root}",
            file=sys.stderr,
        )
        return 1
    print(f"Game ready: {workspace.root}")
    if args.run:
        print("Running generated code with the game environment.")
        return run_game(workspace.root, game_environment.python)
    print(f"Run it with: agent-game-dev --output {workspace.root} run")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    try:
        _load_environment()
        args = build_parser().parse_args(argv)
        return asyncio.run(_execute(args))
    except KeyboardInterrupt:
        print("\nCancelled. Resume this run with the resume command.", file=sys.stderr)
        return 130
    except (
        AgentError,
        GameEnvironmentError,
        JournalError,
        WorkspaceError,
        RuntimeError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
