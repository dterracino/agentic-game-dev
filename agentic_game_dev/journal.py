from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

JOURNAL_VERSION = 1


def _now() -> str:
    return datetime.now(UTC).isoformat()


class JournalError(RuntimeError):
    pass


class RunJournal:
    def __init__(self, root: Path, state: dict[str, Any]) -> None:
        self.root = root.resolve()
        self.directory = self.root / ".agentic"
        self.artifacts = self.directory / "artifacts"
        self.path = self.directory / "run.json"
        self.state = state

    @classmethod
    def create(
        cls,
        root: Path,
        *,
        brief: str,
        model: str,
        renderer: str,
        repair_attempts: int,
        smoke_timeout: float,
        design_iterations: int = 1,
        implementation_iterations: int = 0,
        provider: str = "anthropic",
        provider_host: str = "",
    ) -> RunJournal:
        journal = cls(
            root,
            {
                "version": JOURNAL_VERSION,
                "status": "running",
                "stage": "created",
                "created_at": _now(),
                "updated_at": _now(),
                "brief": brief,
                "model": model,
                "provider": provider,
                "provider_host": provider_host,
                "renderer": renderer,
                "qa_approved": False,
                "repair_attempts": repair_attempts,
                "smoke_timeout": smoke_timeout,
                "design_iterations": design_iterations,
                "implementation_iterations": implementation_iterations,
                "tasks": {},
                "last_error": None,
            },
        )
        journal.directory.mkdir(parents=True, exist_ok=True)
        journal.artifacts.mkdir(parents=True, exist_ok=True)
        journal._save()
        return journal

    @classmethod
    def load(cls, root: Path) -> RunJournal:
        path = root.resolve() / ".agentic" / "run.json"
        if not path.is_file():
            raise JournalError(f"No resumable run found at: {path}")
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise JournalError(f"Cannot read run journal: {exc}") from exc
        if state.get("version") != JOURNAL_VERSION:
            raise JournalError(f"Unsupported run journal version: {state.get('version')}")
        journal = cls(root, state)
        journal.artifacts.mkdir(parents=True, exist_ok=True)
        journal._recover_interrupted_tasks()
        return journal

    def _recover_interrupted_tasks(self) -> None:
        changed = False
        for task in self.state.get("tasks", {}).values():
            if task.get("status") == "running":
                task["status"] = "pending"
                task["error"] = "Previous process stopped while this task was running"
                changed = True
        if self.state.get("status") == "complete":
            return
        if changed:
            self.state["status"] = "running"
            self._save()

    def set_stage(self, stage: str) -> None:
        self.state["stage"] = stage
        self._save()

    def approve_qa_contract(self) -> None:
        self.state["qa_approved"] = True
        self._save()

    def add_repair_attempts(self, count: int) -> None:
        if count < 0:
            raise ValueError("Additional repair attempts cannot be negative")
        self.state["repair_attempts"] = int(self.state["repair_attempts"]) + count
        self._save()

    def start_task(self, name: str) -> None:
        task = self.state.setdefault("tasks", {}).setdefault(name, {})
        task.update({"status": "running", "started_at": _now(), "error": None})
        self.state["last_error"] = None
        self._save()

    def set_task_artifact(self, name: str, artifact: str) -> None:
        task = self.state.setdefault("tasks", {}).setdefault(name, {})
        task["artifact"] = artifact
        self._save()

    def complete_task(self, name: str, artifact: str | None = None) -> None:
        task = self.state.setdefault("tasks", {}).setdefault(name, {})
        task.update({"status": "complete", "completed_at": _now(), "error": None})
        if artifact is not None:
            task["artifact"] = artifact
        self._save()

    def fail_task(self, name: str, error: BaseException | str) -> None:
        message = str(error)
        task = self.state.setdefault("tasks", {}).setdefault(name, {})
        task.update({"status": "failed", "failed_at": _now(), "error": message})
        self.state["status"] = "failed"
        self.state["last_error"] = message
        self._save()

    def task_complete(self, name: str) -> bool:
        return self.state.get("tasks", {}).get(name, {}).get("status") == "complete"

    def task_artifact(self, name: str) -> str | None:
        return self.state.get("tasks", {}).get(name, {}).get("artifact")

    def mark_complete(self) -> None:
        self.state["stage"] = "complete"
        self.state["status"] = "complete"
        self.state["last_error"] = None
        self._save()

    def mark_running(self) -> None:
        self.state["status"] = "running"
        self.state["last_error"] = None
        self._save()

    def write_text_artifact(self, relative: str, content: str) -> str:
        path = self._artifact_path(relative)
        self._atomic_write_text(path, content.rstrip() + "\n")
        return path.relative_to(self.directory).as_posix()

    def read_text_artifact(self, relative: str) -> str:
        return self._resolve_artifact(relative).read_text(encoding="utf-8")

    def write_json_artifact(self, relative: str, value: Any) -> str:
        path = self._artifact_path(relative)
        self._atomic_write_text(path, json.dumps(value, indent=2) + "\n")
        return path.relative_to(self.directory).as_posix()

    def read_json_artifact(self, relative: str) -> Any:
        return json.loads(self._resolve_artifact(relative).read_text(encoding="utf-8"))

    def _artifact_path(self, relative: str) -> Path:
        path = (self.artifacts / relative).resolve()
        if self.artifacts.resolve() not in path.parents:
            raise JournalError(f"Artifact escapes journal directory: {relative!r}")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _resolve_artifact(self, relative: str) -> Path:
        path = (self.directory / relative).resolve()
        if self.directory.resolve() not in path.parents:
            raise JournalError(f"Artifact escapes journal directory: {relative!r}")
        if not path.is_file():
            raise JournalError(f"Missing journal artifact: {relative}")
        return path

    def _save(self) -> None:
        self.state["updated_at"] = _now()
        self.directory.mkdir(parents=True, exist_ok=True)
        self._atomic_write_text(self.path, json.dumps(self.state, indent=2) + "\n")

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
