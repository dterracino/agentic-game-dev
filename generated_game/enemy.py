"""
Enemy AI and movement for both Stalker and Patroller types.
Each enemy tracks its own trail, updates position with delta time,
and returns movement vectors for next frame.
"""

from enum import Enum
from typing import List, Set, Tuple
import math


class EnemyType(Enum):
    """Enum for enemy types."""
    STALKER = "stalker"
    PATROLLER = "patroller"


class Enemy:
    """
    Base class for enemies.
    Handles position tracking, trail recording, and boundary constraints.
    """

    def __init__(self, pos: Tuple[float, float], speed: float, enemy_type: EnemyType) -> None:
        """
        Initialize an enemy.

        Args:
            pos: Initial position (x, y) as floats
            speed: Movement speed in pixels per second
            enemy_type: EnemyType enum value
        """
        self.x: float = pos[0]
        self.y: float = pos[1]
        self.speed: float = speed
        self.enemy_type: EnemyType = enemy_type
        self.trail: List[Tuple[float, float]] = [pos]
        self.velocity_x: float = 0.0
        self.velocity_y: float = 0.0

    def get_position(self) -> Tuple[float, float]:
        """Return current position as (x, y) tuple."""
        return (self.x, self.y)

    def get_trail(self) -> List[Tuple[float, float]]:
        """Return the trail of positions visited by this enemy."""
        return self.trail.copy()

    def reset_trail(self) -> None:
        """Clear the trail, keeping only current position."""
        self.trail = [(self.x, self.y)]

    def _clamp_to_boundaries(
        self, x: float, y: float, boundaries: Tuple[float, float, float, float]
    ) -> Tuple[float, float]:
        """
        Clamp position to arena boundaries.

        Args:
            x: X coordinate
            y: Y coordinate
            boundaries: (left, top, right, bottom) tuple

        Returns:
            Clamped (x, y) tuple
        """
        left, top, right, bottom = boundaries
        x = max(left, min(x, right))
        y = max(top, min(y, bottom))
        return (x, y)

    def _distance(self, x1: float, y1: float, x2: float, y2: float) -> float:
        """Calculate Euclidean distance between two points."""
        return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

    def _normalize_vector(self, vx: float, vy: float) -> Tuple[float, float]:
        """Normalize a vector to unit length."""
        length = math.sqrt(vx * vx + vy * vy)
        if length < 1e-6:
            return (0.0, 0.0)
        return (vx / length, vy / length)

    def update(
        self,
        dt: float,
        player_pos: Tuple[float, float],
        player_trail: List[Tuple[float, float]],
        claimed_cells: Set[Tuple[int, int]],
        boundaries: Tuple[float, float, float, float],
    ) -> Tuple[float, float]:
        """
        Update enemy position based on game state.
        Subclasses override this for specific behavior.

        Args:
            dt: Delta time since last frame (clamped to ~16ms)
            player_pos: Current player position
            player_trail: List of player trail points
            claimed_cells: Set of claimed grid cells
            boundaries: (left, top, right, bottom) arena boundaries

        Returns:
            New position (x, y)
        """
        # Base implementation: move in current velocity direction
        distance = self.speed * dt
        self.x += self.velocity_x * distance
        self.y += self.velocity_y * distance

        # Clamp to boundaries
        self.x, self.y = self._clamp_to_boundaries(self.x, self.y, boundaries)

        # Record position in trail
        if not self.trail or self._distance(self.x, self.y, self.trail[-1][0], self.trail[-1][1]) > 2.0:
            self.trail.append((self.x, self.y))
            # Keep trail reasonable length (last 200 points)
            if len(self.trail) > 200:
                self.trail.pop(0)

        return (self.x, self.y)


class StalkerEnemy(Enemy):
    """
    Stalker enemy that pathfinds toward the player's active line.
    Pursues the closest point on the player trail.
    """

    def __init__(self, pos: Tuple[float, float], speed: float) -> None:
        """
        Initialize a Stalker enemy.

        Args:
            pos: Initial position
            speed: Movement speed in pixels per second
        """
        super().__init__(pos, speed, EnemyType.STALKER)

    def update(
        self,
        dt: float,
        player_pos: Tuple[float, float],
        player_trail: List[Tuple[float, float]],
        claimed_cells: Set[Tuple[int, int]],
        boundaries: Tuple[float, float, float, float],
    ) -> Tuple[float, float]:
        """
        Update Stalker position: pathfind toward closest point on player trail.

        Args:
            dt: Delta time since last frame
            player_pos: Current player position
            player_trail: List of player trail points
            claimed_cells: Set of claimed grid cells (unused for Stalker)
            boundaries: Arena boundaries

        Returns:
            New position (x, y)
        """
        # Find closest point on player trail
        target_x, target_y = player_pos
        min_distance = float("inf")

        if player_trail:
            for trail_point in player_trail:
                dist = self._distance(self.x, self.y, trail_point[0], trail_point[1])
                if dist < min_distance:
                    min_distance = dist
                    target_x, target_y = trail_point

        # Calculate direction vector toward target
        dx = target_x - self.x
        dy = target_y - self.y

        # Normalize and set velocity
        self.velocity_x, self.velocity_y = self._normalize_vector(dx, dy)

        # Move using parent update
        return super().update(dt, player_pos, player_trail, claimed_cells, boundaries)


class PatrollerEnemy(Enemy):
    """
    Patroller enemy that bounces within claimed territory.
    Avoids unclaimed areas and bounces off boundaries.
    """

    def __init__(self, pos: Tuple[float, float], speed: float) -> None:
        """
        Initialize a Patroller enemy.

        Args:
            pos: Initial position
            speed: Movement speed in pixels per second
        """
        super().__init__(pos, speed, EnemyType.PATROLLER)
        self.bounce_timer: float = 0.0
        self.bounce_interval: float = 0.5  # Recalculate direction every 0.5s

    def update(
        self,
        dt: float,
        player_pos: Tuple[float, float],
        player_trail: List[Tuple[float, float]],
        claimed_cells: Set[Tuple[int, int]],
        boundaries: Tuple[float, float, float, float],
    ) -> Tuple[float, float]:
        """
        Update Patroller position: bounce within claimed territory.

        Args:
            dt: Delta time since last frame
            player_pos: Current player position (unused for Patroller targeting)
            player_trail: List of player trail points (unused for Patroller)
            claimed_cells: Set of claimed grid cells to patrol within
            boundaries: Arena boundaries

        Returns:
            New position (x, y)
        """
        self.bounce_timer += dt

        # Recalculate direction periodically or if no claimed cells
        if self.bounce_timer > self.bounce_interval or not claimed_cells:
            self.bounce_timer = 0.0

            if claimed_cells:
                # Find a claimed cell near current position
                closest_claimed = None
                min_dist = float("inf")

                for cell in claimed_cells:
                    # Cell center position (assuming grid_size = 32 as per config)
                    cell_x = cell[0] * 32 + 16
                    cell_y = cell[1] * 32 + 16
                    dist = self._distance(self.x, self.y, cell_x, cell_y)
                    if dist < min_dist:
                        min_dist = dist
                        closest_claimed = (cell_x, cell_y)

                if closest_claimed:
                    dx = closest_claimed[0] - self.x
                    dy = closest_claimed[1] - self.y
                    self.velocity_x, self.velocity_y = self._normalize_vector(dx, dy)
                else:
                    # Random direction if no claimed cells
                    import random
                    angle = random.uniform(0, 2 * math.pi)
                    self.velocity_x = math.cos(angle)
                    self.velocity_y = math.sin(angle)
            else:
                # No claimed cells: random walk
                import random
                angle = random.uniform(0, 2 * math.pi)
                self.velocity_x = math.cos(angle)
                self.velocity_y = math.sin(angle)

        # Move using parent update
        old_x, old_y = self.x, self.y
        super().update(dt, player_pos, player_trail, claimed_cells, boundaries)

        # Bounce detection: if hit boundary, reverse direction
        left, top, right, bottom = boundaries
        if self.x <= left or self.x >= right:
            self.velocity_x *= -1.0
        if self.y <= top or self.y >= bottom:
            self.velocity_y *= -1.0

        return (self.x, self.y)
