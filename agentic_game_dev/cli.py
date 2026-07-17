from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Sequence

from .orchestrator import GameBuilder
from .provider import AgentError, ClaudeProvider
from .validation import run_game
from .workspace import GameWorkspace, WorkspaceError


DEFAULT_MODEL = "claude-sonnet-5"


def _load_environment() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise RuntimeError(
            "python-dotenv is not installed. Run: python -m pip install -e ."
        ) from exc
    # Project-local configuration is authoritative for this CLI. Explicit
    # --model arguments are parsed afterwards and still take highest priority.
    load_dotenv(override=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-game-dev",
        description="Build a polished, asset-free Pygame game with a coordinated agent team.",
    )
    parser.add_argument("--model", default=os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL))
    parser.add_argument("--output", type=Path, default=Path("generated_game"))
    parser.add_argument("--renderer", choices=("pygame", "moderngl"), default="pygame")
    parser.add_argument("--repair-attempts", type=int, default=2)
    parser.add_argument("--smoke-timeout", type=float, default=8.0)

    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create", help="Design and generate a new game")
    create.add_argument("brief", nargs="?", help="Game description; prompted for when omitted")
    create.add_argument("--replace", action="store_true", help="Replace a non-empty output directory")
    create.add_argument("--run", action="store_true", help="Run generated code after validation")

    refine = subparsers.add_parser("refine", help="Apply playtest feedback to an existing game")
    refine.add_argument("feedback", nargs="?", help="Feedback; prompted for when omitted")
    refine.add_argument("--run", action="store_true", help="Run the game after refinement")
    return parser


def _require_api_key() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set")


async def _execute(args: argparse.Namespace) -> int:
    _require_api_key()
    workspace = GameWorkspace(args.output)
    builder = GameBuilder(
        ClaudeProvider(args.model),
        workspace,
        renderer=args.renderer,
        repair_attempts=max(0, args.repair_attempts),
        smoke_timeout=max(1.0, args.smoke_timeout),
    )

    if args.command == "create":
        brief = args.brief or input("Describe the game you want to create: ").strip()
        result = await builder.create(brief, replace=args.replace)
    else:
        feedback = args.feedback or input("Describe what should improve: ").strip()
        result = await builder.refine(feedback)

    print(result.report)
    if not result.ok:
        print(f"Generation stopped with validation errors. Inspect: {workspace.root}", file=sys.stderr)
        return 1
    print(f"Game ready: {workspace.root}")
    if args.run:
        print("Running generated code because --run was explicitly supplied.")
        return run_game(workspace.root)
    print(f"Run it with: {sys.executable} {workspace.root / 'main.py'}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    try:
        _load_environment()
        args = build_parser().parse_args(argv)
        return asyncio.run(_execute(args))
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
    except (AgentError, WorkspaceError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
