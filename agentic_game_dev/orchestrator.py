from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

from .environment import GameEnvironment
from .journal import RunJournal
from .models import DependencySpec, FileSpec, GamePlan
from .validation import ValidationResult, smoke_test, validate_project
from .workspace import GameWorkspace, WorkspaceError


class Provider(Protocol):
    model: str

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


class Environment(Protocol):
    python: Path

    def is_ready(self, dependencies: Sequence[DependencySpec]) -> bool: ...

    def ensure(self, dependencies: Sequence[DependencySpec]) -> None: ...


DependencyApprover = Callable[[Sequence[DependencySpec], str], bool]


DEPENDENCY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "distribution": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]*$"},
        "import_name": {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
        "version": {"type": "string", "pattern": "^[A-Za-z0-9.,<>=!~*+_-]*$"},
        "reason": {"type": "string"},
    },
    "required": ["distribution", "import_name", "version", "reason"],
    "additionalProperties": False,
}

PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "pitch": {"type": "string"},
        "core_loop": {"type": "array", "items": {"type": "string"}, "minItems": 3},
        "controls": {"type": "array", "items": {"type": "string"}},
        "quality_bar": {"type": "array", "items": {"type": "string"}, "minItems": 4},
        "dependencies": {"type": "array", "items": DEPENDENCY_SCHEMA},
        "files": {
            "type": "array",
            "minItems": 2,
            "items": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "pattern": "^(?:[A-Za-z_][A-Za-z0-9_]*/)*[A-Za-z_][A-Za-z0-9_]*\\.py$",
                    },
                    "purpose": {"type": "string"},
                    "public_api": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "purpose", "public_api"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "title",
        "pitch",
        "core_loop",
        "controls",
        "quality_bar",
        "dependencies",
        "files",
    ],
    "additionalProperties": False,
}

FILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"filename": {"type": "string"}, "content": {"type": "string"}},
    "required": ["filename", "content"],
    "additionalProperties": False,
}

ITERATION_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "updated_plan": PLAN_SCHEMA,
        "files_to_change": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "pattern": "^(?:[A-Za-z_][A-Za-z0-9_]*/)*[A-Za-z_][A-Za-z0-9_]*\\.py$",
                    },
                    "reason": {"type": "string"},
                },
                "required": ["filename", "reason"],
                "additionalProperties": False,
            },
        },
        "review_summary": {"type": "string"},
    },
    "required": ["updated_plan", "files_to_change", "review_summary"],
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
movement, explicit game states, and no circular imports. Declare every third-party dependency with
its PyPI distribution, Python import name, version constraint, and reason. Prefer the standard
library unless a dependency materially improves the game. Never propose shell commands, network
access, dynamic code execution, or file access outside the game directory."""

IMPLEMENTER_ROLE = """You are an expert Python game developer. Implement exactly one complete file
from an agreed plan. Return executable source, not a sketch: no TODOs, ellipses, missing bodies, or
external assets. Use type hints, separation of concerns, delta time, clamped frame spikes, and
defensive Pygame initialization. Respect every declared cross-file API. Import third-party packages
only when they appear in the plan's declared dependency list. Do not use network, subprocess, eval,
exec, pickle, package installation, or filesystem writes. main.py must expose main() and only run it
under an __name__ guard."""

GAMEPLAY_REVIEWER_ROLE = """You are a critical game-design implementation reviewer. Assess the
complete implemented project against its original brief and final design. Focus on whether the
promised mechanics, progression, controls, feedback, game states, replayability, and polish are
actually represented in the code. Use the supplied validation result as runtime evidence, but do
not claim to have visually played the game. Return a concise, prioritized assessment."""

TECHNICAL_REVIEWER_ROLE = """You are a senior Python game-engineering reviewer. Assess the complete
project for correctness, separation of concerns, DRY design, coherent APIs, frame-rate independence,
state transitions, collision and resource handling, renderer usage, and maintainability. Identify
specific high-impact changes. Use validation output as evidence and do not invent runtime results."""

ITERATION_ARCHITECT_ROLE = """You are the lead architect for an implementation improvement round.
Reconcile gameplay and technical reviews into a focused updated build contract. Preserve every
existing planned file; additions are allowed when they represent genuine new responsibilities and
improve separation of concerns. Select only files that genuinely need changes. Declare every
third-party import. Never weaken working functionality merely to simplify testing."""

REVIEWER_ROLE = """You are a meticulous senior gameplay and Python reviewer. Given the complete
small project and validation report, return full replacements only for files that need fixes.
Prioritize crashes, import/API mismatches, unwinnable or unclear play, frame-rate dependence,
missing state transitions, bad collision logic, and weak feedback. Preserve the architecture and
declared dependency policy. Never introduce undeclared packages, external assets, network,
subprocess, eval, exec, pickle, package installation, or filesystem writes."""


class GameBuilder:
    def __init__(
        self,
        provider: Provider,
        workspace: GameWorkspace,
        *,
        renderer: str = "pygame",
        repair_attempts: int = 2,
        smoke_timeout: float = 8.0,
        design_iterations: int = 1,
        implementation_iterations: int = 0,
        environment: Environment | None = None,
        dependency_approver: DependencyApprover | None = None,
        progress: Callable[[str], None] = print,
    ) -> None:
        self.provider = provider
        self.workspace = workspace
        self.renderer = renderer
        self.repair_attempts = repair_attempts
        self.smoke_timeout = smoke_timeout
        self.design_iterations = max(1, design_iterations)
        self.implementation_iterations = max(0, implementation_iterations)
        self.progress = progress
        self.environment = environment or GameEnvironment(workspace.root, progress=progress)
        self.dependency_approver = dependency_approver or (lambda _deps, _reason: False)
        self.journal: RunJournal | None = None

    async def create(self, brief: str, *, replace: bool = False) -> ValidationResult:
        if not brief.strip():
            raise ValueError("The game brief cannot be empty")
        self._print_options()
        self.workspace.prepare(replace)
        self.workspace.write_support_file(".gitignore", ".venv/\n__pycache__/\n*.py[cod]\n")
        self.journal = RunJournal.create(
            self.workspace.root,
            brief=brief,
            model=self.provider.model,
            renderer=self.renderer,
            repair_attempts=self.repair_attempts,
            smoke_timeout=self.smoke_timeout,
            design_iterations=self.design_iterations,
            implementation_iterations=self.implementation_iterations,
        )
        try:
            return await self._continue_run()
        except BaseException as exc:
            self.journal.fail_task("run", exc)
            raise

    async def resume(self) -> ValidationResult:
        self.workspace.prepare_resume()
        self.journal = RunJournal.load(self.workspace.root)
        expected_model = str(self.journal.state["model"])
        if self.provider.model != expected_model:
            raise WorkspaceError(
                f"Run uses model {expected_model!r}, but provider uses {self.provider.model!r}"
            )
        self.renderer = str(self.journal.state["renderer"])
        self.repair_attempts = int(self.journal.state["repair_attempts"])
        self.smoke_timeout = float(self.journal.state["smoke_timeout"])
        self.design_iterations = int(self.journal.state.get("design_iterations", 1))
        self.implementation_iterations = int(
            self.journal.state.get("implementation_iterations", 0)
        )
        self.journal.mark_running()
        self._print_options(resuming=True)
        try:
            return await self._continue_run()
        except BaseException as exc:
            self.journal.fail_task("run", exc)
            raise

    async def _continue_run(self) -> ValidationResult:
        journal = self._journal()
        brief = str(journal.state["brief"])

        journal.set_stage("design")
        self.progress(
            f"[1/7] Running {self.design_iterations} checkpointed design "
            f"{'pass' if self.design_iterations == 1 else 'passes'}..."
        )
        design = await self._run_design_iterations(brief)

        journal.set_stage("plan")
        self.progress("[2/7] Architect is producing the dependency-aware build contract...")
        architecture = await self._text_checkpoint(
            "architecture",
            "planning/architecture.txt",
            role=ARCHITECT_ROLE,
            prompt=(
                f"Explore a robust architecture for this brief:\n{brief}\n\n"
                f"Final iterated design:\n{design}\n\nRequested renderer: {self.renderer}"
            ),
        )
        plan = await self._plan_checkpoint(brief, design, architecture)
        self.workspace.write_plan(plan)

        journal.set_stage("environment")
        self.progress("[3/7] Preparing the isolated game environment...")
        self._ensure_environment(plan, "Dependencies declared by the game plan")

        journal.set_stage("implementation")
        pending = [spec for spec in plan.files if not self._restore_completed_file(spec)]
        if pending:
            self.progress(
                f"[4/7] {len(pending)} implementation agents are writing checkpointed files..."
            )
            outcomes = await asyncio.gather(
                *(self._generate_file_checkpoint(spec, plan) for spec in pending),
                return_exceptions=True,
            )
            failures = [item for item in outcomes if isinstance(item, BaseException)]
            if failures:
                raise failures[0]
        else:
            self.progress("[4/7] All initial implementation files restored from checkpoints.")

        journal.set_stage("initial_validation")
        self.progress("[5/7] Validating and repairing the initial implementation...")
        result = await self._validate_and_repair(plan)
        if not result.ok:
            journal.fail_task("validation", result.report)
            return result

        journal.set_stage("implementation_iterations")
        if self.implementation_iterations:
            self.progress(
                f"[6/7] Running {self.implementation_iterations} implementation improvement "
                f"{'round' if self.implementation_iterations == 1 else 'rounds'}..."
            )
        else:
            self.progress("[6/7] No implementation improvement rounds requested.")
        for round_number in range(1, self.implementation_iterations + 1):
            plan, result = await self._run_implementation_iteration(
                round_number, brief, plan, result
            )
            if not result.ok:
                return result

        journal.set_stage("final_validation")
        self.progress("[7/7] Final validated project is checkpointed.")
        self.workspace.write_plan(plan)
        journal.mark_complete()
        return result

    async def _run_design_iterations(self, brief: str) -> str:
        design = ""
        for round_number in range(1, self.design_iterations + 1):
            if round_number == 1:
                task_name = "designer"
                artifact_name = "planning/designer.txt"
                prompt = f"Create a concise game design critique and proposal for:\n{brief}"
            else:
                task_name = f"design:{round_number:03d}"
                artifact_name = f"planning/design_{round_number:03d}.txt"
                prompt = (
                    f"Original brief:\n{brief}\n\nPrevious design:\n{design}\n\n"
                    f"This is design pass {round_number}/{self.design_iterations}. Critique the "
                    "previous design, retain its strongest decisions, resolve weaknesses and vague "
                    "areas, and return a complete replacement design ready for architecture."
                )
            self.progress(f"  Design pass {round_number}/{self.design_iterations}")
            design = await self._text_checkpoint(
                task_name, artifact_name, role=DESIGNER_ROLE, prompt=prompt
            )
        return design

    async def refine(self, feedback: str) -> ValidationResult:
        files = self.workspace.read_python_files()
        if not files or "main.py" not in files:
            raise WorkspaceError("No generated game with main.py was found to refine")
        plan = self.workspace.read_plan()
        if not self.environment.is_ready(plan.dependencies):
            raise WorkspaceError("The game environment is not ready; resume the build first")
        result = await self._review(
            context=f"User playtest feedback:\n{feedback}",
            allowed_names=set(files),
        )
        self._apply_replacements(result, set(files))
        return self._run_validation()

    async def _run_implementation_iteration(
        self,
        round_number: int,
        brief: str,
        current_plan: GamePlan,
        previous_validation: ValidationResult,
    ) -> tuple[GamePlan, ValidationResult]:
        prefix = f"iteration:{round_number:03d}"
        directory = f"iterations/{round_number:03d}"
        self.progress(
            f"  Implementation round {round_number}/{self.implementation_iterations}: "
            "gameplay and technical reviews"
        )
        context = (
            f"Original brief:\n{brief}\n\nFinal design/build contract:\n"
            f"{current_plan.as_context()}\n\nLatest validation:\n"
            f"{previous_validation.report}\n\nComplete project:\n{self._project_snapshot()}"
        )
        reviews = await asyncio.gather(
            self._text_checkpoint(
                f"{prefix}:gameplay_review",
                f"{directory}/gameplay_review.txt",
                role=GAMEPLAY_REVIEWER_ROLE,
                prompt=context,
            ),
            self._text_checkpoint(
                f"{prefix}:technical_review",
                f"{directory}/technical_review.txt",
                role=TECHNICAL_REVIEWER_ROLE,
                prompt=context,
            ),
            return_exceptions=True,
        )
        failures = [item for item in reviews if isinstance(item, BaseException)]
        if failures:
            raise failures[0]
        gameplay_review, technical_review = (str(item) for item in reviews)

        plan, changes, summary = await self._iteration_plan_checkpoint(
            round_number, brief, current_plan, gameplay_review, technical_review
        )
        self.workspace.write_plan(plan)
        self._ensure_environment(
            plan,
            f"Dependencies added by implementation round {round_number}",
            task_name=f"{prefix}:environment",
        )
        if summary:
            self.progress(f"    Improvement plan: {summary}")

        pending = [
            (spec, reason)
            for spec, reason in changes
            if not self._restore_iteration_file(round_number, spec)
        ]
        if pending:
            self.progress(f"    Updating {len(pending)} checkpointed files...")
            snapshot = self._project_snapshot()
            outcomes = await asyncio.gather(
                *(
                    self._generate_iteration_file_checkpoint(
                        round_number,
                        spec,
                        reason,
                        plan,
                        gameplay_review,
                        technical_review,
                        snapshot,
                    )
                    for spec, reason in pending
                ),
                return_exceptions=True,
            )
            failures = [item for item in outcomes if isinstance(item, BaseException)]
            if failures:
                raise failures[0]
        else:
            self.progress("    All planned file changes restored from checkpoints.")

        result = await self._validate_and_repair(
            plan,
            checkpoint_prefix=prefix,
            plan_task_name=f"{prefix}:plan",
        )
        if not result.ok:
            self._journal().fail_task(f"{prefix}:validation", result.report)
        return plan, result

    async def _iteration_plan_checkpoint(
        self,
        round_number: int,
        brief: str,
        current_plan: GamePlan,
        gameplay_review: str,
        technical_review: str,
    ) -> tuple[GamePlan, list[tuple[FileSpec, str]], str]:
        journal = self._journal()
        prefix = f"iteration:{round_number:03d}"
        task_name = f"{prefix}:plan"
        if journal.task_complete(task_name):
            artifact = journal.task_artifact(task_name)
            if not artifact:
                raise WorkspaceError(f"Implementation round {round_number} plan has no artifact")
            self.progress(f"    Reusing checkpoint: implementation plan {round_number}")
            raw = dict(journal.read_json_artifact(artifact))
        else:
            journal.start_task(task_name)
            try:
                raw = await self.provider.structured(
                    role=ITERATION_ARCHITECT_ROLE,
                    prompt=(
                        f"Original brief:\n{brief}\n\nCurrent contract:\n"
                        f"{current_plan.as_context()}\n\nGameplay review:\n{gameplay_review}\n\n"
                        f"Technical review:\n{technical_review}\n\nSubmit the complete updated "
                        "contract and the exact Python files to change. Preserve all existing "
                        "planned filenames; add files only for genuine new responsibilities."
                    ),
                    tool_name="submit_iteration_plan",
                    description="Submit an updated build contract and focused file-change list.",
                    schema=ITERATION_PLAN_SCHEMA,
                )
                normalized = self._normalize_plan(
                    GamePlan.from_dict(dict(raw["updated_plan"]))
                )
                self._validate_plan(normalized)
                previous_names = {spec.name for spec in current_plan.files}
                updated_names = {spec.name for spec in normalized.files}
                removed = sorted(previous_names - updated_names)
                if removed:
                    raise WorkspaceError(
                        "Implementation iteration attempted to remove planned files: "
                        + ", ".join(removed)
                    )
                selected = [str(item["filename"]) for item in raw["files_to_change"]]
                unknown = sorted(set(selected) - updated_names)
                if unknown:
                    raise WorkspaceError(
                        "Implementation plan selected unplanned files: "
                        + ", ".join(unknown)
                    )
                if len(selected) != len(set(selected)):
                    raise WorkspaceError("Implementation plan selected duplicate files")
                raw = dict(raw)
                raw["updated_plan"] = normalized.as_dict()
                artifact = journal.write_json_artifact(
                    f"iterations/{round_number:03d}/plan.json", raw
                )
                journal.complete_task(task_name, artifact)
            except BaseException as exc:
                journal.fail_task(task_name, exc)
                raise

        plan = GamePlan.from_dict(dict(raw["updated_plan"]))
        self._validate_plan(plan)
        removed = sorted(
            {spec.name for spec in current_plan.files}
            - {spec.name for spec in plan.files}
        )
        if removed:
            raise WorkspaceError(
                "Implementation iteration attempted to remove planned files: "
                + ", ".join(removed)
            )
        specs = {spec.name: spec for spec in plan.files}
        changes: list[tuple[FileSpec, str]] = []
        seen: set[str] = set()
        for item in raw["files_to_change"]:
            filename = str(item["filename"])
            if filename not in specs:
                raise WorkspaceError(f"Implementation plan selected unplanned file {filename!r}")
            if filename in seen:
                raise WorkspaceError(f"Implementation plan selected duplicate file {filename!r}")
            seen.add(filename)
            changes.append((specs[filename], str(item["reason"])))
        return plan, changes, str(raw.get("review_summary", ""))

    def _restore_iteration_file(self, round_number: int, spec: FileSpec) -> bool:
        journal = self._journal()
        task_name = f"iteration:{round_number:03d}:file:{spec.name}"
        artifact = journal.task_artifact(task_name)
        if not artifact:
            return False
        result = journal.read_json_artifact(artifact)
        if result.get("filename") != spec.name:
            raise WorkspaceError(f"Corrupt iteration checkpoint for {spec.name}")
        self.workspace.write_python(spec.name, str(result["content"]))
        if not journal.task_complete(task_name):
            journal.complete_task(task_name, artifact)
        self.progress(f"    Reusing checkpoint: round {round_number} {spec.name}")
        return True

    async def _generate_iteration_file_checkpoint(
        self,
        round_number: int,
        spec: FileSpec,
        reason: str,
        plan: GamePlan,
        gameplay_review: str,
        technical_review: str,
        snapshot: str,
    ) -> str:
        journal = self._journal()
        task_name = f"iteration:{round_number:03d}:file:{spec.name}"
        journal.start_task(task_name)
        try:
            result = await self.provider.structured(
                role=IMPLEMENTER_ROLE,
                prompt=(
                    f"Updated complete plan:\n{plan.as_context()}\n\n"
                    f"Gameplay review:\n{gameplay_review}\n\nTechnical review:\n"
                    f"{technical_review}\n\nComplete project before this round:\n{snapshot}\n\n"
                    f"Your assigned file: {spec.name}\nReason for change: {reason}\n"
                    f"Purpose: {spec.purpose}\nRequired public API: "
                    f"{', '.join(spec.public_api) or 'none'}\nReturn the complete revised file, "
                    "integrated with both the current project and updated contract."
                ),
                tool_name="submit_python_file",
                description="Submit one complete revised or newly added Python source file.",
                schema=FILE_SCHEMA,
            )
            if result["filename"] != spec.name:
                raise WorkspaceError(
                    f"Implementer returned {result['filename']!r}; expected {spec.name!r}"
                )
            artifact = journal.write_json_artifact(
                f"iterations/{round_number:03d}/files/{spec.name}.json", result
            )
            journal.set_task_artifact(task_name, artifact)
            self.workspace.write_python(spec.name, str(result["content"]))
            journal.complete_task(task_name, artifact)
            return spec.name
        except BaseException as exc:
            journal.fail_task(task_name, exc)
            raise

    def _project_snapshot(self) -> str:
        return "\n\n".join(
            f"===== {name} =====\n{content}"
            for name, content in self.workspace.read_python_files().items()
        )

    async def _text_checkpoint(
        self,
        task_name: str,
        artifact_name: str,
        *,
        role: str,
        prompt: str,
    ) -> str:
        journal = self._journal()
        if journal.task_complete(task_name):
            artifact = journal.task_artifact(task_name)
            if artifact:
                self.progress(f"  Reusing checkpoint: {task_name}")
                return journal.read_text_artifact(artifact)
        journal.start_task(task_name)
        try:
            response = await self.provider.text(role=role, prompt=prompt)
            artifact = journal.write_text_artifact(artifact_name, response)
            journal.complete_task(task_name, artifact)
            return response
        except BaseException as exc:
            journal.fail_task(task_name, exc)
            raise

    async def _plan_checkpoint(
        self,
        brief: str,
        design: str,
        architecture: str,
    ) -> GamePlan:
        journal = self._journal()
        task_name = "plan"
        if journal.task_complete(task_name):
            artifact = journal.task_artifact(task_name)
            if not artifact:
                raise WorkspaceError("Plan checkpoint has no artifact")
            self.progress("  Reusing checkpoint: plan")
            return GamePlan.from_dict(journal.read_json_artifact(artifact))
        journal.start_task(task_name)
        try:
            raw_plan = await self.provider.structured(
                role=ARCHITECT_ROLE,
                prompt=(
                    f"Original brief:\n{brief}\n\nDesigner proposal:\n{design}\n\n"
                    f"Architecture proposal:\n{architecture}\n\nRenderer: {self.renderer}. "
                    "Resolve conflicts and submit the final build contract. Include main.py exactly "
                    "once and declare every non-standard-library import."
                ),
                tool_name="submit_game_plan",
                description="Submit the final implementation and dependency contract.",
                schema=PLAN_SCHEMA,
            )
            plan = self._normalize_plan(GamePlan.from_dict(raw_plan))
            self._validate_plan(plan)
            artifact = journal.write_json_artifact("planning/plan.json", plan.as_dict())
            journal.complete_task(task_name, artifact)
            return plan
        except BaseException as exc:
            journal.fail_task(task_name, exc)
            raise

    def _restore_completed_file(self, spec: FileSpec) -> bool:
        journal = self._journal()
        task_name = f"file:{spec.name}"
        artifact = journal.task_artifact(task_name)
        if not artifact:
            return False
        result = journal.read_json_artifact(artifact)
        if result.get("filename") != spec.name:
            raise WorkspaceError(f"Corrupt file checkpoint for {spec.name}")
        self.workspace.write_python(spec.name, str(result["content"]))
        if not journal.task_complete(task_name):
            journal.complete_task(task_name, artifact)
        self.progress(f"  Reusing checkpoint: {spec.name}")
        return True

    async def _generate_file_checkpoint(self, spec: FileSpec, plan: GamePlan) -> str:
        journal = self._journal()
        task_name = f"file:{spec.name}"
        journal.start_task(task_name)
        try:
            result = await self.provider.structured(
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
            if result["filename"] != spec.name:
                raise WorkspaceError(
                    f"Implementer returned {result['filename']!r}; expected {spec.name!r}"
                )
            artifact = journal.write_json_artifact(f"files/{spec.name}.json", result)
            journal.set_task_artifact(task_name, artifact)
            self.workspace.write_python(spec.name, str(result["content"]))
            journal.complete_task(task_name, artifact)
            return spec.name
        except BaseException as exc:
            journal.fail_task(task_name, exc)
            raise

    def _ensure_environment(
        self,
        plan: GamePlan,
        reason: str,
        *,
        task_name: str = "environment",
    ) -> None:
        journal = self._journal()
        requirements = "\n".join(
            sorted({item.requirement for item in plan.dependencies}, key=str.lower)
        )
        self.workspace.write_support_file("requirements.txt", requirements)
        if self.environment.is_ready(plan.dependencies):
            if not journal.task_complete(task_name):
                journal.complete_task(task_name)
            self.progress("  Reusing game environment checkpoint.")
            return
        if not self.dependency_approver(plan.dependencies, reason):
            raise WorkspaceError("Dependency installation was not approved")
        journal.start_task(task_name)
        try:
            self.environment.ensure(plan.dependencies)
            journal.complete_task(task_name)
        except BaseException as exc:
            journal.fail_task(task_name, exc)
            raise

    async def _validate_and_repair(
        self,
        plan: GamePlan,
        *,
        checkpoint_prefix: str = "",
        plan_task_name: str = "plan",
    ) -> ValidationResult:
        journal = self._journal()
        allowed = {spec.name for spec in plan.files}
        validation_task = (
            f"{checkpoint_prefix}:validation" if checkpoint_prefix else "validation"
        )

        for attempt in range(1, self.repair_attempts + 1):
            task_name = self._repair_task_name(checkpoint_prefix, attempt)
            if journal.task_complete(task_name):
                patch = await self._review_checkpoint(
                    attempt=attempt,
                    context="Restoring a completed repair checkpoint.",
                    allowed_names=allowed,
                    checkpoint_prefix=checkpoint_prefix,
                )
                self._apply_replacements(patch, allowed)

        result = self._handle_missing_dependency(
            plan,
            self._run_validation(),
            plan_task_name=plan_task_name,
            checkpoint_prefix=checkpoint_prefix,
        )
        for attempt in range(1, self.repair_attempts + 1):
            if result.ok:
                journal.complete_task(validation_task)
                return result
            task_name = self._repair_task_name(checkpoint_prefix, attempt)
            if journal.task_complete(task_name):
                continue
            self.progress(f"  Repair pass {attempt}/{self.repair_attempts}: {result.report}")
            patch = await self._review_checkpoint(
                attempt=attempt,
                context=f"Automated validation failed:\n{result.report}",
                allowed_names=allowed,
                checkpoint_prefix=checkpoint_prefix,
            )
            self._apply_replacements(patch, allowed)
            result = self._handle_missing_dependency(
                plan,
                self._run_validation(),
                plan_task_name=plan_task_name,
                checkpoint_prefix=checkpoint_prefix,
            )
        if result.ok:
            journal.complete_task(validation_task)
        return result

    def _handle_missing_dependency(
        self,
        plan: GamePlan,
        result: ValidationResult,
        *,
        plan_task_name: str = "plan",
        checkpoint_prefix: str = "",
    ) -> ValidationResult:
        module = result.missing_module
        if result.ok or not module:
            return result
        if module in {Path(spec.name).stem for spec in plan.files}:
            return result
        if plan.dependency_for_import(module):
            return result
        distribution = {
            "pygame": "pygame-ce",
            "moderngl": "moderngl",
            "numpy": "numpy",
        }.get(module, module)
        dependency = DependencySpec(
            distribution=distribution,
            import_name=module,
            reason=f"Generated code imports {module}; detected during smoke validation",
        )
        dependency.validate()
        if not self.dependency_approver(
            [dependency], f"An undeclared dependency was detected: {module}"
        ):
            self.progress(f"  Dependency {distribution!r} was declined; asking reviewer to revise.")
            return result
        plan.dependencies.append(dependency)
        self._validate_plan(plan)
        self.workspace.write_plan(plan)
        journal = self._journal()
        artifact = journal.task_artifact(plan_task_name)
        if artifact:
            saved = journal.read_json_artifact(artifact)
            if plan_task_name == "plan":
                saved = plan.as_dict()
            else:
                saved = dict(saved)
                saved["updated_plan"] = plan.as_dict()
            journal.write_json_artifact(artifact.removeprefix("artifacts/"), saved)
        prefix = f"{checkpoint_prefix}:" if checkpoint_prefix else ""
        task_name = f"{prefix}dependency:{distribution}"
        environment_task = f"{prefix}environment"
        journal.start_task(task_name)
        try:
            self.environment.ensure(plan.dependencies)
            journal.complete_task(task_name)
            journal.complete_task(environment_task)
        except BaseException as exc:
            journal.fail_task(task_name, exc)
            raise
        return self._run_validation()

    @staticmethod
    def _repair_task_name(checkpoint_prefix: str, attempt: int) -> str:
        prefix = f"{checkpoint_prefix}:" if checkpoint_prefix else ""
        return f"{prefix}repair:{attempt}"

    async def _review_checkpoint(
        self,
        *,
        attempt: int,
        context: str,
        allowed_names: set[str],
        checkpoint_prefix: str = "",
    ) -> dict[str, Any]:
        journal = self._journal()
        task_name = self._repair_task_name(checkpoint_prefix, attempt)
        artifact_prefix = checkpoint_prefix.replace(":", "_")
        directory = f"{artifact_prefix}/" if artifact_prefix else ""
        if journal.task_complete(task_name):
            artifact = journal.task_artifact(task_name)
            if not artifact:
                raise WorkspaceError(f"Repair checkpoint {attempt} has no artifact")
            self.progress(f"  Reusing checkpoint: {task_name}")
            return dict(journal.read_json_artifact(artifact))
        journal.start_task(task_name)
        try:
            patch = await self._review(context=context, allowed_names=allowed_names)
            artifact = journal.write_json_artifact(
                f"{directory}repairs/{attempt}.json", patch
            )
            journal.complete_task(task_name, artifact)
            return patch
        except BaseException as exc:
            journal.fail_task(task_name, exc)
            raise

    async def _review(self, *, context: str, allowed_names: set[str]) -> dict[str, Any]:
        return await self.provider.structured(
            role=REVIEWER_ROLE,
            prompt=(
                f"{context}\n\nAllowed filenames: {sorted(allowed_names)}\n\n"
                f"Complete project:\n{self._project_snapshot()}"
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
        return smoke_test(self.workspace.root, self.environment.python, self.smoke_timeout)

    def _normalize_plan(self, plan: GamePlan) -> GamePlan:
        baseline = [
            DependencySpec(
                distribution="pygame-ce",
                import_name="pygame",
                version=">=2.5,<3",
                reason="Required Pygame runtime",
            )
        ]
        if self.renderer == "moderngl":
            baseline.append(
                DependencySpec(
                    distribution="moderngl",
                    import_name="moderngl",
                    version=">=5.12,<6",
                    reason="Requested ModernGL renderer",
                )
            )
        baseline_imports = {item.import_name for item in baseline}
        dependencies = [
            item for item in plan.dependencies if item.import_name not in baseline_imports
        ]
        dependencies.extend(baseline)
        return GamePlan(
            title=plan.title,
            pitch=plan.pitch,
            core_loop=plan.core_loop,
            controls=plan.controls,
            quality_bar=plan.quality_bar,
            files=plan.files,
            dependencies=dependencies,
        )

    @staticmethod
    def _validate_plan(plan: GamePlan) -> None:
        names = [spec.name for spec in plan.files]
        if names.count("main.py") != 1:
            raise ValueError("Plan must contain main.py exactly once")
        if len(names) != len(set(names)):
            raise ValueError("Plan contains duplicate filenames")
        imports: set[str] = set()
        distributions: set[str] = set()
        for dependency in plan.dependencies:
            dependency.validate()
            normalized_distribution = dependency.distribution.lower()
            if dependency.import_name in imports:
                raise ValueError(f"Duplicate dependency import: {dependency.import_name}")
            if normalized_distribution in distributions:
                raise ValueError(f"Duplicate dependency: {dependency.distribution}")
            imports.add(dependency.import_name)
            distributions.add(normalized_distribution)

    def _print_options(self, *, resuming: bool = False) -> None:
        label = "Resuming with options:" if resuming else "Effective options:"
        self.progress(label)
        self.progress(f"  output: {self.workspace.root}")
        self.progress(f"  model: {self.provider.model}")
        self.progress(f"  renderer: {self.renderer}")
        self.progress(f"  design iterations: {self.design_iterations}")
        self.progress(f"  implementation iterations: {self.implementation_iterations}")
        self.progress(f"  repair attempts: {self.repair_attempts}")
        self.progress(f"  game environment: {self.environment.python}")

    def _journal(self) -> RunJournal:
        if self.journal is None:
            raise RuntimeError("Run journal has not been initialized")
        return self.journal
