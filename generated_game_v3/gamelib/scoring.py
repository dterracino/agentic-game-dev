"""Pure-Python scoring, lives, and area-claim reward tracking.

No pygame/moderngl imports here: gamelib must stay headless-testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Points awarded per 1.0 percent (i.e. per whole percentage point) of area
# claimed via a normal (careful) trail commit.
POINTS_PER_PERCENT: float = 100.0

# Multiplier applied to the base area reward when the claim was drawn using
# the fast-draw (Shift) risk/reward knob.
FAST_DRAW_BONUS_MULTIPLIER: float = 1.5

# Starting number of lives for a fresh game.
STARTING_LIVES: int = 3


@dataclass
class ScoreBoard:
    """Tracks cumulative score, remaining lives, and total area claimed."""

    score: int = 0
    lives: int = STARTING_LIVES
    total_percent_claimed: float = 0.0
    fast_draw_claims: int = 0
    normal_claims: int = 0
    _level: int = field(default=1)

    def add_area(self, percent: float, fast_draw: bool) -> None:
        """Register a newly claimed area (as a percent of total board area).

        `percent` is the incremental percentage of the board just claimed
        (not the running total). Awards base points scaled by percent, with
        a bonus multiplier when the claim was made using fast-draw.
        """
        if percent <= 0.0:
            return

        base_points = percent * POINTS_PER_PERCENT
        if fast_draw:
            base_points *= FAST_DRAW_BONUS_MULTIPLIER
            self.fast_draw_claims += 1
        else:
            self.normal_claims += 1

        self.score += int(round(base_points))
        self.total_percent_claimed += percent

    def lose_life(self) -> bool:
        """Decrement lives; returns True if the player is still alive."""
        self.lives -= 1
        return self.lives > 0

    def add_life(self) -> None:
        self.lives += 1

    def set_level(self, level: int) -> None:
        self._level = level

    def level(self) -> int:
        return self._level

    def reset(self) -> None:
        self.score = 0
        self.lives = STARTING_LIVES
        self.total_percent_claimed = 0.0
        self.fast_draw_claims = 0
        self.normal_claims = 0
        self._level = 1
