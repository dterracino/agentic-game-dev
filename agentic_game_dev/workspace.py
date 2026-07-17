from __future__ import annotations

import ast
import json
import os
import re
import shutil
from pathlib import Path

from .models import GamePlan


SAFE_FILENAME = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*\.py$")
SAFE_SUPPORT_FILES = {".gitignore", "requirements.txt"}


class WorkspaceError(RuntimeError):
    pass


class GameWorkspace:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def prepare(self, replace: bool) -> None:
        current = Path.cwd().resolve()
        protected = (
            self.root == current
            or self.root.parent == self.root
            or (self.root / ".git").exists()
        )
        if replace and protected:
            raise WorkspaceError(f"Refusing to replace protected directory: {self.root}")
        if self.root.exists() and any(self.root.iterdir()):
            if not replace:
                raise WorkspaceError(
                    f"Output directory is not empty: {self.root}. "
                    "Use resume to continue it or --replace to start over."
                )
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True, exist_ok=True)

    def prepare_resume(self) -> None:
        if not self.root.is_dir():
            raise WorkspaceError(f"Output directory does not exist: {self.root}")
        if not (self.root / ".agentic" / "run.json").is_file():
            raise WorkspaceError(f"No resumable run found in: {self.root}")

    def path_for(self, filename: str) -> Path:
        if not SAFE_FILENAME.fullmatch(filename):
            raise WorkspaceError(f"Unsafe generated filename: {filename!r}")
        path = (self.root / filename).resolve()
        if path.parent != self.root:
            raise WorkspaceError(f"File escapes output directory: {filename!r}")
        return path

    def write_plan(self, plan: GamePlan) -> None:
        self._atomic_write(
            self.root / "game_plan.json",
            json.dumps(plan.as_dict(), indent=2) + "\n",
        )

    def read_plan(self) -> GamePlan:
        path = self.root / "game_plan.json"
        if not path.is_file():
            raise WorkspaceError(f"Missing game plan: {path}")
        try:
            return GamePlan.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise WorkspaceError(f"Cannot read game plan: {exc}") from exc

    def write_python(self, filename: str, content: str) -> None:
        ast.parse(content, filename=filename)
        self._atomic_write(self.path_for(filename), content.rstrip() + "\n")

    def write_support_file(self, filename: str, content: str) -> None:
        if filename not in SAFE_SUPPORT_FILES:
            raise WorkspaceError(f"Unsafe support filename: {filename!r}")
        self._atomic_write(self.root / filename, content.rstrip() + "\n")

    def read_python_files(self) -> dict[str, str]:
        return {
            path.name: path.read_text(encoding="utf-8")
            for path in sorted(self.root.glob("*.py"))
        }

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
