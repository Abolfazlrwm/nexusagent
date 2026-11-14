# NexusAgent — Project Status (Snapshot)

This file exists so that whoever picks this project back up — even months
later — can understand exactly what works, what doesn't exist yet, and
where to resume without re-reading the entire history.

## Current state: WORKING and STABLE

- 1098 tests, all passing.
- `ruff check .` and `ruff format --check .` — clean.
- `mypy --strict` — clean.
- `pytest` enforces a coverage floor of 95% (currently ~99.85%).
- `python scripts/check.py` — passes.
- No known bugs, no known regressions, no unfinished/half-done code.

This is a safe point to stop at. Nothing is broken or left mid-change.

## What NexusAgent can actually do today

A real, working, tested agent runtime that can:

- Run a prompt through a Provider (`FakeProvider`/`ScriptedProvider` for
  offline/dev use, `HttpProvider` for a real HTTP backend, `OpenAIProvider`
  for OpenAI-compatible APIs, `AnthropicProvider` for Anthropic-compatible
  APIs, `GeminiProvider` for Gemini) and get an answer via `Agent.run()` /
  `Runtime.run()`.
- **Talk to OpenAI and every OpenAI-compatible server** (Ollama, LM Studio,
  vLLM, OpenRouter, Groq, ...) with full tool calling, statelessly rehydrated
  into the Chat Completions `messages` wire format. See ADR 0005.
- **Talk to Anthropic and every Anthropic-compatible gateway** with full
  tool calling, statelessly rehydrated into the Messages `tool_use` /
  `tool_result` block wire format, with native `is_error` feedback. See
  ADR 0007.
- **Talk to Google Gemini and every Gemini-compatible gateway** with full
  tool calling, statelessly rehydrated into the `generateContent`
  `functionCall` / `functionResponse` parts, with structured error feedback
  inside the response object. See ADR 0008.
- **Run the autonomous tool loop**: the Provider can answer with a
  `ToolCallRequest` instead of text; the Agent executes the requested tool
  through the registry/executor, feeds the `ToolResult` back, and repeats
  until the Provider answers in plain text (bounded by `max_iterations`,
  default 10). See `docs/adr/0002-tool-call-wire-format-and-agent-loop.md`
  and `docs/protocol.md`.
- **Run the same runtime under asyncio** (`AsyncAgent`, `AsyncRuntime`,
  `create_async_runtime`): the sync `Agent`/`Runtime` stay first-class, and
  the async layer mirrors them contract-for-contract. Sync providers (fake,
  http, openai, anthropic, gemini) work under the event loop through `SyncProviderAdapter`
  (worker threads, no new dependencies); `AsyncTool` adds awaited tools.
  See ADR 0006 and `docs/guides/async.md`.
- **Stream responses as they are generated** (ADR 0009): every HTTP adapter
  (`openai`, `anthropic`, `gemini`) speaks its wire format's SSE mode
  through the shared `post_sse()` transport; `Agent.run(..., on_delta=...)`
  and `AsyncAgent.run(..., on_delta=...)` forward text fragments as they
  arrive (tool calling fully supported while streaming), `nexusagent
  --stream` streams in the terminal, and providers that cannot stream keep
  working unchanged (the callback simply never fires).
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

- **No further native vendor adapters.** The three dominant wire-format
  families are covered: Chat Completions (ADR 0005), Messages (ADR 0007)
  and generateContent (ADR 0008); the vendor-neutral `http` provider
  (`docs/protocol.md`) covers everything else. Native adapters for other
  vendors are future work. The `http` wire protocol has no streaming mode
  of its own yet.
- **No memory, planning, or multi-agent orchestration.** The loop is
  single-turn from the caller's perspective: one input, one final answer.
- **No automatic retries/backoff** on HTTP failures.

## Next natural steps (in order)

1. Release 0.9.0 (streaming responses) to PyPI — Trusted Publishing is
   wired; tagging `v0.9.0` is enough.
2. Consider retries/backoff for HTTP providers, or in-process memory
   between runs, each with its own ADR — do not add them ad hoc.

## How to run things

```bash
pip install -e ".[dev]"
python -m pytest              # run the test suite (coverage reported)
ruff check .                  # lint
ruff format --check .         # format check
mypy                          # strict type check
python scripts/check.py       # full project check (what CI runs)

python -m nexusagent "your prompt here"          # run the agent
python -m nexusagent --stream "your prompt here" # stream text as it is generated
python -m nexusagent tool list                   # list built-in tools
python -m nexusagent tool run echo "hello"       # run a tool directly
python examples/tool_loop_demo.py                # watch the tool loop end to end
python examples/streaming.py                     # watch streamed text arrive
```
