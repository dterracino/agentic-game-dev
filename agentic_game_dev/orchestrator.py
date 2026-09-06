from __future__ import annotations

import ast
import asyncio
import json
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

from .agents import (
    AgentRole,
    ArchitectRole,
    DesignerRole,
    GameplayReviewerRole,
    ImplementerRole,
    IterationArchitectRole,
    QaAuthorRole,
    RepairReviewerRole,
    TechnicalReviewerRole,
)
from .environment import GameEnvironment
from .journal import RunJournal
from .models import DependencySpec, FileSpec, GamePlan
from .policies import DEFAULT_ENGINEERING_POLICY, get_renderer_profile
from .validation import (
    ValidationResult,
    smoke_test,
    validate_project,
    validate_renderer_project,
    validate_types,
)
from .workspace import GameWorkspace, WorkspaceError


class Provider(Protocol):
    model: str
    provider_name: str

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
QAApprover = Callable[[str, Path], bool]


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
        "rendering_strategy": {"type": "string", "minLength": 1},
        "render_effects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "experience": {"type": "string", "minLength": 1},
                    "technique": {"type": "string", "minLength": 1},
                    "owner": {"type": "string", "minLength": 1},
                    "validation": {"type": "string", "minLength": 1},
                    "source_files": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                },
                "required": [
                    "experience",
                    "technique",
                    "owner",
                    "validation",
                    "source_files",
                ],
                "additionalProperties": False,
            },
        },
        "visual_assets": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "experience": {"type": "string", "minLength": 1},
                    "kind": {"type": "string", "minLength": 1},
                    "owner": {"type": "string", "minLength": 1},
                    "technique": {"type": "string", "minLength": 1},
                    "validation": {"type": "string", "minLength": 1},
                },
                "required": [
                    "experience",
                    "kind",
                    "owner",
                    "technique",
                    "validation",
                ],
                "additionalProperties": False,
            },
        },
        "audio_assets": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "experience": {"type": "string", "minLength": 1},
                    "kind": {"type": "string", "minLength": 1},
                    "owner": {"type": "string", "minLength": 1},
                    "technique": {"type": "string", "minLength": 1},
                    "validation": {"type": "string", "minLength": 1},
                },
                "required": [
                    "experience",
                    "kind",
                    "owner",
                    "technique",
                    "validation",
                ],
                "additionalProperties": False,
            },
        },
        "dependencies": {"type": "array", "items": DEPENDENCY_SCHEMA},
        "files": {
            "type": "array",
            "minItems": 2,
            "items": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "pattern": (
                            "^(?:[A-Za-z_][A-Za-z0-9_]*/)*"
                            "[A-Za-z_][A-Za-z0-9_]*\\.(?:py|vert|frag|glsl)$"
                        ),
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
        "rendering_strategy",
        "render_effects",
        "visual_assets",
        "audio_assets",
        "dependencies",
        "files",
    ],
    "additionalProperties": False,
}

QA_CONTRACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "criteria": {
            "type": "array",
            "minItems": 6,
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "requirement": {"type": "string"},
                    "rationale": {"type": "string"},
                    "automated_test": {"type": "string"},
                    "scripted_playtest": {"type": "string"},
                    "visual_evidence": {"type": "string"},
                    "blocking": {"type": "boolean"},
                },
                "required": [
                    "id",
                    "requirement",
                    "rationale",
                    "automated_test",
                    "scripted_playtest",
                    "visual_evidence",
                    "blocking",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "criteria"],
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
                        "pattern": (
                            "^(?:[A-Za-z_][A-Za-z0-9_]*/)*"
                            "[A-Za-z_][A-Za-z0-9_]*\\.(?:py|vert|frag|glsl)$"
                        ),
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

FILE_GENERATION_ATTEMPTS = 3
PLAN_GENERATION_ATTEMPTS = 3
ARCHITECTURE_GENERATION_ATTEMPTS = 2

KNOWN_DEPENDENCY_CONSTRAINTS: dict[str, tuple[str, str]] = {
    "pygame_gui": ("pygame-gui", ">=0.6,<0.7"),
}


DESIGNER_ROLE = DesignerRole.system_prompt()


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
        qa_approver: QAApprover | None = None,
        progress: Callable[[str], None] = print,
        type_checker: Callable[[Path, Path], ValidationResult] | None = None,
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
        self.qa_approver = qa_approver or (lambda _contract, _path: True)
        self.type_checker = type_checker or validate_types
        self.journal: RunJournal | None = None

    async def create(
        self,
        brief: str,
        *,
        replace: bool = False,
        specification: str = "",
        specification_source: str = "",
    ) -> ValidationResult:
        if not brief.strip():
            raise ValueError("The game brief cannot be empty")
        if specification and not specification.strip():
            raise ValueError("The game specification cannot be empty")
        self._print_options()
        self.workspace.prepare(replace)
        self.workspace.write_support_file(".gitignore", ".venv/\n__pycache__/\n*.py[cod]\n")
        self.journal = RunJournal.create(
            self.workspace.root,
            brief=brief,
            model=self.provider.model,
            provider=self.provider.provider_name,
            provider_host=str(getattr(self.provider, "host", "")),
            renderer=self.renderer,
            repair_attempts=self.repair_attempts,
            smoke_timeout=self.smoke_timeout,
            design_iterations=self.design_iterations,
            implementation_iterations=self.implementation_iterations,
        )
        if specification:
            self.journal.record_specification(specification_source, specification)
        try:
            return await self._continue_run()
        except BaseException as exc:
            self.journal.fail_task("run", exc)
            raise

    async def resume(self) -> ValidationResult:
        self.workspace.prepare_resume()
        self.journal = RunJournal.load(self.workspace.root)
        expected_model = str(self.journal.state["model"])
        expected_provider = str(self.journal.state.get("provider", "anthropic"))
        if (
            self.provider.model != expected_model
            or self.provider.provider_name != expected_provider
        ):
            raise WorkspaceError(
                f"Run uses {expected_provider}/{expected_model}, but provider uses "
                f"{self.provider.provider_name}/{self.provider.model}"
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
        specification = journal.read_specification()

        journal.set_stage("design")
        self.progress(
            f"[1/7] Running {self.design_iterations} checkpointed design "
            f"{'pass' if self.design_iterations == 1 else 'passes'}..."
        )
        design = await self._run_design_iterations(brief, specification)

        journal.set_stage("plan")
        self.progress("[2/7] Architect is producing the dependency-aware build contract...")
        architecture = await self._architecture_checkpoint(brief, design)
        plan = await self._plan_checkpoint(brief, design, architecture)
        self.workspace.write_plan(plan)

        journal.set_stage("qa_contract")
        self.progress("[3/8] QA author is defining executable gameplay acceptance criteria...")
        qa_contract = await self._qa_contract_checkpoint(brief, design, architecture, plan)
        qa_path = self.workspace.root / "QA_ACCEPTANCE.md"
        self.workspace.write_support_file("QA_ACCEPTANCE.md", qa_contract)
        if not bool(journal.state.get("qa_approved", False)):
            self.progress("")
            self.progress(qa_contract)
            self.progress("")
            if not self.qa_approver(qa_contract, qa_path):
                raise WorkspaceError(
                    "QA acceptance contract was not approved. The design and QA checkpoints are "
                    "saved; resume the run when ready to review it again."
                )
            journal.approve_qa_contract()
            self.progress("QA acceptance contract approved.")
        else:
            self.progress("  Reusing approved QA acceptance contract.")

        journal.set_stage("environment")
        self.progress("[4/8] Preparing the isolated game environment...")
        self._ensure_environment(plan, "Dependencies declared by the game plan")

        journal.set_stage("implementation")
        pending = [spec for spec in plan.files if not self._restore_completed_file(spec)]
        if pending:
            self.progress(
                f"[5/8] Lead game developer is implementing {len(pending)} ordered checkpoints..."
            )
            for number, spec in enumerate(pending, start=1):
                self.progress(f"  Lead checkpoint {number}/{len(pending)}: {spec.name}")
                await self._generate_file_checkpoint(spec, plan, qa_contract)
        else:
            self.progress("[5/8] All lead-developer checkpoints restored.")

        journal.set_stage("initial_validation")
        self.progress("[6/8] Validating and repairing the initial implementation...")
        result = await self._validate_and_repair(plan)
        if not result.ok:
            journal.fail_task("validation", result.report)
            return result

        journal.set_stage("implementation_iterations")
        if self.implementation_iterations:
            self.progress(
                f"[7/8] Running {self.implementation_iterations} implementation improvement "
                f"{'round' if self.implementation_iterations == 1 else 'rounds'}..."
            )
        else:
            self.progress("[7/8] No implementation improvement rounds requested.")
        for round_number in range(1, self.implementation_iterations + 1):
            plan, result = await self._run_implementation_iteration(
                round_number, brief, plan, result
            )
            if not result.ok:
                return result

        journal.set_stage("refinements")
        refinements_restored = self._restore_refinement_checkpoints(plan)
        if refinements_restored:
            self.progress("[8/8] Validating restored user refinements...")
            result = self._handle_missing_dependency(
                plan, self._run_validation(), plan_task_name="refinement"
            )
            if not result.ok:
                journal.fail_task("refinement_validation", result.report)
                return result
        else:
            self.progress("[8/8] Final validated project is checkpointed.")

        journal.set_stage("final_validation")
        self.workspace.write_plan(plan)
        journal.mark_complete()
        return result

    async def _run_design_iterations(self, brief: str, specification: str = "") -> str:
        design = ""
        for round_number in range(1, self.design_iterations + 1):
            if round_number == 1:
                task_name = "designer"
                artifact_name = "planning/designer.txt"
            else:
                task_name = f"design:{round_number:03d}"
                artifact_name = f"planning/design_{round_number:03d}.txt"
            prompt = DesignerRole.build_prompt(
                brief,
                specification,
                previous_design=design,
                round_number=round_number,
                total_rounds=self.design_iterations,
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

        self.journal = RunJournal.load(self.workspace.root)
        self.journal.mark_running()
        existing = [
            int(name.split(":", 1)[1])
            for name in self.journal.state.get("tasks", {})
            if name.startswith("refine:") and name.split(":", 1)[1].isdigit()
        ]
        refinement_number = max(existing, default=0) + 1
        task_name = f"refine:{refinement_number:03d}"
        self.journal.start_task(task_name)
        try:
            patch = self._normalize_patch(
                await self._review(
                    context=f"User playtest feedback:\n{feedback}",
                    allowed_names=set(files),
                    allow_new=True,
                )
            )
            artifact = self.journal.write_json_artifact(
                f"refinements/{refinement_number:03d}.json",
                patch,
            )
            self.journal.set_task_artifact(task_name, artifact)
            self._apply_refinement_patch(patch, plan)
            result = self._handle_missing_dependency(
                plan, self._run_validation(), plan_task_name="refinement"
            )
            if result.ok:
                self.journal.complete_task(task_name, artifact)
                self.journal.mark_complete()
            else:
                self.journal.fail_task(task_name, result.report)
            return result
        except BaseException as exc:
            self.journal.fail_task(task_name, exc)
            raise

    def _apply_refinement_patch(self, patch: dict[str, Any], plan: GamePlan) -> None:
        patch = self._normalize_patch(patch)
        specs = {spec.name: spec for spec in plan.files}
        summary = str(patch.get("summary", "")).strip()
        for replacement in patch["files"]:
            filename = str(replacement["filename"])
            content = str(replacement["content"])
            self.workspace.write_generated_source(filename, content)
            if filename not in specs:
                spec = FileSpec(
                    name=filename,
                    purpose=(
                        f"Added during refinement: {summary[:200]}"
                        if summary
                        else "Added during user-directed refinement"
                    ),
                    public_api=[],
                )
                main_index = next(
                    (
                        index
                        for index, planned in enumerate(plan.files)
                        if planned.name == "main.py"
                    ),
                    len(plan.files),
                )
                plan.files.insert(main_index, spec)
                specs[filename] = spec

        self._validate_plan(plan)
        self.workspace.write_plan(plan)
        if summary:
            self.progress(f"  Reviewer: {summary}")

    def _restore_refinement_checkpoints(self, plan: GamePlan) -> bool:
        journal = self._journal()
        restored = False
        task_names = sorted(
            name
            for name, task in journal.state.get("tasks", {}).items()
            if name.startswith("refine:") and task.get("artifact")
        )
        for task_name in task_names:
            artifact = journal.task_artifact(task_name)
            if not artifact:
                continue
            patch = self._normalize_patch(
                dict(journal.read_json_artifact(artifact))
            )
            self._apply_refinement_patch(patch, plan)
            restored = True
            self.progress(f"  Reusing checkpoint artifact: {task_name}")
        return restored
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
        qa_contract = (self.workspace.root / "QA_ACCEPTANCE.md").read_text(encoding="utf-8")
        context = (
            f"{self._specification_context()}"
            f"Original brief:\n{brief}\n\nFinal design/build contract:\n"
            f"{current_plan.as_context()}\n\nApproved QA contract:\n{qa_contract}\n\n"
            f"Latest validation:\n"
            f"{previous_validation.report}\n\nComplete project:\n{self._project_snapshot()}"
            f"\n\nDiagnostic log tails:\n{self._diagnostic_logs()}"
        )
        reviews = await asyncio.gather(
            self._text_checkpoint(
                f"{prefix}:gameplay_review",
                f"{directory}/gameplay_review.txt",
                role=self._technical_role(GameplayReviewerRole),
                prompt=context,
            ),
            self._text_checkpoint(
                f"{prefix}:technical_review",
                f"{directory}/technical_review.txt",
                role=self._technical_role(TechnicalReviewerRole),
                prompt=context,
            ),
            return_exceptions=True,
        )
        failures = [item for item in reviews if isinstance(item, BaseException)]
        if failures:
            raise failures[0]
        gameplay_review, technical_review = (str(item) for item in reviews)
        self.progress("    Reviews complete: gameplay and technical findings captured.")

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
        changed_names = [spec.name for spec, _reason in changes]
        if changed_names:
            self.progress(
                f"    Planned file updates ({len(changed_names)}): "
                + ", ".join(changed_names)
            )
        else:
            self.progress("    Planned file updates: none")

        pending = [
            (spec, reason)
            for spec, reason in changes
            if not self._restore_iteration_file(round_number, spec)
        ]
        if pending:
            self.progress(
                f"    Lead developer is updating {len(pending)} ordered checkpoints..."
            )
            for number, (spec, reason) in enumerate(pending, start=1):
                self.progress(f"      Lead checkpoint {number}/{len(pending)}: {spec.name}")
                await self._generate_iteration_file_checkpoint(
                    round_number,
                    spec,
                    reason,
                    plan,
                    gameplay_review,
                    technical_review,
                    self._project_snapshot(),
                )
        else:
            self.progress("    All planned file changes restored from checkpoints.")

        result = await self._validate_and_repair(
            plan,
            checkpoint_prefix=prefix,
            plan_task_name=f"{prefix}:plan",
        )
        if not result.ok:
            self._journal().fail_task(f"{prefix}:validation", result.report)
            self.progress(f"    Implementation round {round_number} validation failed.")
        else:
            self.progress(f"    Implementation round {round_number} complete.")
            for line in result.report.splitlines():
                self.progress(f"      {line}")
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
                    role=self._technical_role(IterationArchitectRole),
                    prompt=(
                        f"{self._specification_context()}"
                        f"Original brief:\n{brief}\n\nCurrent contract:\n"
                        f"{current_plan.as_context()}\n\nGameplay review:\n{gameplay_review}\n\n"
                        f"Technical review:\n{technical_review}\n\nSubmit the complete updated "
                        "contract and the exact source files to change. Preserve all existing "
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
        try:
            self.workspace.write_generated_source(spec.name, str(result["content"]))
        except (SyntaxError, WorkspaceError) as exc:
            self.progress(
                f"    Ignoring invalid round {round_number} checkpoint "
                f"for {spec.name}: {exc}"
            )
            return False
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
        task_name = f"iteration:{round_number:03d}:file:{spec.name}"
        return await self._generate_valid_source_checkpoint(
            task_name=task_name,
            artifact_name=f"iterations/{round_number:03d}/files/{spec.name}.json",
            spec=spec,
            prompt=(
                f"{self._specification_context()}"
                f"Updated complete plan:\n{plan.as_context()}\n\n"
                f"Gameplay review:\n{gameplay_review}\n\nTechnical review:\n"
                f"{technical_review}\n\nComplete project before this round:\n{snapshot}\n\n"
                f"Your assigned file: {spec.name}\nReason for change: {reason}\n"
                f"Purpose: {spec.purpose}\nRequired public API: "
                f"{', '.join(spec.public_api) or 'none'}\nReturn the complete revised file, "
                "integrated with both the current project and updated contract."
            ),
        )

    def _project_snapshot(self) -> str:
        return "\n\n".join(
            f"===== {name} =====\n{content}"
            for name, content in self.workspace.read_generated_sources().items()
        )

    def _diagnostic_logs(self) -> str:
        sections: list[str] = []
        for path in (
            self.workspace.root / "game.log",
            self.workspace.root / ".agentic" / "runtime.log",
            self.workspace.root / ".agentic" / "playtest.log",
        ):
            if not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                sections.append(f"===== {path.name} =====\nCould not read log: {exc}")
                continue
            sections.append(f"===== {path.name} (tail) =====\n{content[-8000:]}")
        return "\n\n".join(sections) or "(no diagnostic logs yet)"

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

    async def _architecture_checkpoint(self, brief: str, design: str) -> str:
        journal = self._journal()
        task_name = "architecture"
        artifact = journal.task_artifact(task_name)
        if journal.task_complete(task_name) and artifact:
            architecture = journal.read_text_artifact(artifact)
            try:
                self._validate_architecture(architecture)
            except ValueError as exc:
                self.progress(
                    "  Saved architecture does not meet the current shader/asset "
                    f"contract; regenerating it: {exc}"
                )
                journal.invalidate_task("architecture", str(exc))
                journal.invalidate_task(
                    "plan", "Architecture changed and requires a new build plan"
                )
                journal.invalidate_task(
                    "qa_contract",
                    "Architecture changed and requires a new QA acceptance contract",
                )
                journal.revoke_qa_contract()
            else:
                self.progress("  Reusing checkpoint: architecture")
                return architecture

        recovered = self._recover_architecture_attempt()
        if recovered is not None:
            journal.invalidate_task(
                "plan", "Recovered architecture requires a matching build plan"
            )
            journal.invalidate_task(
                "qa_contract",
                "Recovered architecture requires a matching QA acceptance contract",
            )
            journal.revoke_qa_contract()
            artifact = journal.write_text_artifact(
                "planning/architecture.txt", recovered
            )
            journal.complete_task(task_name, artifact)
            self.progress(
                "  Recovered the newest valid saved architecture attempt; "
                "no model call needed."
            )
            return recovered

        prompt = (
            f"{self._specification_context()}"
            f"Explore a robust architecture for this brief:\n{brief}\n\n"
            f"Final iterated design:\n{design}\n\nRequested renderer: {self.renderer}\n\n"
            "Return a complete Markdown architecture document using these exact level-two "
            "headings: Module Responsibilities, Rendering Pipeline, Visual Asset Manifest, "
            "Audio Asset Manifest, Cross-File APIs, Lifecycle and Cleanup, and Validation "
            "Strategy. For ModernGL also include Shader Source Manifest. Each manifest must "
            "enumerate concrete player-facing assets/effects rather than merely naming a folder. "
            "Use tables that name the experience, technique, exact owning source file, runtime "
            "integration point, and observable validation. The shader manifest must list separate "
            "vertex and fragment stage filenames and map every shader-driven effect to them. The "
            "visual manifest must cover player animation states, hazards, level/world pieces, "
            "items, backgrounds, UI, and feedback promised by the design, whether generated by "
            "script, built as Pygame surfaces, or drawn inline. The audio manifest must cover "
            "required interaction, movement, hazard, success/failure, and ambience cues and state "
            "whether each is synthesized or loaded."
        )
        retry_context = ""
        journal.start_task(task_name)
        try:
            for attempt in range(1, ARCHITECTURE_GENERATION_ATTEMPTS + 1):
                response = await self.provider.text(
                    role=self._technical_role(ArchitectRole),
                    prompt=prompt + retry_context,
                )
                try:
                    self._validate_architecture(response)
                except ValueError as exc:
                    journal.write_text_artifact(
                        f"planning/architecture.failed_{attempt:02d}.txt",
                        f"{response}\n\nValidation error: {exc}",
                    )
                    if attempt >= ARCHITECTURE_GENERATION_ATTEMPTS:
                        raise
                    self.progress(
                        f"  Architecture failed local validation: {exc}. "
                        f"Retrying ({attempt + 1}/{ARCHITECTURE_GENERATION_ATTEMPTS})..."
                    )
                    retry_context = (
                        "\n\nYour previous architecture document failed local validation.\n"
                        f"Validation error: {exc}\n"
                        "Return a corrected, complete replacement using every required heading "
                        "and concrete source-file ownership in all manifests."
                    )
                    continue
                artifact = journal.write_text_artifact(
                    "planning/architecture.txt", response
                )
                journal.complete_task(task_name, artifact)
                return response
        except BaseException as exc:
            journal.fail_task(task_name, exc)
            raise
        raise WorkspaceError("Architecture generation exhausted validation attempts")

    def _validate_architecture(self, architecture: str) -> None:
        required_sections = [
            "Module Responsibilities",
            "Rendering Pipeline",
            "Visual Asset Manifest",
            "Audio Asset Manifest",
            "Cross-File APIs",
            "Lifecycle and Cleanup",
            "Validation Strategy",
        ]
        if self.renderer == "moderngl":
            required_sections.append("Shader Source Manifest")
        missing = [
            heading
            for heading in required_sections
            if not re.search(
                rf"(?im)^#{{2,4}}[ \t]+{re.escape(heading)}[ \t]*:?[ \t]*$",
                architecture,
            )
        ]
        if missing:
            raise ValueError(
                "missing required architecture sections: " + ", ".join(missing)
            )
        if re.search(r"(?i)assets?\s+.*not included", architecture):
            raise ValueError("asset responsibilities cannot be deferred as not included")

        for heading in ("Visual Asset Manifest", "Audio Asset Manifest"):
            section = self._architecture_section(architecture, heading)
            lowered = section.lower()
            has_method = any(
                term in lowered
                for term in ("technique", "description", "generation", "method")
            )
            has_owner = any(
                term in lowered for term in ("owner", "owning", "responsible")
            )
            if not has_owner or "validation" not in lowered or not has_method:
                raise ValueError(
                    f"{heading} must include owner, implementation method, and "
                    "validation columns"
                )
            if not re.search(
                r"(?:[A-Za-z_][A-Za-z0-9_]*/)*[A-Za-z_][A-Za-z0-9_]*\.py",
                section,
            ):
                raise ValueError(f"{heading} must name at least one owning Python file")

        if self.renderer == "moderngl":
            shader_section = self._architecture_section(
                architecture, "Shader Source Manifest"
            )
            shader_files = set(
                re.findall(
                    r"(?:[A-Za-z_][A-Za-z0-9_]*/)*"
                    r"[A-Za-z_][A-Za-z0-9_]*\.(?:vert|frag|glsl)",
                    shader_section,
                )
            )
            if len(shader_files) < 2:
                raise ValueError(
                    "Shader Source Manifest must name separate vertex and fragment sources"
                )

    @staticmethod
    def _architecture_section(architecture: str, heading: str) -> str:
        match = re.search(
            rf"(?ims)^#{{2,4}}[ \t]+{re.escape(heading)}[ \t]*:?[ \t]*$"
            r"(.*?)(?=^##\s+|\Z)",
            architecture,
        )
        return match.group(1) if match else ""

    def _recover_architecture_attempt(self) -> str | None:
        planning = self._journal().artifacts / "planning"
        for path in sorted(
            planning.glob("architecture.failed_*.txt"), reverse=True
        ):
            try:
                content = path.read_text(encoding="utf-8")
            except OSError:
                continue
            architecture = content.rsplit("\n\nValidation error:", 1)[0].rstrip()
            try:
                self._validate_architecture(architecture)
            except ValueError:
                continue
            return architecture
        return None

    async def _qa_contract_checkpoint(
        self,
        brief: str,
        design: str,
        architecture: str,
        plan: GamePlan,
    ) -> str:
        journal = self._journal()
        task_name = "qa_contract"
        artifact = journal.task_artifact(task_name)
        if journal.task_complete(task_name) and artifact:
            self.progress("  Reusing checkpoint: QA acceptance contract")
            raw = journal.read_json_artifact(artifact)
            if not journal.task_complete(task_name):
                journal.complete_task(task_name, artifact)
        else:
            journal.start_task(task_name)
            try:
                raw = await self.provider.structured(
                    role=self._technical_role(QaAuthorRole),
                    prompt=(
                        f"{self._specification_context()}"
                        f"Original brief:\n{brief}\n\nFinal design:\n{design}\n\n"
                        f"Architecture:\n{architecture}\n\nBuild contract:\n{plan.as_context()}\n\n"
                        "Author the preimplementation QA acceptance contract. Make criteria "
                        "specific enough that a developer cannot substitute placeholder mechanics."
                    ),
                    tool_name="submit_qa_contract",
                    description=(
                        "Submit observable, testable preimplementation acceptance criteria."
                    ),
                    schema=QA_CONTRACT_SCHEMA,
                )
                artifact = journal.write_json_artifact("planning/qa_contract.json", raw)
                journal.complete_task(task_name, artifact)
            except BaseException as exc:
                journal.fail_task(task_name, exc)
                raise
        return self._render_qa_contract(raw)

    @staticmethod
    def _render_qa_contract(raw: dict[str, Any]) -> str:
        criteria = raw.get("criteria")
        if not isinstance(criteria, list) or len(criteria) < 1:
            raise WorkspaceError("QA author returned no acceptance criteria")
        lines = [
            "# Gameplay QA Acceptance Contract",
            "",
            str(raw.get("summary", "")).strip(),
            "",
        ]
        for number, item in enumerate(criteria, start=1):
            if not isinstance(item, dict):
                raise WorkspaceError("QA author returned an invalid acceptance criterion")
            identifier = str(item.get("id", number)).strip()
            requirement = str(item.get("requirement", "")).strip()
            if not requirement:
                raise WorkspaceError("QA author returned an empty requirement")
            blocking = "Yes" if bool(item.get("blocking", False)) else "No"
            lines.extend([
                f"## {number}. {identifier}: {requirement}",
                "",
                f"- Rationale: {str(item.get('rationale', '')).strip()}",
                f"- Automated test: {str(item.get('automated_test', '')).strip()}",
                f"- Scripted playtest: {str(item.get('scripted_playtest', '')).strip()}",
                f"- Visual evidence: {str(item.get('visual_evidence', '')).strip()}",
                f"- Blocking failure: {blocking}",
                "",
            ])
        return "\n".join(lines).rstrip() + "\n"

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
            plan = self._normalize_plan(GamePlan.from_dict(journal.read_json_artifact(artifact)))
            try:
                self._validate_plan(plan)
            except ValueError as exc:
                self.progress(
                    "  Saved plan does not meet the current build contract; "
                    f"regenerating it: {exc}"
                )
                journal.invalidate_task("plan", str(exc))
                journal.invalidate_task(
                    "qa_contract",
                    "The build plan changed and requires a new QA acceptance contract",
                )
                journal.revoke_qa_contract()
            else:
                self.progress("  Reusing checkpoint: plan")
                return plan
        journal.start_task(task_name)
        try:
            prompt = (
                f"{self._specification_context()}"
                f"Original brief:\n{brief}\n\nDesigner proposal:\n{design}\n\n"
                f"Architecture proposal:\n{architecture}\n\nRenderer: {self.renderer}. "
                "Resolve conflicts and submit the final build contract. Include main.py "
                "exactly once and declare every non-standard-library import."
            )
            retry_context = ""
            for attempt in range(1, PLAN_GENERATION_ATTEMPTS + 1):
                raw_plan = await self.provider.structured(
                    role=self._technical_role(ArchitectRole),
                    prompt=prompt + retry_context,
                    tool_name="submit_game_plan",
                    description="Submit the final implementation and dependency contract.",
                    schema=PLAN_SCHEMA,
                )
                try:
                    plan = self._normalize_plan(GamePlan.from_dict(raw_plan))
                    self._validate_plan(plan)
                except (KeyError, TypeError, ValueError, WorkspaceError) as exc:
                    failed = dict(raw_plan)
                    failed["validation_error"] = str(exc)
                    journal.write_json_artifact(
                        f"planning/plan.failed_{attempt:02d}.json", failed
                    )
                    if attempt >= PLAN_GENERATION_ATTEMPTS:
                        raise
                    self.progress(
                        f"  Build contract failed local validation: {exc}. "
                        f"Retrying ({attempt + 1}/{PLAN_GENERATION_ATTEMPTS})..."
                    )
                    retry_context = (
                        "\n\nYour previous build contract failed local validation.\n"
                        f"Validation error: {exc}\n\n"
                        "Return a corrected complete contract. Every render-effect shader "
                        "source and every visual/audio asset owner must also appear in files."
                    )
                    continue
                artifact = journal.write_json_artifact(
                    "planning/plan.json", plan.as_dict()
                )
                journal.complete_task(task_name, artifact)
                return plan
        except BaseException as exc:
            journal.fail_task(task_name, exc)
            raise
        raise WorkspaceError("Plan generation exhausted validation attempts")

    def _restore_completed_file(self, spec: FileSpec) -> bool:
        journal = self._journal()
        task_name = f"file:{spec.name}"
        artifact = journal.task_artifact(task_name)
        if not artifact:
            return False
        result = journal.read_json_artifact(artifact)
        if result.get("filename") != spec.name:
            raise WorkspaceError(f"Corrupt file checkpoint for {spec.name}")
        try:
            self.workspace.write_generated_source(spec.name, str(result["content"]))
        except (SyntaxError, WorkspaceError) as exc:
            self.progress(f"  Ignoring invalid checkpoint for {spec.name}: {exc}")
            return False
        if not journal.task_complete(task_name):
            journal.complete_task(task_name, artifact)
        self.progress(f"  Reusing checkpoint: {spec.name}")
        return True

    async def _generate_file_checkpoint(
        self,
        spec: FileSpec,
        plan: GamePlan,
        qa_contract: str,
    ) -> str:
        task_name = f"file:{spec.name}"
        return await self._generate_valid_source_checkpoint(
            task_name=task_name,
            artifact_name=f"files/{spec.name}.json",
            spec=spec,
            prompt=(
                f"{self._specification_context()}"
                f"Complete plan:\n{plan.as_context()}\n\n"
                f"Approved QA contract:\n{qa_contract}\n\n"
                "Project implemented so far:\n"
                f"{self._project_snapshot() or '(no files yet)'}\n\n"
                f"Your current checkpoint file: {spec.name}\n"
                f"Your assigned file: {spec.name}\nPurpose: {spec.purpose}\n"
                f"Required public API: {', '.join(spec.public_api) or 'none'}\n"
                "Implement this file as the lead developer. Keep all existing and future "
                "cross-file contracts coherent and satisfy the approved QA criteria."
            ),
        )

    async def _generate_valid_source_checkpoint(
        self,
        *,
        task_name: str,
        artifact_name: str,
        spec: FileSpec,
        prompt: str,
    ) -> str:
        journal = self._journal()
        journal.start_task(task_name)
        retry_context = ""
        try:
            for attempt in range(1, FILE_GENERATION_ATTEMPTS + 1):
                result = await self.provider.structured(
                    role=self._technical_role(ImplementerRole),
                    prompt=prompt + retry_context,
                    tool_name="submit_source_file",
                    description="Submit one complete validated Python or GLSL source file.",
                    schema=FILE_SCHEMA,
                )
                try:
                    if result["filename"] != spec.name:
                        raise WorkspaceError(
                            f"Implementer returned {result['filename']!r}; "
                            f"expected {spec.name!r}"
                        )
                    self.workspace.write_generated_source(spec.name, str(result["content"]))
                except (SyntaxError, WorkspaceError) as exc:
                    failed = dict(result)
                    failed["validation_error"] = str(exc)
                    stem = artifact_name.removesuffix(".json")
                    journal.write_json_artifact(
                        f"{stem}.failed_{attempt:02d}.json", failed
                    )
                    if attempt >= FILE_GENERATION_ATTEMPTS:
                        raise
                    self.progress(
                        f"    {spec.name} failed source validation: {exc}. "
                        f"Retrying ({attempt + 1}/{FILE_GENERATION_ATTEMPTS})..."
                    )
                    retry_context = (
                        "\n\nYour previous response failed local source validation.\n"
                        f"Validation error: {exc}\n\nPrevious invalid source:\n"
                        f"{result.get('content', '')}\n\nReturn a corrected complete file."
                    )
                    continue
                artifact = journal.write_json_artifact(artifact_name, result)
                journal.set_task_artifact(task_name, artifact)
                journal.complete_task(task_name, artifact)
                return spec.name
        except BaseException as exc:
            journal.fail_task(task_name, exc)
            raise
        raise WorkspaceError(f"File generation exhausted attempts for {spec.name}")

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
        ordered_names = [spec.name for spec in plan.files]
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
                try:
                    self._apply_replacements(patch, allowed)
                except WorkspaceError as exc:
                    journal.invalidate_task(task_name, str(exc))
                    self.progress(
                        f"  Ignoring invalid legacy repair checkpoint {task_name}: {exc}"
                    )
        self._restore_file_repair_checkpoints(checkpoint_prefix, allowed)
        if journal.task_complete(validation_task):
            self.progress(f"  Reusing completed validation checkpoint: {validation_task}")
            return ValidationResult(
                True, f"Validation checkpoint {validation_task} was already complete"
            )

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
            self.progress(f"  Repair pass {attempt}/{self.repair_attempts}: {result.report}")
            diagnostic_files = self._diagnostic_files(result.report, ordered_names)
            changed: list[str] = []
            if diagnostic_files:
                self.progress(
                    f"    Repairing {len(diagnostic_files)} affected files individually: "
                    + ", ".join(diagnostic_files)
                )
                for number, filename in enumerate(diagnostic_files, start=1):
                    self.progress(
                        f"    Repair checkpoint {number}/{len(diagnostic_files)}: {filename}"
                    )
                    patch = await self._review_file_checkpoint(
                        attempt=attempt,
                        filename=filename,
                        validation_report=result.report,
                        allowed_names=allowed,
                        checkpoint_prefix=checkpoint_prefix,
                    )
                    changed.extend(self._apply_replacements(patch, allowed))
            else:
                if journal.task_complete(task_name):
                    continue
                patch = await self._review_checkpoint(
                    attempt=attempt,
                    context=f"Automated validation failed:\n{result.report}",
                    allowed_names=allowed,
                    checkpoint_prefix=checkpoint_prefix,
                )
                changed.extend(self._apply_replacements(patch, allowed))
            if not changed:
                message = (
                    "Repair stopped because the reviewer produced no source changes; "
                    "remaining repair passes were not spent."
                )
                self.progress(f"  {message}")
                return ValidationResult(False, f"{result.report}\n{message}")
            self.progress(
                f"    Applied repairs to {len(set(changed))} files: "
                + ", ".join(dict.fromkeys(changed))
            )
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
        if module in {
            Path(spec.name).stem for spec in plan.files if Path(spec.name).suffix == ".py"
        }:
            return result
        if plan.dependency_for_import(module):
            return result
        distribution = {
            "pygame": "pygame-ce",
            "pygame_gui": "pygame-gui",
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

    @staticmethod
    def _repair_file_task_name(
        checkpoint_prefix: str, attempt: int, filename: str
    ) -> str:
        prefix = f"{checkpoint_prefix}:" if checkpoint_prefix else ""
        return f"{prefix}repair_file:{attempt:03d}:{filename}"

    @staticmethod
    def _diagnostic_files(report: str, ordered_names: Sequence[str]) -> list[str]:
        normalized_report = report.replace("\\", "/").lower()
        return [
            filename
            for filename in ordered_names
            if filename.endswith(".py") and filename.lower() in normalized_report
        ]

    def _restore_file_repair_checkpoints(
        self, checkpoint_prefix: str, allowed_names: set[str]
    ) -> None:
        journal = self._journal()
        prefix = f"{checkpoint_prefix}:" if checkpoint_prefix else ""
        task_prefix = f"{prefix}repair_file:"
        task_names = sorted(
            name
            for name, task in journal.state.get("tasks", {}).items()
            if name.startswith(task_prefix)
            and task.get("status") == "complete"
            and task.get("artifact")
        )
        for task_name in task_names:
            artifact = journal.task_artifact(task_name)
            if not artifact:
                continue
            patch = self._normalize_patch(dict(journal.read_json_artifact(artifact)))
            self._apply_replacements(patch, allowed_names)
            self.progress(f"  Reusing checkpoint artifact: {task_name}")

    async def _review_file_checkpoint(
        self,
        *,
        attempt: int,
        filename: str,
        validation_report: str,
        allowed_names: set[str],
        checkpoint_prefix: str = "",
    ) -> dict[str, Any]:
        if filename not in allowed_names:
            raise WorkspaceError(f"Cannot repair unplanned file {filename!r}")
        journal = self._journal()
        task_name = self._repair_file_task_name(
            checkpoint_prefix, attempt, filename
        )
        artifact_prefix = checkpoint_prefix.replace(":", "_")
        directory = f"{artifact_prefix}/" if artifact_prefix else ""
        artifact = journal.task_artifact(task_name)
        if artifact:
            saved_patch = self._normalize_patch(
                dict(journal.read_json_artifact(artifact))
            )
            try:
                self._validate_file_repair_patch(saved_patch, filename)
            except (SyntaxError, WorkspaceError) as exc:
                journal.invalidate_task(task_name, str(exc))
                self.progress(
                    f"  Ignoring invalid file repair checkpoint {task_name}: {exc}"
                )
            else:
                self.progress(f"  Reusing checkpoint artifact: {task_name}")
                return saved_patch

        source_path = self.workspace.path_for(filename)
        source = source_path.read_text(encoding="utf-8")
        related_sources = self._related_source_context(filename, allowed_names)
        journal.start_task(task_name)
        retry_context = ""
        try:
            prompt = (
                f"{self._specification_context()}Automated validation failed:\n"
                f"{validation_report}\n\nYour sole repair target is {filename}. Return "
                "exactly one complete replacement for that file, even when diagnostics "
                "also name other files; those files receive separate checkpoints. Do not "
                "return a diff, partial file, or decline the repair. Preserve behavior and "
                "fix types at their source without ignore comments or weakened checks.\n\n"
                f"Build contract:\n{self.workspace.read_plan().as_context()}\n\n"
                f"Current {filename}:\n===== {filename} =====\n{source}\n\n"
                f"Related local sources for API context:\n{related_sources}"
            )
            for source_attempt in range(1, FILE_GENERATION_ATTEMPTS + 1):
                patch = self._normalize_patch(
                    await self.provider.structured(
                        role=self._technical_role(RepairReviewerRole),
                        prompt=prompt + retry_context,
                        tool_name="submit_replacements",
                        description=(
                            f"Submit one complete corrected replacement for {filename}."
                        ),
                        schema=PATCH_SCHEMA,
                    )
                )
                try:
                    self._validate_file_repair_patch(patch, filename)
                except (SyntaxError, WorkspaceError) as exc:
                    failed = dict(patch)
                    failed["validation_error"] = str(exc)
                    journal.write_json_artifact(
                        f"{directory}repairs/{attempt:03d}/{filename}"
                        f".failed_{source_attempt:02d}.json",
                        failed,
                    )
                    if source_attempt >= FILE_GENERATION_ATTEMPTS:
                        raise
                    self.progress(
                        f"      {filename} failed source validation: {exc}. "
                        f"Retrying ({source_attempt + 1}/{FILE_GENERATION_ATTEMPTS})..."
                    )
                    retry_context = (
                        "\n\nYour previous repair failed local source validation.\n"
                        f"Validation error: {exc}\n\nPrevious invalid replacement:\n"
                        f"{patch.get('files', [])}\n\nReturn a corrected complete file."
                    )
                    continue
                artifact = journal.write_json_artifact(
                    f"{directory}repairs/{attempt:03d}/{filename}.json", patch
                )
                journal.complete_task(task_name, artifact)
                return patch
        except BaseException as exc:
            journal.fail_task(task_name, exc)
            raise
        raise WorkspaceError(f"File repair exhausted attempts for {filename}")

    def _validate_file_repair_patch(
        self, patch: dict[str, Any], filename: str
    ) -> None:
        replacements = patch["files"]
        if len(replacements) > 1 or (
            replacements and replacements[0]["filename"] != filename
        ):
            raise WorkspaceError(
                f"File repair for {filename!r} must return only that filename"
            )
        for replacement in replacements:
            self.workspace.validate_generated_source(
                filename, str(replacement["content"])
            )

    def _related_source_context(
        self, filename: str, allowed_names: set[str]
    ) -> str:
        """Include locally imported modules without resending the entire project."""
        try:
            source = self.workspace.path_for(filename).read_text(encoding="utf-8")
            tree = ast.parse(source, filename=filename)
        except (OSError, SyntaxError):
            return "(source imports could not be inspected)"
        imported_modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)

        sections: list[str] = []
        for candidate in sorted(allowed_names):
            if candidate == filename or not candidate.endswith(".py"):
                continue
            module = candidate.removesuffix(".py").replace("/", ".")
            if module.endswith(".__init__"):
                module = module.removesuffix(".__init__")
            if not any(
                imported == module
                or imported.startswith(f"{module}.")
                or module.endswith(f".{imported}")
                for imported in imported_modules
            ):
                continue
            path = self.workspace.path_for(candidate)
            if path.is_file():
                sections.append(
                    f"===== {candidate} =====\n{path.read_text(encoding='utf-8')}"
                )
        return "\n\n".join(sections) or "(no project-local imports detected)"

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
        artifact = journal.task_artifact(task_name)
        if artifact and journal.task_complete(task_name):
            self.progress(f"  Reusing checkpoint artifact: {task_name}")
            raw_patch = dict(journal.read_json_artifact(artifact))
            try:
                patch = self._normalize_patch(raw_patch)
            except BaseException as exc:
                journal.fail_task(task_name, exc)
                raise
            if patch != raw_patch:
                journal.write_json_artifact(artifact.removeprefix("artifacts/"), patch)
                self.progress(f"  Normalized checkpoint: {task_name}")
            if not journal.task_complete(task_name):
                journal.complete_task(task_name, artifact)
            return patch
        if journal.task_complete(task_name):
            raise WorkspaceError(f"Repair checkpoint {attempt} has no artifact")
        journal.start_task(task_name)
        try:
            patch = self._normalize_patch(
                await self._review(context=context, allowed_names=allowed_names)
            )
            self._validate_replacement_names(patch, allowed_names)
            artifact = journal.write_json_artifact(
                f"{directory}repairs/{attempt}.json", patch
            )
            journal.complete_task(task_name, artifact)
            return patch
        except BaseException as exc:
            journal.fail_task(task_name, exc)
            raise

    async def _review(
        self,
        *,
        context: str,
        allowed_names: set[str],
        allow_new: bool = False,
    ) -> dict[str, Any]:
        filename_policy = (
            "Existing filenames may be modified. New safe nested .py, .vert, .frag, or .glsl "
            "source files are allowed when "
            "they represent a distinct responsibility and improve separation of concerns."
            if allow_new
            else f"Allowed filenames: {sorted(allowed_names)}"
        )
        return await self.provider.structured(
            role=self._technical_role(RepairReviewerRole),
            prompt=(
                f"{self._specification_context()}{context}\n\n{filename_policy}\n\n"
                f"Complete project:\n{self._project_snapshot()}\n\n"
                f"Diagnostic log tails:\n{self._diagnostic_logs()}"
            ),
            tool_name="submit_replacements",
            description="Submit complete replacement files and a concise review summary.",
            schema=PATCH_SCHEMA,
        )

    def _apply_replacements(
        self, patch: dict[str, Any], allowed: set[str]
    ) -> list[str]:
        patch = self._normalize_patch(patch)
        self._validate_replacement_names(patch, allowed)
        changed: list[str] = []
        for replacement in patch["files"]:
            filename = str(replacement["filename"])
            content = str(replacement["content"])
            path = self.workspace.path_for(filename)
            normalized_content = content.rstrip() + "\n"
            if path.is_file() and path.read_text(encoding="utf-8") == normalized_content:
                continue
            self.workspace.write_generated_source(filename, content)
            changed.append(filename)
        if patch.get("summary"):
            self.progress(f"  Reviewer: {patch['summary']}")
        return changed

    @staticmethod
    def _validate_replacement_names(
        patch: dict[str, Any], allowed: set[str]
    ) -> None:
        for replacement in patch["files"]:
            filename = str(replacement["filename"])
            if filename not in allowed:
                raise WorkspaceError(
                    f"Reviewer attempted to write unplanned file {filename!r}"
                )

    @staticmethod
    def _normalize_patch(patch: dict[str, Any]) -> dict[str, Any]:
        raw_files = patch.get("files")
        if isinstance(raw_files, str):
            try:
                raw_files = json.loads(raw_files)
            except json.JSONDecodeError:
                try:
                    raw_files = json.loads(
                        GameBuilder._escape_json_string_control_characters(raw_files)
                    )
                except json.JSONDecodeError:
                    raw_files = GameBuilder._parse_loose_replacement_list(raw_files)
        if isinstance(raw_files, dict):
            if "filename" in raw_files and "content" in raw_files:
                raw_files = [raw_files]
            else:
                raw_files = [
                    {"filename": filename, "content": content}
                    for filename, content in raw_files.items()
                ]
        if not isinstance(raw_files, list):
            raise WorkspaceError("Reviewer files must be a list of replacement objects")

        files: list[dict[str, str]] = []
        for index, replacement in enumerate(raw_files):
            if not isinstance(replacement, dict):
                raise WorkspaceError(f"Reviewer replacement {index} must be an object")
            filename = replacement.get("filename")
            content = replacement.get("content")
            if not isinstance(filename, str) or not isinstance(content, str):
                raise WorkspaceError(
                    f"Reviewer replacement {index} requires string filename and content"
                )
            files.append({"filename": filename, "content": content})

        summary = patch.get("summary", "")
        if not isinstance(summary, str):
            raise WorkspaceError("Reviewer summary must be a string")
        return {"files": files, "summary": summary}

    @staticmethod
    def _escape_json_string_control_characters(value: str) -> str:
        output: list[str] = []
        in_string = False
        escaped = False
        for character in value:
            if not in_string:
                output.append(character)
                if character == '"':
                    in_string = True
                continue
            if escaped:
                output.append(character)
                escaped = False
            elif character == "\\":
                output.append(character)
                escaped = True
            elif character == '"':
                output.append(character)
                in_string = False
            elif ord(character) < 32:
                output.append(json.dumps(character)[1:-1])
            else:
                output.append(character)
        return "".join(output)

    @staticmethod
    def _parse_loose_replacement_list(value: str) -> list[dict[str, str]]:
        prefix = '[{"filename": "'
        separator = '", "content": "'
        item_separator = '"}, {"filename": "'
        suffix = '"}]'
        if not value.startswith(prefix) or not value.endswith(suffix):
            raise WorkspaceError("Reviewer returned invalid JSON in files")

        body = value[len(prefix) : -len(suffix)]
        items: list[dict[str, str]] = []
        while True:
            boundary = body.find(separator)
            if boundary < 0:
                raise WorkspaceError("Reviewer replacement is missing content")
            filename = body[:boundary]
            remainder = body[boundary + len(separator) :]
            next_item = remainder.find(item_separator)
            if next_item < 0:
                content = remainder
                items.append(
                    {
                        "filename": filename,
                        "content": GameBuilder._decode_loose_json_string(content),
                    }
                )
                break
            content = remainder[:next_item]
            items.append(
                {
                    "filename": filename,
                    "content": GameBuilder._decode_loose_json_string(content),
                }
            )
            body = remainder[next_item + len(item_separator) :]
        return items

    @staticmethod
    def _decode_loose_json_string(value: str) -> str:
        escapes = {
            '"': '"',
            "\\": "\\",
            "/": "/",
            "b": "\b",
            "f": "\f",
            "n": "\n",
            "r": "\r",
            "t": "\t",
        }
        output: list[str] = []
        index = 0
        while index < len(value):
            character = value[index]
            if character != "\\" or index + 1 >= len(value):
                output.append(character)
                index += 1
                continue
            marker = value[index + 1]
            if marker == "u" and index + 5 < len(value):
                digits = value[index + 2 : index + 6]
                try:
                    output.append(chr(int(digits, 16)))
                    index += 6
                    continue
                except ValueError:
                    pass
            if marker in escapes:
                output.append(escapes[marker])
                index += 2
                continue
            output.append(character)
            index += 1
        return "".join(output)

    def _run_validation(self) -> ValidationResult:
        reports: list[str] = []
        self.workspace.write_typecheck_config()
        self.progress("    Validating Python compilation...")
        static = validate_project(self.workspace.root)
        if not static.ok:
            return static
        reports.append(static.report)
        self.progress("    Running strict Pyright validation...")
        typing = self.type_checker(self.workspace.root, self.environment.python)
        if not typing.ok:
            return ValidationResult(False, "\n".join((*reports, typing.report)))
        reports.append(typing.report)
        self.progress("    Checking the renderer contract...")
        renderer = validate_renderer_project(self.workspace.root, self.renderer)
        if not renderer.ok:
            return ValidationResult(False, "\n".join((*reports, renderer.report)))
        reports.append(renderer.report)
        self.progress(f"    Running the {self.smoke_timeout:g}s runtime smoke test...")
        runtime = smoke_test(
            self.workspace.root, self.environment.python, self.smoke_timeout
        )
        return ValidationResult(runtime.ok, "\n".join((*reports, runtime.report)))

    @staticmethod
    def _owner_files(owner: str) -> list[str]:
        """Return one or more explicitly listed owner paths from a contract field."""
        owners: list[str] = []
        for part in re.split(r"\s+(?:and|&)\s+|\s*[,;]\s*", owner):
            normalized = re.sub(r"^(?:and|&)\s+", "", part.strip(), flags=re.IGNORECASE)
            normalized = normalized.strip().strip("`")
            if normalized:
                owners.append(normalized)
        return owners

    @classmethod
    def _validate_owner(
        cls,
        owner: str,
        planned_files: set[str],
        label: str,
    ) -> None:
        owners = cls._owner_files(owner)
        missing = [candidate for candidate in owners if candidate not in planned_files]
        if not owners or missing:
            raise ValueError(
                f"{label} owner is not a planned file: {owner!r}"
                + (f"; unplanned owners: {missing}" if missing else "")
            )

    def _normalize_plan(self, plan: GamePlan) -> GamePlan:
        renderer_profile = get_renderer_profile(self.renderer)
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
        dependencies: list[DependencySpec] = []
        for item in plan.dependencies:
            if item.import_name in baseline_imports:
                continue
            known = KNOWN_DEPENDENCY_CONSTRAINTS.get(item.import_name)
            if known:
                distribution, version = known
                item = DependencySpec(
                    distribution=distribution,
                    import_name=item.import_name,
                    version=version,
                    reason=item.reason,
                )
            dependencies.append(item)
        dependencies.extend(baseline)
        files = [item for item in plan.files if item.name != "main.py"]
        planned_names = {item.name for item in plan.files}
        referenced_files: list[tuple[str, str]] = []
        for effect in plan.render_effects:
            referenced_files.append(
                (effect.owner, f"Owns render effect: {effect.experience}")
            )
            referenced_files.extend(
                (source, f"Shader source for: {effect.experience}")
                for source in effect.source_files
            )
        referenced_files.extend(
            (asset.owner, f"Generates visual asset: {asset.experience}")
            for asset in plan.visual_assets
        )
        referenced_files.extend(
            (asset.owner, f"Generates audio asset: {asset.experience}")
            for asset in plan.audio_assets
        )
        for filename, purpose in referenced_files:
            if filename in planned_names:
                continue
            try:
                self.workspace.path_for(filename)
            except WorkspaceError:
                continue
            files.append(FileSpec(name=filename, purpose=purpose, public_api=[]))
            planned_names.add(filename)
        files.extend(item for item in plan.files if item.name == "main.py")
        return GamePlan(
            title=plan.title,
            pitch=plan.pitch,
            core_loop=plan.core_loop,
            controls=plan.controls,
            quality_bar=plan.quality_bar,
            files=files,
            dependencies=dependencies,
            rendering_strategy=(
                plan.rendering_strategy or renderer_profile.default_strategy
            ),
            render_effects=plan.render_effects,
            visual_assets=plan.visual_assets,
            audio_assets=plan.audio_assets,
        )

    def _validate_plan(self, plan: GamePlan) -> None:
        names = [spec.name for spec in plan.files]
        if names.count("main.py") != 1:
            raise ValueError("Plan must contain main.py exactly once")
        if names[-1] != "main.py":
            raise ValueError("Plan must place main.py last")
        if len(names) != len(set(names)):
            raise ValueError("Plan contains duplicate filenames")
        planned_files = set(names)
        for number, effect in enumerate(plan.render_effects, start=1):
            if not all(
                (
                    effect.experience,
                    effect.technique,
                    effect.owner,
                    effect.validation,
                )
            ):
                raise ValueError(f"Render effect {number} has an empty contract field")
            self._validate_owner(
                effect.owner, planned_files, f"Render effect {number}"
            )
            missing_sources = [
                source for source in effect.source_files if source not in planned_files
            ]
            if missing_sources:
                raise ValueError(
                    f"Render effect {number} references unplanned source files: "
                    f"{missing_sources}"
                )
        for number, asset in enumerate(plan.visual_assets, start=1):
            if not all(
                (
                    asset.experience,
                    asset.kind,
                    asset.owner,
                    asset.technique,
                    asset.validation,
                )
            ):
                raise ValueError(f"Visual asset {number} has an empty contract field")
            self._validate_owner(
                asset.owner, planned_files, f"Visual asset {number}"
            )
        for number, asset in enumerate(plan.audio_assets, start=1):
            if not all(
                (
                    asset.experience,
                    asset.kind,
                    asset.owner,
                    asset.technique,
                    asset.validation,
                )
            ):
                raise ValueError(f"Audio asset {number} has an empty contract field")
            self._validate_owner(
                asset.owner, planned_files, f"Audio asset {number}"
            )
        if self.renderer == "moderngl":
            shader_sources = {
                name
                for name in names
                if Path(name).suffix in {".vert", ".frag", ".glsl"}
            }
            if len(shader_sources) < 2:
                raise ValueError(
                    "ModernGL plans must include separate planned vertex and fragment "
                    "shader sources using .vert, .frag, or stage-specific .glsl files"
                )
            referenced_shader_sources = {
                source
                for effect in plan.render_effects
                for source in effect.source_files
                if Path(source).suffix in {".vert", ".frag", ".glsl"}
            }
            unreferenced = shader_sources - referenced_shader_sources
            if unreferenced:
                raise ValueError(
                    "ModernGL shader files must be assigned to render effects: "
                    f"{sorted(unreferenced)}"
                )
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
        self.progress(f"  provider: {self.provider.provider_name}")
        self.progress(f"  model: {self.provider.model}")
        provider_host = str(getattr(self.provider, "host", ""))
        if provider_host:
            self.progress(f"  provider host: {provider_host}")
        self.progress(f"  renderer: {self.renderer}")
        self.progress(f"  design iterations: {self.design_iterations}")
        self.progress(f"  implementation iterations: {self.implementation_iterations}")
        self.progress(f"  repair attempts: {self.repair_attempts}")
        self.progress(f"  game environment: {self.environment.python}")

    def _specification_context(self) -> str:
        return DesignerRole.specification_section(self._journal().read_specification())

    def _technical_role(self, role: type[AgentRole]) -> str:
        return role.system_prompt(
            DEFAULT_ENGINEERING_POLICY.prompt_section(),
            get_renderer_profile(self.renderer).prompt_section(),
        )

    def _journal(self) -> RunJournal:
        if self.journal is None:
            raise RuntimeError("Run journal has not been initialized")
        return self.journal
