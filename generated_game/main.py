"""
TERRITORY: Qix Clone - Main Game Loop and Orchestrator

This module implements the core game loop, state machine, and entry point.
It polls input per frame, updates all game systems with delta time, and
delegates rendering to the GameRenderer. No external assets or file I/O.
"""

import sys
import math
from typing import Tuple

import pygame

from config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    FPS,
    PLAYER_SPEED,
    ENEMY_SPEED,
    STALKER_SPEED,
    PATROLLER_SPEED,
    GRID_CELL_SIZE,
    COLLISION_RADIUS,
    BOUNDARY,
)
from game_state import GameState, GameData
from player import Player
from enemy import StalkerEnemy, PatrollerEnemy
from territory import detect_closed_loop, bresenham_line
from render import GameRenderer
from audio import AudioEngine


class QixGame:
    """
    Main game orchestrator: state machine, input polling, system updates,
    and frame rendering delegation.
    """

    def __init__(self) -> None:
        """Initialize the game with pygame, game state, and all subsystems."""
        # Initialize pygame defensively
        if not pygame.get_init():
            pygame.init()

        # Core display and timing
        self.screen: pygame.Surface = pygame.display.set_mode(
            (SCREEN_WIDTH, SCREEN_HEIGHT)
        )
        pygame.display.set_caption("TERRITORY: Qix Clone")
        self.clock: pygame.time.Clock = pygame.time.Clock()
        self.running: bool = True

        # Game state and systems
        self.game_data: GameData = GameData()
        self.player: Player = Player(
            pos=(BOUNDARY["left"] + 50, BOUNDARY["top"]),
            speed=PLAYER_SPEED,
        )
        self.renderer: GameRenderer = GameRenderer(
            surface=self.screen,
            width=SCREEN_WIDTH,
            height=SCREEN_HEIGHT,
        )
        self.audio: AudioEngine = AudioEngine()

        # Drawing state
        self.drawing: bool = False
        self.line_start_pos: Tuple[float, float] = self.player.get_position()
        self.current_line_points: list = []

        # Wave and difficulty tracking
        self.wave: int = 0
        self.enemies_spawned_this_wave: int = 0
        self.time_since_level_start: float = 0.0
        self.spawn_interval: float = 2.0  # Seconds between enemy spawns

    def handle_events(self) -> None:
        """
        Poll events and update input state. ESC quits to menu,
        SPACE is polled per frame (not event-driven) for line drawing.
        """
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    # Return to menu (game over state)
                    self.game_data.state = GameState.MENU
                    self.reset_level()

    def update(self, dt: float) -> None:
        """
        Update all game systems with delta time. Clamp frame spikes.
        Handles state machine, player movement, enemy updates, collision
        detection, territory claiming, and difficulty progression.
        """
        # Clamp delta time to prevent frame spikes (max 50ms)
        dt = min(dt, 0.05)

        if self.game_data.state == GameState.MENU:
            # On menu, wait for SPACE to start
            keys = pygame.key.get_pressed()
            if keys[pygame.K_SPACE]:
                self.game_data.state = GameState.PLAYING
                self.audio.play_enemy_spawn()

        elif self.game_data.state == GameState.PLAYING:
            self._update_playing(dt)

        elif self.game_data.state == GameState.CAUGHT:
            # Wait for SPACE to restart
            keys = pygame.key.get_pressed()
            if keys[pygame.K_SPACE]:
                self.reset_level()
                self.game_data.state = GameState.PLAYING

        elif self.game_data.state == GameState.LEVEL_COMPLETE:
            # Wait for SPACE to continue to next level
            keys = pygame.key.get_pressed()
            if keys[pygame.K_SPACE]:
                self.game_data.level += 1
                self.reset_level()
                self.game_data.state = GameState.PLAYING
                self.audio.play_enemy_spawn()

    def _update_playing(self, dt: float) -> None:
        """Update during PLAYING state: player, enemies, collisions, territory."""
        # Poll input
        keys = pygame.key.get_pressed()
        drawing_input = keys[pygame.K_SPACE]

        # Update player movement (always)
        self.player.update(dt, keys, BOUNDARY)
        current_pos = self.player.get_position()
        self.game_data.player_pos = current_pos

        # Handle line drawing: START
        if drawing_input and not self.drawing:
            self.drawing = True
            self.line_start_pos = current_pos
            self.current_line_points = [current_pos]
            self.player.reset_trail()  # Clear old trail
            self.audio.play_background_loop()

        # Handle line drawing: CONTINUE (record points)
        elif drawing_input and self.drawing:
            # Record player trail while drawing
            if not self.current_line_points or current_pos != self.current_line_points[-1]:
                # Only add if position changed significantly
                dist = math.hypot(
                    current_pos[0] - self.current_line_points[-1][0],
                    current_pos[1] - self.current_line_points[-1][1],
                )
                if dist > 1.0:  # Only add if moved at least 1 pixel
                    self.current_line_points.append(current_pos)

            # Check collision with enemies while drawing
            for enemy in self.game_data.enemies:
                enemy_pos = enemy.get_position()
                dist = math.hypot(
                    current_pos[0] - enemy_pos[0],
                    current_pos[1] - enemy_pos[1],
                )
                if dist < COLLISION_RADIUS:
                    # Caught by enemy
                    self.game_data.state = GameState.CAUGHT
                    self.audio.play_death()
                    return

            # Check collision with enemy trails
            for enemy in self.game_data.enemies:
                enemy_trail = enemy.get_trail()
                for trail_pos in enemy_trail:
                    dist = math.hypot(
                        current_pos[0] - trail_pos[0],
                        current_pos[1] - trail_pos[1],
                    )
                    if dist < COLLISION_RADIUS:
                        # Caught by enemy trail
                        self.game_data.state = GameState.CAUGHT
                        self.audio.play_death()
                        return

        # Handle line drawing: RELEASE
        elif not drawing_input and self.drawing:
            self.drawing = False
            self.audio.stop_all()

            # Finalize line and check for closed loop
            if len(self.current_line_points) > 10:  # Minimum line length
                is_closed, claimed_cells = detect_closed_loop(
                    player_trail=self.current_line_points,
                    qix_trail=[],  # No qix in this variant
                    grid_size=GRID_CELL_SIZE,
                    boundaries=BOUNDARY,
                )

                if is_closed and claimed_cells:
                    # Successful territory claim
                    self.game_data.add_claimed(claimed_cells)
                    self.audio.play_line_complete()
                    self.game_data.score += len(claimed_cells) * 10

                    # Check for level completion
                    total_cells = (
                        (BOUNDARY["right"] - BOUNDARY["left"]) // GRID_CELL_SIZE
                    ) * (
                        (BOUNDARY["bottom"] - BOUNDARY["top"]) // GRID_CELL_SIZE
                    )
                    self.game_data.update_claimed_percentage(total_cells)
                    if self.game_data.claimed_percentage >= 90.0:
                        self.game_data.state = GameState.LEVEL_COMPLETE
                        self.audio.play_line_complete()

            self.current_line_points = []
            self.player.reset_trail()

        # Spawn enemies based on time and wave progression
        self.time_since_level_start += dt
        max_enemies_this_wave = 2 + self.game_data.wave
        target_spawn_time = self.spawn_interval * (self.enemies_spawned_this_wave + 1)

        if (
            self.time_since_level_start >= target_spawn_time
            and len(self.game_data.enemies) < max_enemies_this_wave
        ):
            self._spawn_enemy()
            self.enemies_spawned_this_wave += 1
            self.audio.play_enemy_spawn()

        # Update all enemies
        for enemy in self.game_data.enemies:
            new_pos = enemy.update(
                dt,
                player_pos=current_pos,
                player_trail=self.current_line_points if self.drawing else [],
                claimed_cells=self.game_data.claimed_cells,
                boundaries=BOUNDARY,
            )

        # Check collision between player and enemies (not while drawing)
        if not self.drawing:
            for enemy in self.game_data.enemies:
                enemy_pos = enemy.get_position()
                dist = math.hypot(
                    current_pos[0] - enemy_pos[0],
                    current_pos[1] - enemy_pos[1],
                )
                if dist < COLLISION_RADIUS:
                    self.game_data.state = GameState.CAUGHT
                    self.audio.play_death()
                    return

    def _spawn_enemy(self) -> None:
        """Spawn a new enemy (alternating Stalker and Patroller) in unclaimed territory."""
        # Simple alternating pattern: even spawns are Stalkers, odd are Patrollers
        if self.enemies_spawned_this_wave % 2 == 0:
            speed = STALKER_SPEED
            enemy = StalkerEnemy(pos=self._find_spawn_position(), speed=speed)
        else:
            speed = PATROLLER_SPEED
            enemy = PatrollerEnemy(pos=self._find_spawn_position(), speed=speed)

        self.game_data.enemies.append(enemy)

    def _find_spawn_position(self) -> Tuple[float, float]:
        """Find a spawn position in unclaimed territory near the boundary."""
        # Simple heuristic: try corners and sides
        candidates = [
            (BOUNDARY["left"] + 50, BOUNDARY["top"] + 50),
            (BOUNDARY["right"] - 50, BOUNDARY["top"] + 50),
            (BOUNDARY["left"] + 50, BOUNDARY["bottom"] - 50),
            (BOUNDARY["right"] - 50, BOUNDARY["bottom"] - 50),
        ]

        for pos in candidates:
            cell = (
                int((pos[0] - BOUNDARY["left"]) / GRID_CELL_SIZE),
                int((pos[1] - BOUNDARY["top"]) / GRID_CELL_SIZE),
            )
            if cell not in self.game_data.claimed_cells:
                return pos

        return candidates[0]  # Fallback

    def render(self) -> None:
        """
        Delegate all rendering to GameRenderer. Pass current game state,
        player position, enemies, and active line.
        """
        # Prepare line data for rendering
        line_points = self.current_line_points if self.drawing else []

        # Call renderer
        self.renderer.draw_frame(
            game_data=self.game_data,
            boundaries=BOUNDARY,
        )

        # Overlay active line if drawing
        if self.drawing and line_points:
            self.renderer.draw_trail(
                trail=line_points,
                color=(255, 200, 0),  # Yellow for active line
                is_solid=False,
            )

        # Update display
        pygame.display.flip()

    def run(self) -> None:
        """
        Main game loop: poll events, update with delta time, render,
        and cap frame rate. Runs until quit.
        """
        # Start on menu
        self.game_data.state = GameState.MENU

        while self.running:
            # Delta time from clock (clamped during update)
            dt = self.clock.tick(FPS) / 1000.0

            # Input and state updates
            self.handle_events()
            self.update(dt)

            # Render
            self.render()

        pygame.quit()

    def reset_level(self) -> None:
        """Reset level state: clear enemies, trails, drawing state."""
        self.game_data.enemies = []
        self.game_data.player_trail = []
        self.current_line_points = []
        self.drawing = False
        self.player.reset_trail()
        self.time_since_level_start = 0.0
        self.enemies_spawned_this_wave = 0
        self.game_data.wave = self.game_data.level // 3  # Wave increases every 3 levels


def main() -> None:
    """Entry point: create game instance and run main loop."""
    game = QixGame()
    game.run()


if __name__ == "__main__":
    main()
