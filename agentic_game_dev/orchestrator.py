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
        environment: Environment | None = None,
        dependency_approver: DependencyApprover | None = None,
        progress: Callable[[str], None] = print,
    ) -> None:
        self.provider = provider
        self.workspace = workspace
        self.renderer = renderer
        self.repair_attempts = repair_attempts
        self.smoke_timeout = smoke_timeout
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

        journal.set_stage("planning")
        self.progress("[1/5] Designer and architecture agents are exploring the brief...")
        proposals = await asyncio.gather(
            self._text_checkpoint(
                "designer",
                "planning/designer.txt",
                role=DESIGNER_ROLE,
                prompt=f"Create a concise game design critique and proposal for:\n{brief}",
            ),
            self._text_checkpoint(
                "architecture",
                "planning/architecture.txt",
                role=ARCHITECT_ROLE,
                prompt=(
                    f"Explore a robust architecture for this brief:\n{brief}\n"
                    f"Requested renderer: {self.renderer}"
                ),
            ),
            return_exceptions=True,
        )
        failures = [item for item in proposals if isinstance(item, BaseException)]
        if failures:
            raise failures[0]
        design, architecture = (str(item) for item in proposals)

        journal.set_stage("plan")
        self.progress("[2/5] Lead architect is synthesizing a dependency-aware contract...")
        plan = await self._plan_checkpoint(brief, design, architecture)
        self.workspace.write_plan(plan)

        journal.set_stage("environment")
        self.progress("[3/5] Preparing the isolated game environment...")
        self._ensure_environment(plan, "Dependencies declared by the game plan")

        journal.set_stage("implementation")
        pending = [spec for spec in plan.files if not self._restore_completed_file(spec)]
        if pending:
            self.progress(
                f"[4/5] {len(pending)} implementation agents are writing checkpointed files..."
            )
            outcomes = await asyncio.gather(
                *(self._generate_file_checkpoint(spec, plan) for spec in pending),
                return_exceptions=True,
            )
            failures = [item for item in outcomes if isinstance(item, BaseException)]
            if failures:
                raise failures[0]
        else:
            self.progress("[4/5] All implementation files restored from checkpoints.")

        journal.set_stage("validation")
        self.progress("[5/5] Reviewer is validating and repairing the integrated game...")
        result = await self._validate_and_repair(plan)
        if result.ok:
            journal.mark_complete()
        else:
            journal.fail_task("validation", result.report)
        return result
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

    def _ensure_environment(self, plan: GamePlan, reason: str) -> None:
        journal = self._journal()
        requirements = "\n".join(
            sorted({item.requirement for item in plan.dependencies}, key=str.lower)
        )
        self.workspace.write_support_file("requirements.txt", requirements)
        if self.environment.is_ready(plan.dependencies):
            if not journal.task_complete("environment"):
                journal.complete_task("environment")
            self.progress("  Reusing game environment checkpoint.")
            return
        if not self.dependency_approver(plan.dependencies, reason):
            raise WorkspaceError("Dependency installation was not approved")
        journal.start_task("environment")
        try:
            self.environment.ensure(plan.dependencies)
            journal.complete_task("environment")
        except BaseException as exc:
            journal.fail_task("environment", exc)
            raise

    async def _validate_and_repair(self, plan: GamePlan) -> ValidationResult:
        allowed = {spec.name for spec in plan.files}
        result = self._handle_missing_dependency(plan, self._run_validation())
        for attempt in range(1, self.repair_attempts + 1):
            if result.ok:
                self._journal().complete_task("validation")
                return result
            self.progress(f"  Repair pass {attempt}/{self.repair_attempts}: {result.report}")
            patch = await self._review_checkpoint(
                attempt=attempt,
                context=f"Automated validation failed:\n{result.report}",
                allowed_names=allowed,
            )
            self._apply_replacements(patch, allowed)
            result = self._handle_missing_dependency(plan, self._run_validation())
        if result.ok:
            self._journal().complete_task("validation")
        return result

    def _handle_missing_dependency(
        self,
        plan: GamePlan,
        result: ValidationResult,
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
            [dependency],
            f"An undeclared dependency was detected: {module}",
        ):
            self.progress(f"  Dependency {distribution!r} was declined; asking reviewer to revise.")
            return result
        plan.dependencies.append(dependency)
        self._validate_plan(plan)
        self.workspace.write_plan(plan)
        artifact = self._journal().task_artifact("plan")
        if artifact:
            relative = artifact.removeprefix("artifacts/")
            self._journal().write_json_artifact(relative, plan.as_dict())
        task_name = f"dependency:{distribution}"
        self._journal().start_task(task_name)
        try:
            self.environment.ensure(plan.dependencies)
            self._journal().complete_task(task_name)
            self._journal().complete_task("environment")
        except BaseException as exc:
            self._journal().fail_task(task_name, exc)
            raise
        return self._run_validation()

    async def _review_checkpoint(
        self,
        *,
        attempt: int,
        context: str,
        allowed_names: set[str],
    ) -> dict[str, Any]:
        journal = self._journal()
        task_name = f"repair:{attempt}"
        if journal.task_complete(task_name):
            artifact = journal.task_artifact(task_name)
            if not artifact:
                raise WorkspaceError(f"Repair checkpoint {attempt} has no artifact")
            self.progress(f"  Reusing checkpoint: repair {attempt}")
            return dict(journal.read_json_artifact(artifact))
        journal.start_task(task_name)
        try:
            patch = await self._review(context=context, allowed_names=allowed_names)
            artifact = journal.write_json_artifact(f"repairs/{attempt}.json", patch)
            journal.complete_task(task_name, artifact)
            return patch
        except BaseException as exc:
            journal.fail_task(task_name, exc)
            raise

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
        self.progress(f"  repair attempts: {self.repair_attempts}")
        self.progress(f"  game environment: {self.environment.python}")

    def _journal(self) -> RunJournal:
        if self.journal is None:
            raise RuntimeError("Run journal has not been initialized")
        return self.journal
