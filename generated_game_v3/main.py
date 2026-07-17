"""Single entry point for Qix Clone: Ink & Exposure.

Initializes pygame with an OpenGL-capable window, creates the moderngl
context and renderer, builds the GameContext, and runs the fixed-timestep
main loop that drives the StateMachine.
"""

from __future__ import annotations

import sys

import pygame

from settings import WINDOW_SIZE, FPS
from core.clock import clamp_dt
from core.game_context import GameContext
from core.state_machine import StateMachine
from core.input import poll
from states.base import StateID
from states.menu_state import MenuState
from states.playing_state import PlayingState
from states.paused_state import PausedState
from states.game_over_state import GameOverState
from render.gl_context import create_context
from render.renderer import Renderer


def main() -> None:
    pygame.init()
    try:
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
        pygame.display.gl_set_attribute(
            pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE
        )

        gl_ctx = create_context(WINDOW_SIZE)
        pygame.display.set_caption("Qix Clone: Ink & Exposure")

        renderer = Renderer(gl_ctx, WINDOW_SIZE)

        context = GameContext(
            renderer=renderer,
            window_size=WINDOW_SIZE,
        )

        clock = pygame.time.Clock()

        state_factories = {
            StateID.MENU: lambda ctx: MenuState(ctx),
            StateID.PLAYING: lambda ctx: PlayingState(ctx),
            StateID.PAUSED: lambda ctx: PausedState(ctx, None),
            StateID.GAME_OVER: lambda ctx: GameOverState(ctx),
        }

        machine = StateMachine(context, state_factories, StateID.MENU)

        running = True
        while running:
            raw_dt = clock.tick(FPS) / 1000.0
            dt = clamp_dt(raw_dt)

            events = pygame.event.get()

            input_state = poll(events)
            context.input_state = input_state

            if input_state.quit_requested:
                running = False
                break

            machine.handle_events(events)
            machine.update(dt)
            machine.render()

            pygame.display.flip()

            if not context.running:
                running = False

    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
