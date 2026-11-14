# ADR 0009: Streaming responses (SSE)

- Status: Accepted
- Date: 2026-11-13
- Deciders: Abolfazl Ranjbaran
- Extends: [ADR 0002](0002-tool-call-wire-format-and-agent-loop.md),
  [ADR 0005](0005-openai-compatible-provider.md)
- Related: [ADR 0001](0001-sync-first-core.md),
  [ADR 0006](0006-async-execution-model.md),
  [ADR 0007](0007-anthropic-compatible-provider.md),
  [ADR 0008](0008-gemini-provider.md)

## Context

Every provider so far answers in one shot: `generate_response()` blocks until
the backend produces the complete JSON body, and the Agent consumes that
single answer. For chat-shaped products that means the user waits — often
seconds — before the first word appears. All three HTTP wire formats the
adapters speak (Chat Completions, Messages, `generateContent`) have a
streaming mode based on Server-Sent Events, and the missing capability was
listed honestly as "streaming responses ❌" in the README.

The design has to respect the foundations: the core is sync-first (ADR
0001), the tool loop is single-request-per-iteration with stateless
rehydration (ADR 0002), and the async layer is additive with
`asyncio.to_thread` as the only bridge (ADR 0006).

## Decision

**Add an opt-in streaming contract — `stream_response()` — to the provider
layer, a shared SSE transport next to `post_json()`, and an `on_delta`
callback to both agent loops. Nothing changes without the caller opting in.**

- **The contract.** `Provider.stream_response()` yields
  `ProviderStreamEvent`s: zero or more `StreamTextDelta` fragments as text
  arrives, then exactly one final `ProviderResponse` — the same object
  `generate_response()` returns, carrying the complete accumulated text.
  The default implementation does not stream: it requests the complete
  response and yields it as the only event, so text-only providers and the
  existing fakes need no changes. `AsyncProvider` mirrors this with an
  async iterator. Errors surface where they belong: configuration errors
  when the method is called, network and protocol errors while the
  iterator is consumed.
- **One shared SSE transport.** `post_sse()` lives next to `post_json()` in
  `http_provider.py`: it posts the JSON body with
  `Accept: text/event-stream`, parses the response as an SSE stream, and
  yields the raw `data:` payload strings in arrival order — multi-line data
  fields joined with newlines, event names/ids/retries/comments ignored
  (the JSON payloads carry their own event types). HTTP and network
  failures map to the same typed provider errors as `post_json()`; a
  mid-stream failure raises `ProviderRequestError` during iteration.
  Header handling, error mapping, snippet truncation and timeout semantics
  stay defined in one place.
- **Each adapter maps its own wire.** `OpenAIProvider` sends `stream: true`
  and accumulates `delta.content` fragments plus the first
  `delta.tool_calls` index (arguments concatenated, then decoded — exactly
  the non-streaming parser's single-call rule). `AnthropicProvider` handles
  the typed event sequence, forwards `text_delta` fragments, records the
  first `tool_use` block and joins its `input_json_delta` fragments;
  `ping`, `thinking_delta` and other unknown delta types are skipped, and
  in-band `error` events raise `ProviderResponseError`.
  `GeminiProvider` requests `:streamGenerateContent?alt=sse` and forwards
  `text` parts as they arrive while the first `functionCall` part decides
  the final response; usage-only chunks are skipped. All three adapters
  reuse their existing tool-input helpers, so lenient single-parameter
  acceptance behaves identically on both paths.
- **Agents opt in per call.** `Agent.run(..., on_delta=callable)` consumes
  `stream_response()` and calls `on_delta` with every text fragment as it
  arrives — including text the model emits before requesting a tool, since
  buffering would defeat the point — while `AgentResult.output` still
  carries only the final answer. Callbacks fire only when the backend
  actually streams; an exception raised by `on_delta` aborts the run and is
  reported like a provider error. Without `on_delta`, the loop uses
  `generate_response()` exactly as before, so `ScriptedProvider` and every
  existing caller keep byte-for-byte behavior. `AsyncAgent.run()` mirrors
  this over the async contract, and `SyncProviderAdapter.stream_response()`
  bridges a streaming sync provider into the event loop one
  `asyncio.to_thread(next(...))` step at a time. `Runtime` and
  `AsyncRuntime` pass `on_delta` through.
- **CLI visibility.** `nexusagent --stream "prompt"` prints fragments as
  they arrive and prints the complete answer only when nothing streamed
  (a non-streaming backend), so the flag is safe to leave on.
- **Deliberately not an environment variable.** Streaming changes the shape
  of consumption, not behavior; it is a per-call choice at the API and a
  flag at the CLI. No new `NEXUS_*` variable, no `Settings` change.
- **Tool loop unchanged.** The final event of every stream is the same
  `ProviderResponse` the loop has always consumed; `max_iterations`,
  error-as-result feedback and rehydration semantics are untouched. A
  stream that ends without a final response is a `ProviderResponseError`.

## Consequences

- Text can be displayed as it is generated on all three HTTP wire formats,
  under both the sync and the async runtime, with zero runtime
  dependencies (SSE is parsed with the standard library).
- The README "Streaming responses ❌" gap is retired; the remaining honest
  gaps are memory/planning/orchestration and HTTP retries.
- Architecture rules stay intact: `post_sse()` joins `post_json()` inside
  the transport module the providers already import, so no new layering
  rule is needed.
- ~152 new offline contract tests cover the SSE parser (comments, CRLF,
  multi-line data, error mapping), the three adapters' streaming paths,
  the agent/callback integration on both loops, the adapter bridge and the
  CLI flag; the suite grows from 946 to 1098 tests, coverage 99.50% →
  99.85% (the floor is 95%).
- Live behavior depends on the backend honoring SSE; a server that ignores
  `stream: true` and answers with plain JSON still surfaces a clear
  "stream ended without …" error instead of hanging.
