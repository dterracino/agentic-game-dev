from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

DISTRIBUTION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
IMPORT_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
VERSION_PATTERN = re.compile(r"^[A-Za-z0-9.,<>=!~*+_-]*$")


def _list_field(
    value: dict[str, object], field_name: str, *, required: bool = False
) -> list[object]:
    raw = value[field_name] if required else value.get(field_name, [])
    if not isinstance(raw, list):
        raise TypeError(f"{field_name} must be a list")
    return raw


def _mapping_item(value: object, field_name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"Each {field_name} entry must be an object")
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError(f"Each {field_name} key must be a string")
        result[key] = item
    return result


@dataclass(frozen=True)
class DependencySpec:
    distribution: str
    import_name: str
    version: str = ""
    reason: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> DependencySpec:
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
    def from_dict(cls, value: dict[str, object]) -> FileSpec:
        return cls(
            name=str(value["name"]),
            purpose=str(value["purpose"]),
            public_api=[str(item) for item in _list_field(value, "public_api")],
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "purpose": self.purpose,
            "public_api": self.public_api,
        }


@dataclass(frozen=True)
class RenderEffectSpec:
    experience: str
    technique: str
    owner: str
    validation: str
    source_files: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> RenderEffectSpec:
        return cls(
            experience=str(value["experience"]).strip(),
            technique=str(value["technique"]).strip(),
            owner=str(value["owner"]).strip(),
            validation=str(value["validation"]).strip(),
            source_files=[
                str(item).strip() for item in _list_field(value, "source_files")
            ],
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "experience": self.experience,
            "technique": self.technique,
            "owner": self.owner,
            "validation": self.validation,
            "source_files": self.source_files,
        }


@dataclass(frozen=True)
class VisualAssetSpec:
    experience: str
    kind: str
    owner: str
    technique: str
    validation: str

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> VisualAssetSpec:
        return cls(
            experience=str(value["experience"]).strip(),
            kind=str(value["kind"]).strip(),
            owner=str(value["owner"]).strip(),
            technique=str(value["technique"]).strip(),
            validation=str(value["validation"]).strip(),
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "experience": self.experience,
            "kind": self.kind,
            "owner": self.owner,
            "technique": self.technique,
            "validation": self.validation,
        }


@dataclass(frozen=True)
class AudioAssetSpec:
    experience: str
    kind: str
    owner: str
    technique: str
    validation: str

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> AudioAssetSpec:
        return cls(
            experience=str(value["experience"]).strip(),
            kind=str(value["kind"]).strip(),
            owner=str(value["owner"]).strip(),
            technique=str(value["technique"]).strip(),
            validation=str(value["validation"]).strip(),
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "experience": self.experience,
            "kind": self.kind,
            "owner": self.owner,
            "technique": self.technique,
            "validation": self.validation,
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
    rendering_strategy: str = ""
    render_effects: list[RenderEffectSpec] = field(default_factory=list)
    visual_assets: list[VisualAssetSpec] = field(default_factory=list)
    audio_assets: list[AudioAssetSpec] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> GamePlan:
        files = [
            FileSpec.from_dict(_mapping_item(item, "files"))
            for item in _list_field(value, "files", required=True)
        ]
        dependencies = [
            DependencySpec.from_dict(_mapping_item(item, "dependencies"))
            for item in _list_field(value, "dependencies")
        ]
        render_effects = [
            RenderEffectSpec.from_dict(_mapping_item(item, "render_effects"))
            for item in _list_field(value, "render_effects")
        ]
        visual_assets = [
            VisualAssetSpec.from_dict(_mapping_item(item, "visual_assets"))
            for item in _list_field(value, "visual_assets")
        ]
        audio_assets = [
            AudioAssetSpec.from_dict(_mapping_item(item, "audio_assets"))
            for item in _list_field(value, "audio_assets")
        ]
        return cls(
            title=str(value["title"]),
            pitch=str(value["pitch"]),
            core_loop=[
                str(item) for item in _list_field(value, "core_loop", required=True)
            ],
            controls=[str(item) for item in _list_field(value, "controls")],
            quality_bar=[
                str(item) for item in _list_field(value, "quality_bar", required=True)
            ],
            files=files,
            dependencies=dependencies,
            rendering_strategy=str(value.get("rendering_strategy", "")).strip(),
            render_effects=render_effects,
            visual_assets=visual_assets,
            audio_assets=audio_assets,
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
            "rendering_strategy": self.rendering_strategy,
            "render_effects": [item.as_dict() for item in self.render_effects],
            "visual_assets": [item.as_dict() for item in self.visual_assets],
            "audio_assets": [item.as_dict() for item in self.audio_assets],
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
        effect_lines = "\n".join(
            f"- {item.experience}: {item.technique}; owner: {item.owner}; "
            f"sources: {', '.join(item.source_files) or 'none'}; "
            f"validation: {item.validation}"
            for item in self.render_effects
        ) or "- No special visual effects requested"
        asset_lines = "\n".join(
            f"- {item.experience} ({item.kind}): {item.technique}; "
            f"owner: {item.owner}; validation: {item.validation}"
            for item in self.visual_assets
        ) or "- No visual assets planned"
        audio_lines = "\n".join(
            f"- {item.experience} ({item.kind}): {item.technique}; "
            f"owner: {item.owner}; validation: {item.validation}"
            for item in self.audio_assets
        ) or "- No audio assets planned"
        return (
            f"Title: {self.title}\nPitch: {self.pitch}\n"
            f"Core loop: {'; '.join(self.core_loop)}\n"
            f"Controls: {'; '.join(self.controls)}\n"
            f"Quality bar: {'; '.join(self.quality_bar)}\n"
            f"Rendering strategy: {self.rendering_strategy or 'Not specified'}\n"
            f"Render effects:\n{effect_lines}\n"
            f"Visual assets:\n{asset_lines}\n"
            f"Audio assets:\n{audio_lines}\n"
            f"Dependencies:\n{dependency_lines}\nFiles:\n{file_lines}"
        )

    def dependency_for_import(self, import_name: str) -> DependencySpec | None:
        return next(
            (item for item in self.dependencies if item.import_name == import_name),
            None,
        )
