from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EngineeringPolicy:
    """Reusable non-functional requirements that do not belong in a game spec."""

    name: str
    requirements: tuple[str, ...]

    def prompt_section(self) -> str:
        rules = "\n".join(f"- {requirement}" for requirement in self.requirements)
        return f"Engineering policy ({self.name}; non-negotiable):\n{rules}"


DEFAULT_ENGINEERING_POLICY = EngineeringPolicy(
    name="maintainable-small-game",
    requirements=(
        "Apply separation of concerns: domain and gameplay rules must not depend on rendering, "
        "windowing, audio, or GUI toolkit objects.",
        "Apply DRY deliberately: centralize shared constants, configuration, state transitions, "
        "and cross-module contracts instead of duplicating knowledge.",
        "Give every module one clear responsibility; avoid monolithic game, renderer, and utility "
        "modules as well as needless abstraction layers.",
        "Keep dependency direction explicit, APIs typed and coherent, and imports acyclic.",
        "All generated Python must pass Pyright in strict mode with zero errors. Fix typing "
        "problems through accurate annotations, narrowing, Protocols, overloads, stubs, or "
        "corrected APIs; never use type: ignore, pyright: ignore, weakened per-file modes, or "
        "disabled diagnostic rules.",
        "Make deterministic domain behavior testable without opening a window or creating a GPU "
        "context.",
        "Give renderer resources, subscriptions, and other stateful objects explicit ownership "
        "and lifecycle cleanup.",
        "Prefer the simplest design that satisfies the game specification and quality contract.",
    ),
)
