"""Title/menu screen state.

Shows instructions and waits for the player to confirm (Enter) to start
the PlayingState. Implements the State Protocol from states/base.py.
"""

from __future__ import annotations

from typing import Optional

from states.base import State, StateID
from core.game_context import GameContext
from core.input import InputState


class MenuState:
    """Title/menu screen.

    Displays basic instructions and waits for confirm input to transition
    into PlayingState. Also allows quitting via the input state's quit
    flag (handled by the state machine / main loop).
    """

    def __init__(self, context: GameContext) -> None:
        self._context = context
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

    def on_enter(self) -> None:
        self._next_state = None

    def on_exit(self) -> None:
        pass

    def handle_events(self, events: list) -> None:
        # Events are translated into InputState by core.input.poll and
        # stored on the context by the state machine / main loop before
        # calling handle_events; menu only cares about confirm/quit.
        pass

    def update(self, dt: float) -> None:
        input_state: InputState = self._context.input_state
        if input_state.confirm:
            self._next_state = StateID.PLAYING
        elif input_state.quit:
            self._next_state = StateID.QUIT

    def render(self) -> None:
        renderer = self._context.renderer
        renderer.begin_frame()

        width, height = self._context.window_size
        center_x = width / 2.0
        center_y = height / 2.0

        title_pos = (center_x, center_y - 120.0)
        renderer.draw_marker(title_pos, 6.0, (1.0, 1.0, 1.0, 1.0))

        line_spacing = 28.0
        start_y = center_y - 40.0
        for i, _line in enumerate(self._instructions):
            pos = (center_x, start_y + i * line_spacing)
            renderer.draw_marker(pos, 3.0, (0.7, 0.9, 1.0, 1.0))

        renderer.end_frame()

    def next(self) -> Optional[StateID]:
        return self._next_state
