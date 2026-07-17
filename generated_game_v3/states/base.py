"""State Protocol and StateID enum defining explicit game states and
transition contract.

This module defines the explicit finite state machine contract used by
core/state_machine.py. Every concrete state (MenuState, PlayingState,
PausedState, GameOverState) implements the `State` Protocol below.

No pygame or moderngl imports occur here beyond typing-only primitives;
this module stays lightweight and dependency-free so it can be imported
by both core and states without creating circular imports.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import List, Optional, Protocol, runtime_checkable

from core.game_context import GameContext


class StateID(Enum):
    """Explicit identifiers for every game state."""

    MENU = auto()
    PLAYING = auto()
    PAUSED = auto()
    GAME_OVER = auto()


@runtime_checkable
class State(Protocol):
    """Contract that every game state must fulfill.

    The StateMachine drives a State by calling, in order each frame:
      1. handle_events(events, ctx)
      2. update(dt, ctx)
      3. render(ctx)
      4. next(ctx) -> to determine whether/how to transition

    on_enter/on_exit bracket the lifetime of a state within the machine.
    """

    def on_enter(self, ctx: GameContext) -> None:
        """Called once when this state becomes the active state."""
        ...

    def on_exit(self, ctx: GameContext) -> None:
        """Called once when this state stops being the active state."""
        ...

    def handle_events(self, events: List[object], ctx: GameContext) -> None:
        """Process a batch of raw pygame events (or compatible objects)."""
        ...

    def update(self, dt: float, ctx: GameContext) -> None:
        """Advance state logic by dt seconds (already clamped)."""
        ...

    def render(self, ctx: GameContext) -> None:
        """Draw the current state using ctx.renderer."""
        ...

    def next(self, ctx: GameContext) -> Optional[StateID]:
        """Return the StateID to transition to, or None to stay."""
        ...
