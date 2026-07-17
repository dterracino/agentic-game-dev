from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


DISTRIBUTION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
IMPORT_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
VERSION_PATTERN = re.compile(r"^[A-Za-z0-9.,<>=!~*+_-]*$")


@dataclass(frozen=True)
class DependencySpec:
    distribution: str
    import_name: str
    version: str = ""
    reason: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "DependencySpec":
        dependency = cls(
            distribution=str(value["distribution"]).strip(),
            import_name=str(value["import_name"]).strip(),
            version=str(value.get("version", "")).strip(),
            reason=str(value.get("reason", "")).strip(),
        )
        dependency.validate()
        return dependency

    def validate(self) -> None:
        if not DISTRIBUTION_PATTERN.fullmatch(self.distribution):
            raise ValueError(f"Unsafe dependency name: {self.distribution!r}")
        if not IMPORT_PATTERN.fullmatch(self.import_name):
            raise ValueError(f"Unsafe dependency import: {self.import_name!r}")
        if self.version and not VERSION_PATTERN.fullmatch(self.version):
            raise ValueError(f"Unsafe dependency version: {self.version!r}")

    @property
    def requirement(self) -> str:
        return f"{self.distribution}{self.version}"

    def as_dict(self) -> dict[str, str]:
        return {
            "distribution": self.distribution,
            "import_name": self.import_name,
            "version": self.version,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class FileSpec:
    name: str
    purpose: str
    public_api: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "FileSpec":
        return cls(
            name=str(value["name"]),
            purpose=str(value["purpose"]),
            public_api=[str(item) for item in value.get("public_api", [])],
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "purpose": self.purpose,
            "public_api": self.public_api,
        }


@dataclass(frozen=True)
class GamePlan:
    title: str
    pitch: str
    core_loop: list[str]
    controls: list[str]
    quality_bar: list[str]
    files: list[FileSpec]
    dependencies: list[DependencySpec] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "GamePlan":
        files = [FileSpec.from_dict(item) for item in value["files"]]  # type: ignore[arg-type]
        dependencies = [
            DependencySpec.from_dict(item)
            for item in value.get("dependencies", [])  # type: ignore[union-attr]
        ]
        return cls(
            title=str(value["title"]),
            pitch=str(value["pitch"]),
            core_loop=[str(item) for item in value["core_loop"]],  # type: ignore[union-attr]
            controls=[str(item) for item in value["controls"]],  # type: ignore[union-attr]
            quality_bar=[str(item) for item in value["quality_bar"]],  # type: ignore[union-attr]
            files=files,
            dependencies=dependencies,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "pitch": self.pitch,
            "core_loop": self.core_loop,
            "controls": self.controls,
            "quality_bar": self.quality_bar,
            "files": [item.as_dict() for item in self.files],
            "dependencies": [item.as_dict() for item in self.dependencies],
        }

    def as_context(self) -> str:
        file_lines = "\n".join(
            f"- {item.name}: {item.purpose}; API: {', '.join(item.public_api) or 'internal'}"
            for item in self.files
        )
        dependency_lines = "\n".join(
            f"- {item.requirement} (import {item.import_name}): {item.reason}"
            for item in self.dependencies
        ) or "- Standard library only"
        return (
            f"Title: {self.title}\nPitch: {self.pitch}\n"
            f"Core loop: {'; '.join(self.core_loop)}\n"
            f"Controls: {'; '.join(self.controls)}\n"
            f"Quality bar: {'; '.join(self.quality_bar)}\n"
            f"Dependencies:\n{dependency_lines}\nFiles:\n{file_lines}"
        )

    def dependency_for_import(self, import_name: str) -> DependencySpec | None:
        return next(
            (item for item in self.dependencies if item.import_name == import_name),
            None,
        )
