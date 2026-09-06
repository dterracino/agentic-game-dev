from __future__ import annotations

import ast
import io
import json
import os
import re
import shutil
import tokenize
from pathlib import Path, PurePosixPath

from .models import GamePlan

SAFE_PATH_PART = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SAFE_SUPPORT_FILES = {
    ".gitignore",
    "requirements.txt",
    "QA_ACCEPTANCE.md",
    "pyrightconfig.json",
}
GENERATED_SOURCE_SUFFIXES = {".py", ".vert", ".frag", ".glsl"}


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
        if "\\" in filename or ":" in filename:
            raise WorkspaceError(f"Unsafe generated filename: {filename!r}")
        relative = PurePosixPath(filename)
        parts = relative.parts
        if (
            relative.is_absolute()
            or not parts
            or any(part in {"", ".", ".."} for part in parts)
            or relative.suffix not in GENERATED_SOURCE_SUFFIXES
            or not SAFE_PATH_PART.fullmatch(relative.stem)
            or any(not SAFE_PATH_PART.fullmatch(part) for part in parts[:-1])
        ):
            raise WorkspaceError(f"Unsafe generated filename: {filename!r}")
        path = self.root.joinpath(*parts).resolve()
        if self.root not in path.parents:
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
        if Path(filename).suffix != ".py":
            raise WorkspaceError(f"Expected a Python filename: {filename!r}")
        ast.parse(content, filename=filename)
        self._atomic_write(self.path_for(filename), content.rstrip() + "\n")

    def write_generated_source(self, filename: str, content: str) -> None:
        path = self.validate_generated_source(filename, content)
        self._atomic_write(path, content.rstrip() + "\n")

    def validate_generated_source(self, filename: str, content: str) -> Path:
        """Validate a generated source response without changing the workspace."""
        path = self.path_for(filename)
        if path.suffix == ".py":
            tree = ast.parse(content, filename=filename)
            self._reject_placeholder_python(filename, content, tree)
        elif not content.strip():
            raise WorkspaceError(f"Generated shader source is empty: {filename!r}")
        if "\x00" in content:
            raise WorkspaceError(f"Generated source contains a null byte: {filename!r}")
        return path

    def write_typecheck_config(self) -> None:
        """Write the coordinator-owned strict configuration used by Pyright and Pylance."""
        config = {
            "include": ["."],
            "exclude": [".agentic", ".venv"],
            "typeCheckingMode": "strict",
        }
        self.write_support_file("pyrightconfig.json", json.dumps(config, indent=2))

    @staticmethod
    def _reject_placeholder_python(
        filename: str, content: str, tree: ast.AST
    ) -> None:
        provisional = re.compile(
            r"\b(?:TODO|placeholder|not implemented|would be implemented|for now)\b",
            re.IGNORECASE,
        )
        try:
            comments = (
                token.string
                for token in tokenize.generate_tokens(io.StringIO(content).readline)
                if token.type == tokenize.COMMENT
            )
            comment_list = list(comments)
            matching_comment = next(
                (comment for comment in comment_list if provisional.search(comment)), None
            )
        except tokenize.TokenError as exc:
            raise WorkspaceError(
                f"Generated Python tokenization failed for {filename!r}: {exc}"
            ) from exc
        if matching_comment:
            raise WorkspaceError(
                f"Generated Python contains provisional implementation language in "
                f"{filename!r}: {matching_comment.strip()}"
            )
        type_suppression = next(
            (
                comment
                for comment in comment_list
                if re.search(
                    r"#\s*(?:type\s*:\s*ignore\b|pyright\s*:\s*(?:ignore\b|"
                    r"(?:basic|standard|off)\b|report\w+\s*=\s*(?:false|none)\b))",
                    comment,
                    re.IGNORECASE,
                )
            ),
            None,
        )
        if type_suppression:
            raise WorkspaceError(
                f"Generated Python contains a prohibited type-check suppression in "
                f"{filename!r}: {type_suppression.strip()}"
            )

        declaration_functions: set[int] = set()
        for class_node in (
            node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        ):
            is_protocol = any(
                (isinstance(base, ast.Name) and base.id == "Protocol")
                or (isinstance(base, ast.Attribute) and base.attr == "Protocol")
                for base in class_node.bases
            )
            if is_protocol:
                declaration_functions.update(
                    id(member)
                    for member in class_node.body
                    if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
                )

        for node in ast.walk(tree):
            if not isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                continue
            body = list(node.body)
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                body = body[1:]
            is_stub = len(body) == 1 and (
                isinstance(body[0], ast.Pass)
                or (
                    isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and body[0].value.value is Ellipsis
                )
                or (
                    isinstance(body[0], ast.Raise)
                    and isinstance(body[0].exc, ast.Call)
                    and isinstance(body[0].exc.func, ast.Name)
                    and body[0].exc.func.id == "NotImplementedError"
                )
            )
            if is_stub:
                decorator_names = {
                    decorator.id
                    if isinstance(decorator, ast.Name)
                    else decorator.attr
                    if isinstance(decorator, ast.Attribute)
                    else ""
                    for decorator in node.decorator_list
                }
                if id(node) in declaration_functions or decorator_names.intersection(
                    {"abstractmethod", "overload"}
                ):
                    continue
                kind = "class" if isinstance(node, ast.ClassDef) else "function"
                raise WorkspaceError(
                    f"Generated Python contains stub {kind} {node.name!r} "
                    f"in {filename!r}"
                )

    def write_support_file(self, filename: str, content: str) -> None:
        if filename not in SAFE_SUPPORT_FILES:
            raise WorkspaceError(f"Unsafe support filename: {filename!r}")
        self._atomic_write(self.root / filename, content.rstrip() + "\n")

    def read_python_files(self) -> dict[str, str]:
        return {
            path.relative_to(self.root).as_posix(): path.read_text(encoding="utf-8")
            for path in sorted(self.root.rglob("*.py"))
            if ".venv" not in path.relative_to(self.root).parts
        }

    def read_generated_sources(self) -> dict[str, str]:
        return {
            path.relative_to(self.root).as_posix(): path.read_text(encoding="utf-8")
            for path in sorted(self.root.rglob("*"))
            if path.is_file()
            and path.suffix in GENERATED_SOURCE_SUFFIXES
            and not {".venv", ".agentic"}.intersection(path.relative_to(self.root).parts)
        }

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
