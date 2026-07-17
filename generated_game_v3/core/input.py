"""Pure translation of pygame events + key state into an InputState dataclass.

This module is the single point of pygame.event / pygame.key coupling in the
codebase. Every other module (states, gamelib, render) should consume the
InputState dataclass rather than touching pygame.event or pygame.key
directly.
"""

from __future__ import annotations

from dataclasses import dataclass

import pygame


@dataclass(frozen=True)
class InputState:
    """Snapshot of player intent for a single frame.

    Attributes:
        move_x: Horizontal intent in {-1, 0, 1} (left=-1, right=1).
        move_y: Vertical intent in {-1, 0, 1} (up=-1, down=1).
        fast_draw: True while the fast-draw (Shift) modifier is held.
        pause_pressed: True on the frame pause/unpause was toggled (edge).
        confirm_pressed: True on the frame confirm (Enter) was pressed (edge).
        quit_requested: True if the window/OS requested application quit.
    """

    move_x: int = 0
    move_y: int = 0
    fast_draw: bool = False
    pause_pressed: bool = False
    confirm_pressed: bool = False
    quit_requested: bool = False

    # Backwards/forwards-compatible aliases used by some states.
    @property
    def confirm(self) -> bool:
        return self.confirm_pressed

    @property
    def quit(self) -> bool:
        return self.quit_requested

    @property
    def pause_toggled(self) -> bool:
        return self.pause_pressed


def poll(events: list) -> InputState:
    """Translate a list of pygame events (plus current key state) into an
    InputState. This is a pure function of the given events and the current
    pygame key state; it does not read wall-clock time.
    """
    quit_requested = False
    pause_pressed = False
    confirm_pressed = False

    for event in events:
        if event.type == pygame.QUIT:
            quit_requested = True
        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_p):
                pause_pressed = True
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                confirm_pressed = True

    try:
        keys = pygame.key.get_pressed()
    except pygame.error:
        keys = None

    move_x = 0
    move_y = 0
    fast_draw = False

    if keys is not None:
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            move_x -= 1
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            move_x += 1
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            move_y -= 1
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            move_y += 1
        if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
            fast_draw = True

    # Clamp to strict -1/0/1 intent (prefer horizontal on diagonal conflict
    # resolution is left to consumers; here we just pass raw axis intent).
    move_x = max(-1, min(1, move_x))
    move_y = max(-1, min(1, move_y))

    return InputState(
        move_x=move_x,
        move_y=move_y,
        fast_draw=fast_draw,
        pause_pressed=pause_pressed,
        confirm_pressed=confirm_pressed,
        quit_requested=quit_requested,
    )
