"""QixEnemy: erratic bouncing polygon confined to unclaimed space.

Pure Python module - no pygame/moderngl imports allowed. Speed and
turn-rate scale with the current level. The enemy is represented as a
small closed polygon (a rotated shape) whose centroid moves through
open (unclaimed) space, reflecting off the claimed border and off the
edges of the overall play field.

The Board object is expected to expose:
    - Board.border: list[Point] -- outer play-field border (closed polygon)
    - Board.claimed_polygons: list[list[Point]] -- claimed area polygons
      (i.e. regions the Qix must NOT enter)

We use gamelib.grid_geometry.point_in_polygon to test whether the
candidate next position would land inside any claimed polygon (or
outside the overall border), and if so we bounce (reflect velocity)
and reduce the step to avoid tunnelling.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import List, Tuple

from gamelib.grid_geometry import Point, point_in_polygon

# Base tuning constants (can be scaled per-level from outside via
# QixEnemy.set_level, or by passing level directly to constructor).
_BASE_SPEED = 120.0  # pixels/second
_BASE_TURN_RATE = 2.5  # radians/second max erratic turn contribution
_DIRECTION_CHANGE_INTERVAL = 0.6  # seconds between erratic direction jitters
_SHAPE_RADIUS = 14.0
_SHAPE_SIDES = 5


def _make_shape_offsets(sides: int, radius: float) -> List[Point]:
    offsets: List[Point] = []
    for i in range(sides):
        angle = (2.0 * math.pi * i) / sides
        offsets.append((radius * math.cos(angle), radius * math.sin(angle)))
    return offsets


@dataclass
class QixEnemy:
    position: Point
    velocity: Tuple[float, float] = field(default_factory=lambda: (0.0, 0.0))
    level: int = 1
    rotation: float = 0.0
    rotation_speed: float = 1.2
    _time_since_jitter: float = 0.0
    _rng: random.Random = field(default_factory=random.Random)
    _shape_offsets: List[Point] = field(default_factory=lambda: _make_shape_offsets(_SHAPE_SIDES, _SHAPE_RADIUS))

    def __post_init__(self) -> None:
        if self.velocity == (0.0, 0.0):
            angle = self._rng.uniform(0.0, 2.0 * math.pi)
            speed = self._speed()
            self.velocity = (speed * math.cos(angle), speed * math.sin(angle))

    def set_level(self, level: int) -> None:
        self.level = max(1, level)

    def _speed(self) -> float:
        return _BASE_SPEED * (1.0 + 0.15 * (self.level - 1))

    def _turn_rate(self) -> float:
        return _BASE_TURN_RATE * (1.0 + 0.10 * (self.level - 1))

    def polygon(self) -> List[Point]:
        """Return the enemy's current world-space polygon vertices."""
        cos_r = math.cos(self.rotation)
        sin_r = math.sin(self.rotation)
        px, py = self.position
        pts: List[Point] = []
        for ox, oy in self._shape_offsets:
            rx = ox * cos_r - oy * sin_r
            ry = ox * sin_r + oy * cos_r
            pts.append((px + rx, py + ry))
        return pts

    def _is_blocked(self, point: Point, board) -> bool:
        border = getattr(board, "border", None)
        if border and not point_in_polygon(point, border):
            return True
        claimed = getattr(board, "claimed_polygons", None) or []
        for poly in claimed:
            if poly and point_in_polygon(point, poly):
                return True
        return False

    def _bbox_of(self, poly: List[Point]) -> Tuple[float, float, float, float]:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        return (min(xs), min(ys), max(xs), max(ys))

    def update(self, dt: float, board) -> None:
        if dt <= 0.0:
            return

        self._time_since_jitter += dt
        if self._time_since_jitter >= _DIRECTION_CHANGE_INTERVAL:
            self._time_since_jitter = 0.0
            turn = self._rng.uniform(-1.0, 1.0) * self._turn_rate() * _DIRECTION_CHANGE_INTERVAL
            self._apply_turn(turn)

        speed = self._speed()
        vx, vy = self.velocity
        mag = math.hypot(vx, vy)
        if mag > 1e-6:
            vx, vy = (vx / mag) * speed, (vy / mag) * speed
            self.velocity = (vx, vy)

        step_dt = dt
        remaining = 1.0
        bounces = 0
        px, py = self.position

        while remaining > 0.0 and bounces < 4:
            dx = self.velocity[0] * step_dt * remaining
            dy = self.velocity[1] * step_dt * remaining
            candidate = (px + dx, py + dy)

            if self._is_blocked(candidate, board):
                normal = self._estimate_normal(board, (px, py), candidate)
                self._reflect(normal)
                bounces += 1
                remaining *= 0.5
                continue
            else:
                px, py = candidate
                remaining = 0.0

        self.position = (px, py)
        self.rotation += self.rotation_speed * dt

    def _apply_turn(self, angle: float) -> None:
        vx, vy = self.velocity
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        nvx = vx * cos_a - vy * sin_a
        nvy = vx * sin_a + vy * cos_a
        self.velocity = (nvx, nvy)

    def _reflect(self, normal: Tuple[float, float]) -> None:
        nx, ny = normal
        nlen = math.hypot(nx, ny)
        if nlen < 1e-6:
            self.velocity = (-self.velocity[0], -self.velocity[1])
            return
        nx, ny = nx / nlen, ny / nlen
        vx, vy = self.velocity
        dot = vx * nx + vy * ny
        rvx = vx - 2.0 * dot * nx
        rvy = vy - 2.0 * dot * ny
        jitter = self._rng.uniform(-0.3, 0.3)
        cos_j = math.cos(jitter)
        sin_j = math.sin(jitter)
        fvx = rvx * cos_j - rvy * sin_j
        fvy = rvx * sin_j + rvy * cos_j
        self.velocity = (fvx, fvy)

    def _estimate_normal(self, board, from_pt: Point, to_pt: Point) -> Tuple[float, float]:
        dx = to_pt[0] - from_pt[0]
        dy = to_pt[1] - from_pt[1]
        return (-dx, -dy)
