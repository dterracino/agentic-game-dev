"""Paused state: freezes gameplay update, renders overlay, resumes on unpause."""

from __future__ import annotations

from typing import List, Optional

import pygame

from core.game_context import GameContext
from states.base import State, StateID


class PausedState:
    """Freezes gameplay update, renders a paused overlay, resumes on input."""

    def __init__(self, ctx: GameContext, previous_state: State) -> None:
        self._ctx = ctx
        self._previous_state = previous_state
        self._next_id: Optional[StateID] = None
        self._resume = False

    def on_enter(self, ctx: GameContext) -> None:
        self._next_id = None
        self._resume = False

    def on_exit(self, ctx: GameContext) -> None:
        pass

    def handle_events(self, ctx: GameContext, events: List[pygame.event.Event]) -> None:
        for event in events:
            if event.type == pygame.QUIT:
                self._next_id = StateID.MENU
                return
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_p):
                    self._resume = True
                elif event.key == pygame.K_RETURN:
                    self._resume = True

    def update(self, ctx: GameContext, dt: float) -> None:
        # Gameplay is frozen while paused; no update of underlying state.
        if self._resume:
            self._next_id = StateID.PLAYING

    def render(self, ctx: GameContext) -> None:
        # Render the frozen gameplay frame beneath the overlay.
        self._previous_state.render(ctx)

        renderer = ctx.renderer
        overlay_color = (0.0, 0.0, 0.0, 0.5)
        width, height = ctx.window_size

        overlay_tris = [
            (0.0, 0.0),
            (float(width), 0.0),
            (float(width), float(height)),
            (0.0, 0.0),
            (float(width), float(height)),
            (0.0, float(height)),
        ]
        renderer.draw_claimed_area(overlay_tris)

        center = (width / 2.0, height / 2.0)
        renderer.draw_marker(center, 10.0, (1.0, 1.0, 1.0))

    def next(self) -> Optional[StateID]:
        return self._next_id
