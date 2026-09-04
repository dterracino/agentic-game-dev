from __future__ import annotations

from abc import ABC
from typing import ClassVar


class AgentRole(ABC):
    """Base contract for a model role and its prompt context."""

    name: ClassVar[str]
    instructions: ClassVar[str]

    @classmethod
    def system_prompt(cls) -> str:
        prompt = cls.instructions.strip()
        if not prompt:
            raise ValueError(f"{cls.__name__} has no instructions")
        return prompt

    @staticmethod
    def specification_section(specification: str) -> str:
        if not specification.strip():
            return ""
        return (
            "Authoritative game specification (preserve its explicit requirements):\n"
            f"{specification.strip()}\n\n"
        )
