"""
Player entity: dt-based movement constrained to border-walk or trail-draw
modes per Qix rules.

This module is pure Python (dataclasses/functions only) and must not import
pygame, moderngl, or any state/render module. It only depends on
gamelib.grid_geometry for geometric primitives and interacts with a Board
instance strictly through its declared public API
(Board.border, Board.active_trail, Board.start_trail, Board.extend_trail,
Board.commit_trail, Board.cancel_trail).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from gamelib.grid_geometry import Point, point_in_polygon

# Base movement speed in world units per second (units are the same as the
# board's coordinate space, typically pixels).
BASE_SPEED: float = 180.0
# Fast-draw multiplier applied when the input requests fast draw (Shift).
FAST_DRAW_MULTIPLIER: float = 1.5
# Once a fast-draw dash begins, the player is committed to the current
# direction for this many seconds before a new direction can be chosen.
FAST_DRAW_COMMIT_WINDOW: float = 0.18
# Minimum distance from a border point to be considered "on the border".
BORDER_SNAP_EPS: float = 2.0


def _direction_from_intent(dx: int, dy: int) -> Optional[Tuple[float, float]]:
    """Convert discrete intent (-1,0,1) axis values into a normalized
    direction vector, prioritizing a single axis (4-directional intent).
    Returns None if there is no intent."""
    if dx == 0 and dy == 0:
        return None
    # Prefer horizontal over vertical if both pressed simultaneously,
    # to keep motion strictly 4-directional and deterministic.
    if dx != 0:
        return (1.0 if dx > 0 else -1.0, 0.0)
    return (0.0, 1.0 if dy > 0 else -1.0)


def _closest_point_on_segment(p: Point, a: Point, b: Point) -> Tuple[Point, float]:
    ax, ay = a
    bx, by = b
    px, py = p
    dx = bx - ax
    dy = by - ay
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq <= 1e-12:
        return a, ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = ((px - ax) * dx + (py - ay) * dy) / seg_len_sq
    if t < 0.0:
        t = 0.0
    elif t > 1.0:
        t = 1.0
    cx = ax + dx * t
    cy = ay + dy * t
    dist = ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5
    return (cx, cy), dist


def _nearest_border_point(pos: Point, border: list) -> Tuple[Point, float, int]:
    """Return (closest_point, distance, segment_index) of the closest point
    on the border polygon boundary to pos."""
    best_point: Point = pos
    best_dist = float("inf")
    best_idx = 0
    n = len(border)
    for i in range(n):
        a = border[i]
        b = border[(i + 1) % n]
        cp, dist = _closest_point_on_segment(pos, a, b)
        if dist < best_dist:
            best_dist = dist
            best_point = cp
            best_idx = i
    return best_point, best_dist, best_idx


@dataclass
class Player:
    """The player-controlled head that walks the claimed border or draws a
    trail across unclaimed space.

    Attributes:
        pos: current world-space position.
        drawing: whether the player is currently drawing an active trail.
        alive: whether the player is alive (killed externally by
            enemy-collision logic living elsewhere; Player itself does not
            perform collision-with-enemy checks).
        fast_draw_timer: remaining seconds of the current fast-draw
            no-turn commitment window (0 when not committed).
        committed_dir: the direction locked in during a fast-draw
            commitment window.
        speed: base movement speed (units/sec), may scale with level.
    """

    pos: Point
    drawing: bool = False
    alive: bool = True
    fast_draw_timer: float = 0.0
    committed_dir: Optional[Tuple[float, float]] = None
    speed: float = BASE_SPEED
    _last_dir: Optional[Tuple[float, float]] = field(default=None, repr=False)

    def update(self, dt: float, input_state, board) -> None:
        """Advance the player by dt seconds using input_state intent,
        constrained to border-walk or trail-draw modes as defined by the
        current Board state.

        input_state is expected to expose (as attributes or truthy values):
            move_x: int in {-1, 0, 1}
            move_y: int in {-1, 0, 1}
            fast_draw: bool (Shift held)

        board is expected to expose the Board public API:
            board.border -> list[Point]
            board.active_trail -> list[Point] | None
            board.start_trail(origin) -> None
            board.extend_trail(point) -> None
            board.commit_trail(exit_point, side_hint) -> float
            board.cancel_trail() -> None
        """
        if not self.alive:
            return

        dt = max(0.0, float(dt))

        move_x = int(getattr(input_state, "move_x", 0))
        move_y = int(getattr(input_state, "move_y", 0))
        fast_draw_requested = bool(getattr(input_state, "fast_draw", False))

        # Decrement fast-draw commitment window first.
        if self.fast_draw_timer > 0.0:
            self.fast_draw_timer = max(0.0, self.fast_draw_timer - dt)

        intent = _direction_from_intent(move_x, move_y)

        # If we're locked into a fast-draw commitment, ignore new direction
        # input and keep moving in the committed direction.
        if self.fast_draw_timer > 0.0 and self.committed_dir is not None:
            direction = self.committed_dir
        else:
            self.committed_dir = None
            direction = intent

        if direction is None:
            self._last_dir = None
            return

        speed = self.speed
        if fast_draw_requested:
            speed *= FAST_DRAW_MULTIPLIER

        dx, dy = direction
        new_pos: Point = (self.pos[0] + dx * speed * dt, self.pos[1] + dy * speed * dt)

        border = list(board.border)
        on_border_before = self._is_on_border(self.pos, border)

        if not self.drawing:
            # Currently walking the border (safe). Determine whether this
            # move keeps us on the border (auto walk) or pushes us into
            # unclaimed space (start drawing a trail).
            if on_border_before:
                still_on_border = self._is_on_border(new_pos, border)
                if still_on_border or point_in_polygon(new_pos, border):
                    # Moving along border edge or trivially inside claimed
                    # region boundary tolerance: snap to nearest border
                    # point to avoid drifting off the polygon edge.
                    snapped, dist, _ = _nearest_border_point(new_pos, border)
                    if dist <= BORDER_SNAP_EPS or still_on_border:
                        self.pos = snapped if still_on_border else self.pos
                        if still_on_border:
                            self.pos = new_pos
                        else:
                            self.pos = self.pos
                    else:
                        self.pos = new_pos
                else:
                    # Moved off the border into open (unclaimed) space:
                    # begin drawing a trail from our current border
                    # position.
                    self.drawing = True
                    board.start_trail(self.pos)
                    board.extend_trail(new_pos)
                    self.pos = new_pos
                    if fast_draw_requested:
                        self.fast_draw_timer = FAST_DRAW_COMMIT_WINDOW
                        self.committed_dir = direction
            else:
                # Not exactly on border (shouldn't normally happen); snap.
                snapped, _dist, _ = _nearest_border_point(self.pos, border)
                self.pos = snapped
        else:
            # Currently drawing a trail through unclaimed space.
            self.pos = new_pos
            reached_border, side_hint = self._check_reached_border(new_pos, border)
            if reached_border:
                board.extend_trail(new_pos)
                board.commit_trail(new_pos, side_hint)
                self.drawing = False
                self.fast_draw_timer = 0.0
                self.committed_dir = None
            else:
                board.extend_trail(new_pos)
                if fast_draw_requested and self.fast_draw_timer <= 0.0:
                    self.fast_draw_timer = FAST_DRAW_COMMIT_WINDOW
                    self.committed_dir = direction

        self._last_dir = direction

    def _is_on_border(self, p: Point, border: list) -> bool:
        _cp, dist, _idx = _nearest_border_point(p, border)
        return dist <= BORDER_SNAP_EPS

    def _check_reached_border(self, p: Point, border: list) -> Tuple[bool, int]:
        """Return (reached, side_hint) where side_hint is the segment index
        of the border edge the trail reconnected to."""
        _cp, dist, idx = _nearest_border_point(p, border)
        if dist <= BORDER_SNAP_EPS:
            return True, idx
        return False, 0
