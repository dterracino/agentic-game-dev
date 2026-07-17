"""Static constants for the game: window size, FPS, colors, speeds, area targets.

This module contains only plain-Python primitives (tuples, ints, floats,
lists) so it can be freely imported by any layer (core, states, gamelib,
render) without introducing coupling or circular imports.
"""

from typing import Final, List, Tuple

# --- Window / display ---------------------------------------------------

WINDOW_SIZE: Final[Tuple[int, int]] = (1024, 768)
FPS: Final[int] = 60

# --- Colors (RGBA floats 0..1, suitable for GPU upload) ------------------

COLOR_BACKGROUND: Final[Tuple[float, float, float, float]] = (0.05, 0.05, 0.08, 1.0)
COLOR_BORDER: Final[Tuple[float, float, float, float]] = (0.2, 0.9, 1.0, 1.0)
COLOR_CLAIMED_AREA: Final[Tuple[float, float, float, float]] = (0.1, 0.3, 0.6, 0.65)
COLOR_TRAIL_SAFE: Final[Tuple[float, float, float, float]] = (1.0, 0.9, 0.2, 1.0)
COLOR_TRAIL_FAST: Final[Tuple[float, float, float, float]] = (1.0, 0.4, 0.1, 1.0)
COLOR_PLAYER: Final[Tuple[float, float, float, float]] = (1.0, 1.0, 1.0, 1.0)
COLOR_QIX: Final[Tuple[float, float, float, float]] = (0.9, 0.1, 0.8, 1.0)
COLOR_SPARX: Final[Tuple[float, float, float, float]] = (1.0, 0.2, 0.2, 1.0)
COLOR_UI_TEXT: Final[Tuple[float, float, float, float]] = (1.0, 1.0, 1.0, 1.0)

# --- Gameplay speeds (units per second, in board/world coordinate space) -

BASE_PLAYER_SPEED: Final[float] = 180.0
FAST_DRAW_SPEED_MULTIPLIER: Final[float] = 1.5
FAST_DRAW_NO_TURN_WINDOW: Final[float] = 0.18  # seconds of commitment when dashing

BASE_QIX_SPEED: Final[float] = 140.0
BASE_QIX_TURN_RATE: Final[float] = 3.2  # radians/sec max turn rate at level 1

BASE_SPARX_SPEED: Final[float] = 110.0
BASE_SPARX_COUNT: Final[int] = 1

# Per-level escalation factors, applied multiplicatively per level index.
QIX_SPEED_LEVEL_SCALE: Final[float] = 0.12
QIX_TURN_LEVEL_SCALE: Final[float] = 0.08
SPARX_SPEED_LEVEL_SCALE: Final[float] = 0.10
SPARX_COUNT_LEVEL_STEP: Final[int] = 1  # additional sparx every N levels
SPARX_COUNT_LEVEL_STEP_SIZE: Final[int] = 2

# Soft timer pressure: after this many seconds on a level, escalate speed.
LEVEL_SOFT_TIMER_SECONDS: Final[float] = 20.0
LEVEL_SOFT_TIMER_SPEED_BUMP: Final[float] = 0.05

# --- Scoring --------------------------------------------------------------

SCORE_PER_PERCENT_AREA: Final[float] = 100.0
FAST_DRAW_SCORE_BONUS_MULTIPLIER: Final[float] = 1.5
STARTING_LIVES: Final[int] = 3

# --- Area percent targets per level (index 0 == level 1) ------------------

AREA_TARGETS: Final[List[float]] = [
    75.0,
    78.0,
    80.0,
    82.0,
    85.0,
    85.0,
    85.0,
    85.0,
    85.0,
    85.0,
]

# --- Frame timing -----------------------------------------------------

MAX_DT: Final[float] = 0.05
