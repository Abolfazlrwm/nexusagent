# ADR 0005: OpenAI-compatible provider adapter

- Status: Accepted
- Date: 2026-11-11
- Deciders: Abolfazl Ranjbaran
- Extends: [ADR 0001](0001-sync-first-core.md),
  [ADR 0002](0002-tool-call-wire-format-and-agent-loop.md)

## Context

v0.4.0 shipped three providers: `fake` (offline default), `http` (the
vendor-neutral wire format from ADR 0002) and the test-only
`ScriptedProvider`. The single most requested integration is OpenAI's Chat
Completions API — not just `api.openai.com`, but the de-facto standard wire
format spoken by Ollama, LM Studio, vLLM, OpenRouter, Groq and others.

The core provider contract (ADR 0002) is deliberately stateless:
`generate_response(prompt, *, tools, tool_results)`. OpenAI's API is
conversational and stateful on the caller side: it expects a full `messages`
array, with tool results appearing as `tool` role messages that reference an
assistant `tool_calls` message by id.

## Decision

- Add `openai` as a first-class provider name (`NEXUS_PROVIDER=openai`,
  `create_provider("openai", config)`), implemented in
  `src/nexusagent/openai_provider.py`.
- **Stateless rehydration.** Every call maps `prompt` to a `user` message and
  each accumulated `ToolResult` to a synthesized assistant `tool_calls`
  message (id `call_<index>`) followed by a matching `tool` message. No state
  survives between iterations, so the provider stays pure and the tool loop
  stays entirely the core's.
- **Single-string tool schema.** NexusAgent tools take one string (ADR 0002);
  every tool is advertised as a function with one required `input` string
  parameter. Models that return their own single-parameter name are accepted;
  anything else is a `ProviderResponseError`. Only the first tool call of a
  response is consumed per iteration — the loop naturally collects the rest.
- **Error visibility.** Failed tool results are fed back with an `Error: `
  prefix, since the OpenAI tool-message format has no error flag.
- **Shared transport.** The HTTP mechanics move to a module-level
  `http_provider.post_json()` used by both HTTP-based providers. Wire formats
  stay provider-specific; timeouts, error mapping and key-safety are defined
  once.
- **Zero dependencies preserved.** The adapter uses the same stdlib `urllib`
  transport. No vendor SDK.
- Configuration: `model` required, `endpoint` optional (defaults to the
  official API), `api_key` optional (local servers need none), `timeout`
  positive. Endpoint scheme validation now applies to any provider that sets
  one, not only `http`.
- The provider is not re-exported from `nexusagent/__init__` (same policy as
  `HttpProvider`); architecture rule N pins its dependency direction and is
  enforced by tests.

## Alternatives considered

- **Vendor SDK (`openai` package)** — would break the
  zero-runtime-dependency guarantee the project is built on.
- **A LangChain-style message model in the core** — rejected: the core
  contract is prompt + tool results by design; rehydration is an adapter
  concern, not a core one.
- **Async first** — rejected for this release; ADR 0001 keeps the core
  sync-first. An async surface needs its own ADR.

## Consequences

- `pip install nexusagent-runtime` can now run against OpenAI and every
  OpenAI-compatible local or hosted server out of the box, with working tool
  calling.
- The feature table moves "OpenAI-compatible adapter" from ❌ to ✅; native
  Anthropic/Gemini adapters remain future work.
- 88 new contract tests; the suite grows to 716 tests with 99.21% coverage.
