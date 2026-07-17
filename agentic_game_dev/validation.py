from __future__ import annotations

import ast
import os
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
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
    files = [
        path
        for path in sorted(root.rglob("*.py"))
        if ".venv" not in path.relative_to(root).parts
    ]
    if not (root / "main.py").is_file():
        errors.append("main.py is missing")

    for path in files:
        try:
            source = path.read_text(encoding="utf-8")
            ast.parse(source, filename=path.name)
            compile(source, path.name, "exec")
        except (OSError, SyntaxError) as exc:
            errors.append(f"{path.relative_to(root).as_posix()}: {exc}")

    if errors:
        return ValidationResult(False, "\n".join(errors))
    return ValidationResult(True, f"Static compilation passed for {len(files)} Python files")


def smoke_test(root: Path, python: Path, timeout: float) -> ValidationResult:
    """Launch the real entry point and require it to remain alive for the interval."""
    if not python.is_file():
        return ValidationResult(False, f"Game interpreter is missing: {python}")
    env = os.environ.copy()
    env.setdefault("SDL_AUDIODRIVER", "dummy")
    log_path = root / ".agentic" / "runtime.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            [str(python), "main.py"],
            cwd=root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            output, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                output, _ = process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                output, _ = process.communicate()
            elapsed = time.monotonic() - started
            _append_runtime_log(log_path, "active", elapsed, output)
            return ValidationResult(
                True,
                f"Runtime launch remained active for {timeout:g}s; log: {log_path}",
            )
    except OSError as exc:
        return ValidationResult(False, f"Could not launch game: {exc}")

    elapsed = time.monotonic() - started
    _append_runtime_log(log_path, f"exit {process.returncode}", elapsed, output)
    detail = output.strip()[-4000:] or "No stdout or stderr was produced."
    return ValidationResult(
        False,
        f"Game exited after {elapsed:.2f}s with code {process.returncode}; "
        f"expected it to remain active for {timeout:g}s. Log: {log_path}\n{detail}",
    )


def _append_runtime_log(path: Path, status: str, elapsed: float, output: str) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"\n=== {timestamp} | {status} | {elapsed:.2f}s ===\n")
        handle.write(output.rstrip() or "(no output)")
        handle.write("\n")


def run_game(root: Path, python: Path) -> int:
    if not python.is_file():
        raise RuntimeError(f"Game interpreter is missing: {python}")
    log_path = root / ".agentic" / "playtest.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n=== Interactive run {timestamp} ===\n")
        process = subprocess.Popen(
            [str(python), "main.py"],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        if process.stdout is not None:
            with process.stdout:
                for line in process.stdout:
                    print(line, end="")
                    log.write(line)
                    log.flush()
        return_code = process.wait()
        log.write(f"=== Exit code {return_code} ===\n")
    return return_code
