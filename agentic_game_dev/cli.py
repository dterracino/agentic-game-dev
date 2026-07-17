from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from .environment import GameEnvironment, GameEnvironmentError
from .journal import JournalError, RunJournal
from .models import DependencySpec
from .orchestrator import GameBuilder
from .provider import AgentError, ClaudeProvider
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
    parser.add_argument("--model", default=os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL))
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
    create.add_argument("--replace", action="store_true", help="Replace a non-empty output directory")
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
    resume.add_argument("--run", action="store_true", help="Run the game after completion")

    refine = subparsers.add_parser("refine", help="Apply playtest feedback to an existing game")
    refine.add_argument("feedback", nargs="?", help="Feedback; prompted for when omitted")
    refine.add_argument("--run", action="store_true", help="Run the game after refinement")
    return parser


def _require_api_key() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set")


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
    _require_api_key()
    workspace = GameWorkspace(args.output)
    progress = print
    game_environment = GameEnvironment(workspace.root, progress=progress)
    approver = _dependency_approver(args.dependency_policy)

    if args.command == "resume":
        workspace.prepare_resume()
        saved = RunJournal.load(workspace.root).state
        provider = ClaudeProvider(str(saved["model"]))
        builder = GameBuilder(
            provider,
            workspace,
            renderer=str(saved["renderer"]),
            repair_attempts=int(saved["repair_attempts"]),
            smoke_timeout=float(saved["smoke_timeout"]),
            environment=game_environment,
            dependency_approver=approver,
            progress=progress,
        )
        result = await builder.resume()
    else:
        provider = ClaudeProvider(args.model)
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
    print(f"Run it with: {game_environment.python} {workspace.root / 'main.py'}")
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
