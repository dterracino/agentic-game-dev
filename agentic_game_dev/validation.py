from __future__ import annotations

import ast
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


MISSING_MODULE_PATTERN = re.compile(r"No module named ['\"]([^'\"]+)['\"]")


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    report: str

    @property
    def missing_module(self) -> str | None:
        match = MISSING_MODULE_PATTERN.search(self.report)
        return match.group(1).split(".", 1)[0] if match else None


def validate_project(root: Path) -> ValidationResult:
    errors: list[str] = []
    files = sorted(root.glob("*.py"))
    if not (root / "main.py").is_file():
        errors.append("main.py is missing")

    for path in files:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
        except (OSError, SyntaxError) as exc:
            errors.append(f"{path.name}: {exc}")

    if errors:
        return ValidationResult(False, "\n".join(errors))
    return ValidationResult(True, f"Static validation passed for {len(files)} Python files")


def smoke_test(root: Path, python: Path, timeout: float) -> ValidationResult:
    """Import main with the game environment and SDL dummy drivers."""
    if not python.is_file():
        return ValidationResult(False, f"Game interpreter is missing: {python}")
    env = os.environ.copy()
    env.setdefault("SDL_VIDEODRIVER", "dummy")
    env.setdefault("SDL_AUDIODRIVER", "dummy")
    try:
        completed = subprocess.run(
            [str(python), "-c", "import main; assert callable(main.main)"],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ValidationResult(False, f"Import smoke test timed out after {timeout:g}s")
    output = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())
    if completed.returncode:
        return ValidationResult(False, output or f"Import exited with {completed.returncode}")
    return ValidationResult(True, output or "Import smoke test passed")


def run_game(root: Path, python: Path) -> int:
    if not python.is_file():
        raise RuntimeError(f"Game interpreter is missing: {python}")
    return subprocess.call([str(python), "main.py"], cwd=root)
