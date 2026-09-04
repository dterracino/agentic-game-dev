# Game Specification: Pixel Vault

## Vision

Pixel Vault is a crisp, single-screen retro arcade platformer inspired by territory-claiming
platform games such as Miner 2049er. The player races across a compact industrial vault, energizing
every section of its floor network while avoiding predictable patrol hazards.

Target session length: 36 minutes per attempt.
Intended player experience: immediately readable movement, route-planning under pressure, and a
satisfying transformation of a dark playfield into a fully energized machine.

## Player Interaction

The player directly controls a small character in a fixed side-view playfield.

Required actions:

- Move left or right with the arrow keys or A/D.
- Jump with Space.
- Climb aligned ladders with Up/Down or W/S.
- Pause or resume with Escape.
- Restart after game over or stage completion with Enter.

Jumping uses a consistent committed arc once airborne; horizontal direction cannot be reversed
until the player lands. Climbing begins only when the player is horizontally aligned with a ladder.
Jumping or falling away from a ladder exits climbing mode.

## World and Content

The game contains one authored screen with five visually distinct girder tiers. Ladders connect the
tiers into multiple viable routes, and each walkable girder is divided into clearly readable
claimable floor segments.

The screen must include:

- A safe starting platform and respawn point.
- At least four ladders, including one route that requires changing tiers more than once.
- Two patrol hazards with distinct silhouettes and readable, repeating movement patterns.
- At least one optional longer route that rewards planning rather than reflex alone.
- A lethal lower boundary for falling out of the playfield.

Every claimable segment must be reachable. No patrol route may permanently block the only path to a
required segment.

## Rules and Invariants

- Stepping onto or landing on an unclaimed floor segment energizes it permanently for the current
  game and awards points exactly once.
- Already energized segments remain safe to cross but award no additional claim points.
- Patrol contact and falling below the playfield cost one life.
- Patrol motion must be predictable and must reverse or loop without leaving its authored route.
- The player may stand only on valid floor geometry and may climb only within a ladder's bounds.
- Collision resolution must not trap the player inside a platform, ladder, or patrol hazard.
- All claimable floor segments must remain obtainable after any non-terminal death.

## State and Persistence

Track:

- Player position, velocity, facing direction, grounded state, climbing state, and current
  animation state.
- Energized status for every claimable floor segment.
- Patrol positions, directions, and route progress.
- Score, saved high score, remaining lives, per-life countdown, pause state, stage-complete state,
  and game-over state.

The player starts with three lives and 120 seconds. Losing a life resets the player, patrols, and
countdown to their authored starting states; energized floor segments and score remain. Reaching
zero lives ends the game. The high score persists between application runs; all other state resets
when a new game begins.

## Progression, Success, and Failure

The lower tiers provide space to learn movement and claiming. Higher tiers require tighter timing,
more ladder transitions, and route choices around overlapping patrol patterns. The final unclaimed
segments should demand deliberate traversal without requiring blind jumps.

Success condition: every claimable floor segment is energized before the player runs out of lives.
Remaining time is converted into a completion bonus.

Failure condition: patrol contact, falling out of bounds, or allowing the countdown to expire costs
one life. Reaching zero lives produces game over.

Recovery behavior: after a short, clearly signaled death beat, restore the player and patrols to
safe starting positions and reset the countdown. After game over or completion, Enter starts a
clean new game.

## Presentation and Feedback

Visual style: sharp low-resolution pixel art with a dark steel vault, saturated cyan, magenta, and
amber energy colors, high-contrast silhouettes, and a restrained arcade-display character. Pixels
must remain crisp when the window is resized.

Desired visual effects and their player-facing purpose:

- A subtle scanline texture, gentle screen-edge vignette, and extremely light color fringing give
  the playfield an old high-quality arcade-monitor character without making text or platforms
  blurry.
- Claiming a floor segment sends a fast band of light across that segment, followed by a soft neon
  glow that remains visible so claimed and unclaimed routes are unmistakable.
- Consecutive claims within a short interval briefly intensify the playfield glow and leave a faint
  motion trail behind the player, reinforcing momentum without obscuring collision boundaries.
- Patrol hazards carry a low pulsing aura whose rhythm and color distinguish them from safe floor
  energy.
- During the final ten seconds, the screen edges and timer pulse in a restrained warning rhythm;
  the playfield itself must remain stable and readable.
- On damage, the image briefly compresses toward the impact point with a small color-channel split,
  then cleanly settles before respawn. The effect must never conceal the cause of death.
- Stage completion triggers an energy cascade through all claimed floor segments, a brief bloom of
  the vault lights, and a celebratory palette lift before showing the completion result.

Audio and interaction feedback:

- Movement, jumping, landing, ladder entry, claiming, damage, countdown warning, completion, and
  menu confirmation each have distinct concise feedback.
- Claim sounds rise slightly in pitch during a quick sequence but remain comfortable and
  non-piercing.

Readability requirements:

- The player, patrols, ladders, claimed segments, unclaimed segments, and lethal boundary must be
  distinguishable at a glance.
- Score, high score, lives, countdown, and percentage claimed remain sharp and legible during every
  effect.
- Strong effects are brief and cannot alter collision timing or hide gameplay-critical geometry.

## Completion and Acceptance

The finished game must demonstrate:

- A complete route that can energize every floor segment and trigger stage completion.
- Patrol contact, falling, and timeout each producing the same coherent life-loss and recovery
  sequence.
- Energized segments and score surviving a non-terminal death while patrols, player position, and
  countdown reset.
- A saved high score surviving application restart.
- Frame-rate-independent movement, patrol behavior, countdown, and short-lived presentation
  effects.
- Observable evidence for the claim sweep and glow, patrol aura, low-time warning, damage response,
  and completion cascade.
- A stable, readable image at the default window size and at least one larger resized window.

## Non-goals

- No scrolling camera or additional stages.
- No procedural level generation.
- No combat, weapons, health bars, power-ups, or boss encounters.
- No online features, leaderboards, accounts, or multiplayer.
- No requirement to reproduce the rules, level layout, characters, or assets of any existing game.

## Designer Latitude

The designer may choose the exact vault layout, platform dimensions, patrol routes, scoring values,
animation timing, palette values, sound character, and visual-effect intensity. These choices must
preserve reachability, predictable hazards, crisp readability, and the 36 minute target session.
