from __future__ import annotations

from dataclasses import dataclass, field


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


@dataclass(frozen=True)
class GamePlan:
    title: str
    pitch: str
    core_loop: list[str]
    controls: list[str]
    quality_bar: list[str]
    files: list[FileSpec]

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "GamePlan":
        files = [FileSpec.from_dict(item) for item in value["files"]]  # type: ignore[arg-type]
        return cls(
            title=str(value["title"]),
            pitch=str(value["pitch"]),
            core_loop=[str(item) for item in value["core_loop"]],  # type: ignore[union-attr]
            controls=[str(item) for item in value["controls"]],  # type: ignore[union-attr]
            quality_bar=[str(item) for item in value["quality_bar"]],  # type: ignore[union-attr]
            files=files,
        )

    def as_context(self) -> str:
        file_lines = "\n".join(
            f"- {item.name}: {item.purpose}; API: {', '.join(item.public_api) or 'internal'}"
            for item in self.files
        )
        return (
            f"Title: {self.title}\nPitch: {self.pitch}\n"
            f"Core loop: {'; '.join(self.core_loop)}\n"
            f"Controls: {'; '.join(self.controls)}\n"
            f"Quality bar: {'; '.join(self.quality_bar)}\nFiles:\n{file_lines}"
        )
