"""Single entry point for the Qix Clone game.

Initializes pygame, builds the screen/clock/renderer/input handler,
constructs the GameContext, registers all States with the StateManager,
and runs the App main loop.
"""

from __future__ import annotations

import sys
from typing import Optional

import pygame

from game.core.constants import SCREEN_W, SCREEN_H, FPS_CAP, STARTING_LIVES
from game.core.types import GameState
from game.core.context import GameContext
from game.engine.input import InputHandler
from game.engine.renderer import Renderer
from game.engine.app import App
from game.states.state_manager import StateManager
from game.states.game_states import (
    MenuState,
    PlayingState,
    PausedState,
    GameOverState,
    VictoryState,
)


class AssetManager:
    """Minimal asset manager owning fonts (and any future images/sounds).

    Kept in main.py because no dedicated file was declared for it in the
    plan; it only exposes what Renderer/States need (fonts) and performs
    no filesystem writes or network access.
    """

    def __init__(self) -> None:
        self.fonts: dict[int, pygame.font.Font] = {}
        self._default_sizes = (18, 24, 36, 48, 64)
        for size in self._default_sizes:
            self.fonts[size] = self._make_font(size)

    @staticmethod
    def _make_font(size: int) -> pygame.font.Font:
        try:
            return pygame.font.SysFont("consolas,couriernew,monospace", size)
        except Exception:
            return pygame.font.Font(None, size)

    def get_font(self, size: int) -> pygame.font.Font:
        font = self.fonts.get(size)
        if font is None:
            font = self._make_font(size)
            self.fonts[size] = font
        return font


def _build_state_manager(context: GameContext) -> StateManager:
    manager = StateManager()

    menu_state = MenuState(manager, context)
    playing_state = PlayingState(manager, context)
    paused_state = PausedState(manager, context)
    game_over_state = GameOverState(manager, context)
    victory_state = VictoryState(manager, context)

    manager.register(GameState.MENU, menu_state)
    manager.register(GameState.PLAYING, playing_state)
    manager.register(GameState.PAUSED, paused_state)
    manager.register(GameState.GAME_OVER, game_over_state)
    manager.register(GameState.VICTORY, victory_state)

    manager.switch_to(GameState.MENU)
    return manager


def _init_pygame() -> tuple[pygame.Surface, pygame.time.Clock]:
    if not pygame.get_init():
        pygame.init()
    if not pygame.font.get_init():
        pygame.font.init()
    if not pygame.display.get_init():
        pygame.display.init()

    screen: Optional[pygame.Surface] = None
    try:
        screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    except pygame.error:
        screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.NOFRAME)

    pygame.display.set_caption("Qix Clone")
    clock = pygame.time.Clock()
    return screen, clock


def main() -> None:
    screen, clock = _init_pygame()

    renderer = Renderer(screen)
    assets = AssetManager()
    input_handler = InputHandler()

    context = GameContext(
        screen=screen,
        renderer=renderer,
        assets=assets,
        dt=0.0,
        score=0,
        lives=STARTING_LIVES,
        level=1,
        pressure=0.0,
    )

    manager = _build_state_manager(context)

    app = App(
        screen=screen,
        clock=clock,
        input_handler=input_handler,
        state_manager=manager,
        fps_cap=FPS_CAP,
    )

    try:
        app.run()
    finally:
        pygame.quit()
        sys.exit(0)


if __name__ == "__main__":
    main()
