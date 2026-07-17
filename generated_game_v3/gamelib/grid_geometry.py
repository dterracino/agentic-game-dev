"""Pure geometry primitives shared across board/player/enemies.

This module is pure Python (no pygame/moderngl imports) and is
headless-testable. It defines the basic Point type and geometric
predicates used elsewhere in the codebase: point-in-polygon testing,
segment intersection, and polygon area computation.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

# A Point is a simple (x, y) float tuple.
Point = Tuple[float, float]

_EPS = 1e-9


def point_in_polygon(p: Point, poly: Sequence[Point]) -> bool:
    """Return True if point p lies inside polygon poly (ray casting).

    Uses a standard even-odd ray casting algorithm. Points exactly on
    an edge are treated as inside for robustness in claim logic.
    """
    if len(poly) < 3:
        return False

    x, y = p
    n = len(poly)
    inside = False

    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]

        # Check if point lies exactly on this edge (treat as inside).
        if _point_on_segment(p, (x1, y1), (x2, y2)):
            return True

        if (y1 > y) != (y2 > y):
            denom = (y2 - y1)
            if abs(denom) > _EPS:
                x_intersect = x1 + (y - y1) * (x2 - x1) / denom
                if x_intersect > x:
                    inside = not inside

    return inside


def _point_on_segment(p: Point, a: Point, b: Point) -> bool:
    """Return True if p lies on segment a-b (inclusive), within epsilon."""
    px, py = p
    ax, ay = a
    bx, by = b

    cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
    if abs(cross) > _EPS:
        return False

    dot = (px - ax) * (bx - ax) + (py - ay) * (by - ay)
    if dot < -_EPS:
        return False

    sq_len = (bx - ax) ** 2 + (by - ay) ** 2
    if dot > sq_len + _EPS:
        return False

    return True


def segment_intersects(
    a1: Point, a2: Point, b1: Point, b2: Point
) -> Optional[Point]:
    """Return the intersection point of segments a1-a2 and b1-b2, or None.

    Handles general intersection as well as collinear overlap by
    returning the first point of overlap encountered. Returns None if
    the segments do not intersect.
    """
    x1, y1 = a1
    x2, y2 = a2
    x3, y3 = b1
    x4, y4 = b2

    d1x = x2 - x1
    d1y = y2 - y1
    d2x = x4 - x3
    d2y = y4 - y3

    denom = d1x * d2y - d1y * d2x

    if abs(denom) < _EPS:
        # Parallel or collinear segments.
        cross = (x3 - x1) * d1y - (y3 - y1) * d1x
        if abs(cross) > _EPS:
            return None  # Parallel, not collinear.
        return _collinear_overlap_point(a1, a2, b1, b2)

    t = ((x3 - x1) * d2y - (y3 - y1) * d2x) / denom
    u = ((x3 - x1) * d1y - (y3 - y1) * d1x) / denom

    if -_EPS <= t <= 1 + _EPS and -_EPS <= u <= 1 + _EPS:
        ix = x1 + t * d1x
        iy = y1 + t * d1y
        return (ix, iy)

    return None


def _collinear_overlap_point(
    a1: Point, a2: Point, b1: Point, b2: Point
) -> Optional[Point]:
    """Find a point of overlap for two collinear segments, if any."""
    # Project onto the dominant axis to parametrize the shared line.
    dx = a2[0] - a1[0]
    dy = a2[1] - a1[1]

    if abs(dx) >= abs(dy):
        def param(p: Point) -> float:
            return p[0]
    else:
        def param(p: Point) -> float:
            return p[1]

    a_lo, a_hi = sorted((param(a1), param(a2)))
    b_lo, b_hi = sorted((param(b1), param(b2)))

    lo = max(a_lo, b_lo)
    hi = min(a_hi, b_hi)

    if lo > hi + _EPS:
        return None

    # Return the point on segment a corresponding to the overlap start.
    if abs(a_hi - a_lo) < _EPS:
        return a1

    t = (lo - a_lo) / (a_hi - a_lo)
    ix = a1[0] + t * (a2[0] - a1[0])
    iy = a1[1] + t * (a2[1] - a1[1])
    return (ix, iy)


def polygon_area(poly: Sequence[Point]) -> float:
    """Return the unsigned area of polygon poly via the shoelace formula."""
    n = len(poly)
    if n < 3:
        return 0.0

    total = 0.0
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        total += x1 * y2 - x2 * y1

    return abs(total) * 0.5


def polygon_signed_area(poly: Sequence[Point]) -> float:
    """Return the signed area of polygon poly (positive = CCW)."""
    n = len(poly)
    if n < 3:
        return 0.0

    total = 0.0
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        total += x1 * y2 - x2 * y1

    return total * 0.5
