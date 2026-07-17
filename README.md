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
7. Static compilation and timed runtime validation run in the generated game's virtual environment.
8. Optional implementation iterations use independent gameplay and technical reviews, then route ordered changes back through the lead developer.

This keeps SoC in the generated project without assigning tightly coupled gameplay files to isolated parallel implementers. Independent review calls may still run concurrently.

Every model request displays an ASCII-safe spinner with elapsed time in an interactive terminal. Redirected output receives a plain waiting message instead.

Generated Python files are parsed immediately. A syntax-invalid response is saved as a diagnostic attempt and returned to the lead for up to three file-local attempts without consuming the later project repair budget.

## Setup

Python 3.11 or newer is recommended.

~~~powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
Copy-Item .env.example .env
~~~

The .env file is ignored by Git.

### Anthropic

~~~dotenv
AGENT_PROVIDER=anthropic
ANTHROPIC_API_KEY=your-anthropic-api-key
ANTHROPIC_MODEL=claude-sonnet-5
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
agent-game-dev --provider ollama --model qwen3-coder:30b --ollama-host http://192.168.1.50:11434 --output generated_game create "A Qix clone"
~~~

## Create a game

Global options go before the command:

~~~powershell
agent-game-dev --output generated_game create "A neon arena game where movement paints walls"
~~~

After design and architecture, the CLI prints the numbered QA acceptance contract and asks:

~~~text
Approve this gameplay contract and begin implementation? [y/N]:
~~~

Answering no stops before implementation. All work completed so far remains checkpointed, and resume will display the contract for approval again.

For a trusted unattended run, use --qa-policy approve. The contract is still generated and saved.

Design and implementation iteration counts remain configurable:

~~~powershell
agent-game-dev --output generated_game create "A Qix clone" --design-iterations 3 --implementation-iterations 2
~~~

Before generated-game packages are installed, the CLI shows every requirement and asks for approval. Use --dependency-policy allow for a trusted unattended run or never to prohibit installs.

## Checkpoints and resume

Checkpoints live under generated_game/.agentic. The journal records the provider, provider host, model, brief, renderer, QA approval, stages, task status, errors, and artifact locations. It never stores an API key.

~~~powershell
agent-game-dev --output generated_game resume
~~~

Resume uses the saved provider and model so a partially generated project cannot silently switch backends. It restores completed design, QA, implementation, refinement, and repair artifacts and calls a model only for unfinished work.

If validation needs a larger repair budget:

~~~powershell
agent-game-dev --output generated_game resume --add-repair-attempts 2
~~~

## Generated environment and dependencies

Each game receives its own virtual environment and requirements.txt. The coordinator installs only validated structured dependencies after approval. Missing imports discovered during validation pause for dependency approval rather than encouraging an agent to rewrite working code around the package.

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
  requirements.txt
  game_plan.json
  main.py
  ...
~~~

## Run and refine

Run a completed game while teeing output to .agentic/playtest.log:

~~~powershell
agent-game-dev --output generated_game run
~~~

Every automated validation appends captured output to .agentic/runtime.log. Runtime, playtest, and game-log tails are supplied to repair and implementation-review agents.

Apply playtest feedback with:

~~~powershell
agent-game-dev --output generated_game refine "Hits need stronger feedback"
~~~

## Important options

~~~text
--provider anthropic|ollama
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

## Validation boundary

The built-in runtime probe proves that the program imports, starts, and remains alive for the configured interval. The QA contract defines the additional mechanical, scripted-playtest, telemetry, and visual evidence needed to prove that it is the promised game. Runtime liveness alone is not considered gameplay correctness.

## Safety

Generated source is restricted to validated project-local Python paths. Package installation is performed by the trusted coordinator only after a structured plan and approval. Generated agents cannot supply package URLs, shell commands, Git repositories, or alternate indexes.

These controls reduce risk but cannot prove arbitrary generated code is safe. Review generated files before running games made from untrusted prompts.

## Development

~~~powershell
python -m unittest discover -s tests -v
python -m compileall -q agentic_game_dev tests agent_game_maker.py
~~~
