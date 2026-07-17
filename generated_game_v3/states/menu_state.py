"""Title/menu screen state.

Shows instructions and waits for the player to confirm (Enter) to start
the PlayingState. Implements the State Protocol from states/base.py.
"""

from __future__ import annotations

from typing import Optional, List, Any

from states.base import State, StateID
from core.game_context import GameContext
from core.input import InputState


class MenuState:
    """Title/menu screen.

    Displays basic instructions and waits for confirm input to transition
    into PlayingState. Also allows quitting via the input state's quit
    flag (handled by the state machine / main loop).
    """

    def __init__(self, ctx: GameContext) -> None:
        self._next_state: Optional[StateID] = None
        self._title = "QIX CLONE: INK & EXPOSURE"
        self._instructions = [
            "Arrow keys / WASD: move",
            "Hold Left Shift: fast (risky) draw",
            "Claim 75% of the field to win",
            "Escape/P: pause",
            "",
            "Press ENTER to start",
        ]

    def on_enter(self, ctx: GameContext) -> None:
        self._next_state = None

    def on_exit(self, ctx: GameContext) -> None:
        pass

    def handle_events(self, ctx: GameContext, events: List[Any]) -> None:
        # Events are translated into InputState by core.input.poll and
        # stored on the context by main.py before calling handle_events;
        # menu only cares about confirm (checked in update()).
        pass

    def update(self, ctx: GameContext, dt: float) -> None:
        input_state: InputState = ctx.input_state
        if input_state.confirm:
            self._next_state = StateID.PLAYING

    def render(self, ctx: GameContext) -> None:
        renderer = ctx.renderer
        renderer.begin_frame()

        width, height = ctx.window_size
        center_x = width / 2.0
        center_y = height / 2.0

        title_pos = (center_x, center_y - 150.0)
        renderer.draw_text(
            self._title,
            title_pos,
            size=42,
            color=(1.0, 1.0, 1.0, 1.0),
            align="center",
        )

        line_spacing = 32.0
        start_y = center_y - 60.0
        for i, line in enumerate(self._instructions):
            pos = (center_x, start_y + i * line_spacing)
            if not line:
                continue
            is_prompt = line.strip().upper().startswith("PRESS ENTER")
            color = (1.0, 0.9, 0.3, 1.0) if is_prompt else (0.75, 0.9, 1.0, 1.0)
            size = 26 if is_prompt else 22
            renderer.draw_text(line, pos, size=size, color=color, align="center")

        renderer.end_frame()

    def next(self, ctx: GameContext) -> Optional[StateID]:
        return self._next_state
