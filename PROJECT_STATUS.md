# NexusAgent — Project Status (Snapshot)

This file exists so that whoever picks this project back up — even months
later — can understand exactly what works, what doesn't exist yet, and
where to resume without re-reading the entire history.

## Current state: WORKING and STABLE

- 716 tests, all passing.
- `ruff check .` and `ruff format --check .` — clean.
- `mypy --strict` — clean.
- `pytest` enforces a coverage floor of 95% (currently ~99%).
- `python scripts/check.py` — passes.
- No known bugs, no known regressions, no unfinished/half-done code.

This is a safe point to stop at. Nothing is broken or left mid-change.

## What NexusAgent can actually do today

A real, working, tested agent runtime that can:

- Run a prompt through a Provider (`FakeProvider`/`ScriptedProvider` for
  offline/dev use, `HttpProvider` for a real HTTP backend, `OpenAIProvider`
  for OpenAI-compatible APIs) and get an answer via `Agent.run()` /
  `Runtime.run()`.
- **Talk to OpenAI and every OpenAI-compatible server** (Ollama, LM Studio,
  vLLM, OpenRouter, Groq, ...) with full tool calling, statelessly rehydrated
  into the Chat Completions `messages` wire format. See ADR 0005.
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

- **No native Anthropic/Gemini adapters.** The `openai` provider covers the
  Chat Completions wire format family (ADR 0005); the vendor-neutral `http`
  provider (`docs/protocol.md`) covers everything else. Native adapters for
  other vendors are future work.
- **No async.** The core is synchronous by design (ADR 0001); streaming
  does not exist.
- **No memory, planning, or multi-agent orchestration.** The loop is
  single-turn from the caller's perspective: one input, one final answer.
- **No automatic retries/backoff** on HTTP failures.

## Next natural steps (in order)

1. Release 0.5.0 (OpenAI-compatible provider) to PyPI — Trusted Publishing
   is wired; tagging `v0.5.0` is enough.
2. Optionally add a native Anthropic adapter following the ADR 0005 pattern.
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
