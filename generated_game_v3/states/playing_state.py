"""Core gameplay state: glues gamelib entities to the renderer.

This module owns the live Board/Player/QixEnemy/Sparx instances during a
level of play, advances them with delta-time, and translates their pure
geometry primitives into calls on the Renderer. It never imports pygame or
moderngl types directly beyond what is exposed through GameContext/Renderer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from core.game_context import GameContext
from core.input import InputState
from states.base import StateID, State

from gamelib.board import Board
from gamelib.player import Player
from gamelib.enemies import QixEnemy
from gamelib.sparx import Sparx
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


@dataclass
class PlayingState:
    """Runs one round of the core gameplay loop."""

    ctx: GameContext
    _next: Optional[StateID] = field(default=None, init=False)

    board: Board = field(init=False)
    player: Player = field(init=False)
    qix: QixEnemy = field(init=False)
    sparx_list: List[Sparx] = field(init=False, default_factory=list)
    scoreboard: ScoreBoard = field(init=False)

    level: int = field(default=1, init=False)
    _time_in_level: float = field(default=0.0, init=False)
    _paused_requested: bool = field(default=False, init=False)
    _dead: bool = field(default=False, init=False)

    def __init__(self, ctx: GameContext) -> None:
        self.ctx = ctx
        self._next = None
        self.level = 1
        self._time_in_level = 0.0
        self._paused_requested = False
        self._dead = False
        self._reset_level()

    def _reset_level(self) -> None:
        border = _make_default_border()
        self.board = Board(border=border)
        cx = (border[0][0] + border[2][0]) / 2.0
        top_y = border[0][1]
        self.player = Player(position=(cx, top_y))

        w, h = settings.WINDOW_SIZE
        qix_speed = settings.BASE_QIX_SPEED * (1.0 + 0.15 * (self.level - 1))
        self.qix = QixEnemy(
            position=(w / 2.0, h / 2.0),
            speed=qix_speed,
            level=self.level,
        )

        sparx_count = 1 + (self.level - 1) // 2
        self.sparx_list = []
        border_len = max(1, len(self.board.border))
        for i in range(sparx_count):
            t = i / float(sparx_count)
            sparx_speed = settings.BASE_SPARX_SPEED * (1.0 + 0.1 * (self.level - 1))
            self.sparx_list.append(
                Sparx(border_position=t, speed=sparx_speed, level=self.level)
            )

        if not hasattr(self, "scoreboard"):
            self.scoreboard = ScoreBoard()

        self._time_in_level = 0.0
        self._dead = False
        self._paused_requested = False
        self._next = None

    # --- State protocol -------------------------------------------------

    def on_enter(self) -> None:
        pass

    def on_exit(self) -> None:
        pass

    def handle_events(self, events: list) -> None:
        # Actual pygame event -> InputState translation happens in core.input
        # and is applied via update(); pause key handling is derived from
        # the InputState passed to update as well, so nothing to do here.
        pass

    def update(self, dt: float, input_state: InputState) -> None:
        if self._dead:
            return

        if input_state.pause_toggled:
            self._paused_requested = True
            return

        self._time_in_level += dt

        target = self._area_target()

        self.player.update(dt, input_state, self.board)
        self.qix.update(dt, self.board)

        for sparx in self.sparx_list:
            sparx.update(dt, self.board)

        self._check_collisions()

        if not self._dead:
            percent = self.board.percent_claimed()
            if percent >= target:
                self.level += 1
                self._reset_level()

        if self.scoreboard.lives <= 0:
            self._next = StateID.GAME_OVER

    def _area_target(self) -> float:
        targets = settings.AREA_TARGETS
        idx = min(self.level - 1, len(targets) - 1)
        idx = max(0, idx)
        return targets[idx]

    def _check_collisions(self) -> None:
        px, py = self.player.position
        kill_radius = 10.0

        qx, qy = self.qix.position
        if (px - qx) ** 2 + (py - qy) ** 2 <= kill_radius ** 2:
            self._on_player_death()
            return

        for sparx in self.sparx_list:
            sx, sy = sparx.position
            if (px - sx) ** 2 + (py - sy) ** 2 <= kill_radius ** 2:
                if self.player.is_drawing():
                    self._on_player_death()
                    return

    def _on_player_death(self) -> None:
        self._dead = True
        self.scoreboard.lives -= 1
        if self.scoreboard.lives > 0:
            self._respawn()
        else:
            self._next = StateID.GAME_OVER

    def _respawn(self) -> None:
        self.board.cancel_trail()
        border = self.board.border
        cx = (border[0][0] + border[2][0]) / 2.0
        top_y = border[0][1]
        self.player = Player(position=(cx, top_y))
        self._dead = False

    def render(self) -> None:
        renderer = self.ctx.renderer
        renderer.begin_frame()

        renderer.draw_border(list(self.board.border))

        tris: List[tuple] = []
        for poly in self.board.claimed_polygons:
            tris.extend(poly)
        if tris:
            renderer.draw_claimed_area(tris)

        if self.board.active_trail:
            renderer.draw_trail(list(self.board.active_trail))

        renderer.draw_marker(
            self.player.position, 6.0, settings.PLAYER_COLOR
        )
        renderer.draw_marker(
            self.qix.position, 12.0, settings.QIX_COLOR
        )
        for sparx in self.sparx_list:
            renderer.draw_marker(sparx.position, 8.0, settings.SPARX_COLOR)

        renderer.end_frame()

    def next(self) -> Optional[StateID]:
        if self._next is not None:
            result = self._next
            self._next = None
            return result
        if self._paused_requested:
            self._paused_requested = False
            return StateID.PAUSED
        return None
