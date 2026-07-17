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


def _build_states() -> dict:
    return {
        StateID.MENU: MenuState(),
        StateID.PLAYING: PlayingState(),
        StateID.PAUSED: PausedState(),
        StateID.GAME_OVER: GameOverState(),
    }


def main() -> None:
    pygame.init()
    try:
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
        pygame.display.gl_set_attribute(
            pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE
        )

        surface = pygame.display.set_mode(
            WINDOW_SIZE, pygame.OPENGL | pygame.DOUBLEBUF
        )
        pygame.display.set_caption("Qix Clone: Ink & Exposure")

        clock = pygame.time.Clock()

        gl_ctx = create_context(WINDOW_SIZE)
        renderer = Renderer(gl_ctx, WINDOW_SIZE)

        context = GameContext(
            gl_ctx=gl_ctx,
            renderer=renderer,
            window_size=WINDOW_SIZE,
        )

        states = _build_states()
        machine = StateMachine(states, StateID.MENU, context)
        machine.current.on_enter(context)

        running = True
        while running:
            raw_dt = clock.tick(FPS) / 1000.0
            dt = clamp_dt(raw_dt)

            events = pygame.event.get()
            for event in events:
                if event.type == pygame.QUIT:
                    running = False

            if not running:
                break

            input_state = poll(events)
            context.input_state = input_state

            machine.handle_events(events)
            machine.update(dt)
            machine.render()

            pygame.display.flip()

            if machine.should_quit():
                running = False

    finally:
        pygame.quit()
        sys.exit(0)


if __name__ == "__main__":
    main()
