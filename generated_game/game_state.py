from enum import Enum
from typing import List, Set, Tuple, Optional


class GameState(Enum):
    """Enumeration of all possible game states."""
    MENU = "menu"
    PLAYING = "playing"
    CAUGHT = "caught"
    LEVEL_COMPLETE = "level_complete"
    GAME_OVER = "game_over"


class GameData:
    """Central game data container tracking all mutable state.
    
    Attributes:
        state: Current game state from GameState enum.
        score: Total points accumulated across all levels.
        level: Current level number (1-indexed).
        wave: Current enemy wave number within the level.
        claimed_percentage: Percentage of arena claimed by player (0-100).
        player_pos: Current player cursor position as (x, y) tuple.
        enemies: List of enemy objects with position and type.
        player_trail: List of (x, y) tuples representing active draw line.
        claimed_cells: Set of grid cell coordinates claimed by player.
    """

    def __init__(self) -> None:
        """Initialize game data with default/reset values."""
        self.state: GameState = GameState.MENU
        self.score: int = 0
        self.level: int = 1
        self.wave: int = 1
        self.claimed_percentage: float = 0.0
        self.player_pos: Tuple[float, float] = (0.0, 0.0)
        self.enemies: List = []
        self.player_trail: List[Tuple[float, float]] = []
        self.claimed_cells: Set[Tuple[int, int]] = set()

    def reset_level(self) -> None:
        """Reset level-specific state for a fresh attempt.
        
        Preserves score and level, clears trail, enemies, and claimed cells.
        Resets wave counter and claimed percentage.
        """
        self.wave = 1
        self.claimed_percentage = 0.0
        self.player_trail = []
        self.enemies = []
        self.claimed_cells = set()

    def add_claimed(self, cells: Set[Tuple[int, int]]) -> None:
        """Add a set of grid cells to claimed territory.
        
        Args:
            cells: Set of (row, col) grid cell coordinates to claim.
        """
        self.claimed_cells.update(cells)

    def check_collision(
        self,
        pos: Tuple[float, float],
        collision_radius: float
    ) -> Optional[int]:
        """Check if a position collides with any enemy.
        
        Uses axis-aligned bounding box (AABB) with collision radius.
        
        Args:
            pos: (x, y) position to check.
            collision_radius: Radius for collision detection.
            
        Returns:
            Index of colliding enemy in self.enemies, or None if no collision.
        """
        x, y = pos
        for idx, enemy in enumerate(self.enemies):
            enemy_pos = enemy.get_position()
            ex, ey = enemy_pos
            
            # AABB collision check using collision radius as half-width
            if (abs(x - ex) < collision_radius and
                abs(y - ey) < collision_radius):
                return idx
        
        return None

    def update_claimed_percentage(self, total_cells: int) -> None:
        """Update claimed percentage based on total arena cells.
        
        Args:
            total_cells: Total number of grid cells in arena.
        """
        if total_cells > 0:
            self.claimed_percentage = (len(self.claimed_cells) / total_cells) * 100.0
        else:
            self.claimed_percentage = 0.0

    def get_enemy_by_id(self, enemy_id: int) -> Optional:
        """Retrieve an enemy object by its index in the enemies list.
        
        Args:
            enemy_id: Index of the enemy in self.enemies.
            
        Returns:
            Enemy object if found, None otherwise.
        """
        if 0 <= enemy_id < len(self.enemies):
            return self.enemies[enemy_id]
        return None
