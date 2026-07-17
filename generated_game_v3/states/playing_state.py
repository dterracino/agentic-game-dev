"""Core gameplay state: glues gamelib entities to the renderer.

This module owns the live Board/Player/QixEnemy/Sparx instances during a
level of play, advances them with delta-time, and translates their pure
geometry primitives into calls on the Renderer. It never imports pygame or
moderngl types directly beyond what is exposed through GameContext/Renderer.
"""

from __future__ import annotations

from typing import List, Optional, Any

from core.game_context import GameContext
from core.input import InputState
from states.base import StateID, State

from gamelib.board import Board
from gamelib.player import Player
from gamelib.enemies import QixEnemy
from gamelib.sparx import Sparx, SparxSquad
from gamelib.scoring import ScoreBoard

import settings


def _make_default_border() -> List[tuple]:
    w, h = settings.WINDOW_SIZE
    margin = 40.0
    return [
        (margin, margin),
        (w - margin, margin),
        (w - margin, h - margin),
        (margin, h - margin),
    ]


class PlayingState:
    """Runs one round of the core gameplay loop."""

    def __init__(self, ctx: GameContext) -> None:
        self.ctx = ctx
        self._next: Optional[StateID] = None
        self.level = 1
        self._time_in_level = 0.0
        self._paused_requested = False
        self._dead = False
        self.scoreboard = ScoreBoard()
        self._reset_level()

    def _reset_level(self) -> None:
        border = _make_default_border()
        self.board = Board(width=settings.WINDOW_SIZE[0], height=settings.WINDOW_SIZE[1], border=border)
        cx = (border[0][0] + border[2][0]) / 2.0
        top_y = border[0][1]
        self.player = Player(pos=(cx, top_y))

        w, h = settings.WINDOW_SIZE
        qix_speed = settings.BASE_QIX_SPEED * (1.0 + settings.QIX_SPEED_LEVEL_SCALE * (self.level - 1))
        self.qix = QixEnemy(
            position=(w / 2.0, h / 2.0),
            level=self.level,
        )

        self.sparx_squad = SparxSquad(base_speed=settings.BASE_SPARX_SPEED, base_count=settings.BASE_SPARX_COUNT)
        self.sparx_squad.escalate(self.level)

        self._time_in_level = 0.0
        self._dead = False
        self._paused_requested = False
        self._next = None

    # --- State protocol -------------------------------------------------

    def on_enter(self, ctx: GameContext) -> None:
        pass

    def on_exit(self, ctx: GameContext) -> None:
        pass

    def handle_events(self, ctx: GameContext, events: List[Any]) -> None:
        # Actual pygame event -> InputState translation happens in core.input
        # and is applied via update(); pause key handling is derived from
        # the InputState passed to update as well, so nothing to do here.
        pass

    def update(self, ctx: GameContext, dt: float) -> None:
        if self._dead:
            return

        input_state: InputState = ctx.input_state

        if input_state.pause_toggled:
            self._paused_requested = True
            return

        self._time_in_level += dt

        target = self._area_target()

        self.player.update(dt, input_state, self.board)
        self.qix.update(dt, self.board)
        self.sparx_squad.update(dt, self.board)

        self._check_collisions()

        if not self._dead:
            percent = self.board.percent_claimed()
            ctx.percent_claimed = percent
            ctx.score = self.scoreboard.score
            if percent >= target:
                self.level += 1
                ctx.level = self.level
                self._reset_level()

        if self.scoreboard.lives <= 0:
            self._next = StateID.GAME_OVER

    def _area_target(self) -> float:
        targets = settings.AREA_TARGETS
        idx = min(self.level - 1, len(targets) - 1)
        idx = max(0, idx)
        return targets[idx]

    def _check_collisions(self) -> None:
        px, py = self.player.pos
        kill_radius = 10.0

        qx, qy = self.qix.position
        if (px - qx) ** 2 + (py - qy) ** 2 <= kill_radius ** 2:
            self._on_player_death()
            return

        for sparx in self.sparx_squad.sparx_list:
            sx, sy = sparx.position
            if (px - sx) ** 2 + (py - sy) ** 2 <= kill_radius ** 2:
                if self.player.drawing:
                    self._on_player_death()
                    return

    def _on_player_death(self) -> None:
        self._dead = True
        alive = self.scoreboard.lose_life()
        if alive:
            self._respawn()
        else:
            self._next = StateID.GAME_OVER

    def _respawn(self) -> None:
        self.board.cancel_trail()
        border = self.board.border
        cx = (border[0][0] + border[2][0]) / 2.0
        top_y = border[0][1]
        self.player = Player(pos=(cx, top_y))
        self._dead = False

    def render(self, ctx: GameContext) -> None:
        renderer = ctx.renderer
        renderer.begin_frame()

        renderer.draw_border(list(self.board.border))

        for poly in self.board.claimed_polygons:
            if len(poly) >= 3:
                from gamelib.polygon_fill import triangulate
                tris = triangulate(poly)
                if tris:
                    renderer.draw_claimed_area(tris)

        if self.board.active_trail:
            renderer.draw_trail(list(self.board.active_trail))

        renderer.draw_marker(
            self.player.pos, 6.0, settings.COLOR_PLAYER
        )
        renderer.draw_marker(
            self.qix.position, 12.0, settings.COLOR_QIX
        )
        for sparx in self.sparx_squad.sparx_list:
            renderer.draw_marker(sparx.position, 8.0, settings.COLOR_SPARX)

        renderer.end_frame()

    def next(self, ctx: GameContext) -> Optional[StateID]:
        if self._next is not None:
            result = self._next
            self._next = None
            return result
        if self._paused_requested:
            self._paused_requested = False
            return StateID.PAUSED
        return None
