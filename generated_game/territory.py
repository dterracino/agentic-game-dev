"""
Territory claim detection algorithms.

Implements loop closure detection via grid snapping and polygon ray-casting,
flood-fill to identify claimed cells, and Bresenham line rasterization.
"""

from typing import List, Tuple, Set


def snap_to_grid(pos: Tuple[float, float], grid_size: int) -> Tuple[int, int]:
    """
    Snap a position to the nearest grid cell.
    
    Args:
        pos: (x, y) position in pixel coordinates
        grid_size: Size of each grid cell in pixels
    
    Returns:
        (grid_x, grid_y) grid cell coordinates
    """
    x, y = pos
    grid_x = int(x // grid_size)
    grid_y = int(y // grid_size)
    return (grid_x, grid_y)


def bresenham_line(p1: Tuple[float, float], p2: Tuple[float, float]) -> List[Tuple[int, int]]:
    """
    Rasterize a line using Bresenham's algorithm.
    
    Args:
        p1: (x1, y1) start point
        p2: (x2, y2) end point
    
    Returns:
        List of (x, y) integer pixel coordinates along the line
    """
    x1, y1 = int(round(p1[0])), int(round(p1[1]))
    x2, y2 = int(round(p2[0])), int(round(p2[1]))
    
    points: List[Tuple[int, int]] = []
    
    dx = abs(x2 - x1)
    dy = abs(y2 - y1)
    sx = 1 if x2 > x1 else -1
    sy = 1 if y2 > y1 else -1
    
    # Handle vertical/horizontal lines
    if dx == 0 and dy == 0:
        return [(x1, y1)]
    
    if dx > dy:
        # More horizontal
        err = dx / 2
        y = y1
        for x in range(x1, x2 + sx, sx):
            points.append((x, y))
            err -= dy
            if err < 0:
                y += sy
                err += dx
    else:
        # More vertical
        err = dy / 2
        x = x1
        for y in range(y1, y2 + sy, sy):
            points.append((x, y))
            err -= dx
            if err < 0:
                x += sx
                err += dy
    
    return points


def line_intersect(p1: Tuple[float, float], p2: Tuple[float, float],
                   p3: Tuple[float, float], p4: Tuple[float, float]) -> bool:
    """
    Check if two line segments intersect using orientation method.
    
    Args:
        p1, p2: First line segment endpoints
        p3, p4: Second line segment endpoints
    
    Returns:
        True if segments intersect, False otherwise
    """
    def orientation(p: Tuple[float, float], q: Tuple[float, float],
                    r: Tuple[float, float]) -> int:
        """Compute orientation of ordered triplet (p, q, r).
        Returns: 0 if collinear, 1 if clockwise, 2 if counterclockwise"""
        val = (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1])
        if abs(val) < 1e-9:
            return 0
        return 1 if val > 0 else 2
    
    def on_segment(p: Tuple[float, float], q: Tuple[float, float],
                   r: Tuple[float, float]) -> bool:
        """Check if q lies on segment pr"""
        return (min(p[0], r[0]) <= q[0] <= max(p[0], r[0]) and
                min(p[1], r[1]) <= q[1] <= max(p[1], r[1]))
    
    o1 = orientation(p1, p2, p3)
    o2 = orientation(p1, p2, p4)
    o3 = orientation(p3, p4, p1)
    o4 = orientation(p3, p4, p2)
    
    # General case
    if o1 != o2 and o3 != o4:
        return True
    
    # Collinear cases
    if o1 == 0 and on_segment(p1, p3, p2):
        return True
    if o2 == 0 and on_segment(p1, p4, p2):
        return True
    if o3 == 0 and on_segment(p3, p1, p4):
        return True
    if o4 == 0 and on_segment(p3, p2, p4):
        return True
    
    return False


def detect_closed_loop(player_trail: List[Tuple[float, float]],
                       qix_trail: List[Tuple[float, float]],
                       grid_size: int,
                       boundaries: Tuple[float, float, float, float]) -> Tuple[bool, Set[Tuple[int, int]]]:
    """
    Detect if player's active line forms a closed loop and identify claimed cells.
    
    Loop closure is detected by:
    1. Checking if the active line intersects the player's own trail
    2. Checking if the line intersects existing boundary (qix_trail)
    3. Snapping endpoints to grid for collision detection
    
    Args:
        player_trail: List of (x, y) positions of completed player trails
        qix_trail: List of (x, y) positions of the active line being drawn
        grid_size: Size of grid cells in pixels
        boundaries: (left, top, right, bottom) arena boundary in pixels
    
    Returns:
        (is_closed, claimed_cells_set) where claimed_cells_set is empty if not closed
    """
    # Need at least 3 points in qix_trail to form a meaningful loop
    if len(qix_trail) < 3:
        return (False, set())
    
    # Need player trail to close against
    if len(player_trail) == 0:
        return (False, set())
    
    # Check if qix_trail starts and ends at the boundary
    start_snapped = snap_to_grid(qix_trail[0], grid_size)
    end_snapped = snap_to_grid(qix_trail[-1], grid_size)
    
    # Both endpoints must be on the boundary or very close to it
    left, top, right, bottom = boundaries
    
    def is_on_boundary(pos: Tuple[float, float]) -> bool:
        """Check if position is on arena boundary (with small tolerance)"""
        x, y = pos
        margin = grid_size
        on_left = x < left + margin
        on_right = x > right - margin
        on_top = y < top + margin
        on_bottom = y > bottom - margin
        
        return (on_left or on_right) and (top <= y <= bottom) or \
               (on_top or on_bottom) and (left <= x <= right)
    
    if not (is_on_boundary(qix_trail[0]) and is_on_boundary(qix_trail[-1])):
        return (False, set())
    
    # Check if the active line intersects with itself (self-intersection)
    for i in range(len(qix_trail) - 1):
        for j in range(i + 2, len(qix_trail) - 1):
            # Avoid checking adjacent segments
            if j == i + 1:
                continue
            if line_intersect(qix_trail[i], qix_trail[i + 1],
                             qix_trail[j], qix_trail[j + 1]):
                return (False, set())
    
    # Check if active line intersects with completed player trail
    for i in range(len(qix_trail) - 1):
        for j in range(len(player_trail) - 1):
            if line_intersect(qix_trail[i], qix_trail[i + 1],
                             player_trail[j], player_trail[j + 1]):
                return (False, set())
    
    # If we reach here, the loop is closed
    # Combine trails to form the boundary of claimed territory
    combined_boundary = player_trail + qix_trail
    
    # Find a point inside the loop using ray casting
    # Start from the center of the bounding box of the boundary
    if len(combined_boundary) < 3:
        return (False, set())
    
    min_x = min(p[0] for p in combined_boundary)
    max_x = max(p[0] for p in combined_boundary)
    min_y = min(p[1] for p in combined_boundary)
    max_y = max(p[1] for p in combined_boundary)
    
    # Interior point for flood-fill
    interior_x = (min_x + max_x) / 2.0
    interior_y = (min_y + max_y) / 2.0
    interior_cell = snap_to_grid((interior_x, interior_y), grid_size)
    
    # Flood-fill from interior to find all claimed cells
    claimed = flood_fill(combined_boundary, interior_cell, boundaries, grid_size)
    
    return (True, claimed)


def flood_fill(grid_points: List[Tuple[float, float]],
               start_cell: Tuple[int, int],
               boundaries: Tuple[float, float, float, float],
               grid_size: int) -> Set[Tuple[int, int]]:
    """
    Flood-fill algorithm to find all cells enclosed by a polygon.
    
    Uses a simple BFS from start_cell to find all connected unclaimed cells
    within the boundary. Stops at cells on the polygon boundary.
    
    Args:
        grid_points: List of (x, y) points defining the boundary polygon
        start_cell: Starting (grid_x, grid_y) for flood-fill
        boundaries: (left, top, right, bottom) arena boundaries
        grid_size: Size of grid cells
    
    Returns:
        Set of (grid_x, grid_y) cells that are enclosed
    """
    left, top, right, bottom = boundaries
    
    # Convert polygon points to grid cells
    boundary_cells: Set[Tuple[int, int]] = set()
    for i in range(len(grid_points)):
        p1 = grid_points[i]
        p2 = grid_points[(i + 1) % len(grid_points)]
        
        # Rasterize the line segment
        line_cells = bresenham_line(p1, p2)
        for cell in line_cells:
            grid_x = int(cell[0] // grid_size)
            grid_y = int(cell[1] // grid_size)
            boundary_cells.add((grid_x, grid_y))
    
    # BFS flood-fill from start_cell
    visited: Set[Tuple[int, int]] = set()
    queue: List[Tuple[int, int]] = [start_cell]
    visited.add(start_cell)
    
    # Calculate grid boundaries
    grid_left = int(left // grid_size)
    grid_top = int(top // grid_size)
    grid_right = int(right // grid_size)
    grid_bottom = int(bottom // grid_size)
    
    while queue:
        cell_x, cell_y = queue.pop(0)
        
        # Check all 4 neighbors
        for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
            nx, ny = cell_x + dx, cell_y + dy
            
            # Skip if already visited or on boundary
            if (nx, ny) in visited or (nx, ny) in boundary_cells:
                continue
            
            # Skip if outside arena
            if not (grid_left <= nx <= grid_right and grid_top <= ny <= grid_bottom):
                continue
            
            visited.add((nx, ny))
            queue.append((nx, ny))
    
    return visited
