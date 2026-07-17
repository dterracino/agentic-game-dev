"""
Pygame rendering engine for TERRITORY: Qix Clone.
Handles all visual output: background, grid, trails, claimed territory,
sprites, HUD, and state overlays. Zero game logic.
"""

from typing import List, Tuple, Optional, Set
import pygame
from config import (
    COLOR_BG,
    COLOR_GRID,
    COLOR_PLAYER_LINE,
    COLOR_PLAYER_CURSOR,
    COLOR_STALKER,
    COLOR_PATROLLER,
    COLOR_CLAIMED_P1,
    LINE_WIDTH,
    GRID_CELL_SIZE,
)
from game_state import GameState


class GameRenderer:
    """Encapsulates all Pygame rendering operations."""

    def __init__(self, surface: pygame.Surface, width: int, height: int) -> None:
        """
        Initialize renderer with target surface and dimensions.

        Args:
            surface: Pygame Surface to render to
            width: Screen width in pixels
            height: Screen height in pixels
        """
        self.surface = surface
        self.width = width
        self.height = height

        # Initialize font for HUD and overlays
        try:
            self.font_large = pygame.font.Font(None, 48)
            self.font_medium = pygame.font.Font(None, 32)
            self.font_small = pygame.font.Font(None, 24)
        except pygame.error:
            # Fallback to system default if font loading fails
            self.font_large = pygame.font.Font(None, 48)
            self.font_medium = pygame.font.Font(None, 32)
            self.font_small = pygame.font.Font(None, 24)

    def draw_frame(self, game_data, boundaries: Tuple[int, int, int, int]) -> None:
        """
        Draw complete game frame: background, grid, claims, trails, sprites, HUD.
        Orchestrates all rendering in correct layering order.

        Args:
            game_data: GameData instance containing all game state
            boundaries: (left, top, right, bottom) arena bounds in pixels
        """
        # Clear screen with background color
        self.surface.fill(COLOR_BG)

        # Draw grid first (background layer)
        self.draw_grid(boundaries)

        # Draw claimed territory fills (beneath trails)
        if game_data.claimed_cells:
            self.draw_claimed_cells(game_data.claimed_cells, GRID_CELL_SIZE)

        # Draw all trails (player and enemies)
        if game_data.player_trail:
            self.draw_trail(game_data.player_trail, COLOR_PLAYER_LINE, is_solid=True)

        # Draw enemy trails with type-specific colors
        for enemy in game_data.enemies:
            enemy_trail = enemy.get_trail()
            if enemy_trail:
                enemy_color = (
                    COLOR_STALKER
                    if enemy.enemy_type == "stalker"
                    else COLOR_PATROLLER
                )
                self.draw_trail(enemy_trail, enemy_color, is_solid=False)

        # Draw sprites (cursor and enemies)
        self.draw_sprites(game_data.player_pos, game_data.enemies)

        # Draw HUD (score, level, percentage, wave)
        self.draw_hud(
            game_data.score, game_data.level, game_data.claimed_percentage, game_data.wave
        )

        # Draw state-specific overlays if not playing
        if game_data.state != GameState.PLAYING:
            self._draw_state_overlay(game_data.state)

        pygame.display.flip()

    def draw_grid(self, boundaries: Tuple[int, int, int, int]) -> None:
        """
        Draw arena grid: vertical and horizontal lines at GRID_CELL_SIZE intervals.
        Constrained to arena boundaries.

        Args:
            boundaries: (left, top, right, bottom) arena bounds in pixels
        """
        left, top, right, bottom = boundaries

        # Draw vertical lines
        x = left
        while x <= right:
            pygame.draw.line(self.surface, COLOR_GRID, (x, top), (x, bottom), 1)
            x += GRID_CELL_SIZE

        # Draw horizontal lines
        y = top
        while y <= bottom:
            pygame.draw.line(self.surface, COLOR_GRID, (left, y), (right, y), 1)
            y += GRID_CELL_SIZE

    def draw_trail(self, trail: List[Tuple[float, float]], color: Tuple[int, int, int], is_solid: bool = True) -> None:
        """
        Draw a trail as connected line segments.

        Args:
            trail: List of (x, y) coordinates forming the trail
            color: RGB color tuple
            is_solid: If True, draw solid line; if False, draw dashed/dotted
        """
        if len(trail) < 2:
            return

        # Convert trail to integer coordinates for pixel-perfect rendering
        trail_points = [(int(x), int(y)) for x, y in trail]

        if is_solid:
            # Draw solid line for player trail
            pygame.draw.lines(self.surface, color, trail_points, LINE_WIDTH)
        else:
            # Draw dashed line for enemy trails (every other segment)
            for i in range(0, len(trail_points) - 1, 2):
                pygame.draw.line(
                    self.surface,
                    color,
                    trail_points[i],
                    trail_points[min(i + 1, len(trail_points) - 1)],
                    LINE_WIDTH,
                )

    def draw_claimed_cells(self, claimed_cells: Set[Tuple[int, int]], grid_size: int) -> None:
        """
        Fill claimed territory cells with solid color.
        Each cell is a GRID_CELL_SIZE x GRID_CELL_SIZE rectangle.

        Args:
            claimed_cells: Set of (grid_x, grid_y) tuples representing claimed cells
            grid_size: Size of each grid cell in pixels
        """
        for grid_x, grid_y in claimed_cells:
            rect = pygame.Rect(grid_x * grid_size, grid_y * grid_size, grid_size, grid_size)
            pygame.draw.rect(self.surface, COLOR_CLAIMED_P1, rect)

    def draw_sprites(
        self, player_pos: Tuple[float, float], enemies: List
    ) -> None:
        """
        Draw player cursor and all enemy sprites.

        Args:
            player_pos: (x, y) player cursor position
            enemies: List of Enemy objects
        """
        # Draw player cursor as a small circle
        player_x, player_y = int(player_pos[0]), int(player_pos[1])
        pygame.draw.circle(self.surface, COLOR_PLAYER_CURSOR, (player_x, player_y), 6)

        # Draw enemies as circles, color-coded by type
        for enemy in enemies:
            enemy_x, enemy_y = enemy.get_position()
            enemy_x, enemy_y = int(enemy_x), int(enemy_y)

            enemy_color = (
                COLOR_STALKER if enemy.enemy_type == "stalker" else COLOR_PATROLLER
            )
            pygame.draw.circle(self.surface, enemy_color, (enemy_x, enemy_y), 5)

    def draw_hud(
        self, score: int, level: int, percentage: float, wave: int
    ) -> None:
        """
        Draw heads-up display: score, level, claimed percentage, enemy wave.
        Positioned in top-left corner with white text.

        Args:
            score: Player's current score
            level: Current level number
            percentage: Percentage of arena claimed (0-100)
            wave: Current enemy wave count
        """
        y_offset = 10
        line_height = 28

        # Score
        score_text = self.font_small.render(f"Score: {score}", True, (255, 255, 255))
        self.surface.blit(score_text, (10, y_offset))
        y_offset += line_height

        # Level
        level_text = self.font_small.render(f"Level: {level}", True, (255, 255, 255))
        self.surface.blit(level_text, (10, y_offset))
        y_offset += line_height

        # Claimed percentage
        percentage_text = self.font_small.render(
            f"Claimed: {percentage:.1f}%", True, (255, 255, 255)
        )
        self.surface.blit(percentage_text, (10, y_offset))
        y_offset += line_height

        # Wave
        wave_text = self.font_small.render(f"Wave: {wave}", True, (255, 255, 255))
        self.surface.blit(wave_text, (10, y_offset))

    def _draw_state_overlay(self, state: GameState) -> None:
        """
        Draw semi-transparent overlay with state-specific message.

        Args:
            state: Current GameState
        """
        # Create semi-transparent overlay
        overlay = pygame.Surface((self.width, self.height))
        overlay.set_alpha(200)
        overlay.fill((0, 0, 0))
        self.surface.blit(overlay, (0, 0))

        # Determine message based on state
        title = ""
        subtitle = ""

        if state == GameState.MENU:
            title = "TERRITORY"
            subtitle = "Press SPACE to start"
        elif state == GameState.CAUGHT:
            title = "CAUGHT!"
            subtitle = "Press SPACE to restart"
        elif state == GameState.LEVEL_COMPLETE:
            title = "LEVEL COMPLETE!"
            subtitle = "Press SPACE for next wave"
        elif state == GameState.GAME_OVER:
            title = "GAME OVER"
            subtitle = "Press SPACE to restart"

        # Render title
        if title:
            title_text = self.font_large.render(title, True, (255, 255, 0))
            title_rect = title_text.get_rect(
                center=(self.width // 2, self.height // 2 - 40)
            )
            self.surface.blit(title_text, title_rect)

        # Render subtitle
        if subtitle:
            subtitle_text = self.font_medium.render(subtitle, True, (255, 255, 255))
            subtitle_rect = subtitle_text.get_rect(
                center=(self.width // 2, self.height // 2 + 40)
            )
            self.surface.blit(subtitle_text, subtitle_rect)
