"""Sparx enemies: patrol the claimed border of the Board.

Pure Python module (no pygame/moderngl imports) so it stays headless-testable.
Sparx entities walk along the polygon border formed by Board.border, moving
from vertex to vertex at a configurable speed. They can be spawned in either
direction along the border and reverse direction periodically or on level
escalation triggers handled by the caller (playing_state / level manager).

The Board is expected (per gamelib/board.py contract) to expose:
    - border: list[Point]  (closed polygon, ordered vertices)

Sparx only reads Board.border; it never mutates Board state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from gamelib.grid_geometry import Point

Color = Tuple[float, float, float]


def _border_length(border: List[Point]) -> float:
    if len(border) < 2:
        return 0.0
    total = 0.0
    n = len(border)
    for i in range(n):
        a = border[i]
        b = border[(i + 1) % n]
        dx = b[0] - a[0]
        dy = b[1] - a[1]
        total += (dx * dx + dy * dy) ** 0.5
    return total


def _point_at_distance(border: List[Point], distance: float) -> Point:
    """Return the point on the closed border polygon at arc-length `distance`
    from the border's first vertex, walking in vertex order (wrapping)."""
    n = len(border)
    if n < 2:
        return border[0] if border else (0.0, 0.0)

    total = _border_length(border)
    if total <= 0.0:
        return border[0]

    d = distance % total
    for i in range(n):
        a = border[i]
        b = border[(i + 1) % n]
        dx = b[0] - a[0]
        dy = b[1] - a[1]
        seg_len = (dx * dx + dy * dy) ** 0.5
        if seg_len <= 1e-9:
            continue
        if d <= seg_len:
            t = d / seg_len
            return (a[0] + dx * t, a[1] + dy * t)
        d -= seg_len
    # Fallback: last vertex
    return border[-1]


@dataclass
class Sparx:
    """A single Sparx enemy patrolling the claimed border.

    Position is tracked as arc-length distance along the border polygon,
    which naturally re-maps as the border changes shape after claims.
    """

    arc_distance: float = 0.0
    direction: int = 1  # +1 or -1 along vertex order
    speed: float = 60.0  # pixels/second along the border
    color: Color = (1.0, 0.6, 0.0)
    position: Point = field(default=(0.0, 0.0))
    radius: float = 6.0

    def update(self, dt: float, board) -> None:
        border = getattr(board, "border", None)
        if not border or len(border) < 2:
            self.position = self.position
            return

        total = _border_length(border)
        if total <= 0.0:
            return

        self.arc_distance = (self.arc_distance + self.direction * self.speed * dt) % total
        self.position = _point_at_distance(border, self.arc_distance)

    def reverse(self) -> None:
        self.direction *= -1


@dataclass
class SparxSquad:
    """Manages a collection of Sparx enemies and their level-based escalation."""

    sparx_list: List[Sparx] = field(default_factory=list)
    base_speed: float = 60.0
    base_count: int = 1

    def escalate(self, level: int) -> None:
        """Recompute count/speed for the given level, preserving existing
        sparx arc positions where possible and adding new ones as needed."""
        target_count = self.base_count + max(0, (level - 1) // 2)
        target_speed = self.base_speed * (1.0 + 0.15 * max(0, level - 1))

        for s in self.sparx_list:
            s.speed = target_speed

        while len(self.sparx_list) < target_count:
            idx = len(self.sparx_list)
            direction = 1 if idx % 2 == 0 else -1
            offset = (idx * 137.0)
            self.sparx_list.append(
                Sparx(
                    arc_distance=offset,
                    direction=direction,
                    speed=target_speed,
                )
            )

        while len(self.sparx_list) > target_count:
            self.sparx_list.pop()

    def update(self, dt: float, board) -> None:
        for s in self.sparx_list:
            s.update(dt, board)

    def positions(self) -> List[Point]:
        return [s.position for s in self.sparx_list]
