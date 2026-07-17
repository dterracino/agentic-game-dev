from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from .models import DependencySpec


class GameEnvironmentError(RuntimeError):
    pass


class GameEnvironment:
    def __init__(
        self,
        root: Path,
        *,
        base_python: Path | None = None,
        runner: Callable[..., Any] = subprocess.run,
        progress: Callable[[str], None] = print,
        timeout: float = 600.0,
    ) -> None:
        self.root = root.resolve()
        self.venv = self.root / ".venv"
        executable = "python.exe" if os.name == "nt" else "python"
        scripts = "Scripts" if os.name == "nt" else "bin"
        self.python = self.venv / scripts / executable
        self.base_python = Path(
            base_python or getattr(sys, "_base_executable", None) or sys.executable
        ).resolve()
        self.requirements_path = self.root / "requirements.txt"
        self.marker_path = self.root / ".agentic" / "environment.json"
        self.runner = runner
        self.progress = progress
        self.timeout = timeout

    def requirements_text(self, dependencies: Sequence[DependencySpec]) -> str:
        requirements = sorted({item.requirement for item in dependencies}, key=str.lower)
        return "\n".join(requirements) + ("\n" if requirements else "")

    def requirements_hash(self, dependencies: Sequence[DependencySpec]) -> str:
        return hashlib.sha256(self.requirements_text(dependencies).encode("utf-8")).hexdigest()

    def write_requirements(self, dependencies: Sequence[DependencySpec]) -> None:
        self._atomic_write(self.requirements_path, self.requirements_text(dependencies))

    def is_ready(self, dependencies: Sequence[DependencySpec]) -> bool:
        if not self.python.is_file() or not self.marker_path.is_file():
            return False
        try:
            marker = json.loads(self.marker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return marker.get("requirements_hash") == self.requirements_hash(dependencies)

    def ensure(self, dependencies: Sequence[DependencySpec]) -> None:
        for dependency in dependencies:
            dependency.validate()
        self.root.mkdir(parents=True, exist_ok=True)
        self.marker_path.parent.mkdir(parents=True, exist_ok=True)
        self.write_requirements(dependencies)

        if not self.python.is_file():
            self.progress(f"  Creating game environment: {self.venv}")
            self._run(
                [str(self.base_python), "-m", "venv", str(self.venv)],
                "create the game virtual environment",
            )

        if not self.python.is_file():
            raise GameEnvironmentError(
                f"Virtual environment did not create its Python interpreter: {self.python}"
            )

        self.progress(f"  Installing game dependencies into: {self.venv}")
        self._run(
            [
                str(self.python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "-r",
                str(self.requirements_path),
            ],
            "install game dependencies",
        )
        marker = {
            "python": str(self.python),
            "base_python": str(self.base_python),
            "requirements_hash": self.requirements_hash(dependencies),
            "requirements": [item.requirement for item in dependencies],
        }
        self._atomic_write(self.marker_path, json.dumps(marker, indent=2) + "\n")

    def _run(self, command: list[str], action: str) -> None:
        try:
            result = self.runner(
                command,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GameEnvironmentError(f"Could not {action}: {exc}") from exc
        if result.returncode != 0:
            output = "\n".join(
                part.strip()
                for part in (getattr(result, "stdout", ""), getattr(result, "stderr", ""))
                if part and part.strip()
            )
            if len(output) > 4000:
                output = output[-4000:]
            raise GameEnvironmentError(
                f"Could not {action} (exit {result.returncode}):\n{output}"
            )

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
