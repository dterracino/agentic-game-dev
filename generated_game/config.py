"""
TERRITORY: Qix Clone - Configuration Module

Centralized constants for screen dimensions, FPS, player/enemy speeds,
colors, and arena boundaries. Zero logic, pure configuration.
"""

# Screen and display settings
SCREEN_WIDTH: int = 1280
SCREEN_HEIGHT: int = 720
FPS: int = 60

# Movement speeds (pixels per second)
PLAYER_SPEED: float = 240.0
ENEMY_SPEED: float = 200.0
STALKER_SPEED: float = 260.0
PATROLLER_SPEED: float = 180.0

# Rendering dimensions
LINE_WIDTH: int = 3
GRID_MARGIN: int = 40  # Pixel margin from screen edge to arena boundary
GRID_CELL_SIZE: int = 20  # Size of grid cells for territory detection

# Collision detection
COLLISION_RADIUS: int = 12  # Radius for cursor and enemy collision checks

# Colors (RGBA format)
COLOR_BG: tuple[int, int, int, int] = (20, 20, 30, 255)  # Dark blue background
COLOR_PLAYER_LINE: tuple[int, int, int, int] = (100, 200, 255, 255)  # Cyan player line
COLOR_PLAYER_CURSOR: tuple[int, int, int, int] = (0, 255, 150, 255)  # Bright cyan cursor
COLOR_STALKER: tuple[int, int, int, int] = (255, 0, 200, 255)  # Magenta stalker
COLOR_PATROLLER: tuple[int, int, int, int] = (0, 255, 255, 255)  # Cyan patroller
COLOR_CLAIMED_P1: tuple[int, int, int, int] = (100, 200, 255, 100)  # Semi-transparent cyan
COLOR_GRID: tuple[int, int, int, int] = (50, 50, 70, 80)  # Dim grid lines

# Arena boundaries and dimensions
ARENA_WIDTH: int = SCREEN_WIDTH - (2 * GRID_MARGIN)
ARENA_HEIGHT: int = SCREEN_HEIGHT - (2 * GRID_MARGIN)
BOUNDARY: dict[str, int] = {
    "left": GRID_MARGIN,
    "right": SCREEN_WIDTH - GRID_MARGIN,
    "top": GRID_MARGIN,
    "bottom": SCREEN_HEIGHT - GRID_MARGIN,
}
