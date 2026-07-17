"""
render/gl_context.py

Creates the moderngl.Context bound to the pygame OPENGL surface.

This module is intentionally minimal: it is responsible only for setting up
the pygame display in OpenGL mode and wrapping it in a moderngl.Context.
It must not import gamelib, states, or core modules to respect the strict
layering rules of the project.
"""

from __future__ import annotations

from typing import Tuple

import pygame
import moderngl


def _ensure_pygame_video_initialized() -> None:
    """Defensively initialize pygame's video subsystem if needed."""
    if not pygame.get_init():
        pygame.init()
    if not pygame.display.get_init():
        pygame.display.init()


def create_context(surface_size: Tuple[int, int]) -> moderngl.Context:
    """Create (or attach to) a pygame OPENGL display surface and return
    a moderngl.Context bound to it.

    Parameters
    ----------
    surface_size:
        (width, height) tuple describing the desired window size.

    Returns
    -------
    moderngl.Context
        A moderngl context created from the current OpenGL context that
        pygame has established.
    """
    _ensure_pygame_video_initialized()

    width, height = int(surface_size[0]), int(surface_size[1])

    # Request a reasonably modern, compatible GL context. moderngl works
    # fine with the default profile pygame gives us as long as double
    # buffering and a depth buffer are requested.
    pygame.display.gl_set_attribute(pygame.GL_DOUBLEBUFFER, 1)
    pygame.display.gl_set_attribute(pygame.GL_DEPTH_SIZE, 24)

    flags = pygame.OPENGL | pygame.DOUBLEBUF
    pygame.display.set_mode((width, height), flags)

    # Create the moderngl context from the currently bound GL context that
    # pygame just created via set_mode.
    ctx = moderngl.create_context()

    # Sensible defaults for a 2D game rendered with alpha-blended glows.
    ctx.enable(moderngl.BLEND)
    ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
    ctx.viewport = (0, 0, width, height)

    return ctx
