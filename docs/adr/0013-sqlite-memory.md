# ADR 0013: Persistent SQLite memory backend

- Status: Accepted
- Date: 2026-11-18
- Deciders: Abolfazl Ranjbaran
- Extends: [ADR 0010](0010-1.0-api-stability-and-versioning-policy.md),
  [ADR 0012](0012-conversation-memory.md)
- Related: [ADR 0011](0011-http-retry-backoff.md)

## Context

ADR 0012 shipped conversation memory as an opt-in, provider-agnostic
abstraction: the `Memory` ABC (three methods — `append`, `history`,
`clear`) with one built-in backend, the process-local bounded FIFO
`InMemoryMemory`. The ADR explicitly left persistence out and named it as
the extension point: "Custom backends (SQLite, Redis, ...) implement the
three-method `Memory` ABC", and PROJECT_STATUS listed the gap honestly —
"No persistence for memory ... no built-in serialization, session store or
cross-process sharing".

That gap is real for the primary use case memory exists for: a
conversation whose history must survive the process that created it — a
CLI session resumed the next day, a service restart that should not
forget the user, two tools reading the same transcript. Re-implementing a
persistent backend above the library forces every user to re-decide
schema, eviction and durability, all while re-deriving the same FIFO
semantics the built-in backend already pins.

Two designs were possible:

1. **Make persistence a mode of `InMemoryMemory`** (a `path=` keyword).
   Cheaper on the surface, but it overloads one class with two lifetimes
   (connection management, close semantics, durability), and the
   constructor of the simplest backend grows the most complex parameter.
2. **A second `Memory` implementation.** The ABC from ADR 0012 was
   designed exactly for this: additive, opt-in, zero changes to the
   agent/runtime wiring — anything implementing the three methods drops
   in everywhere memory is accepted today.

## Decision

**Add `SQLiteMemory`, a persistent `Memory` backend backed by a local
SQLite database file. One new public name (36 → 37), additive per ADR
0010; `Settings` and every other contract stay untouched.**

- **New public name `SQLiteMemory`** in `memory.py`, exported at the top
  level. It subclasses the ADR 0012 `Memory` ABC, so it works unchanged
  with `Agent(memory=...)`, `AsyncAgent(memory=...)`,
  `create_runtime(memory=...)` and `create_async_runtime(memory=...)` —
  no wiring code changes at all.
- **`SQLiteMemory(path, max_turns=100)`** — `path` is a `str` or
  `os.PathLike[str]`; the database file is created on first use and
  missing parent directories are created too. `max_turns` is validated
  exactly like `InMemoryMemory` (`TypeError` for non-integers including
  `bool`, `ValueError` below 1) and defaults to the same
  `DEFAULT_MAX_TURNS`.
- **FIFO semantics identical to the in-process backend.** Turns live in a
  `turns` table (`id INTEGER PRIMARY KEY, role TEXT NOT NULL, text TEXT
  NOT NULL`); `history()` selects ordered by ascending `id` (oldest
  first). When a cap is exceeded the oldest rows are **deleted** — the
  eviction is itself persisted, so a reopened memory resumes inside the
  cap. A contract test asserts both built-ins return identical histories
  for identical operation sequences.
- **Durability over batching.** Every mutation commits immediately, so a
  crash between runs loses nothing that the caller was told was recorded.
- **Explicit lifetime.** The instance opens one `sqlite3` connection in
  its constructor and holds it for its lifetime; `close()` releases it
  (idempotent) and the instance doubles as a context manager that closes
  on exit. Further use of a closed instance raises
  `sqlite3.ProgrammingError`. The instance is deliberately not
  thread-safe and not shared across threads — the runtime never does
  either (ADR 0012), and the ABC documents the same assumption.
- **Zero dependencies.** `sqlite3` ships with Python; the distribution's
  dependency count stays at zero. Two concurrent instances may open the
  same file sequentially (SQLite serializes access); the documented
  sharing pattern is "open, use, close, reopen".
- **`path` property** exposes the resolved database file; `:memory:` is
  not special-cased but works as SQLite defines it (a per-connection
  ephemeral database, useful for tests).

## Consequences

- The PROJECT_STATUS honesty gap "No persistence for memory" is retired;
  remaining memory gaps are network backends (Redis, PostgreSQL) — still
  the user's three-method implementation, now easier to validate against
  the pinned semantics of the two built-ins.
- A persisted memory keeps its transcript **forever** unless the cap or
  `clear()` removes it: callers who resume old sessions should be aware
  the whole bounded history rides along in every prompt (same token cost
  model as ADR 0012, now across restarts).
- 32 new offline contract tests cover construction and validation, FIFO
  eviction and its persistence across reopen, `clear()`, close and
  context-manager behavior, two instances sharing one file, the
  `:memory:` mode, parity with `InMemoryMemory`, and the end-to-end
  agent/factory wiring with a reopened memory; the suite grows from 1194
  to 1226 tests, coverage 99.81% (the floor is 95%).
- The public surface grows to 37 names; `tests/test_public_api.py` and
  this ADR pin it. Nothing else moves, so the 1.0 stability contract
  holds without deprecation.
