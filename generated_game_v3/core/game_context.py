"""Mutable world handle passed to every state.

Holds the ModernGL context (via renderer), the high-level Renderer,
current input state, score, RNG seed, and other cross-cutting world data.

This module intentionally avoids importing gamelib or states to keep the
layering strict: core -> states -> {gamelib, render}. GameContext holds
references to objects but does not itself perform any gamelib or pygame
event logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from core.input import InputState


@dataclass
class GameContext:
    """Mutable world handle passed to every state.

    Attributes:
        renderer: The high-level Renderer instance used for drawing.
        input_state: The most recently polled InputState.
        score: Current numeric score (mirrors ScoreBoard.score if used).
        lives: Current number of lives remaining.
        level: Current level index (1-based).
        rng_seed: Seed used to initialize any deterministic randomness.
        area_claimed_percent: Most recent percent_claimed() value, cached
            for states that need to read it without recomputation.
        window_size: (width, height) of the window in pixels.
        running: Flag the main loop checks to decide whether to keep looping.
        extra: Free-form dict for ad-hoc state-to-state handoff data
            (e.g. final score for GameOverState) without adding new fields
            for every small piece of transient information.
    """

    renderer: Any = None
    input_state: InputState = field(default_factory=InputState)
    score: int = 0
    lives: int = 3
    level: int = 1
    rng_seed: int = 0
    area_claimed_percent: float = 0.0
    window_size: tuple[int, int] = (0, 0)
    running: bool = True
    extra: dict = field(default_factory=dict)

    def reset_for_new_game(self, rng_seed: Optional[int] = None) -> None:
        """Reset mutable fields at the start of a new game/run."""
        self.score = 0
        self.lives = 3
        self.level = 1
        self.area_claimed_percent = 0.0
        self.extra.clear()
        if rng_seed is not None:
            self.rng_seed = rng_seed
