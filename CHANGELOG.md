# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/Abolfazlrwm/nexusagent/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/Abolfazlrwm/nexusagent/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/Abolfazlrwm/nexusagent/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/Abolfazlrwm/nexusagent/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/Abolfazlrwm/nexusagent/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/Abolfazlrwm/nexusagent/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/Abolfazlrwm/nexusagent/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Abolfazlrwm/nexusagent/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Abolfazlrwm/nexusagent/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Abolfazlrwm/nexusagent/releases/tag/v0.1.0
