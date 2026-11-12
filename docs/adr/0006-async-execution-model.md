# ADR 0006: Additive async execution model

- Status: Accepted
- Date: 2026-11-12
- Deciders: Abolfazl Ranjbaran
- Extends: [ADR 0001](0001-sync-first-core.md),
  [ADR 0002](0002-tool-call-wire-format-and-agent-loop.md)

## Context

ADR 0001 locked the core to synchronous, dependency-free Python: one thread
of control, no hidden I/O, no event loop. That decision made the runtime
auditable and kept `dependencies = []` true. It also means a caller who
wants concurrency — many agents in one process, an agent inside a web
server's event loop, awaited tools over async I/O — has to build threading
or subprocess scaffolding themselves.

The recurring ask is "can I run NexusAgent under asyncio?" — not "rewrite
the core". A rewrite to async-first would break the ADR 0002 wire contract
for every existing provider and tool, and would drag an async HTTP client
dependency into a zero-dependency package.

## Decision

**Async is an additive layer; the sync core stays first-class and
unchanged.**

- **`AsyncProvider`** lives in `provider.py`, next to the sync `Provider`
  ABC: `async generate()` plus an awaited `generate_response()` with the
  same response protocol (`TextResponse | ToolCallRequest`) and the same
  wrap-`generate()` default. One contract, two execution models.
- **`SyncProviderAdapter`** (`async_provider.py`) turns any sync provider
  into an `AsyncProvider` by running its blocking calls in worker threads
  through `asyncio.to_thread`. The `fake`, `scripted`, `http` and `openai`
  providers drive `AsyncAgent` with zero changes and zero new runtime
  dependencies. No native async HTTP client is bundled; the adapter is the
  honest, documented bridge.
- **`AsyncTool`** (`tool.py`) extends the sync `Tool` ABC with
  `async aexecute()`. Its sync `execute()` fails fast with
  `NotImplementedError`, so an async tool can never silently produce an
  un-awaited coroutine on the sync path.
- **`AsyncToolExecutor`** (`async_tool_executor.py`) awaits `AsyncTool`
  natively and runs plain sync tools through the sync executor in a worker
  thread. Validation and `ToolExecutionError` wrapping are identical on
  both paths.
- **`AsyncAgent`** (`async_agent.py`) mirrors the sync agent's bounded tool
  loop exactly: same `AgentResult`, same `max_iterations` bound, same rule
  that tool failures become error `ToolResult`s fed back to the provider.
- **`AsyncRuntime` / `create_async_runtime()`** (`async_runtime.py`) mirror
  the sync facade and factory, wrapping the factory-chosen provider in
  `SyncProviderAdapter`.
- **No loop is created at import time.** Importing `nexusagent` performs no
  I/O and starts no event loop (enforced by the existing import-contract
  tests).
- **pytest-asyncio** is a dev-only extra; runtime dependencies stay empty.

Layer rules O–R (`tests/test_architecture.py`) pin the new modules into the
same layering as their sync counterparts: the bridge may not see the agent,
the async agent may not see the bridge, and the async runtime must go
through the provider factory.

## Consequences

- Callers get real concurrency: many `AsyncAgent.run()` calls interleave in
  one event loop, and awaited tools coexist with blocking provider calls.
- The event loop never stalls: every blocking call (provider HTTP, sync
  tools) runs in a worker thread.
- Two parallel loop implementations exist on purpose. Refactoring the sync
  agent to share code with the async one would couple the two and risk the
  established sync contract for marginal line savings; if the duplication
  ever hurts, the fix is a new ADR, not a silent refactor.
- Threads are the bridge, not a parallelism promise: `asyncio.to_thread`
  uses the default executor, so CPU-bound sync providers still serialize.
- Streaming remains out of scope (see the README feature table).
