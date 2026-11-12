# ADR 0007: Anthropic-compatible Messages API provider

- Status: Accepted
- Date: 2026-11-12
- Deciders: Abolfazl Ranjbaran
- Extends: [ADR 0002](0002-tool-call-wire-format-and-agent-loop.md),
  [ADR 0005](0005-openai-compatible-provider.md)
- Related: [ADR 0001](0001-sync-first-core.md),
  [ADR 0006](0006-async-execution-model.md)

## Context

ADR 0005 added an OpenAI-compatible provider and established a repeating
pattern: one adapter module per wire-format family, speaking real vendor
HTTP from the shared `post_json()` transport, staying at zero runtime
dependencies, and rehydrating the stateless (prompt + tool results) loop
into whatever conversation shape the wire format expects.

The Anthropic Messages API is the second wire-format family worth
supporting first-class: it differs structurally from Chat Completions
(top-level `system` instead of a system role, a **required** `max_tokens`
on every request, content blocks instead of strings, `tool_use` /
`tool_result` blocks instead of `tool_calls` / `tool` messages, and a
native `is_error` flag on tool results). Mapping it through the OpenAI
adapter is impossible without a lossy translation layer; honest support
means a dedicated adapter.

## Decision

**Add `AnthropicProvider` as a third HTTP-based provider, mirroring the
ADR 0005 pattern block for block.**

- **One module, shared transport.** `anthropic_provider.py` uses the same
  `post_json()` transport as `http_provider.py` and `openai_provider.py`:
  error mapping, timeouts, body snippets and key-safety are defined once.
  No vendor SDK, still zero runtime dependencies.
- **Wire shape.** `POST /v1/messages` with `anthropic-version: 2023-06-01`
  and, when configured, `x-api-key`. The prompt is the first `user`
  message; the top-level `system` parameter is deliberately unused — the
  stateless loop stays free of a hidden system prompt, mirroring the
  OpenAI adapter's decision. Tools are advertised with a JSON Schema of
  one required string `input` parameter; models that pick their own single
  string parameter name are accepted.
- **Stateless rehydration.** Each `ToolResult` becomes an assistant
  message with one `tool_use` block immediately followed by a user message
  with the matching `tool_result` block — the ordering the Messages API
  requires. Call ids are synthesized as `call_0`, `call_1`, ... and only
  have to match within the request, so no state survives between
  iterations.
- **Native error channel.** Failed tool results set `is_error: true` on
  the `tool_result` block instead of the `Error: ` prefix used on the
  OpenAI wire — each adapter maps errors to its format's own first-class
  mechanism.
- **`max_tokens` is required by the wire format.** The provider sends
  `DEFAULT_MAX_TOKENS = 1024` by default; an explicit constructor override
  must be a positive integer. It is deliberately *not* part of
  `ProviderConfig` or `Settings`: it is Anthropic-specific, and no second
  knob joins the shared configuration until a real need appears.
- **Parsing is content-driven.** The first `tool_use` block wins (the
  core loop is single-request-per-iteration, as on the OpenAI wire);
  otherwise the `text` blocks are joined. Unknown future block types are
  skipped, not fatal. Empty content, non-object blocks, non-string text
  and unusable tool inputs raise `ProviderResponseError`.
- **Factory and configuration.** `create_provider("anthropic")` and
  `NEXUS_PROVIDER=anthropic` (model required, endpoint optional, api key
  optional for gateways and required by the official API). The async layer
  needs nothing new: `SyncProviderAdapter` already bridges any sync
  provider.

## Consequences

- Anthropic-compatible backends work end to end — text answers, tool
  calling, error feedback — under both the sync and the async runtime.
- The provider matrix is now honest about what it covers: Chat Completions
  (ADR 0005), Messages (this ADR), the vendor-neutral `http` protocol, and
  offline fakes. Gemini remains future work.
- Architecture rules (new rule S, plus updated rules I/O/P/Q/R) keep the
  adapter in the provider layer: it may import the transport and the
  contract ABCs, never anything above it.
- 88 new offline contract tests cover request shape, rehydration, parsing,
  `max_tokens` validation and key-safety; the suite grows from 766 to 854
  tests, and `anthropic_provider.py` lands at 100% coverage.
