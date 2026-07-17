"""
gamelib/board.py

Owns claimed polygons, border, and active trail; resolves claim commits and
exposes percent_claimed.

This module is pure Python (no pygame/moderngl imports) so it stays
headless-testable, per the plan's layering rules. It relies only on
gamelib.grid_geometry and gamelib.polygon_fill for geometry operations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from gamelib.grid_geometry import Point, polygon_area, point_in_polygon
from gamelib.polygon_fill import split_polygon_by_path


@dataclass
class Board:
    """Owns the claimed polygon(s), the outer border, and the active trail.

    Attributes:
        width: field width in world units.
        height: field height in world units.
        border: the current outer boundary polygon (list of points) that the
            player is allowed to walk along safely. Initially the full
            rectangular field boundary.
        claimed_polygons: list of polygons (each a list of Points) that
            represent areas already claimed (filled) by the player.
        active_trail: the in-progress trail path being drawn by the player
            while off the border, or an empty list if no trail is active.
    """

    width: float
    height: float
    border: List[Point] = field(default_factory=list)
    claimed_polygons: List[List[Point]] = field(default_factory=list)
    active_trail: List[Point] = field(default_factory=list)

    _total_area: float = field(default=0.0, init=False, repr=False)
    _claimed_area: float = field(default=0.0, init=False, repr=False)
    _trail_active: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.border:
            self.border = [
                (0.0, 0.0),
                (self.width, 0.0),
                (self.width, self.height),
                (0.0, self.height),
            ]
        self._total_area = abs(polygon_area(self.border)) if self.border else (
            self.width * self.height
        )
        if self._total_area <= 0.0:
            self._total_area = max(self.width * self.height, 1e-9)
        self._claimed_area = 0.0
        self.active_trail = []
        self._trail_active = False

    # ------------------------------------------------------------------
    # Trail lifecycle
    # ------------------------------------------------------------------

    def start_trail(self, origin: Point) -> None:
        """Begin a new active trail at the given origin point.

        The origin should be a point on the current border (or on the
        boundary of a previously claimed polygon). Any previously active
        trail is discarded.
        """
        self.active_trail = [origin]
        self._trail_active = True

    def extend_trail(self, point: Point) -> None:
        """Append a new point to the active trail.

        No-op if no trail is currently active. Avoids appending duplicate
        consecutive points.
        """
        if not self._trail_active:
            return
        if self.active_trail and self.active_trail[-1] == point:
            return
        self.active_trail.append(point)

    def cancel_trail(self) -> None:
        """Discard the active trail without committing any claim."""
        self.active_trail = []
        self._trail_active = False

    def is_trail_active(self) -> bool:
        return self._trail_active

    # ------------------------------------------------------------------
    # Commit resolution
    # ------------------------------------------------------------------

    def commit_trail(self, exit_point: Point, side_hint: Optional[Point] = None) -> float:
        """Finalize the active trail by connecting it back to the border.

        This splits the current border polygon into two (or more) regions
        using the trail path (start point through exit_point), determines
        which resulting region(s) do NOT contain the side_hint (i.e. the
        newly claimed area, since side_hint typically marks a point known
        to remain "open"/unclaimed such as an enemy position or the
        board's designated open-area marker), adds those regions to
        claimed_polygons, and updates the border to be the union / just the
        remaining open region.

        Returns the percent of total board area claimed as a float in
        [0.0, 100.0], reflecting the state *after* this commit.

        If there is no active trail, or the trail has fewer than 2 points,
        this is a no-op that returns the current percent_claimed().
        """
        if not self._trail_active or len(self.active_trail) < 1:
            return self.percent_claimed()

        path = list(self.active_trail)
        if not path or path[-1] != exit_point:
            path.append(exit_point)

        if len(path) < 2:
            self.cancel_trail()
            return self.percent_claimed()

        try:
            regions, _ = split_polygon_by_path(self.border, path)
        except Exception:
            # Defensive: malformed geometry should not crash the game loop;
            # simply cancel the trail and report current state.
            self.cancel_trail()
            return self.percent_claimed()

        if not regions:
            self.cancel_trail()
            return self.percent_claimed()

        # Determine which regions are newly claimed vs. remain open.
        # side_hint marks a point that should remain in the *open* (border)
        # region. Any region NOT containing side_hint is considered claimed.
        claimed_regions: List[List[Point]] = []
        open_regions: List[List[Point]] = []

        if side_hint is not None and len(regions) > 1:
            for region in regions:
                if len(region) < 3:
                    continue
                if point_in_polygon(side_hint, region):
                    open_regions.append(region)
                else:
                    claimed_regions.append(region)
            # If side_hint didn't land cleanly in any region (edge case),
            # fall back to treating the largest region as open and the
            # rest as claimed.
            if not open_regions:
                regions_sorted = sorted(
                    regions, key=lambda r: abs(polygon_area(r)), reverse=True
                )
                open_regions = [regions_sorted[0]]
                claimed_regions = regions_sorted[1:]
        else:
            # No usable side hint, or a single region resulted (degenerate
            # split): treat the largest region as the remaining open area
            # and all others as claimed.
            regions_sorted = sorted(
                regions, key=lambda r: abs(polygon_area(r)), reverse=True
            )
            open_regions = [regions_sorted[0]]
            claimed_regions = regions_sorted[1:]

        for region in claimed_regions:
            if len(region) >= 3:
                self.claimed_polygons.append(region)
                self._claimed_area += abs(polygon_area(region))

        if open_regions:
            # Keep the largest open region as the new border to walk along.
            open_regions.sort(key=lambda r: abs(polygon_area(r)), reverse=True)
            self.border = open_regions[0]
            # Any additional smaller "open" regions are unusual (would
            # imply a fragmented playfield); treat them as claimed too so
            # the area accounting stays consistent and the border remains
            # a single simple polygon.
            for extra in open_regions[1:]:
                if len(extra) >= 3:
                    self.claimed_polygons.append(extra)
                    self._claimed_area += abs(polygon_area(extra))

        self.cancel_trail()
        return self.percent_claimed()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def percent_claimed(self) -> float:
        """Return percent of total board area currently claimed, 0..100."""
        if self._total_area <= 0.0:
            return 0.0
        pct = (self._claimed_area / self._total_area) * 100.0
        if pct < 0.0:
            pct = 0.0
        if pct > 100.0:
            pct = 100.0
        return pct

    def point_on_border(self, point: Point, tolerance: float = 1e-6) -> bool:
        """Check whether a point lies on (or very near) the current border
        polygon's edges. Useful for validating trail start/end points.
        """
        border = self.border
        n = len(border)
        if n < 2:
            return False
        for i in range(n):
            a = border[i]
            b = border[(i + 1) % n]
            if _point_on_segment(point, a, b, tolerance):
                return True
        return False

    def is_point_in_open_area(self, point: Point) -> bool:
        """Return True if the point lies within the current open (border)
        region, i.e. is a valid location for drawing a new trail.
        """
        return point_in_polygon(point, self.border)


def _point_on_segment(
    p: Point, a: Point, b: Point, tolerance: float
) -> bool:
    """Return True if point p lies on segment a-b within tolerance."""
    ax, ay = a
    bx, by = b
    px, py = p

    cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
    seg_len_sq = (bx - ax) ** 2 + (by - ay) ** 2
    if seg_len_sq <= 1e-12:
        dist_sq = (px - ax) ** 2 + (py - ay) ** 2
        return dist_sq <= tolerance ** 2

    if abs(cross) > tolerance * (seg_len_sq ** 0.5) * 4.0:
        return False

    dot = (px - ax) * (bx - ax) + (py - ay) * (by - ay)
    t = dot / seg_len_sq
    return -1e-6 <= t <= 1.0 + 1e-6
