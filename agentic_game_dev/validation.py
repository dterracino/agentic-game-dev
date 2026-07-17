from __future__ import annotations

import ast
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    report: str


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


def smoke_test(root: Path, timeout: float) -> ValidationResult:
    """Import main under SDL dummy drivers; never calls the interactive game loop."""
    env = os.environ.copy()
    env.setdefault("SDL_VIDEODRIVER", "dummy")
    env.setdefault("SDL_AUDIODRIVER", "dummy")
    try:
        completed = subprocess.run(
            [sys.executable, "-c", "import main; assert callable(main.main)"],
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


def run_game(root: Path) -> int:
    return subprocess.call([sys.executable, "main.py"], cwd=root)
