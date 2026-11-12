# ADR 0008: Gemini generateContent provider

- Status: Accepted
- Date: 2026-11-12
- Deciders: Abolfazl Ranjbaran
- Extends: [ADR 0002](0002-tool-call-wire-format-and-agent-loop.md),
  [ADR 0005](0005-openai-compatible-provider.md),
  [ADR 0007](0007-anthropic-compatible-provider.md)
- Related: [ADR 0001](0001-sync-first-core.md),
  [ADR 0006](0006-async-execution-model.md)

## Context

ADR 0005 and ADR 0007 established the repeating adapter pattern: one module
per wire-format family, speaking real vendor HTTP from the shared
`post_json()` transport, staying at zero runtime dependencies, and
rehydrating the stateless (prompt + tool results) loop into whatever
conversation shape the wire format expects.

The Gemini `generateContent` API is the third wire-format family worth
supporting first-class. It differs structurally from both Chat Completions
and Messages: roles are `user`/`model` (not `assistant`), the model id is
part of the request **URL** (`POST /v1beta/models/{model}:generateContent`)
rather than the body, tool requests and results are `functionCall` /
`functionResponse` **parts** inside turn `contents` (with `args` and a
required response **object** instead of string arguments), tool
declarations use an OpenAPI-style Schema whose type enums are spelled
uppercase (`OBJECT`, `STRING`), and `max_tokens` is optional rather than
required. Mapping it through the OpenAI adapter is impossible without a
lossy translation layer; honest support means a dedicated adapter.

## Decision

**Add `GeminiProvider` as a fourth HTTP-based provider, mirroring the
ADR 0005/0007 pattern block for block.**

- **One module, shared transport.** `gemini_provider.py` uses the same
  `post_json()` transport as the other HTTP providers: error mapping,
  timeouts, body snippets and key-safety are defined once. No vendor SDK,
  still zero runtime dependencies.
- **Wire shape.** `POST {base}/v1beta/models/{model}:generateContent` with,
  when configured, `x-goog-api-key` — sent as a header, never as a query
  parameter, so the key stays out of URLs and logs. `ProviderConfig.endpoint`
  overrides the **base URL** (default: the official Gemini API) and the
  adapter appends `/v1beta/models/{model}:generateContent`; the model id is
  validated non-empty before the URL is composed.
- **Stateless rehydration.** The prompt is the first `user` turn; each
  `ToolResult` becomes a `model` turn with one `functionCall` part
  (args synthesized as the single `input` string) immediately followed by a
  `user` turn with the matching `functionResponse` part. No state survives
  between iterations.
- **Tool declarations.** One required string `input` parameter, declared
  with the uppercase Schema enums this wire format expects; models that
  pick their own single string parameter name are accepted.
- **No native error channel.** `functionResponse` has no `is_error` flag,
  so the required response object carries the signal: `{"result": <output>}`
  on success, `{"error": <message>}` on failure — structured feedback
  instead of the OpenAI adapter's `Error: ` text prefix.
- **`max_tokens` is optional here.** Unlike Messages, no generation config
  is required: by default the adapter sends no `generationConfig` at all.
  An explicit constructor override must be a positive integer and is sent
  as `generationConfig.maxOutputTokens`. It is deliberately *not* part of
  `ProviderConfig` or `Settings` — provider-specific knobs do not join the
  shared configuration until a real need appears.
- **Parsing is content-driven.** The first `functionCall` part wins (the
  core loop is single-request-per-iteration, as on the other wires);
  otherwise the `text` parts are joined. Unknown future part types are
  skipped, not fatal. Missing or empty `candidates`, missing content or
  parts, non-object parts, non-string text and unusable tool inputs raise
  `ProviderResponseError`.
- **Factory and configuration.** `create_provider("gemini")` and
  `NEXUS_PROVIDER=gemini` (model required, endpoint optional base URL, api
  key optional for gateways and required by the official API). The async
  layer needs nothing new: `SyncProviderAdapter` already bridges any sync
  provider.

## Consequences

- Gemini-compatible backends work end to end — text answers, tool calling,
  structured error feedback — under both the sync and the async runtime.
- The provider matrix now covers the three dominant wire-format families:
  Chat Completions (ADR 0005), Messages (ADR 0007), generateContent (this
  ADR), plus the vendor-neutral `http` protocol and offline fakes.
- Architecture rules (new rule T, plus updated rules I/O/P/Q/R/S) keep the
  adapter in the provider layer: it may import the transport and the
  contract ABCs, never anything above it.
- 92 new offline contract tests cover request shape, URL composition,
  rehydration, parsing, `max_tokens` validation and key-safety; the suite
  grows from 854 to 946 tests, and `gemini_provider.py` lands at 100%
  coverage.
