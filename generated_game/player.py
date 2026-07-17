"""
Player cursor logic: movement along arena boundary, trail recording, and line-drawing state.
Updates position based on input and delta time, enforces boundary constraints, and manages active draw line.
"""

from typing import Tuple, List
import math


class Player:
    """
    Manages the player cursor, movement along arena boundary, trail tracking, and line drawing.
    """

    def __init__(self, pos: Tuple[float, float], speed: float) -> None:
        """
        Initialize the player cursor.

        Args:
            pos: Starting position (x, y) tuple, expected to be on the arena boundary.
            speed: Movement speed in pixels per second.
        """
        self.x: float = pos[0]
        self.y: float = pos[1]
        self.speed: float = speed
        self.trail: List[Tuple[float, float]] = [pos]
        self.drawing: bool = False
        self.draw_start_pos: Tuple[float, float] = pos
        self.draw_trail: List[Tuple[float, float]] = []

    def update(
        self,
        dt: float,
        keys: dict,
        boundaries: Tuple[float, float, float, float],
    ) -> None:
        """
        Update player position based on input and time delta, enforce boundary constraints.

        Args:
            dt: Delta time in seconds (clamped to prevent spikes).
            keys: Dictionary of pressed keys (pygame key constants as keys, bool as values).
            boundaries: Arena boundaries as (left, top, right, bottom).
        """
        # Clamp delta time to prevent large jumps
        dt = min(dt, 0.05)

        # Calculate movement direction from input
        dx: float = 0.0
        dy: float = 0.0

        # Arrow keys
        if keys.get("right"):
            dx += 1.0
        if keys.get("left"):
            dx -= 1.0
        if keys.get("down"):
            dy += 1.0
        if keys.get("up"):
            dy -= 1.0

        # WASD keys
        if keys.get("w"):
            dy -= 1.0
        if keys.get("a"):
            dx -= 1.0
        if keys.get("s"):
            dy += 1.0
        if keys.get("d"):
            dx += 1.0

        # Normalize diagonal movement
        magnitude = math.sqrt(dx * dx + dy * dy)
        if magnitude > 0.0:
            dx /= magnitude
            dy /= magnitude

        # Apply speed and delta time
        distance = self.speed * dt
        new_x = self.x + dx * distance
        new_y = self.y + dy * distance

        # Snap to boundary and update position
        self.x, self.y = self._constrain_to_boundary(
            new_x, new_y, boundaries
        )

        # Record trail position if not already at this position
        if len(self.trail) == 0 or (
            abs(self.x - self.trail[-1][0]) > 0.5
            or abs(self.y - self.trail[-1][1]) > 0.5
        ):
            self.trail.append((self.x, self.y))

        # If drawing, extend the draw trail
        if self.drawing:
            if len(self.draw_trail) == 0 or (
                abs(self.x - self.draw_trail[-1][0]) > 0.5
                or abs(self.y - self.draw_trail[-1][1]) > 0.5
            ):
                self.draw_trail.append((self.x, self.y))

    def draw_line(
        self, target_x: float, target_y: float, in_progress: bool = False
    ) -> List[Tuple[float, float]]:
        """
        Draw a perpendicular line from current boundary position toward interior.

        Args:
            target_x: Target x coordinate for the line endpoint.
            target_y: Target y coordinate for the line endpoint.
            in_progress: Whether the line is still being drawn (True) or finalized (False).

        Returns:
            List of (x, y) tuples representing the line points.
        """
        # Determine which edge the player is on
        edge = self._determine_edge(self.x, self.y)

        # Calculate direction perpendicular to the edge, pointing inward
        if edge == "top":
            direction = (0.0, 1.0)
        elif edge == "bottom":
            direction = (0.0, -1.0)
        elif edge == "left":
            direction = (1.0, 0.0)
        elif edge == "right":
            direction = (-1.0, 0.0)
        else:
            return []

        # Generate line points from current position in perpendicular direction
        line_points: List[Tuple[float, float]] = []
        current_x = self.x
        current_y = self.y

        # Step along the perpendicular direction
        step_distance = 1.0
        total_distance = 0.0
        max_distance = 500.0  # Reasonable max line length

        while total_distance < max_distance:
            line_points.append((current_x, current_y))
            current_x += direction[0] * step_distance
            current_y += direction[1] * step_distance
            total_distance += step_distance

        if in_progress:
            self.drawing = True
            self.draw_trail = line_points
        else:
            # Finalize the draw
            self.drawing = False

        return line_points

    def get_position(self) -> Tuple[float, float]:
        """
        Get the current player cursor position.

        Returns:
            (x, y) tuple of the player's position.
        """
        return (self.x, self.y)

    def get_trail(self) -> List[Tuple[float, float]]:
        """
        Get the complete movement trail of the player.

        Returns:
            List of (x, y) positions visited by the player.
        """
        return self.trail.copy()

    def reset_trail(self) -> None:
        """
        Reset the player's movement trail (typically after claiming territory or dying).
        """
        self.trail = [(self.x, self.y)]
        self.draw_trail = []
        self.drawing = False

    @staticmethod
    def is_on_boundary(
        pos: Tuple[float, float], boundaries: Tuple[float, float, float, float]
    ) -> bool:
        """
        Check if a position is on the arena boundary (within tolerance).

        Args:
            pos: (x, y) position to check.
            boundaries: Arena boundaries as (left, top, right, bottom).

        Returns:
            True if the position is on the boundary, False otherwise.
        """
        x, y = pos
        left, top, right, bottom = boundaries
        tolerance = 5.0

        on_top = (top - tolerance <= y <= top + tolerance) and (left <= x <= right)
        on_bottom = (
            bottom - tolerance <= y <= bottom + tolerance
        ) and (left <= x <= right)
        on_left = (left - tolerance <= x <= left + tolerance) and (top <= y <= bottom)
        on_right = (
            right - tolerance <= x <= right + tolerance
        ) and (top <= y <= bottom)

        return on_top or on_bottom or on_left or on_right

    def _constrain_to_boundary(
        self,
        x: float,
        y: float,
        boundaries: Tuple[float, float, float, float],
    ) -> Tuple[float, float]:
        """
        Constrain the player position to the arena boundary.

        Args:
            x: Desired x coordinate.
            y: Desired y coordinate.
            boundaries: Arena boundaries as (left, top, right, bottom).

        Returns:
            Constrained (x, y) position on the boundary.
        """
        left, top, right, bottom = boundaries

        # Determine which edge to snap to based on current position
        edge = self._determine_edge(self.x, self.y)

        if edge == "top":
            # Move along top edge
            clamped_x = max(left, min(right, x))
            return (clamped_x, top)
        elif edge == "bottom":
            # Move along bottom edge
            clamped_x = max(left, min(right, x))
            return (clamped_x, bottom)
        elif edge == "left":
            # Move along left edge
            clamped_y = max(top, min(bottom, y))
            return (left, clamped_y)
        elif edge == "right":
            # Move along right edge
            clamped_y = max(top, min(bottom, y))
            return (right, clamped_y)
        else:
            # Default: snap to nearest edge
            distances = [
                abs(self.x - left),  # distance to left
                abs(self.x - right),  # distance to right
                abs(self.y - top),  # distance to top
                abs(self.y - bottom),  # distance to bottom
            ]
            min_dist_idx = distances.index(min(distances))

            if min_dist_idx == 0:  # left edge
                return (left, max(top, min(bottom, y)))
            elif min_dist_idx == 1:  # right edge
                return (right, max(top, min(bottom, y)))
            elif min_dist_idx == 2:  # top edge
                return (max(left, min(right, x)), top)
            else:  # bottom edge
                return (max(left, min(right, x)), bottom)

    def _determine_edge(self, x: float, y: float) -> str:
        """
        Determine which edge of the arena the player is currently on.

        Args:
            x: Player x coordinate.
            y: Player y coordinate.

        Returns:
            One of: "top", "bottom", "left", "right", or "unknown".
        """
        # This is a simplified determination; in practice, track the edge explicitly
        tolerance = 10.0

        # Check which edge is closest
        if abs(y - 20.0) < tolerance:
            return "top"
        elif abs(y - 580.0) < tolerance:
            return "bottom"
        elif abs(x - 20.0) < tolerance:
            return "left"
        elif abs(x - 780.0) < tolerance:
            return "right"

        return "unknown"
