"""
gamelib/polygon_fill.py

Pure-python geometry module responsible for splitting a claimed border
polygon by a committed trail path (the path the player drew while
exposed) into two or more resulting fill regions, and triangulating
simple polygons for rendering / area calculations.

This module has zero dependencies beyond gamelib.grid_geometry and the
standard library. It must remain headless-testable (no pygame/moderngl
imports).
"""

from __future__ import annotations

from typing import List, Tuple

from gamelib.grid_geometry import Point, polygon_area, segment_intersects

# Small epsilon for float comparisons.
_EPS = 1e-9


def _points_equal(a: Point, b: Point, eps: float = 1e-6) -> bool:
    return abs(a[0] - b[0]) <= eps and abs(a[1] - b[1]) <= eps


def _dedupe_consecutive(points: List[Point]) -> List[Point]:
    """Remove consecutive duplicate points (within epsilon)."""
    if not points:
        return []
    result = [points[0]]
    for p in points[1:]:
        if not _points_equal(result[-1], p):
            result.append(p)
    return result


def _find_border_insertion(border: List[Point], point: Point) -> int:
    """
    Find the index of the border edge (border[i] -> border[i+1]) that the
    given point lies on (or is closest to), returning i such that the
    point should be inserted between i and i+1.

    Falls back to the closest edge by perpendicular distance if no exact
    match is found (robust to minor floating point drift).
    """
    n = len(border)
    best_idx = 0
    best_dist = float("inf")
    for i in range(n):
        a = border[i]
        b = border[(i + 1) % n]
        dist = _point_segment_distance(point, a, b)
        if dist < best_dist:
            best_dist = dist
            best_idx = i
    return best_idx


def _point_segment_distance(p: Point, a: Point, b: Point) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx = bx - ax
    dy = by - ay
    length_sq = dx * dx + dy * dy
    if length_sq <= _EPS:
        ex = px - ax
        ey = py - ay
        return (ex * ex + ey * ey) ** 0.5
    t = ((px - ax) * dx + (py - ay) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    cx = ax + t * dx
    cy = ay + t * dy
    ex = px - cx
    ey = py - cy
    return (ex * ex + ey * ey) ** 0.5


def _insert_path_into_border(
    border: List[Point], entry: Point, exit_: Point, path_interior: List[Point]
) -> Tuple[List[Point], List[Point]]:
    """
    Build the two candidate border loops formed by splicing the trail path
    (entry -> interior points -> exit) into the border polygon at the
    two locations where entry and exit touch the border.

    Returns a tuple of two closed point loops (each a simple polygon,
    without an explicitly repeated final point).
    """
    n = len(border)

    entry_edge = _find_border_insertion(border, entry)
    exit_edge = _find_border_insertion(border, exit_)

    # Build an augmented border list with entry and exit spliced in at
    # their respective edges, preserving winding order.
    # We construct by walking the border and inserting the special points
    # right after the edge start index.
    augmented: List[Tuple[Point, str]] = []
    for i in range(n):
        augmented.append((border[i], "border"))
        if i == entry_edge:
            augmented.append((entry, "entry"))
        if i == exit_edge:
            augmented.append((exit_, "exit"))

    # If entry and exit collapse onto the same edge insertion point pair
    # ordering could be reversed; ensure entry appears before exit in the
    # sequence when both were injected into the same edge index -- if not,
    # swap semantics by finding actual positions.
    entry_pos = next(i for i, (_, tag) in enumerate(augmented) if tag == "entry")
    exit_pos = next(i for i, (_, tag) in enumerate(augmented) if tag == "exit")

    m = len(augmented)

    def collect_forward(start: int, end: int) -> List[Point]:
        pts = []
        i = start
        while True:
            pts.append(augmented[i][0])
            if i == end:
                break
            i = (i + 1) % m
        return pts

    # Loop A: from entry forward around border to exit, then back along
    # the trail path (reversed) to entry.
    loop_a_border_part = collect_forward(entry_pos, exit_pos)
    loop_a = loop_a_border_part + list(reversed(path_interior))

    # Loop B: from exit forward around border to entry, then along the
    # trail path (forward) back to exit.
    loop_b_border_part = collect_forward(exit_pos, entry_pos)
    loop_b = loop_b_border_part + list(path_interior)

    loop_a = _dedupe_consecutive(loop_a)
    loop_b = _dedupe_consecutive(loop_b)

    return loop_a, loop_b


def split_polygon_by_path(
    border: List[Point], path: List[Point]
) -> Tuple[List[List[Point]], List[List[Point]]]:
    """
    Split the claimed border polygon by a committed trail path.

    Args:
        border: closed polygon points (no repeated last point) describing
            the currently claimed border, in consistent winding order.
        path: the sequence of points forming the trail the player drew,
            starting and ending on the border (first and last points lie
            on/near border edges); interior points are the free-space
            trail.

    Returns:
        A tuple (regions, all polygons) where the first element is the
        list of resulting split polygons (each a list of Points), and the
        second element mirrors the same list -- kept as a tuple to match
        the declared API `tuple[list, list]`. Callers (Board) are expected
        to pick the smaller / target region(s) as newly claimed and treat
        the remainder as the new border candidate(s).

    If the path is degenerate (fewer than 2 points) or the border is
    degenerate (fewer than 3 points), returns ([], []).
    """
    if len(border) < 3 or len(path) < 2:
        return [], []

    entry = path[0]
    exit_ = path[-1]
    interior = path  # includes entry and exit endpoints intentionally

    loop_a, loop_b = _insert_path_into_border(border, entry, exit_, interior)

    regions: List[List[Point]] = []
    if len(loop_a) >= 3 and abs(polygon_area(loop_a)) > _EPS:
        regions.append(loop_a)
    if len(loop_b) >= 3 and abs(polygon_area(loop_b)) > _EPS:
        regions.append(loop_b)

    return regions, list(regions)


def _is_convex(a: Point, b: Point, c: Point) -> bool:
    cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return cross > 0


def _cross(o: Point, a: Point, b: Point) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _point_in_triangle(p: Point, a: Point, b: Point, c: Point) -> bool:
    d1 = _cross(a, b, p)
    d2 = _cross(b, c, p)
    d3 = _cross(c, a, p)
    has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (has_neg and has_pos)


def triangulate(poly: List[Point]) -> List[Point]:
    """
    Triangulate a simple polygon (may be convex or concave, no
    self-intersections assumed) using ear-clipping.

    Returns a flat list of Points, three per triangle, suitable for
    conversion into a flat float buffer by the renderer/board layer.
    """
    n = len(poly)
    if n < 3:
        return []
    if n == 3:
        return list(poly)

    # Ensure counter-clockwise winding for consistent ear-clipping
    # (signed area > 0 means CCW under our polygon_area convention).
    area = polygon_area(poly)
    pts = list(poly)
    if area < 0:
        pts = list(reversed(pts))

    indices = list(range(len(pts)))
    triangles: List[Point] = []

    # Safety bound on iterations to avoid infinite loops on degenerate input.
    guard = 0
    max_guard = len(pts) * len(pts) + 8

    while len(indices) > 3 and guard < max_guard:
        guard += 1
        ear_found = False
        num = len(indices)
        for i in range(num):
            i_prev = indices[(i - 1) % num]
            i_curr = indices[i]
            i_next = indices[(i + 1) % num]

            a = pts[i_prev]
            b = pts[i_curr]
            c = pts[i_next]

            if not _is_convex(a, b, c):
                continue

            # Check no other polygon vertex lies inside this candidate ear.
            has_point_inside = False
            for j in indices:
                if j in (i_prev, i_curr, i_next):
                    continue
                if _point_in_triangle(pts[j], a, b, c):
                    has_point_inside = True
                    break

            if has_point_inside:
                continue

            # It's a valid ear; clip it.
            triangles.extend([a, b, c])
            indices.pop(i)
            ear_found = True
            break

        if not ear_found:
            # Degenerate/self-intersecting polygon: fall back to a simple
            # fan triangulation from the first remaining vertex to avoid
            # crashing; this is best-effort robustness.
            fan_origin = indices[0]
            remaining = indices[1:]
            for k in range(len(remaining) - 1):
                triangles.extend(
                    [pts[fan_origin], pts[remaining[k]], pts[remaining[k + 1]]]
                )
            indices = []
            break

    if len(indices) == 3:
        a, b, c = (pts[indices[0]], pts[indices[1]], pts[indices[2]])
        triangles.extend([a, b, c])

    return triangles
