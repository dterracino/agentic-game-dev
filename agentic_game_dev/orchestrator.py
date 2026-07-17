from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from .models import FileSpec, GamePlan
from .validation import ValidationResult, smoke_test, validate_project
from .workspace import GameWorkspace, WorkspaceError


class Provider(Protocol):
    async def text(self, *, role: str, prompt: str) -> str: ...

    async def structured(
        self,
        *,
        role: str,
        prompt: str,
        tool_name: str,
        description: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]: ...


PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "pitch": {"type": "string"},
        "core_loop": {"type": "array", "items": {"type": "string"}, "minItems": 3},
        "controls": {"type": "array", "items": {"type": "string"}},
        "quality_bar": {"type": "array", "items": {"type": "string"}, "minItems": 4},
        "files": {
            "type": "array",
            "minItems": 2,
            "maxItems": 8,
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "pattern": "^[a-zA-Z][a-zA-Z0-9_]*\\.py$"},
                    "purpose": {"type": "string"},
                    "public_api": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "purpose", "public_api"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "pitch", "core_loop", "controls", "quality_bar", "files"],
    "additionalProperties": False,
}

FILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "filename": {"type": "string"},
        "content": {"type": "string"},
    },
    "required": ["filename", "content"],
    "additionalProperties": False,
}

PATCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["filename", "content"],
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["files", "summary"],
    "additionalProperties": False,
}

DESIGNER_ROLE = """You are the lead game designer on a tiny expert team. Design a focused,
replayable game with a clear 30-second loop, meaningful decisions, fair escalation, readable
controls, and satisfying feedback. Scope it so one developer can implement it well. All visual
and audio assets must be drawn or synthesized in code. Be concrete and challenge vague ideas."""

ARCHITECT_ROLE = """You are a senior Python game architect. Produce a compact, coherent plan for
Python 3.11+ using Pygame, with ModernGL only when requested. Enforce separation of concerns and
DRY without over-engineering. Define exact cross-file APIs, a main.py main() entry point, delta-time
movement, explicit game states, and no circular imports. The finished game must run without external
assets. Never propose shell commands, network access, dynamic code execution, or file access outside
the game directory."""

IMPLEMENTER_ROLE = """You are an expert Python game developer. Implement exactly one complete file
from an agreed plan. Return executable source, not a sketch: no TODOs, ellipses, missing bodies, or
external assets. Use type hints, separation of concerns, delta time, clamped frame spikes, and
defensive Pygame initialization. Respect every declared cross-file API. Do not use network,
subprocess, eval, exec, pickle, or filesystem writes. main.py must expose main() and only run it
under an __name__ guard."""

REVIEWER_ROLE = """You are a meticulous senior gameplay and Python reviewer. Given the complete
small project and validation report, return full replacements only for files that need fixes.
Prioritize crashes, import/API mismatches, unwinnable or unclear play, frame-rate dependence,
missing state transitions, bad collision logic, and weak feedback. Preserve the architecture.
Never introduce external assets, network, subprocess, eval, exec, pickle, or filesystem writes."""


class GameBuilder:
    def __init__(
        self,
        provider: Provider,
        workspace: GameWorkspace,
        *,
        renderer: str = "pygame",
        repair_attempts: int = 2,
        smoke_timeout: float = 8.0,
        progress: Callable[[str], None] = print,
    ) -> None:
        self.provider = provider
        self.workspace = workspace
        self.renderer = renderer
        self.repair_attempts = repair_attempts
        self.smoke_timeout = smoke_timeout
        self.progress = progress

    async def create(self, brief: str, *, replace: bool = False) -> ValidationResult:
        if not brief.strip():
            raise ValueError("The game brief cannot be empty")
        self.progress("Effective options:")
        self.progress(f"  output: {self.workspace.root}")
        self.progress(f"  model: {getattr(self.provider, 'model', 'custom provider')}")
        self.progress(f"  renderer: {self.renderer}")
        self.progress(f"  repair attempts: {self.repair_attempts}")
        self.workspace.prepare(replace)

        self.progress("[1/4] Designer and architecture agents are exploring the brief...")
        design, architecture = await asyncio.gather(
            self.provider.text(
                role=DESIGNER_ROLE,
                prompt=f"Create a concise game design critique and proposal for:\n{brief}",
            ),
            self.provider.text(
                role=ARCHITECT_ROLE,
                prompt=(
                    f"Explore a robust architecture for this brief:\n{brief}\n"
                    f"Requested renderer: {self.renderer}"
                ),
            ),
        )

        self.progress("[2/4] Lead architect is synthesizing a contract...")
        raw_plan = await self.provider.structured(
            role=ARCHITECT_ROLE,
            prompt=(
                f"Original brief:\n{brief}\n\nDesigner proposal:\n{design}\n\n"
                f"Architecture proposal:\n{architecture}\n\nRenderer: {self.renderer}. "
                "Resolve conflicts and submit the final build contract. Include main.py exactly once."
            ),
            tool_name="submit_game_plan",
            description="Submit the final, implementation-ready game plan.",
            schema=PLAN_SCHEMA,
        )
        plan = GamePlan.from_dict(raw_plan)
        self._validate_plan(plan)
        self.workspace.write_plan(plan)

        self.progress(f"[3/4] {len(plan.files)} implementation agents are writing files...")
        generated = await asyncio.gather(
            *(self._generate_file(spec, plan) for spec in plan.files)
        )
        for spec, result in zip(plan.files, generated, strict=True):
            if result["filename"] != spec.name:
                raise WorkspaceError(
                    f"Implementer returned {result['filename']!r}; expected {spec.name!r}"
                )
            self.workspace.write_python(spec.name, str(result["content"]))

        self.progress("[4/4] Reviewer is validating and repairing the integrated game...")
        return await self._validate_and_repair(plan)

    async def refine(self, feedback: str) -> ValidationResult:
        files = self.workspace.read_python_files()
        if not files or "main.py" not in files:
            raise WorkspaceError("No generated game with main.py was found to refine")
        result = await self._review(
            context=f"User playtest feedback:\n{feedback}",
            allowed_names=set(files),
        )
        self._apply_replacements(result, set(files))
        return self._run_validation()

    async def _generate_file(self, spec: FileSpec, plan: GamePlan) -> dict[str, Any]:
        return await self.provider.structured(
            role=IMPLEMENTER_ROLE,
            prompt=(
                f"Complete plan:\n{plan.as_context()}\n\n"
                f"Your assigned file: {spec.name}\nPurpose: {spec.purpose}\n"
                f"Required public API: {', '.join(spec.public_api) or 'none'}\n"
                "Implement this file so it integrates exactly with the plan."
            ),
            tool_name="submit_python_file",
            description="Submit the complete source for the assigned Python file.",
            schema=FILE_SCHEMA,
        )

    async def _validate_and_repair(self, plan: GamePlan) -> ValidationResult:
        allowed = {spec.name for spec in plan.files}
        result = self._run_validation()
        for attempt in range(1, self.repair_attempts + 1):
            if result.ok:
                return result
            self.progress(f"  Repair pass {attempt}/{self.repair_attempts}: {result.report}")
            patch = await self._review(
                context=f"Automated validation failed:\n{result.report}",
                allowed_names=allowed,
            )
            if not patch["files"]:
                break
            self._apply_replacements(patch, allowed)
            result = self._run_validation()
        return result

    async def _review(self, *, context: str, allowed_names: set[str]) -> dict[str, Any]:
        snapshot = "\n\n".join(
            f"===== {name} =====\n{content}"
            for name, content in self.workspace.read_python_files().items()
        )
        return await self.provider.structured(
            role=REVIEWER_ROLE,
            prompt=(
                f"{context}\n\nAllowed filenames: {sorted(allowed_names)}\n\n"
                f"Complete project:\n{snapshot}"
            ),
            tool_name="submit_replacements",
            description="Submit complete replacement files and a concise review summary.",
            schema=PATCH_SCHEMA,
        )

    def _apply_replacements(self, patch: dict[str, Any], allowed: set[str]) -> None:
        for replacement in patch["files"]:
            filename = str(replacement["filename"])
            if filename not in allowed:
                raise WorkspaceError(f"Reviewer attempted to write unplanned file {filename!r}")
            self.workspace.write_python(filename, str(replacement["content"]))
        if patch.get("summary"):
            self.progress(f"  Reviewer: {patch['summary']}")

    def _run_validation(self) -> ValidationResult:
        static = validate_project(self.workspace.root)
        if not static.ok:
            return static
        return smoke_test(self.workspace.root, self.smoke_timeout)

    @staticmethod
    def _validate_plan(plan: GamePlan) -> None:
        names = [spec.name for spec in plan.files]
        if names.count("main.py") != 1:
            raise ValueError("Plan must contain main.py exactly once")
        if len(names) != len(set(names)):
            raise ValueError("Plan contains duplicate filenames")
