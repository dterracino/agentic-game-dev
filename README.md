# Agentic Game Dev

Agentic Game Dev coordinates designer, architect, implementation, and review agents to build a complete Pygame game. Runs are checkpointed, resumable, dependency-aware, and isolated from the coordinator's Python environment.

The generator supports checkpointed design passes before architecture and checkpointed implementation review-and-improvement rounds after the initial build.

## Core behavior

- Designer and architect proposals are checkpointed independently.
- Adaptive-thinking models use medium effort with enough output headroom for a final answer.
- The final plan declares exact file APIs and every third-party dependency.
- A requirements.txt file is written before dependency approval.
- Each game receives its own .venv.
- The coordinator asks before installing structured dependencies by default.
- Every successful implementation response is written immediately.
- Plans have no fixed file-count cap; responsibilities determine project structure.
- Interrupted runs resume only missing or failed work.
- Static compilation, timed runtime validation, and gameplay use the generated game's interpreter.
- Missing imports pause for dependency approval before code is rewritten.
- Review responses and source replacements are checkpointed.
- Design and implementation rounds use namespaced artifacts and resume at the unfinished task.
- Validation launches main.main() for a bounded smoke interval; full interactive play remains explicit.

Checkpoints live under generated_game/.agentic. The run journal records stages, task status, model, renderer, errors, and artifact locations. It never stores the API key.

## Setup

Python 3.11 or newer is recommended.

~~~powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
Copy-Item .env.example .env
~~~

Set the key in .env:

~~~dotenv
ANTHROPIC_API_KEY=your-anthropic-api-key
ANTHROPIC_MODEL=claude-sonnet-5
~~~

The .env file is ignored by Git. Model precedence is an explicit --model option, then .env, then the process environment, then the built-in default.

## Create a game

Global options go before the command:

~~~powershell
agent-game-dev --output generated_game create "A neon arena game where movement paints temporary walls"
~~~

To iterate on both the design and its implementation:

~~~powershell
agent-game-dev --output generated_game create "A Qix clone" --design-iterations 3 --implementation-iterations 2
~~~

--design-iterations is the total number of design passes before architecture and must be at least 1. --implementation-iterations is the number of review-and-improve rounds after the initial implementation and may be 0. Each implementation round uses gameplay/completeness and technical reviews based on the brief, final contract, complete source, and validation output. It does not claim to visually play the game.

Before packages are installed, the CLI shows each requirement and asks for approval. The resulting layout includes:

~~~text
generated_game/
  .agentic/
    run.json
    artifacts/
  .venv/
  .gitignore
  requirements.txt
  game_plan.json
  main.py
  ...
~~~

Use --dependency-policy allow for an unattended trusted run, or never to prohibit package installation:

~~~powershell
agent-game-dev --dependency-policy allow create "Your game brief"
~~~

Only validated package names and version constraints are accepted. Agents cannot supply shell commands, package URLs, Git repositories, or alternate indexes.

## Resume an interrupted run

~~~powershell
agent-game-dev --output generated_game resume
~~~

Resume uses the saved model, renderer, repair budget, brief, plan, and completed files. It restores completed files from artifacts and calls agents only for missing or failed tasks. If validation uncovers more sequential failures than the saved budget allows, extend it explicitly:

~~~powershell
agent-game-dev --output generated_game resume --add-repair-attempts 2
~~~

If a previous project predates run journals, it cannot be resumed; use create --replace to begin a checkpointed run.

## Run and refine

A completed game can be launched explicitly while teeing stdout and errors to .agentic/playtest.log:

~~~powershell
agent-game-dev --output generated_game run
~~~

You can also add --run to create or resume. The bounded validator may briefly open a game window. Every automated launch appends its status and captured output to .agentic/runtime.log. Runtime and playtest log tails are supplied to repair and implementation-review agents. Generated entry points are required to log uncaught failures to game.log without converting exceptions into successful exits.

Apply playtest feedback with:

~~~powershell
agent-game-dev --output generated_game refine "Hits need stronger feedback"
~~~

## Options

~~~text
--model MODEL
--output DIRECTORY
--renderer pygame|moderngl
--repair-attempts N
--smoke-timeout SECONDS  (game must remain active for this launch interval)
--dependency-policy ask|allow|never
~~~

The CLI prints the effective model, output, renderer, iteration counts, repair budget, and game interpreter before work begins.

## Safety

Package installation is performed by the trusted coordinator only after a structured plan and, by default, explicit approval. Generated code is restricted to planned Python filenames and cannot write outside the game directory through the generation protocol.

These controls reduce risk but cannot prove arbitrary generated code is safe. Review generated files before running games made from untrusted prompts.

## Development

~~~powershell
python -m unittest discover -s tests -v
python -m compileall -q agentic_game_dev tests agent_game_maker.py
~~~
