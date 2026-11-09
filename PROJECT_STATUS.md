# NexusAgent — Project Status (Snapshot)

This file exists so that whoever picks this project back up — even months
later — can understand exactly what works, what doesn't exist yet, and
where to resume without re-reading the entire history.

## Current state: WORKING and STABLE

- 628 tests, all passing.
- `ruff check .` and `ruff format --check .` — clean.
- `mypy --strict` — clean.
- `pytest` enforces a coverage floor of 95% (currently ~99%).
- `python scripts/check.py` — passes.
- No known bugs, no known regressions, no unfinished/half-done code.

This is a safe point to stop at. Nothing is broken or left mid-change.

## What NexusAgent can actually do today

A real, working, tested agent runtime that can:

- Run a prompt through a Provider (`FakeProvider`/`ScriptedProvider` for
  offline/dev use, `HttpProvider` for a real HTTP backend) and get an
  answer via `Agent.run()` / `Runtime.run()`.
- **Run the autonomous tool loop**: the Provider can answer with a
  `ToolCallRequest` instead of text; the Agent executes the requested tool
  through the registry/executor, feeds the `ToolResult` back, and repeats
  until the Provider answers in plain text (bounded by `max_iterations`,
  default 10). See `docs/adr/0002-tool-call-wire-format-and-agent-loop.md`
  and `docs/protocol.md`.
- Register and run explicit, named tools (`EchoTool`, `UppercaseTool`,
  `CalculatorTool`) through `Agent.execute_tool()` / `Runtime.execute_tool()`,
  from Python or the CLI (`python -m nexusagent tool run ...`).
- Check tool availability (`Agent.has_tool()` / `ToolRegistry.has()`).
- Configure everything through `Settings` (env vars prefixed `NEXUS_`,
  or explicit construction).

Every layer (Provider, Tool, Registry, Executor, Agent, Runtime, and all
factories) is contract-tested, with explicit architecture rules preventing
lower layers from depending upward on higher ones.

## What does NOT exist yet (this is the important part)

- **No vendor Provider adapters.** The `http` provider speaks the small
  NexusAgent wire format (`docs/protocol.md`). Adapting OpenAI, Anthropic,
  or a local model server means writing a thin Provider that translates
  that API into `generate_response()` — deliberately not done yet
  (see ADR 0002 "Consequences").
- **No async.** The core is synchronous by design (ADR 0001); streaming
  does not exist.
- **No memory, planning, or multi-agent orchestration.** The loop is
  single-turn from the caller's perspective: one input, one final answer.
- **No automatic retries/backoff** on HTTP failures.

## Next natural steps (in order)

1. Publish 0.4.0 to PyPI (Trusted Publishing is wired; see
   `.github/workflows/publish.yml`).
2. Optionally write a vendor adapter (e.g. an OpenAI-compatible
   `generate_response()`) as a new ADR — the wire format is stable, so
   this is now incremental work instead of a blocked decision.
3. Revisit async/streaming only with a new ADR; do not add it ad hoc.

## How to run things

```bash
pip install -e ".[dev]"
python -m pytest              # run the test suite (coverage reported)
ruff check .                  # lint
ruff format --check .         # format check
mypy                          # strict type check
python scripts/check.py       # full project check (what CI runs)

python -m nexusagent "your prompt here"          # run the agent
python -m nexusagent tool list                   # list built-in tools
python -m nexusagent tool run echo "hello"       # run a tool directly
python examples/tool_loop_demo.py                # watch the tool loop end to end
```
