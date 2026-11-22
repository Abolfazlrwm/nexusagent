# ADR 0015: Minimal multi-agent orchestration

- Status: Accepted
- Date: 2026-11-23
- Deciders: Abolfazl Ranjbaran
- Extends: [ADR 0010](0010-1.0-api-stability-and-versioning-policy.md),
  [ADR 0002](0002-tool-call-wire-format-and-agent-loop.md),
  [ADR 0012](0012-conversation-memory.md)
- Related: [ADR 0005](0005-openai-compatible-provider.md),
  [ADR 0007](0007-anthropic-compatible-provider.md),
  [ADR 0009](0009-streaming-responses.md),
  [ADR 0014](0014-native-history-threading.md)

## Context

Every capability shipped so far strengthens one agent: the bounded tool
loop (ADR 0002), streaming (ADR 0009), conversation memory (ADR 0012),
persistent memory (ADR 0013) and native per-vendor history threading
(ADR 0014). Once a runtime has strong single agents, the natural next
question — and the one PROJECT_STATUS has named as the remaining gap —
is orchestration: more than one specialist agent behind a single entry
point, so a math question reaches the math agent and a greeting reaches
the greeter without the caller dispatching by hand.

PROJECT_STATUS named the candidate honestly: "Multi-agent orchestration
(an explicit, minimal router-over-agents layer — no framework, no
graphs)". The wording matters. Mature frameworks ship DAGs, shared black-
board state, planner/executor loops and automatic handoff negotiation.
That is exactly the kind of machinery this runtime refuses: it cannot be
kept honest under a 99%+ coverage gate, it hides control flow inside
graph objects, and it duplicates what the bounded tool loop already does
well — one input, one agent, a traceable loop, an explicit result.

Two designs were rejected:

1. **A graph/state-machine orchestrator** (nodes, edges, conditional
   transitions). Untestable at this codebase's quality bar without
   becoming the whole library, and every failure mode ("why did control
   jump there?") is exactly the opacity NexusAgent exists to remove.
2. **Agents negotiate handoffs among themselves** (an agent's response
   may name the next agent). The tool loop already gives the *model* a
   bounded way to call things; making agents callers of other agents
   doubles the loop surface, hides which agent is speaking from the
   caller, and turns a routing bug into an infinite conversation.

## Decision

**Ship one additive module, `nexusagent.orchestration`, with three
public names — `AgentTeam`, `TeamResult` and `create_provider_router` —
that route each prompt to exactly one named `Agent` and return that
agent's result unchanged. Routing is a plain callable; a provider-backed
router is a factory, not a framework. No new control flow, no shared
state, no handoff graph.**

- **`AgentTeam(agents, router)`.** `agents` is a non-empty mapping of
  non-empty string names to `Agent` instances (validated eagerly, like
  `ToolRegistry.register`); `router` is a `Callable[[str], str]` that
  receives the raw user input and returns one agent name. `run()`
  validates the input exactly like `Agent.run()` (TypeError /
  ValueError), asks the router once, and delegates: the selected agent's
  own bounded tool loop, its own tools, its own memory (ADR 0012/0013)
  and its own streaming all run unchanged. Any router failure — an
  exception or an unknown name — becomes a `TeamResult(success=False)`
  with the reason in `output`, mirroring how `Agent.run` reports
  provider errors instead of crashing.
- **`TeamResult(output, success, agent_name)`.** A frozen dataclass that
  mirrors `AgentResult` field-for-field plus the routing fact, so
  callers keep one result shape across single and team runs.
  `agent_name` is empty only when routing itself failed and no agent
  produced output.
- **`create_provider_router(provider, agent_names)`.** Builds a router
  from any `Provider`: one `generate()` call with an instruction that
  lists the agent names and the user prompt, then a documented,
  deterministic parse — exact match after stripping, case-insensitive
  exact match, otherwise the first listed name appearing in the reply
  (earliest occurrence wins; ties resolve to the earlier listed name).
  No match raises `ProviderResponseError`, which the team converts into
  a failed result. The router uses `generate()` — never the tool loop —
  because a routing decision is one question, not a conversation.
- **Streaming.** `AgentTeam.run(..., on_delta=...)` forwards the
  callback to the selected agent unchanged; routing is a separate,
  silent step before the loop, so ADR 0009's contract is untouched.
- **Surface and stability.** The root `__all__` grows 37 → 40 (three
  additions, zero renames or removals) — additive per ADR 0010. The
  async layer is deliberately not mirrored yet: the team sits above the
  agent layer, wraps sync `Agent`s only, and the async mirror is named
  as the next step rather than half-shipped.
- **No team memory.** Each member keeps its own memory; a shared
  team-level transcript is future work and would need its own ADR
  (it re-opens the ADR 0012 provider-agnosticity argument).

## Consequences

- Multi-agent behavior is explicit: the caller can always read the
  router (it is a function), see the names (they are mapping keys) and
  learn who answered (`TeamResult.agent_name`).
- The failure surface stays flat: routing failures are failed results,
  not exceptions mid-loop, and every member agent keeps the exact
  pre-1.6 behavior byte-for-byte.
- The demo can show the whole story offline with `ScriptedProvider`
  and `FakeProvider`: a router prompt, a routing decision, a member
  agent's tool loop — the same trace style as every earlier scene.
- Known limits, named honestly: one routing hop per prompt (no
  chains), no shared team memory, no async mirror. Each is a scoped
  follow-up, not a hidden deficiency.
