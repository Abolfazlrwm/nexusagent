# ADR 0014: Native per-vendor history threading

- Status: Accepted
- Date: 2026-11-20
- Deciders: Abolfazl Ranjbaran
- Extends: [ADR 0010](0010-1.0-api-stability-and-versioning-policy.md),
  [ADR 0012](0012-conversation-memory.md), [ADR 0011](0011-http-retry-backoff.md)
- Related: [ADR 0005](0005-openai-compatible-provider.md),
  [ADR 0007](0007-anthropic-compatible-provider.md),
  [ADR 0008](0008-gemini-provider.md), [ADR 0009](0009-streaming-responses.md)

## Context

ADR 0012 made conversation memory provider-agnostic by keeping the
Provider boundary untouched: the Agent composes remembered turns into a
single text transcript (`compose_prompt`) and sends it as the prompt.
Every provider — including user-written subclasses — works unchanged.

That composition has a real cost on the three vendor-native wire formats.
Chat Completions (`messages`), Messages (`messages`) and generateContent
(`contents`) all have first-class multi-turn conversations with per-role
entries. A flattened transcript erases the roles: the model receives one
`user` message containing a text rendering of the whole conversation.
Vendor APIs are trained on their native shapes, so the composed form
degrades multi-turn behavior exactly where the wire format could carry
it faithfully — role attribution, per-turn caching and vendor-side
conversation handling.

PROJECT_STATUS named the candidate as the next natural step: "Native
per-vendor history threading (an additive `history` keyword on the
Provider contract, rehydrated by each adapter) — must remain additive
per ADR 0010."

Two designs were rejected:

1. **Providers parse the composed transcript back out of the prompt.**
   Fragile: the composition is a presentation detail, byte-pinned by
   tests, and parsing it re-introduces the coupling ADR 0012 removed.
2. **Always send both the composed prompt and the structured history.**
   The vendor model would see the conversation twice — once as roles and
   once flattened — doubling context cost and inviting contradiction.

## Decision

**Add an optional keyword-only `history` parameter to the Provider
contract and let the Agent choose, per provider, between composing the
transcript into the prompt (unchanged) and handing over the structured
turns. Opt-in via a `supports_native_history` capability flag. No new
public names in the root surface (37 stays 37); everything is additive
per ADR 0010.**

- **Contract (sync and async).** `generate_response()` and
  `stream_response()` gain `history: Sequence[tuple[str, str]] = ()` —
  plain `(role, text)` pairs, roles `"user"`/`"assistant"`, oldest
  first. Plain pairs keep the Provider layer decoupled from the Memory
  subsystem (no `ConversationTurn` import crosses the boundary). The
  base implementations ignore an empty `history` and forward non-empty
  turns through the default streaming wrapper, so a provider that
  implements only `generate_response()` gets history on both paths.
- **Capability flag.** `Provider.supports_native_history` / 
  `AsyncProvider.supports_native_history` default to `False`. When
  False (every user-written provider, `FakeProvider`,
  `ScriptedProvider`, `HttpProvider`), the Agent composes the prompt
  exactly as before 1.5 and passes **no** `history` argument — the call
  shape is byte-identical, so duck-typed providers predating 1.5 keep
  working untouched. When True, the Agent passes the raw user input as
  `prompt` plus the remembered turns as `history` on **every** iteration
  of the tool loop (the loop stays stateless; each call rebuilds the
  full conversation). `SyncProviderAdapter` mirrors the wrapped
  provider's flag at construction and forwards `history` only when it
  is set, so the async layer inherits the same guarantee.
- **Vendor adapters opt in.** `OpenAIProvider`,
  `AnthropicProvider` and `GeminiProvider` set the flag and rehydrate
  the turns ahead of the current user message:
  - **OpenAI** — `{"role": ..., "content": ...}` entries; memory roles
    are exactly the wire roles.
  - **Anthropic** — the Messages wire demands strict `user`/`assistant`
    alternation starting with `user`; memory records complete
    `(user, assistant)` pairs so the shape holds, and as a safety net
    for custom backends consecutive same-role turns are merged into one
    message with newline-joined text.
  - **Gemini** — `assistant` becomes `model`; turns map one-to-one into
    `contents` entries.
- **The vendor-neutral `http` protocol does not opt in.** Its body shape
  is a published wire contract (`docs/protocol.md`) with existing
  third-party backends; switching its `input` from the composed
  transcript to a raw prompt plus a new field would break them. It
  keeps receiving the composed prompt, byte-for-byte pre-1.5. A
  structured `history` field there is future work and would be additive
  the same way.
- **Streamed runs** thread history identically (ADR 0009 composes with
  ADR 0014, not instead of it): fragments that arrive before a tool
  request behave exactly as before.

## Consequences

- Memory-backed sessions on the three vendor-native adapters now speak
  their vendor's native conversation shape; `compose_prompt` remains the
  universal fallback and the byte-pinned no-memory path is untouched
  (the composed prompt with no history is the input, byte-for-byte).
- Providers that opt in must accept the keyword on overridden methods
  (the built-ins do); the flag defaults to False, so nothing changes for
  providers written before 1.5 unless their author sets the flag.
- 30 new offline contract tests cover the capability flags, the Agent's
  compose-vs-thread branch on sync/async/streaming/tool-loop paths,
  per-adapter rehydration (including Anthropic's merge), the end-to-end
  wire bodies against stubbed HTTP, the HTTP provider's frozen body, and
  the async adapter bridge; the suite grows from 1230 to 1260 tests,
  coverage 99.57% (the floor is 95%).
- The public surface stays at 37 names; `tests/test_public_api.py` and
  this ADR pin it. Nothing moves, so the 1.0 stability contract holds
  without deprecation.
