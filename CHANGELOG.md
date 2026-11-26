# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.9.1] - 2026-11-26

### Fixed

- **The calculator evaluates arithmetic chains with standard
  precedence** — found by the real-browser E2E while validating 1.9.0:
  a natural prompt like `what is 2+2*3?` was captured whole by the demo
  brain (ADR 0016) but the calculator accepted exactly one binary
  operation, so the browser demo answered with a tool error instead of
  an answer. The tool now runs a hand-written tokenizer and
  precedence-climbing parser: `*`/`/` bind tighter than `+`/`-`, all
  left-associative, unary signs preserved (`-5 - -3` = -2, `2 * -3` =
  -6). Security unchanged: no eval, no exec, no imports beyond
  re/math; malformed shapes, bare numbers, lone operators, parentheses
  and `**` still raise the same ValueError; `Division by zero` is
  unchanged. 14 new tests (1404 → 1418) including end-to-end
  `agent.run("what is 2+2*3?") == "2+2*3 equals 8."`.

## [1.9.0] - 2026-11-23

### Added

- **`nexusagent chat` — the offline chat REPL (ADR 0018)** — the
  zero-config quickstart becomes one command: `pip install
  nexusagent-runtime && nexusagent chat`. The default brain is the
  shipped offline `DemoProvider` (ADR 0016/0017) wired to the real tool
  registry, tool executor and `InMemoryMemory(max_turns=16)` — math
  runs the calculator loop, your name is remembered across turns, the
  knowledge sheet answers chess/colors/science, and answers stream
  word by word (ADR 0009). `--provider openai|anthropic|gemini|http|fake`
  builds a real provider from the same `NEXUS_*` environment as the
  one-shot command (configuration errors surface before any network
  call); `--no-stream` prints whole answers. Commands: `/help`,
  `/reset`, `/tools`, `/exit`, `/quit`; EOF and Ctrl+C exit gracefully.
- 23 new offline tests (1381 → 1404): scripted conversations through
  injected input/output callables — tool-loop math, name memory,
  `/reset` with and without memory, `/tools`, all exit paths, streaming
  vs whole answers, the `--provider` env path, and the real
  `python -m nexusagent chat` subprocess round trip.

## [1.8.0] - 2026-11-23

### Added

- **The demo brain knowledge sheet (ADR 0017)** — `DemoProvider` grows
  from one color sheet to three answer layers with **no public surface
  change** (the root stays at 41 names, additive per ADR 0010). A new
  keyword-scored knowledge sheet answers closed, verifiable everyday
  questions exactly: `who start first in chess? black or white` gets
  "White moves first", `why is the sky blue?` gets the same Rayleigh
  explanation as the color sheet, plus the speed of light, the sun/moon
  distances, the boiling point of water, body temperature, pi, leap
  years, continents, oceans, planets, Everest, the blue whale, the
  cheetah and human bones. Matching scores distinct keyword hits —
  highest wins, ties stay with the earlier entry — so every lookup is
  byte-reproducible.
- **Did-you-mean on every miss** — a color-sheet miss suggests the
  closest known noun (`what color is the skys?` → "did you mean 'sky'?"),
  a total miss suggests the closest topic (`tell me about the moon
  landing` → "did you mean how far the moon is?"), and both keep the
  honest fallback beneath them. Prompts touching no topic still get the
  unchanged plain fallback, a pinned byte-stable constant.
- The fallback and capabilities replies now advertise the new reach, so
  the next visitor's first question is one the brain can answer.
- 29 new offline tests (1352 → 1381): the user's exact chess question,
  all 16 knowledge entries, case/punctuation insensitivity, sun-vs-moon
  scoring, byte-for-byte determinism, both suggestion paths and the
  no-suggestion fallback equality.

## [1.7.0] - 2026-11-23

### Added

- **The offline demo brain (ADR 0016)** — `DemoProvider` ships in the
  public API (root surface 40 → 41, additive per ADR 0010) so the real
  Agent loop runs with zero API keys and zero network, and still answers
  questions worth reading. A small closed fact sheet answers colors
  exactly (`what color is the sky?` gets Rayleigh scattering, not an
  echo); chain math (`2+2*3`) goes through the real calculator tool
  loop, and fed-back tool results are phrased into answers; names are
  remembered across runs from the composed transcript; `generate()`
  understands the ADR 0015 routing-decision shape, so an `AgentTeam`
  is runnable fully offline; `stream_response()` streams word by word
  per ADR 0009. Everything it cannot answer gets a truthful fallback
  naming the built-in real providers. Deterministic by contract — same
  prompt, same answer — pinned by 46 new offline tests (1306 → 1352),
  including an end-to-end offline `agent.run("what is 144 / 12?")`
  through the real tool loop.
- `examples/demo_provider.py` — the four demo-brain tricks end to end,
  offline; added to the CI examples smoke.


## [1.6.0] - 2026-11-23

### Added

- **Minimal multi-agent orchestration (ADR 0015)** — one prompt in, one
  named specialist out, that agent's own result back. `AgentTeam` maps
  non-empty names to `Agent` instances (validated eagerly) and asks a
  router callable which member handles each prompt; the selected
  member's bounded tool loop, tools, memory and streaming all run
  unchanged. Routing failures — any router exception or an unknown
  name — become `TeamResult(success=False)` results with the reason in
  `output`, mirroring how `Agent.run` reports provider errors;
  `TeamResult.agent_name` records who answered.
- **`create_provider_router(provider, agent_names)`** — builds the
  LLM-decides variant of the router from any `Provider`: one
  `generate()` call listing the agent names and the user prompt, then a
  documented, deterministic parse (exact match after stripping,
  case-insensitive exact match, otherwise the earliest listed name
  appearing in the reply; ties resolve to the earlier listed name). No
  match raises `ProviderResponseError`, which the team converts into a
  failed result. The router never runs the tool loop — a routing
  decision is one question, not a conversation.
- **Additive per ADR 0010**: the root surface grows 37 → 40
  (`AgentTeam`, `TeamResult`, `create_provider_router`); zero renames
  or removals. 46 new offline tests (1260 → 1306, coverage 99.59%).
  The async mirror of the team is deliberately deferred and named in
  ADR 0015 as the next step.
- **`examples/orchestration.py`** — a two-agent team (a calculator
  tool-loop member and a memory-backed greeter) routed by a scripted
  provider router, fully offline. Added to the CI examples smoke.
- [ADR 0015](docs/adr/0015-multi-agent-orchestration.md) documents the
  design and the rejected alternatives (graph orchestrators,
  agent-negotiated handoffs).

## [1.5.0] - 2026-11-20

### Added

- **Native per-vendor history threading (ADR 0014)** — with conversation
  memory configured (ADR 0012), the OpenAI, Anthropic and Gemini adapters
  now rehydrate remembered turns into their wire format's real
  multi-message conversation: proper `user`/`assistant` `messages`
  entries on the OpenAI and Anthropic wires, `contents` with `model`
  role on the Gemini wire — instead of the flattened text transcript.
  The mechanism is fully additive: the Provider contract gains a
  keyword-only `history` parameter (plain `(role, text)` pairs) plus a
  `supports_native_history` capability flag (default False). Providers
  that have not opted in — every user-written provider, `FakeProvider`,
  `ScriptedProvider`, and the vendor-neutral `http` provider — keep
  receiving the composed prompt and the exact pre-1.5 keyword set, so
  nothing changes for existing code. Opted-in providers receive the raw
  user input as `prompt` plus the turns as `history` on every iteration
  of the tool loop; streaming and the async layer (including
  `SyncProviderAdapter`) thread history identically. The public surface
  stays at 37 names; 30 new offline tests (1230 → 1260, coverage
  99.57%).
- **`examples/native_history.py`** — runs the real OpenAI adapter
  against a local echo backend and prints the exact request bodies, so
  the native rehydration is visible offline. Added to the CI
  examples smoke.
- [ADR 0014](docs/adr/0014-native-history-threading.md) documents the
  design, the rejected alternatives, and why the vendor-neutral `http`
  protocol deliberately keeps the composed transcript.

## [1.4.0] - 2026-11-18

### Added

- **`nexusagent --version`** — prints the installed version (`nexusagent
  X.Y.Z`) and exits before any runtime construction: no input text, no
  `NEXUS_*` environment variables, no provider, no network access. The
  positional prompt became optional (`nargs="?"`) with an explicit
  `parser.error` when it is missing, so behavior for every existing
  invocation is unchanged. 4 new CLI tests (1226 → 1230).
- **Live in-browser demo** at
  <https://abolfazlrwm.github.io/nexusagent/> — Pyodide loads the real
  wheel from PyPI and runs the actual agent loop, bounded tool loop
  (calculator), conversation memory and streaming right on the page,
  with a scripted model and a trace log. Repo-level deliverable: the
  demo page ships on the `gh-pages` branch; no package code.

### Changed

- `pyproject.toml` gains a `Documentation` project URL pointing at the
  demo site; `.github/CODEOWNERS` added; README gains a live-demo badge
  and a "try it live" callout above the quick start.

## [1.3.0] - 2026-11-18

### Added

- **Persistent conversation memory — `SQLiteMemory` (ADR 0013)** — the
  same opt-in, provider-agnostic memory contract as 1.2.0, now backed by
  a local SQLite database file so history survives process restarts,
  still at zero runtime dependencies:
  - One new public name at the package root (36 → 37, additive per ADR
    0010): `SQLiteMemory(path, max_turns=100)` — a drop-in `Memory`
    implementation storing turns in a `turns` table via the standard
    library's `sqlite3`. Works unchanged with `Agent`, `AsyncAgent`,
    `create_runtime` and `create_async_runtime` via the existing
    `memory=` keyword.
  - **Bounded-FIFO semantics identical to `InMemoryMemory`**: `max_turns`
    is validated the same way (`TypeError` for non-integers including
    `bool`, `ValueError` below 1) and the oldest rows are deleted beyond
    the cap — the eviction itself is persisted, so a reopened memory
    resumes inside the cap. A contract test pins that both built-ins
    return identical histories for identical operation sequences.
  - **Durability and lifetime**: the database file and missing parent
    directories are created on first use; every mutation commits
    immediately; `close()` releases the connection (idempotent) and the
    instance doubles as a context manager that closes on exit — further
    use of a closed instance raises `sqlite3.ProgrammingError`. A read
    -only `path` property exposes the resolved database file.
  - **Sharing by reopening**: runtimes that open the same file one after
    another see the same turns; the instance is deliberately not
    thread-safe, matching the runtime's single-threaded access (ADR
    0012).
  - `Settings` is deliberately unchanged: a file path is a construction
    argument with lifetime, not an environment scalar.
- New offline example `examples/sqlite_memory.py` — persistent memory
  across two "processes" (write, close, reopen), no API keys.

### Docs

- ADR 0013 (`docs/adr/0013-sqlite-memory.md`), README persistent-memory
  section + example, architecture and concepts updated, PROJECT_STATUS
  honesty gap "No persistence for memory" retired.

### Tests

- 32 new offline contract tests: construction and validation (`path`
  forms, parent-directory creation, `max_turns`), FIFO eviction and its
  persistence across reopen, `clear()`, close/context-manager behavior,
  two instances on one file, `:memory:`, parity with `InMemoryMemory`,
  and the end-to-end agent/factory wiring with a reopened memory. Suite:
  1194 → 1226 tests, coverage 99.81% (floor 95%), `ruff`, `ruff format`
  and `mypy --strict` clean.

## [1.2.0] - 2026-11-16

### Added

- **In-process conversation memory (ADR 0012)** — opt-in, provider-agnostic
  memory so the agent carries context across runs, still at zero runtime
  dependencies:
  - New public names at the package root (33 → 36, additive per ADR 0010):
    `ConversationTurn` (one validated, frozen `user`/`assistant` turn),
    `Memory` (the three-method storage contract: `append`, `history`,
    `clear` — implement it for Redis/SQLite/... backends) and
    `InMemoryMemory` (the built-in bounded FIFO: `max_turns`, default 100,
    oldest evicted first; `clear()` to forget).
  - `Agent` and `AsyncAgent` grow an additive final `memory` keyword
    (default `None`; a non-`Memory` object is a `TypeError`). Each
    **successful** run records `(user, input)` and `(assistant, output)`;
    failed runs — provider errors, missing tools, iteration exhaustion,
    `on_delta` failures — record nothing. A run's tool traffic stays
    inside the run: memory holds completed exchanges only.
  - `compose_prompt()` composes the remembered transcript (oldest first,
    one `role: text` line per turn) into the prompt of the next run. With
    an empty history the prompt is the input byte-for-byte, so configuring
    memory never changes a first run and the no-memory path is untouched.
  - **The Provider contract is untouched** — no new keyword, no signature
    change, no adapter code — so memory works with every provider,
    including user-written subclasses, on both the sync and the async
    loops (`SyncProviderAdapter` included).
  - `create_runtime()` and `create_async_runtime()` grow an additive
    `memory` parameter; `Runtime.memory` / `AsyncRuntime.memory` expose
    the configured instance as a read-only property (`None` when absent).
    `Settings` is deliberately unchanged: memory is an object with
    identity and lifetime, not a scalar.

- 52 new offline contract tests: turn and storage validation, FIFO
  bounds and eviction, custom `Memory` backends, the transcript format
  (including the empty-history identity), sync/async recording rules,
  streaming runs, adapter compatibility, runtime/factory wiring. Suite:
  1142 → 1194 tests, coverage 99.80%.
- Docs: ADR 0012, README (highlight, feature row, usage section),
  architecture (diagram + module map), concepts (`Memory` section),
  PROJECT_STATUS, CHANGELOG.

## [1.1.0] - 2026-11-15

### Added

- **Automatic retries with exponential backoff for HTTP providers**
  (ADR 0011) — transient request-level failures are retried in the
  shared transport, so all four HTTP-based providers (`http`, `openai`,
  `anthropic`, `gemini`) gain the policy at once, on both the request
  and the streaming paths, still at zero runtime dependencies:
  - Retryable failures: connection errors (`URLError`), timeouts, and
    HTTP 429, 500, 502, 503, 504. Every other status (authentication,
    bad requests, other 4xx) and every protocol-level response error
    fails fast exactly as before — the raised errors and their messages
    are unchanged.
  - Backoff: 0.5s doubling per attempt, capped at 8s, with full jitter
    (`random.uniform`) so concurrent clients do not retry in lockstep.
    An integer `Retry-After` hint wins when the server sends one,
    bounded by the same 8s cap; the HTTP-date form falls back to the
    exponential curve.
  - The retry window ends at the response headers: a mid-stream
    failure or a body-read timeout is never retried, so streamed
    fragments never repeat (ADR 0009 display safety). Worst case is
    bounded and documented: `(retries + 1) × timeout + Σ backoff`.
  - `ProviderConfig` grows `retries: int = 2` and `Settings` grows
    `retries` (`NEXUS_RETRIES`, default 2, `0` disables; validated
    locally like every other setting); `create_runtime()` wires it
    through. Both are additive dataclass fields — existing constructor
    calls keep working, nothing renamed or removed (ADR 0010).
  - Each provider validates non-negative retries in its configuration
    check and passes `config.retries` to the transport on both paths.

### Tests

- 39 new offline contract tests: the suite grows from 1103 to 1142
  tests; coverage 99.79%. New suites cover the retryable/permanent
  status matrix, exhaustion, `retries=0`, negative configuration,
  `Retry-After` (honored, capped, unusable), the backoff cap curve,
  read-stage and mid-stream non-retry behavior, per-adapter wiring on
  both paths, and the `Settings`/runtime wiring. A suite-wide fixture
  makes the backoff sleep instant except where a test asserts delays
  explicitly.

## [1.0.0] - 2026-11-14

### Added

- **Stable public API under SemVer** (ADR 0010) — 1.0 declares the
  package root as the complete, versioned public surface. Nothing in
  `nexusagent.__all__` is renamed, moved or removed within major
  version 1; additions are minor versions; removals require a new
  major preceded by a documented deprecation release.
  - The top-level facade grows from the minimal 9-name pre-1.0 surface
    to the full 33-name contract: `Agent`, `AgentResult`, `AsyncAgent`,
    `Runtime`, `AsyncRuntime`, `create_runtime`, `create_async_runtime`,
    `create_application_runtime`, `create_provider`, `Settings`,
    `Provider`, `AsyncProvider`, `ProviderConfig`, `TextResponse`,
    `ToolCallRequest`, `StreamTextDelta`, `ProviderResponse`,
    `ProviderStreamEvent`, `ToolSpec`, `ToolResult`, `FakeProvider`,
    `ScriptedProvider`, `SyncProviderAdapter`, `Tool`, `AsyncTool`,
    `ToolRegistry`, `ToolExecutor`, `AsyncToolExecutor`,
    `ProviderError`, `ProviderConfigurationError`, `ProviderRequestError`,
    `ProviderResponseError`, `ToolExecutionError` — every name
    importable as `nexusagent.<name>`. All existing submodule imports
    keep working unchanged; nothing was removed or renamed.
  - Vendor wire adapters (`HttpProvider`, `OpenAIProvider`,
    `AnthropicProvider`, `GeminiProvider`), the built-in demo tools and
    the internal factories stay deliberately off the root — constructed
    via `create_provider()` / `Settings` / a registry. Zero runtime
    dependencies and the Python 3.10–3.13 support matrix are part of
    the contract.
  - `tests/test_public_api.py` pins the surface exactly (contents and
    order), verifies every name resolves at the root, verifies every
    export is defined inside the package (union-type aliases resolve to
    their member classes), and pins the version format — an accidental
    removal, rename or silent addition fails CI.
- ADR 0010, README stability sections, architecture rule update,
  concepts "Public API surface" reference, PROJECT_STATUS 1.0 snapshot.

### Tests

- 5 new public-surface tests: the suite grows from 1098 to 1103 tests;
  coverage stays at 99.85%.

## [0.9.0] - 2026-11-14

### Added

- **Streaming responses** (ADR 0009) — text arrives as it is generated, on
  every HTTP adapter, under both runtimes, still at zero runtime
  dependencies (SSE parsed with the standard library):
  - `Provider.stream_response()` / `AsyncProvider.stream_response()`: yields
    zero or more `StreamTextDelta` fragments as text arrives, then exactly
    one final `ProviderResponse` — the same object `generate_response()`
    returns, with the complete accumulated text. The default implementation
    delegates to `generate_response()` and yields the single complete
    event, so text-only providers and the offline fakes need no changes.
  - Shared SSE transport `nexusagent.http_provider.post_sse()` next to
    `post_json()`: posts the JSON body with `Accept: text/event-stream`,
    parses Server-Sent Events (multi-line data fields, comments, CRLF,
    final-event flush) and maps HTTP/network failures — including
    mid-stream failures — to the same typed provider errors.
  - Adapter wire mappings: OpenAI `stream: true` chunks (`delta.content`
    plus first-`tool_calls` argument accumulation), Anthropic typed events
    (`text_delta` forwarding, first `tool_use` block with
    `input_json_delta` joins, in-band `error` events, `ping`/`thinking`
    skipped), Gemini `:streamGenerateContent?alt=sse` (`text` parts and
    first `functionCall`, usage-only chunks skipped). Each adapter reuses
    its existing tool-input helpers, so lenient single-parameter acceptance
    behaves identically on both paths.
  - `Agent.run(..., on_delta=...)` and `AsyncAgent.run(..., on_delta=...)`:
    the callback fires with every text fragment as it arrives (including
    text emitted before a tool request); `AgentResult.output` still carries
    only the final answer. Without `on_delta` the non-streaming path is
    used, unchanged — no behavior change for existing callers.
  - `SyncProviderAdapter.stream_response()` bridges a streaming sync
    provider into the event loop one `asyncio.to_thread(next(...))` step at
    a time; `Runtime.run()` / `AsyncRuntime.run()` pass `on_delta` through.
  - CLI: `nexusagent --stream "prompt"` prints fragments as they arrive and
    still prints the complete answer when the backend does not stream.
- `examples/streaming.py` — offline demo of streamed text through
  `on_delta` (no API keys).

### Tests

- 152 new offline contract tests: the suite grows from 946 to 1098 tests;
  coverage rises to 99.85%. New suites cover the SSE transport parser (22
  tests), the three adapters' streaming paths (88), the agent/async/
  callback integration (36) and the CLI flag (6).

## [0.8.0] - 2026-11-12

### Added

- **Gemini provider** (`NEXUS_PROVIDER=gemini`,
  `create_provider("gemini", config)`) speaking Google's Gemini
  `generateContent` wire format. Works with Gemini itself and with
  compatible gateways via a `NEXUS_ENDPOINT` **base URL** override — the
  adapter appends `/v1beta/models/{model}:generateContent`
  (see [ADR 0008](docs/adr/0008-gemini-provider.md)):
  - Stateless loop rehydration: prompt + accumulated tool results are
    mapped to alternating `user`/`model` turns with `functionCall` and
    `functionResponse` parts; no state survives between iterations.
  - Full tool calling: tools are declared with a single required `input`
    string parameter (Gemini's uppercase Schema enums); models that pick
    their own single parameter name are accepted. Failed tool results are
    fed back as `{"error": ...}` inside the `functionResponse` object —
    the wire format has no native error flag.
  - Configuration: `model` required, `endpoint` optional (defaults to the
    official API), `api_key` optional (sent as the `x-goog-api-key`
    header, never a query parameter; gateways may not need one) — still
    zero runtime dependencies, no vendor SDK.
  - `max_tokens` is optional here (unlike Anthropic): no
    `generationConfig` is sent by default; an explicit override must be a
    positive integer and is sent as `generationConfig.maxOutputTokens`.
- Shared HTTP transport `nexusagent.http_provider.post_json()` now backs
  four HTTP-based providers; timeout handling, error mapping and
  key-safety remain defined in one place.
- Architecture rule T (no upward dependencies for `gemini_provider.py`),
  enforced by tests like the other layer rules.

### Changed

- `NEXUS_PROVIDER=gemini` accepted by `Settings`; a model is required
  for it, exactly like `openai` and `anthropic`.

### Tests

- 92 new offline contract tests: the suite grows from 854 to 946 tests;
  coverage rises from 99.44% to 99.50% (`gemini_provider.py` itself:
  100%).

## [0.7.0] - 2026-11-12

### Added

- **Anthropic-compatible provider** (`NEXUS_PROVIDER=anthropic`,
  `create_provider("anthropic", config)`) speaking the Anthropic Messages
  wire format. Works with Anthropic itself and with compatible gateways
  via a `NEXUS_ENDPOINT` override
  (see [ADR 0007](docs/adr/0007-anthropic-compatible-provider.md)):
  - Stateless loop rehydration: prompt + accumulated tool results are
    mapped to alternating `user`/`assistant` turns with `tool_use` and
    `tool_result` content blocks and synthesized call ids; no state
    survives between iterations.
  - Full tool calling: tools are advertised with a JSON Schema of a single
    required `input` string parameter; models that pick their own single
    parameter name are accepted. Failed tool results are fed back through
    the native `is_error` flag of `tool_result`.
  - Configuration: `model` required, `endpoint` optional (defaults to the
    official API), `api_key` optional (sent as `x-api-key`; gateways may
    not need one) — still zero runtime dependencies, no vendor SDK.
  - `max_tokens` (required by the wire format) defaults to 1024 and can be
    overridden per provider instance with a positive integer.
- Shared HTTP transport `nexusagent.http_provider.post_json()` now backs
  three HTTP-based providers; timeout handling, error mapping and
  key-safety remain defined in one place.
- Architecture rule S (no upward dependencies for `anthropic_provider.py`),
  enforced by tests like the other layer rules.

### Changed

- `NEXUS_PROVIDER=anthropic` accepted by `Settings`; a model is required
  for it, exactly like `openai`.

### Tests

- 88 new offline contract tests: the suite grows from 766 to 854 tests;
  coverage rises from 99.36% to 99.44% (`anthropic_provider.py` itself:
  100%).

## [0.6.0] - 2026-11-12

### Added

- **Async execution layer** (ADR 0006) — additive; the sync core stays
  first-class and unchanged:
  - `AsyncProvider` ABC in `provider.py`, mirroring the sync `Provider`
    contract (`generate`, `generate_response`) with awaited methods.
  - `SyncProviderAdapter` (`nexusagent.async_provider`): runs any sync
    provider's blocking calls in worker threads via `asyncio.to_thread`, so
    the `fake`, `scripted`, `http` and `openai` providers drive the async
    loop unchanged — still zero runtime dependencies, no HTTP client
    library.
  - `AsyncTool` ABC with `async aexecute()`; the sync path fails fast with
    a clear `NotImplementedError` instead of leaking a coroutine.
  - `AsyncToolExecutor`: awaits `AsyncTool` natively and runs plain sync
    tools in a worker thread — validation and `ToolExecutionError` wrapping
    are identical on both paths.
  - `AsyncAgent`: awaited mirror of the bounded tool loop — same
    `AgentResult`, same `max_iterations` bound, tool failures become error
    results fed back to the provider.
  - `AsyncRuntime` + `create_async_runtime()`: same facade and `NEXUS_*`
    configuration as the sync runtime.
- Public API additions: `AsyncAgent`, `AsyncRuntime`, `create_async_runtime`.
- `examples/async_tool_loop.py` — offline async demo; async guide at
  `docs/guides/async.md`; ADR 0006.
- Architecture rules O–R pin the async modules into the same layering as
  their sync counterparts, enforced by tests.
- Dev-only: `pytest-asyncio` (strict mode) for the async contract tests;
  runtime dependencies remain empty.

### Changed

- 50 new async contract tests: the suite grows from 716 to 766 tests;
  coverage rises from 99.21% to 99.36% (all new async modules: 100%).

## [0.5.0] - 2026-11-11

### Added

- **OpenAI-compatible provider** (`NEXUS_PROVIDER=openai`,
  `create_provider("openai", config)`) speaking the Chat Completions wire
  format. Works with OpenAI itself and with any compatible server — Ollama,
  LM Studio, vLLM, OpenRouter, Groq — via a `NEXUS_ENDPOINT` override
  (see [ADR 0005](docs/adr/0005-openai-compatible-provider.md)):
  - Stateless loop rehydration: prompt + accumulated tool results are mapped
    to `user` / assistant `tool_calls` / `tool` messages with synthesized
    call ids; no state survives between iterations.
  - Full tool calling: tools are advertised as functions with a single
    required `input` string parameter; models that pick their own single
    parameter name are accepted. Failed tool results are fed back with an
    `Error: ` prefix.
  - Configuration: `model` required, `endpoint` optional (defaults to the
    official API), `api_key` optional (local servers need none) — still
    zero runtime dependencies, no vendor SDK.
- Shared HTTP transport `nexusagent.http_provider.post_json()` used by both
  HTTP-based providers; timeout handling, error mapping and key-safety are
  defined in one place.
- Architecture rule N (no upward dependencies for `openai_provider.py`),
  enforced by tests like the other layer rules.

### Changed

- Endpoint scheme validation (`http`/`https` only) now applies to any
  provider that sets an endpoint, not only `http`.
- 88 new contract tests: the suite grows from 628 to 716 tests; coverage
  rises from 99.05% to 99.21% (`openai_provider.py` itself: 100%).

## [0.4.0] - 2026-11-09

First release published to PyPI as [`nexusagent-runtime`](https://pypi.org/project/nexusagent-runtime/).
The **import name** remains `nexusagent`.

### Added

- `py.typed` marker: the package now ships full type information for mypy/IDE users.
- `nexusagent` console command (previously only `python -m nexusagent` was available).
- **Autonomous tool loop**: `Provider.generate_response()` may answer with a
  `ToolCallRequest`; the Agent runs the requested tool, feeds the `ToolResult`
  back, and repeats until a text answer or `max_iterations` (default 10).
  Text-only providers keep working unchanged through the default
  implementation. The vendor-neutral HTTP wire format is documented in
  `docs/protocol.md` (ADR 0002). Includes the deterministic, network-free
  `ScriptedProvider` for demos and tests.
- Project documentation under `docs/`: architecture overview, concepts,
  custom provider/tool guides, the HTTP protocol spec, and ADRs 0001–0004.
- Executable examples under `examples/` (basic runtime, custom tool, tool loop
  demo — all runnable offline, no API keys).
- CI: lint + format (ruff), `mypy --strict`, tests with an enforced coverage
  floor (≥95%) on Python 3.10–3.13, wheel build with a clean-venv smoke test,
  and a self-hosted coverage badge.
- PyPI publishing workflow using Trusted Publishing (OIDC), triggered on `v*` tags.
- `SECURITY.md`, this `CHANGELOG.md`, `.pre-commit-config.yaml`, and an expanded
  `CONTRIBUTING.md`.

### Changed

- Version is single-sourced from `nexusagent.__version__` (it previously
  drifted: `pyproject.toml` said 0.1.0 while repository tags reached v0.3.0).
- Packaging metadata modernized: PEP 639 SPDX license, classifiers,
  `[project.urls]`, package keywords.
- Lint rules extended (bugbear, comprehensions, pyupgrade, simplify, etc.) and
  the whole codebase brought up to them.
- **Distribution name is `nexusagent-runtime`** (originally planned as
  `nexusagent`). PyPI's confusingly-similar-name rule blocks registering
  `nexusagent` because an unrelated placeholder package, `nexus-agent`,
  already exists. The `v0.4.0` tag was moved to the renamed commit before the
  first PyPI upload — nothing was ever published under the old name, so no
  user is affected. See [ADR 0004](docs/adr/0004-pypi-distribution-name.md).

### Fixed

- `NEXUS_TIMEOUT` with a non-numeric value now raises a readable
  `ValueError` ("Invalid NEXUS_TIMEOUT: 'abc' …") instead of a raw
  float-conversion traceback.
- `HttpProvider` HTTP errors now include a short snippet of the response body
  when the backend provides one (rate limits, auth failures), truncated to
  200 characters.
- `ToolExecutionError` messages now preserve the original error class name
  (e.g. `ZeroDivisionError: …`); the exception itself remains available as
  `__cause__`.

## [0.3.0] - 2026-10-12

### Added

- Tool availability checks: `Agent.has_tool()` and `ToolRegistry.has()`.
- Structured provider response groundwork (`TextResponse`, `ToolCallRequest`,
  `ProviderResponse`) with contract tests — not yet produced by any Provider.
- Explicit architecture tests that forbid lower layers importing upward.

### Changed

- Provider factories hardened: unsupported provider names raise
  `ProviderConfigurationError`; `Runtime`/`Settings` construction validated
  before any provider is built.

## [0.2.0] - 2026-09-20

### Added

- CLI tool commands: `python -m nexusagent tool list` and
  `python -m nexusagent tool run <name> <input>`.
- `HttpProvider`: generic HTTP backend sending `{"model", "input"}` and
  reading `{"output"}`, with `NEXUS_PROVIDER` / `NEXUS_ENDPOINT` /
  `NEXUS_API_KEY` / `NEXUS_TIMEOUT` configuration.

### Changed

- `Settings` gained `provider`, `endpoint`, `timeout` fields with local
  validation (no network access during validation).

## [0.1.0] - 2026-08-25

### Added

- Initial foundation: `Provider`/`FakeProvider`, `Agent`/`AgentResult`,
  `Tool`/`ToolRegistry`/`ToolExecutor`, `Runtime`, built-in tools
  (`echo`, `uppercase`, `calculator`), `Settings` from `NEXUS_*` environment
  variables, and the factory layer (`create_runtime`,
  `create_application_runtime`).

[Unreleased]: https://github.com/Abolfazlrwm/nexusagent/compare/v1.4.0...HEAD
[1.5.0]: https://github.com/Abolfazlrwm/nexusagent/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/Abolfazlrwm/nexusagent/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/Abolfazlrwm/nexusagent/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/Abolfazlrwm/nexusagent/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/Abolfazlrwm/nexusagent/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/Abolfazlrwm/nexusagent/compare/v0.9.0...v1.0.0
[0.9.0]: https://github.com/Abolfazlrwm/nexusagent/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/Abolfazlrwm/nexusagent/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/Abolfazlrwm/nexusagent/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/Abolfazlrwm/nexusagent/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/Abolfazlrwm/nexusagent/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/Abolfazlrwm/nexusagent/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Abolfazlrwm/nexusagent/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Abolfazlrwm/nexusagent/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Abolfazlrwm/nexusagent/releases/tag/v0.1.0
