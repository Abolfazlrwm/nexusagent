# ADR 0011: Automatic retry with exponential backoff for HTTP providers

- Status: Accepted
- Date: 2026-11-15
- Deciders: Abolfazl Ranjbaran
- Extends: [ADR 0005](0005-openai-compatible-provider.md),
  [ADR 0007](0007-anthropic-compatible-provider.md),
  [ADR 0008](0008-gemini-provider.md),
  [ADR 0009](0009-streaming-responses.md)
- Related: [ADR 0001](0001-sync-first-core.md),
  [ADR 0010](0010-1.0-api-stability-and-versioning-policy.md)

## Context

Until now a single transient failure — a dropped connection, a blip on a
gateway, a 429 from a rate limiter, a 503 from an overloaded server —
surfaced immediately as a `ProviderRequestError` and ended the run. Real
LLM backends fail transiently often enough that every caller was
reinventing the same retry loop above the library. The gap was listed
honestly in the README ("Retries / backoff on HTTP failures ❌") and in
PROJECT_STATUS as the next candidate after 1.0.

The design has to respect the foundations: the transport is shared by all
four HTTP-based providers (`post_json()` / `post_sse()`), the core stays
zero-dependency, and 1.0 stability (ADR 0010) means the change must be
strictly additive.

## Decision

**Retry transient request-level failures in the shared transport, with
exponential backoff plus full jitter, bounded by configuration — and
never retry once the server has started answering.**

- **One place: the shared transport.** The retry loop lives in
  `http_provider.py` next to `post_json()` and `post_sse()`, where header
  handling and error mapping already live (ADR 0009). All four
  HTTP-based providers gain retries on both the request and the streaming
  paths with no per-adapter code. The raised errors and their messages
  are identical to the pre-retry transport — the last failure surfaces
  exactly as before.
- **What is retryable.** Connection failures (`URLError`), timeouts, and
  HTTP 429, 500, 502, 503, 504. Everything else — authentication, bad
  requests, validation errors — is permanent and fails fast: retrying a
  401 cannot succeed. An invalid JSON body or other protocol-level
  response error is also not retried; those are server bugs, not
  transients. LLM inference POSTs are effectively safe to resend: they
  carry no client-visible side effects, so a retried request cannot
  corrupt anything — the response is simply produced again.
- **The retry window ends at the response headers.** Once the server
  starts answering — a JSON body has begun arriving, or the SSE stream
  is open — nothing is retried. A mid-stream failure or a body-read
  timeout raises `ProviderRequestError` during consumption exactly as
  before, because retrying there could duplicate fragments the caller
  has already seen (a real hazard with `on_delta` display, ADR 0009).
  Worst-case duration is therefore bounded and documented:
  `(retries + 1) × timeout + Σ backoff`.
- **Backoff.** 0.5s doubling per attempt, capped at 8 seconds, with full
  jitter (uniform in `[0, cap]`) so concurrent clients do not retry in
  lockstep. An integer `Retry-After` hint wins when the server sends
  one, capped by the same 8-second maximum so the worst case stays
  predictable; the HTTP-date form is out of scope and falls back to the
  exponential curve.
- **Configuration.** `ProviderConfig` grows `retries: int = 2` (a frozen
  dataclass, additive per ADR 0010 — existing constructor calls keep
  working) and `Settings` grows `retries` with the `NEXUS_RETRIES`
  environment variable (default 2, validated locally like every other
  setting; `0` disables retries entirely). `create_runtime()` wires
  `settings.retries` through; each provider validates non-negative
  retries in its configuration check. There is deliberately no
  per-status tuning surface, no retry-on-anything flag, and no
  callbacks: one number covers the realistic policy space.
- **Zero dependencies.** The loop, backoff and jitter use only the
  standard library (`time.sleep`, `random.uniform`).

## Consequences

- The README's "Retries / backoff ❌" gap is retired; the remaining
  honest gaps are memory/planning/orchestration and further vendor
  adapters.
- Defaults are safe: 2 retries add at most a few seconds to a failing
  run and turn most transient blips into successful runs. `NEXUS_RETRIES=0`
  restores the exact pre-1.1 behavior for callers who prefer to fail fast
  or implement their own policy above the library.
- Architecture rules stay intact: the policy joins the transport module
  the providers already import; no new layering rule is needed.
- 39 new offline contract tests cover the retryable/permanent status
  matrix, exhaustion, `retries=0`, negative configuration, `Retry-After`
  (honored, capped, unusable), the backoff cap curve, read-stage and
  mid-stream non-retry behavior, per-adapter wiring on both paths, and
  the `Settings`/runtime wiring; the suite grows from 1103 to 1142
  tests, coverage 99.79% (the floor is 95%).
