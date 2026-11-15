# ADR 0012: In-process conversation memory

- Status: Accepted
- Date: 2026-11-16
- Deciders: Abolfazl Ranjbaran
- Extends: [ADR 0001](0001-sync-first-core.md),
  [ADR 0002](0002-tool-call-wire-format-and-agent-loop.md),
  [ADR 0006](0006-async-execution-model.md),
  [ADR 0010](0010-1.0-api-stability-and-versioning-policy.md)
- Related: [ADR 0009](0009-streaming-responses.md),
  [ADR 0011](0011-http-retry-backoff.md)

## Context

NexusAgent is stateless by design: every `Agent.run()` call starts a fresh
tool loop, and the Provider never sees what happened in earlier runs. For
one-shot prompts that is exactly right; for conversations it is a real
limitation — the model cannot remember a name, a decision or a result
from the previous run, so every caller was re-implementing history
management above the library. The gap was listed honestly in the README
("Conversation memory ❌") and in PROJECT_STATUS as the next candidate
after the 1.1 retries.

Two designs were possible:

1. **Native wire threading** — extend the Provider contract
   (`generate_response()` / `stream_response()` and their async mirrors)
   with a `history` keyword and rehydrate prior turns as native messages
   in each of the four HTTP adapters. Highest fidelity per vendor, but it
   touches the public Provider ABC that every user subclass implements,
   and every third-party provider that does not accept the new keyword
   breaks the moment an Agent with memory calls it.
2. **Agent-level transcript** — the Agent composes remembered turns into
   the prompt it already sends. The Provider contract stays byte-for-byte
   unchanged; any Provider (built-in adapter or user subclass) works with
   memory with zero changes.

## Decision

**Conversation memory lives in the Agent, is opt-in, provider-agnostic,
and additive to the public surface (ADR 0010).**

- **New module `memory.py`**, three public names exported at the top
  level (33 → 36 in `__all__`):
  - `ConversationTurn` — one completed turn: frozen dataclass with a
    validated `role` (`"user"` or `"assistant"`) and `text`.
  - `Memory` — the storage contract: `append()`, `history()`, `clear()`.
    Custom backends (SQLite, Redis, ...) implement the three methods; a
    `len()` convenience is provided by the ABC.
  - `InMemoryMemory` — the built-in backend: a bounded process-local FIFO
    (`max_turns`, default 100, validated). When the cap is reached the
    oldest turn is evicted, so long sessions cost a fixed amount of
    memory and the next prompt always carries the most recent context.
- **Agent wiring.** `Agent` and `AsyncAgent` grow an additive final
  keyword `memory: Memory | None = None` (a non-`Memory` object is a
  `TypeError`, mirroring the `AsyncProvider` check). Before the first
  provider call of a run the Agent reads `memory.history()` and composes
  the prompt with `compose_prompt()`; after a successful run it records
  `(user, input_text)` and `(assistant, output)`.
- **The transcript format is pinned by tests.** Empty history returns the
  input byte-for-byte — configuring memory never changes a first run, and
  the no-memory path is untouched. With history, the prompt becomes:

  ```
  Previous conversation (oldest first):
  user: My name is Sara
  assistant: Nice to meet you, Sara!

  Respond to this new user message:
  What is my name?
  ```

- **Only completed exchanges are remembered.** The tool loop of a run
  stays inside the run — providers already rehydrate tool results per
  iteration (ADR 0002) — so memory records exactly one user turn and one
  assistant turn per successful run. Failed runs (provider errors,
  missing tools, iteration exhaustion, `on_delta` failures) record
  nothing: memory only ever holds exchanges that actually happened.
- **The Provider contract is untouched.** No keyword, no signature
  change, no adapter code. This protects every user-written
  `Provider`/`AsyncProvider` subclass and keeps the 1.0 stability
  contract intact; native per-vendor message threading can be added
  later as an additive keyword without breaking anything recorded here.
- **Runtime wiring.** `create_runtime()` and `create_async_runtime()`
  grow an additive `memory` parameter; `Runtime.memory` and
  `AsyncRuntime.memory` expose the underlying agent's memory as a
  read-only property (`None` when not configured), so callers can inspect
  or clear history through the facade. `Settings` is deliberately
  unchanged: memory is an object with identity and lifetime, not a
  scalar — an environment variable would imply a persistence story this
  ADR does not decide.
- **Zero dependencies.** Storage is a plain list; nothing is serialized,
  persisted, or shared across processes.

## Consequences

- The README's "Conversation memory ❌" gap is retired; the remaining
  honest gaps are planning/orchestration and further vendor adapters.
- The transcript costs tokens: a run with memory sends the whole bounded
  history plus the new input. `InMemoryMemory.clear()` and the
  `max_turns` cap are the levers; callers who need eviction policies
  implement `Memory`.
- Memory instances are plain objects: sharing one `InMemoryMemory`
  between two agents is allowed and tested (they then share context);
  the runtime itself never crosses threads or processes with it.
- 52 new offline contract tests cover turn validation, FIFO bounds,
  custom `Memory` implementations, the transcript format (including the
  empty-history identity), sync and async recording rules (success,
  provider failure, tool loop, iteration exhaustion, missing tools,
  streaming), `SyncProviderAdapter` compatibility, and the runtime/factory
  wiring; the suite grows from 1142 to 1194 tests, coverage 99.80%
  (the floor is 95%).
