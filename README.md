# Agentic Game Dev

Agentic Game Dev builds checkpointed Pygame games with a coordinated design, QA, implementation, and review workflow. Generated games are resumable, dependency-aware, and isolated in their own virtual environments.

## Workflow

A new run proceeds through these durable stages:

1. A game designer produces one or more checkpointed design passes.
2. An architect defines dependencies, module responsibilities, and exact cross-file APIs.
3. An independent QA author converts the design into observable gameplay acceptance criteria.
4. The complete QA contract is printed and saved as QA_ACCEPTANCE.md.
5. You approve the contract before any implementation tokens or dependency installs are spent.
6. One lead game developer implements files sequentially in dependency order. Every checkpoint includes the approved QA contract and the project produced so far.
7. Static compilation, strict Pyright checking, renderer checks, and timed runtime validation run against the generated game's virtual environment.
8. Optional implementation iterations use independent gameplay and technical reviews, then route ordered changes back through the lead developer. Each round reports its plan, updated files, and validation results.

This keeps SoC in the generated project without assigning tightly coupled gameplay files to isolated parallel implementers. Independent review calls may still run concurrently.

The game description is also the game-type signal. There is no fixed genre registry: the designer
infers the appropriate interaction model and pacing, and the architect selects supporting libraries
through the reviewed dependency plan. For example, a graphical parser adventure can remain a
Pygame game while declaring `pygame-gui` for its text interface. Turn-based designs are not forced
to adopt real-time movement, collision, scoring, or arcade-style progression.

Every model request displays an ASCII-safe spinner with elapsed time in an interactive terminal. Redirected output receives a plain waiting message instead.

Generated Python files are parsed immediately, while planned GLSL files are checked as safe,
non-empty source. An invalid response is saved as a diagnostic attempt and returned to the lead for
up to three file-local attempts without consuming the later project repair budget.

## Setup

Python 3.11 or newer is recommended.

~~~powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
Copy-Item .env.example .env
~~~

The commands below use the virtual environment's Python executable directly, so PowerShell
activation is not required. The editable install also creates
`.\.venv\Scripts\agent-game-dev.exe`; after activating the environment, the shorter
`agent-game-dev` command works as well. `python agent_game_maker.py` remains available as a
compatibility entry point when the active Python already has the project dependencies installed.

The .env file is ignored by Git.

### Anthropic

~~~dotenv
AGENT_PROVIDER=anthropic
ANTHROPIC_API_KEY=your-anthropic-api-key
ANTHROPIC_MODEL=claude-sonnet-5
~~~

### OpenAI

The official OpenAI Python SDK is included. OpenAI requests use the Responses API; structured
agent results use strict JSON Schema output. Responses are sent with storage disabled.

~~~dotenv
AGENT_PROVIDER=openai
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=your-openai-model
~~~

The model is deliberately not hard-coded because availability depends on your OpenAI API project.
Set `OPENAI_MODEL` or pass `--model` explicitly:

~~~powershell
.\.venv\Scripts\python.exe -m agentic_game_dev --provider openai --model your-openai-model --output generated_game create "A Qix clone"
~~~

### Ollama

The official ollama Python package is included. The server can run on the same computer or another computer on your local network.

~~~dotenv
AGENT_PROVIDER=ollama
OLLAMA_HOST=http://192.168.1.50:11434
OLLAMA_MODEL=qwen3-coder:30b
~~~

No Anthropic key is required for an Ollama run. The selected model must already be available to that Ollama server.

Command-line options override .env:

~~~powershell
.\.venv\Scripts\python.exe -m agentic_game_dev --provider ollama --model qwen3-coder:30b --ollama-host http://192.168.1.50:11434 --output generated_game create "A Qix clone"
~~~

## Create a game

Global options go before the command:

~~~powershell
.\.venv\Scripts\python.exe -m agentic_game_dev --output generated_game create "A neon arena game where movement paints walls"
~~~

A brief can describe a different style without selecting a separate game type:

~~~powershell
.\.venv\Scripts\python.exe -m agentic_game_dev --output generated_adventure create "An old Infocom-style parser adventure presented as a polished graphical Pygame application"
~~~

The generated dependency proposal is shown for approval before installation, including an inferred
UI toolkit such as `pygame-gui` when the architect determines that it materially improves the game.

### Start from a game specification

When you already know how the game should work, provide a UTF-8 Markdown or text specification:

A starter template is available in [game_spec.md.example](game_spec.md.example).

~~~powershell
.\.venv\Scripts\python.exe -m agentic_game_dev --output generated_adventure create --spec game_spec.md "Build this parser adventure"
~~~

The positional brief remains useful as a short statement of intent. If it is omitted, the tool uses
the specification filename to create a neutral brief instead of prompting for another description:

~~~powershell
.\.venv\Scripts\python.exe -m agentic_game_dev --output generated_adventure create --spec game_spec.md
~~~

With a specification, the designer reviews it for contradictions and feasibility, preserves its
explicit decisions, and fills only genuine gaps. Without one, the designer continues to develop the
game from the brief. The original specification is snapshotted under
`.agentic/artifacts/input/game_spec.md` and reused by architecture, QA, implementation,
refinement, and resume even if the source file later changes.

After design and architecture, the CLI prints the numbered QA acceptance contract and asks:

~~~text
Approve this gameplay contract and begin implementation? [y/N]:
~~~

Answering no stops before implementation. All work completed so far remains checkpointed, and resume will display the contract for approval again.

For a trusted unattended run, use --qa-policy approve. The contract is still generated and saved.

Design and implementation iteration counts remain configurable:

~~~powershell
.\.venv\Scripts\python.exe -m agentic_game_dev --output generated_game create "A Qix clone" --design-iterations 3 --implementation-iterations 2
~~~

Before generated-game packages are installed, the CLI shows every requirement and asks for approval. Use --dependency-policy allow for a trusted unattended run or never to prohibit installs.

## Checkpoints and resume

Checkpoints live under generated_game/.agentic. The journal records the provider, provider host, model, brief, renderer, QA approval, stages, task status, errors, and artifact locations. It never stores an API key.

~~~powershell
.\.venv\Scripts\python.exe -m agentic_game_dev --output generated_game resume
~~~

Resume uses the saved provider and model so a partially generated project cannot silently switch backends. It restores completed design, QA, implementation, refinement, and repair artifacts and calls a model only for unfinished work.

To intentionally move unfinished work to another provider, use the explicit resume switch. This
updates the run journal while preserving its specification and completed checkpoints:

~~~powershell
.\.venv\Scripts\python.exe -m agentic_game_dev --output generated_game resume --switch-provider openai --switch-model your-openai-model
~~~

If validation needs a larger repair budget:

~~~powershell
.\.venv\Scripts\python.exe -m agentic_game_dev --output generated_game resume --add-repair-attempts 2
~~~

## Generated environment and dependencies

Each game receives its own virtual environment and requirements.txt. The coordinator installs only validated structured dependencies after approval. Missing imports discovered during validation pause for dependency approval rather than encouraging an agent to rewrite working code around the package.

The coordinator also writes `pyrightconfig.json` with strict checking enabled. Generated Python must pass Pyright with zero errors. `# type: ignore`, `# pyright: ignore`, weakened per-file modes, and disabled diagnostic rules are rejected; agents receive the actual diagnostics and must correct the annotations, narrowing, protocols, stubs, or APIs instead. Pylance reads the same project configuration when the generated folder is opened in VS Code.

When validation fails across multiple files, repairs are grouped into a batch of durable per-file checkpoints. Each model call returns one complete file, after which validation is rerun for the batch. The CLI reports the affected and changed filenames. If a batch produces no source changes, the run stops instead of spending the remaining repair attempts on identical requests.

Typical output:

~~~text
generated_game/
  .agentic/
    run.json
    artifacts/
    runtime.log
    playtest.log
  .venv/
  QA_ACCEPTANCE.md
  pyrightconfig.json
  requirements.txt
  game_plan.json
  shaders/
    effect_name.vert
    effect_name.frag
  main.py
  ...
~~~

## Run and refine

Run a completed game while teeing output to .agentic/playtest.log:

~~~powershell
.\.venv\Scripts\python.exe -m agentic_game_dev --output generated_game run
~~~

Every automated validation appends captured output to .agentic/runtime.log. Runtime, playtest, and game-log tails are supplied to repair and implementation-review agents.

Apply playtest feedback with:

~~~powershell
.\.venv\Scripts\python.exe -m agentic_game_dev --output generated_game refine "Hits need stronger feedback"
~~~

## Important options

~~~text
--provider anthropic|openai|ollama
--model MODEL
--ollama-host URL
--qa-policy ask|approve
--output DIRECTORY
--renderer pygame|moderngl
--repair-attempts N
--smoke-timeout SECONDS
--dependency-policy ask|allow|never
~~~

The CLI prints the effective provider, model, provider host when applicable, output, renderer, iteration counts, repair budget, and game interpreter before work begins.

### Renderer decisions and engineering policy

Game specifications should describe player-facing visuals rather than prescribe implementation
technology. For example, request soft bloom, heat distortion, phosphor persistence, or a brief
damage color split without mentioning GLSL. The selected renderer profile tells the architect how
to implement those effects.

Architecture checkpoints are validated before they can be reused. They must contain concrete
module responsibilities, rendering pipeline order, visual and audio asset manifests, cross-file
APIs, lifecycle/cleanup, and validation strategy. ModernGL architectures must additionally include
a shader-source manifest naming separate vertex and fragment stages. Each manifest identifies the
technique, exact owning source file, runtime integration point, and observable validation; merely
listing an `assets/` or `shaders/` directory is insufficient.

With `--renderer moderngl`, the generated build contract must map each requested visual effect to
its concrete GPU or simpler rendering technique, exact owning source file, shader source files,
and observable validation method. Every named owner and shader must also be a planned file.
The generated project must actually import ModernGL, create a context, and compile a vertex/fragment
shader program; declaring the dependency alone fails validation. Shader sources can be generated as
standalone files such as `shaders/bloom.vert`, `shaders/bloom.frag`, or a shared
`shaders/effects.glsl`.
If an architect names a safe project-local shader or asset owner but omits it from the files list,
the coordinator promotes that reference to a planned file automatically. Other locally invalid
build contracts are checkpointed with their validation error and retried with corrective context.

Every plan also contains a visual-asset manifest for the promised player, enemy, world, item,
background, UI, and feedback visuals. Because the language-model generation stage produces source
rather than binary image files, pixel sprites and atlases are normally generated procedurally in a
dedicated source module. That module may construct Pygame surfaces directly or deterministically
write project-local generated sprite sheets. The audio-asset manifest works the same way: simple
effects and ambience are synthesized as reusable mixer-ready samples or project-local WAV files
with Python waveforms and envelopes when recorded files are unavailable. Generic placeholder
rectangles and silent deferred audio do not satisfy those contracts.

Generated Python checkpoints are rejected locally when they contain provisional TODO/placeholder
comments or stub classes/functions whose entire implementation is `pass`, `...`, or
`raise NotImplementedError`. On resume, an older saved plan that does not meet the current
renderer/asset contract is re-planned and its QA contract is regenerated.

Project-wide engineering rules are maintained separately from game specifications. The built-in
policy applies separation of concerns, DRY, explicit ownership, acyclic typed APIs, testable domain
logic, and renderer-resource lifecycle rules to architecture, QA, implementation, and review.

## Validation boundary

The built-in runtime probe proves that the program imports, starts, and remains alive for the configured interval. The QA contract defines the additional mechanical, scripted-playtest, telemetry, and visual evidence needed to prove that it is the promised game. Runtime liveness alone is not considered gameplay correctness.

## Safety

Generated source is restricted to validated project-local Python and GLSL paths. Package
installation is performed by the trusted coordinator only after a structured plan and approval.
Generated agents cannot supply package URLs, shell commands, Git repositories, or alternate
indexes.

These controls reduce risk but cannot prove arbitrary generated code is safe. Review generated files before running games made from untrusted prompts.

## Development

Agent role definitions live under `agentic_game_dev/agents/`. Each role derives from the shared
`AgentRole` contract, keeping role instructions and role-specific prompt behavior separate from
the orchestration and checkpointing machinery.

~~~powershell
python -m unittest discover -s tests -v
python -m compileall -q agentic_game_dev tests agent_game_maker.py
~~~
