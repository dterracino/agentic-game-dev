from __future__ import annotations

import ast
import json
import re
import shutil
from pathlib import Path

from .models import GamePlan


SAFE_FILENAME = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*\.py$")


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
                    f"Output directory is not empty: {self.root}. Use --replace to overwrite it."
                )
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, filename: str) -> Path:
        if not SAFE_FILENAME.fullmatch(filename):
            raise WorkspaceError(f"Unsafe generated filename: {filename!r}")
        path = (self.root / filename).resolve()
        if path.parent != self.root:
            raise WorkspaceError(f"File escapes output directory: {filename!r}")
        return path

    def write_plan(self, plan: GamePlan) -> None:
        data = {
            "title": plan.title,
            "pitch": plan.pitch,
            "core_loop": plan.core_loop,
            "controls": plan.controls,
            "quality_bar": plan.quality_bar,
            "files": [vars(file) for file in plan.files],
        }
        (self.root / "game_plan.json").write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )

    def write_python(self, filename: str, content: str) -> None:
        ast.parse(content, filename=filename)
        self.path_for(filename).write_text(content.rstrip() + "\n", encoding="utf-8")

    def read_python_files(self) -> dict[str, str]:
        return {
            path.name: path.read_text(encoding="utf-8")
            for path in sorted(self.root.glob("*.py"))
        }
