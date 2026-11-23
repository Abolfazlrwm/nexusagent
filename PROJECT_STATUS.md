# NexusAgent — Project Status (Snapshot)

This file exists so that whoever picks this project back up — even months
later — can understand exactly what works, what doesn't exist yet, and
where to resume without re-reading the entire history.

## Current state: WORKING and STABLE — 1.6

- **1.0.0 declared API stability** (ADR 0010): the full public surface is
  `nexusagent.__all__` at the package root, governed by SemVer and pinned
  by `tests/test_public_api.py`; vendor wire adapters, built-in demo tools
  and internal factories stay internal by design. Since 1.0 the surface
  only grew additively: 33 names at 1.0.0, 36 at 1.2.0 (conversation
  memory, ADR 0012), 37 at 1.3.0 (persistent SQLite memory, ADR 0013),
  still 37 at 1.4.0 (CLI `--version` flag and the in-browser live demo —
  no surface change) and at 1.5.0 (native per-vendor history threading,
  ADR 0014 — a capability flag and an additive keyword, no new root
  names), 40 at 1.6.0 (minimal multi-agent orchestration, ADR 0015 —
  `AgentTeam`, `TeamResult`, `create_provider_router`) and 41 at 1.7.0
  (the offline demo brain, ADR 0016 — `DemoProvider`).
- **1.1.0 added automatic HTTP retries** (ADR 0011); **1.2.0 added
  in-process conversation memory** (ADR 0012); **1.3.0 added the
  persistent SQLite memory backend** (ADR 0013); **1.4.0 added a
  `--version` CLI flag and the live in-browser demo**; **1.5.0 added
  native per-vendor history threading** (ADR 0014); **1.6.0 added
  minimal multi-agent orchestration** (ADR 0015); **1.7.0 added the
  offline demo brain** (ADR 0016) — all additive, all offline-tested.
- 1352 tests, all passing.
- `ruff check .` and `ruff format --check .` — clean.
- `mypy --strict` — clean.
- `pytest` enforces a coverage floor of 95% (currently ~99.5%).
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
- **Retry transient HTTP failures automatically** (ADR 0011): connection
  errors, timeouts and 429/5xx statuses are retried with exponential
  backoff, full jitter and `Retry-After` support, bounded by
  `ProviderConfig.retries` / `NEXUS_RETRIES` (default 2, `0` disables);
  permanent failures fail fast and a mid-stream failure is never
  retried.
- **Carry context across runs with conversation memory** (ADR 0012):
  opt-in `Memory` implementations — built-in `InMemoryMemory` (bounded
  FIFO, `max_turns`, default 100) or your own three-method backend —
  record every successful run's `(user, assistant)` exchange and compose
  the remembered transcript into the next run's prompt via
  `compose_prompt()`. Provider-agnostic (the Provider contract is
  untouched), sync and async, failed runs record nothing; an empty
  memory composes the input byte-for-byte.
- **Rehydrate memory natively per vendor** (ADR 0014): the OpenAI,
  Anthropic and Gemini adapters opt into structured history — remembered
  turns ride the wire as real `messages` / `contents` entries (roles
  intact, `assistant` → `model` on Gemini) instead of a flattened
  transcript; every other provider keeps the composed prompt
  byte-for-byte, and the vendor-neutral `http` protocol deliberately
  stays frozen.
- **Keep memory across restarts with `SQLiteMemory`** (ADR 0013): the
  same three-method contract and FIFO semantics, persisted to a local
  SQLite database file (stdlib `sqlite3`, still zero dependencies).
  `SQLiteMemory(path, max_turns=...)` creates the file and missing
  parent directories on first use, commits every mutation immediately,
  evicts the oldest rows beyond the cap (persistently), and supports
  `close()` / context-manager lifetime; runtimes that reopen the same
  file see the same turns.
- **Route prompts across a team of specialists** (ADR 0015): `AgentTeam`
  maps non-empty names to `Agent` instances and asks a router callable —
  a plain function, or `create_provider_router(provider, names)` for a
  one-provider-call LLM decision with a documented deterministic parse —
  which member handles each prompt. The selected member's bounded tool
  loop, tools, memory and streaming run unchanged; routing failures
  become `TeamResult(success=False)` results, and `agent_name` records
  who answered. One hop per prompt: no graphs, no handoff chains, no
  shared team memory.
- **Run the full loop with zero API keys** (ADR 0016): `DemoProvider`
  answers a small closed fact sheet (colors chief among them — the sky
  comes back blue with Rayleigh scattering), routes chain math through
  the real calculator tool loop, remembers names across runs from the
  composed transcript, streams word by word, understands the ADR 0015
  routing-decision shape so an `AgentTeam` runs offline, and falls back
  honestly on everything else. Deterministic by contract — same prompt,
  same answer.
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
- **Memory has no network backend.** Conversation memory is either
  process-local (`InMemoryMemory`) or persisted to a local SQLite file
  (`SQLiteMemory`, ADR 0013); there is no built-in Redis/PostgreSQL
  session store or cross-machine sharing (custom `Memory` backends are
  the extension point).
- **No planning layer.** Within a run the loop is single-agent and the
  orchestration layer (ADR 0015) routes each prompt to exactly one
  member in one hop: no plan-then-execute, no multi-hop handoff chains,
  no shared team-level memory, and no async mirror of `AgentTeam` yet —
  each is a scoped follow-up with its own ADR, not a hidden deficiency.

## Next natural steps (in order)

1. ~~Release 1.1.0 (HTTP retries/backoff, ADR 0011)~~ — released.
2. ~~In-process memory between runs (ADR 0012)~~ — released in 1.2.0.
3. ~~Persistent SQLite memory backend (ADR 0013)~~ — released in 1.3.0.
4. ~~Native per-vendor history threading (additive `history` keyword on
   the Provider contract, rehydrated by each adapter)~~ — released in
   1.5.0 (ADR 0014); the vendor-neutral `http` protocol deliberately
   keeps the composed transcript (additive-frozen).
5. ~~Planning / multi-agent orchestration~~ — released in 1.6.0 as the
   minimal router-over-agents layer (ADR 0015). The async mirror of the
   team is the remaining half of this item; each further extension
   (multi-hop handoffs, shared team memory) needs its own ADR. Under the
   1.0 policy everything stays additive; no public name may move without
   a deprecation release.

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
python examples/orchestration.py                 # watch a team route prompts to specialists
python examples/demo_provider.py                 # watch the offline demo brain answer
```
