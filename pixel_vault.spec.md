# Game Specification: Pixel Vault

## Vision

A crisp, single-screen retro arcade platformer inspired by Miner 2049er. The player claims territory by walking over girders while avoiding hazards.

## Player Interaction

Direct 2D platformer controls: Left, Right, Jump, and Climb (Up/Down on ladders).
Jump trajectory is fixed-arc once airborne.

## World

Single screen containing multiple girder tiers connected by ladders.
Platforms are segmented into discrete claimable floor tiles.
A hazard perimeter kills on fall-out.

## State

Track player position, velocity, grounding/climbing states, score, remaining lives,
stage countdown timer, claimed status per floor tile, and enemy patrol positions.

## Mechanics

Stepping on an unclaimed floor tile marks it claimed and awards points.
Climbing requires horizontal alignment with a ladder.
Jumping off or falling onto a ladder disengages climbing mode.
Touching any patrol hazard or letting the stage timer expire instantly costs one life.

## Interface

Built with Pygame.
Display fixed-screen playfield, current score, high score, remaining lives,
remaining stage time, and percentage of tiles claimed.

## Architecture

Follow separation of concerns:

* `core/`: Pure game state, tile-claim tracking, and collision math with zero dependencies on Pygame.
* `entities/`: Player, enemy patrol routines, and static level geometry models.
* `view/`: Pygame rendering loop, procedural shape/pixel drawing, and audio triggers.
* All game logic updates via fixed delta time (`dt`).

## Completion

All floor tiles on the screen are marked claimed before the countdown timer hits zero.

## Non-goals

No scrolling camera, procedural stage generation, health bars, weapon attacks, or external assets (all visuals drawn via primitives).
