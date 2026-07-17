# Agentic Game Dev

Agentic Game Dev coordinates designer, architect, implementation, and review agents to build a complete Pygame game. Runs are checkpointed, resumable, dependency-aware, and isolated from the coordinator's Python environment.

The current release intentionally uses one planning round while the new recovery lifecycle is proven. Multi-round design iteration is the next layer, not part of this release.

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
- Validation and gameplay use the generated game's interpreter.
- Missing imports pause for dependency approval before code is rewritten.
- Review responses and source replacements are checkpointed.
- Generated code never runs unless --run is explicit.

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

Resume uses the saved model, renderer, repair budget, brief, plan, and completed files. It restores completed files from artifacts and calls agents only for missing or failed tasks.

If a previous project predates run journals, it cannot be resumed; use create --replace to begin a checkpointed run.

## Run and refine

A completed game can be launched explicitly:

~~~powershell
generated_game\.venv\Scripts\python.exe generated_game\main.py
~~~

Or add --run to create or resume.

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
--smoke-timeout SECONDS
--dependency-policy ask|allow|never
~~~

The CLI prints the effective model, output, renderer, repair budget, and game interpreter before work begins.

## Safety

Package installation is performed by the trusted coordinator only after a structured plan and, by default, explicit approval. Generated code is restricted to planned Python filenames and cannot write outside the game directory through the generation protocol.

These controls reduce risk but cannot prove arbitrary generated code is safe. Review generated files before running games made from untrusted prompts.

## Development

~~~powershell
python -m unittest discover -s tests -v
python -m compileall -q agentic_game_dev tests agent_game_maker.py
~~~
