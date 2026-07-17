"""
core/clock.py

Thin wrapper documenting the dt (delta time) convention used throughout the
codebase.

Convention
----------
Every `update(dt)` call across the entire project (states, gamelib entities,
etc.) receives `dt` as a **float number of seconds** elapsed since the last
frame. This value should always originate from a single `pygame.time.Clock`
instance ticked once per frame in `main.py`:

    clock = pygame.time.Clock()
    ...
    while running:
        raw_dt_ms = clock.tick(FPS)
        dt = clamp_dt(raw_dt_ms / 1000.0)

No entity, state, or gamelib module should read wall-clock time directly
(e.g. via `time.time()` or `pygame.time.get_ticks()`); all timing-dependent
behavior must be driven exclusively by the `dt` value passed into `update`.

This module provides a single helper, `clamp_dt`, which clamps a raw delta
time to a maximum value. This prevents "spikes" - e.g. when the window is
dragged, breakpointed in a debugger, or the OS stalls the process - from
causing a single frame to simulate an enormous, destabilizing amount of game
time (which could, for example, let the Qix teleport through a wall or the
player's trail skip over enemies).
"""

from __future__ import annotations


def clamp_dt(raw_dt: float, max_dt: float = 0.05) -> float:
    """Clamp a raw delta-time value (in seconds) to a sane maximum.

    Args:
        raw_dt: The raw elapsed time in seconds since the previous frame.
            Expected to be non-negative under normal operation, but this
            function defensively floors it at 0.0 to guard against
            malformed input (e.g. clock jitter reporting a negative value).
        max_dt: The maximum allowed delta time in seconds. Defaults to
            0.05s (20 FPS equivalent), which is a reasonable floor to
            prevent large simulation steps on frame-time spikes.

    Returns:
        A float dt in seconds, guaranteed to be within [0.0, max_dt].
    """
    if raw_dt < 0.0:
        return 0.0
    if raw_dt > max_dt:
        return max_dt
    return raw_dt
