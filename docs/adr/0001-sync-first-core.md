# ADR 0001: Keep the Core Synchronous

- Status: Accepted
- Date: 2026-11-09 (recorded; the decision has governed the codebase since 0.1.0)
- Deciders: Abolfazl Ranjbaran

## Context

Agent runtimes in the Python ecosystem overwhelmingly default to `asyncio`
(streaming, concurrent tool calls, websockets). NexusAgent's core could have
started async too. Instead, the entire core — `Provider`, `Agent`, `Tool`,
`ToolRegistry`, `ToolExecutor`, `Runtime` — is synchronous.

Considerations:

- The core's purpose is to stay small, readable, and auditable. Sync code
  has no event-loop subtleties (task cancellation, implicit context switches,
  blocking-call-in-async traps) and is dramatically easier to test
  deterministically.
- The project's differentiators are auditability and contract clarity, not
  throughput.
- The intended backends are simple HTTP request/response calls, which work
  fine synchronously.

## Decision

The core stays synchronous through the 0.x series. `Provider.generate()` /
`generate_response()`, `Tool.execute()`, and `Agent`/`Runtime` entry points
are plain functions. Async, streaming, and concurrency require a new ADR
with explicit scope (e.g. "async Provider subclass", "streaming responses")
and will not be added ad hoc.

## Consequences

- Honest limitation: one agent run is one synchronous call; no streaming
  tokens, no parallel tool execution.
- Deterministic testing: 600+ tests run in seconds with no async fixtures.
- Callers who need concurrency can run multiple `Runtime`s in their own
  threads/processes — the core is stateless per run.
- A future async core would likely be a parallel set of classes rather than
  a rewrite; this ADR does not promise either shape.
