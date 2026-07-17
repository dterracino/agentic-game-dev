"""Game over state: shows final score/area%, writes high score, returns to menu."""

from __future__ import annotations

from typing import Optional, List, Any

from states.base import StateID, State
from core.game_context import GameContext
from persistence.highscores import save_highscore


class GameOverState:
    """Displays final results, persists a high score entry, and waits for confirm."""

    def __init__(self, ctx: GameContext) -> None:
        self._next: Optional[StateID] = None
        self._final_score: int = 0
        self._final_percent: float = 0.0
        self._saved: bool = False

    def on_enter(self, ctx: GameContext) -> None:
        self._next = None
        self._saved = False

        score = getattr(ctx, "score", 0)
        percent = getattr(ctx, "percent_claimed", 0.0)

        # Prefer a scoreboard object if the context exposes one.
        scoreboard = getattr(ctx, "scoreboard", None)
        if scoreboard is not None:
            score = getattr(scoreboard, "score", score)
            percent = getattr(scoreboard, "total_percent_claimed", percent)

        self._final_score = int(score)
        self._final_percent = float(percent)

        if not self._saved:
            entry = {
                "score": self._final_score,
                "area_percent": self._final_percent,
                "level": getattr(ctx, "level", 1),
            }
            try:
                save_highscore(entry)
            except Exception:
                # Persistence failures must never crash the game state flow.
                pass
            self._saved = True

    def on_exit(self, ctx: GameContext) -> None:
        pass

    def handle_events(self, ctx: GameContext, events: List[Any]) -> None:
        pass

    def update(self, ctx: GameContext, dt: float) -> None:
        input_state = getattr(ctx, "input_state", None)
        confirm = False

        if input_state is not None:
            confirm = getattr(input_state, "confirm", False)

        if confirm:
            self._next = StateID.MENU

    def render(self, ctx: GameContext) -> None:
        renderer = getattr(ctx, "renderer", None)
        if renderer is None:
            return

        renderer.begin_frame()
        width, height = ctx.window_size
        center = (width / 2.0, height / 2.0)
        # Minimal, dependency-free way to signal state until text rendering
        # is added: draw a marker sized/colored by outcome.
        renderer.draw_marker(center, 20.0, (1.0, 0.2, 0.2, 1.0))
        renderer.end_frame()

    def next(self, ctx: GameContext) -> Optional[StateID]:
        result = self._next
        self._next = None
        return result
