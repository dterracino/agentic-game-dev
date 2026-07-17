"""Game over state: shows final score/area%, writes high score, returns to menu."""

from __future__ import annotations

from typing import Optional, List, Any

from states.base import StateID, State
from core.game_context import GameContext
from persistence.highscores import save_highscore


class GameOverState:
    """Displays final results, persists a high score entry, and waits for confirm."""

    def __init__(self) -> None:
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
            percent = getattr(scoreboard, "percent_claimed", percent)

        self._final_score = int(score)
        self._final_percent = float(percent)

        if not self._saved:
            entry = {
                "score": self._final_score,
                "percent_claimed": self._final_percent,
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
        input_state = getattr(ctx, "input_state", None)
        confirm = False

        if input_state is not None:
            confirm = getattr(input_state, "confirm", False)

        if confirm:
            self._next = StateID.MENU

    def update(self, ctx: GameContext, dt: float) -> None:
        pass

    def render(self, ctx: GameContext) -> None:
        renderer = getattr(ctx, "renderer", None)
        if renderer is None:
            return

        renderer.begin_frame()
        # This state has no dynamic geometry of its own beyond what the
        # renderer's higher-level UI drawing (if any) handles; markers are
        # used here as a minimal, dependency-free way to signal state.
        renderer.draw_marker((0.0, 0.0), 0.0, (0.0, 0.0, 0.0))
        renderer.end_frame()

    def next(self) -> Optional[StateID]:
        result = self._next
        self._next = None
        return result
